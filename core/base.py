"""Base component class for all visualization components."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import polars as pl


class BaseComponent(ABC):
    """
    Abstract base class for all visualization components.

    Components are created with data and interactivity mappings, then rendered
    by calling the component instance.

    Attributes:
        _raw_data: Original polars LazyFrame
        _interactivity: Dict mapping identifiers to column names
        _preprocessed_data: Dict of preprocessed data structures
        _config: Component configuration options
        _component_type: Class-level component type identifier
    """

    _component_type: str = ""

    def __init__(
        self,
        data: pl.LazyFrame,
        interactivity: Dict[str, str],
        **kwargs
    ):
        """
        Initialize the component.

        Args:
            data: Polars LazyFrame with source data
            interactivity: Mapping of identifier names to column names.
                Example: {'spectrum': 'scan_id', 'mass': 'mass_idx'}
                When a selection is made with identifier 'spectrum', components
                filter their data where their mapped column equals the selected value.
            **kwargs: Component-specific configuration options
        """
        self._raw_data = data
        self._interactivity = interactivity
        self._preprocessed_data: Dict[str, Any] = {}
        self._config = kwargs

        # Validate interactivity columns exist in data
        self._validate_interactivity()

        # Run component-specific preprocessing
        self._preprocess()

    def _validate_interactivity(self) -> None:
        """Validate that interactivity columns exist in the data schema."""
        schema = self._raw_data.collect_schema()
        column_names = schema.names()

        for identifier, column in self._interactivity.items():
            if column not in column_names:
                raise ValueError(
                    f"Column '{column}' for identifier '{identifier}' not found in data. "
                    f"Available columns: {column_names}"
                )

    @abstractmethod
    def _preprocess(self) -> None:
        """
        Run component-specific preprocessing.

        This method should populate self._preprocessed_data with any
        preprocessed data structures needed for rendering.
        """
        pass

    @abstractmethod
    def _get_vue_component_name(self) -> str:
        """Return the Vue component name to render (e.g., 'TabulatorTable')."""
        pass

    @abstractmethod
    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        pass

    @abstractmethod
    def _prepare_vue_data(
        self,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare data payload for Vue component.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with data to send to Vue component
        """
        pass

    @abstractmethod
    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with component configuration for Vue
        """
        pass

    def get_interactivity_mapping(self) -> Dict[str, str]:
        """Return the interactivity identifier-to-column mapping."""
        return self._interactivity.copy()

    def get_selection_identifiers(self) -> List[str]:
        """Return list of selection identifiers this component uses."""
        return list(self._interactivity.keys())

    def _get_primary_data(self) -> pl.LazyFrame:
        """
        Get the primary data for operations.

        Override in subclasses for complex data structures.
        """
        return self._raw_data

    def save(self, filepath: str) -> None:
        """
        Save component to disk as a .svcomp zip file.

        Args:
            filepath: Path to save the component (extension added if missing)
        """
        from .serialization import save_component
        save_component(self, filepath)

    @classmethod
    def load(cls, filepath: str) -> 'BaseComponent':
        """
        Load component from a .svcomp file.

        Args:
            filepath: Path to the saved component file

        Returns:
            Reconstructed component instance
        """
        from .serialization import load_component
        return load_component(filepath)

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional['StateManager'] = None,
        height: Optional[int] = None
    ) -> Any:
        """
        Render the component in Streamlit.

        Args:
            key: Optional unique key for the Streamlit component
            state_manager: Optional StateManager for cross-component state.
                If not provided, uses a default shared StateManager.
            height: Optional height in pixels for the component

        Returns:
            The value returned by the Vue component (usually selection state)
        """
        from .state import get_default_state_manager
        from ..rendering.bridge import render_component

        if state_manager is None:
            state_manager = get_default_state_manager()

        return render_component(
            component=self,
            state_manager=state_manager,
            key=key,
            height=height
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"interactivity={self._interactivity}, "
            f"config={self._config})"
        )
