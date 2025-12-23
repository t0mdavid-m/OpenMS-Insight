"""State management for cross-component selection synchronization."""

from typing import Any, Dict, Optional

import numpy as np

# Module-level default state manager
_default_state_manager: Optional["StateManager"] = None


def get_default_state_manager() -> "StateManager":
    """
    Get or create the default shared StateManager.

    Returns:
        The default StateManager instance
    """
    global _default_state_manager
    if _default_state_manager is None:
        _default_state_manager = StateManager()
    return _default_state_manager


def reset_default_state_manager() -> None:
    """Reset the default state manager (useful for testing)."""
    global _default_state_manager
    _default_state_manager = None


class StateManager:
    """
    Manages selection state across components with conflict resolution.

    Features:
        - Counter-based conflict resolution to handle concurrent updates
        - Session ID for multi-tab/session safety
        - Streamlit session_state integration
        - Support for arbitrary selection identifiers

    The StateManager maintains a dict of selections keyed by identifier names.
    When a component updates a selection, all components sharing that identifier
    will see the new value on the next render.
    """

    def __init__(self, session_key: str = "svc_state"):
        """
        Initialize the StateManager.

        Args:
            session_key: Key to use in Streamlit session_state for storing
                state. Use different keys for independent component groups.
        """
        self._session_key = session_key
        self._ensure_session_state()

    def _ensure_session_state(self) -> None:
        """Ensure session state is initialized."""
        import streamlit as st

        if self._session_key not in st.session_state:
            st.session_state[self._session_key] = {
                "counter": 0,
                "id": float(np.random.random()),
                "selections": {},
            }

    @property
    def _state(self) -> Dict[str, Any]:
        """Get the internal state dict from session_state."""
        import streamlit as st

        self._ensure_session_state()
        return st.session_state[self._session_key]

    @property
    def session_id(self) -> float:
        """Get the unique session ID."""
        return self._state["id"]

    @property
    def counter(self) -> int:
        """Get the current state counter."""
        return self._state["counter"]

    def get_selection(self, identifier: str) -> Any:
        """
        Get current selection value for an identifier.

        Args:
            identifier: The selection identifier name

        Returns:
            The current selection value, or None if not set
        """
        return self._state["selections"].get(identifier)

    def set_selection(self, identifier: str, value: Any) -> bool:
        """
        Set selection value for an identifier.

        Args:
            identifier: The selection identifier name
            value: The value to set

        Returns:
            True if the value changed, False otherwise
        """
        current = self._state["selections"].get(identifier)
        if current == value:
            return False

        self._state["selections"][identifier] = value
        self._state["counter"] += 1
        return True

    def clear_selection(self, identifier: str) -> bool:
        """
        Clear selection for an identifier.

        Args:
            identifier: The selection identifier name

        Returns:
            True if a selection was cleared, False if it wasn't set
        """
        if identifier in self._state["selections"]:
            del self._state["selections"][identifier]
            self._state["counter"] += 1
            return True
        return False

    def get_all_selections(self) -> Dict[str, Any]:
        """
        Get all current selections.

        Returns:
            Dict mapping identifiers to their selected values
        """
        return self._state["selections"].copy()

    def get_state_for_vue(self) -> Dict[str, Any]:
        """
        Get state dict formatted for sending to Vue component.

        Returns:
            Dict with counter, id, and all selections as top-level keys
        """
        state = {
            "counter": self._state["counter"],
            "id": self._state["id"],
        }
        state.update(self._state["selections"])
        return state

    def update_from_vue(self, vue_state: Dict[str, Any]) -> bool:
        """
        Update state from Vue component return value.

        Uses counter-based conflict resolution: only accepts updates from
        Vue if its counter is >= our counter (prevents stale updates).

        Args:
            vue_state: State dict returned by Vue component

        Returns:
            True if state was modified, False otherwise
        """
        if vue_state is None:
            return False

        # Verify same session (prevents cross-tab interference)
        if vue_state.get("id") != self._state["id"]:
            return False

        # Extract metadata
        vue_counter = vue_state.pop("counter", 0)
        vue_state.pop("id", None)

        # Filter out internal keys (starting with _)
        vue_state = {k: v for k, v in vue_state.items() if not k.startswith("_")}

        modified = False

        # Always accept previously undefined keys (but skip None/undefined values)
        for key, value in vue_state.items():
            if key not in self._state["selections"]:
                # Only add if value is not None (undefined in Vue = no selection)
                if value is not None:
                    self._state["selections"][key] = value
                    modified = True

        # Only accept conflicting updates if Vue has newer state
        if vue_counter >= self._state["counter"]:
            for key, value in vue_state.items():
                if key in self._state["selections"]:
                    if self._state["selections"][key] != value:
                        self._state["selections"][key] = value
                        modified = True

        if modified:
            # Set counter to be at least vue_counter + 1 to reject future stale updates
            # from other Vue components that haven't received the latest state yet
            self._state["counter"] = max(self._state["counter"] + 1, vue_counter + 1)

        return modified

    def clear(self) -> None:
        """Clear all selections and reset counter."""
        self._state["selections"] = {}
        self._state["counter"] = 0

    def __repr__(self) -> str:
        return (
            f"StateManager(session_key='{self._session_key}', "
            f"counter={self.counter}, "
            f"selections={self.get_all_selections()})"
        )
