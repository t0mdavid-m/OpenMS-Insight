"""Bridge between Python components and Vue frontend."""

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import pandas as pd
import polars as pl
import streamlit as st


def _make_hashable(value: Any) -> Any:
    """
    Convert a value to a hashable form for use in cache keys.

    Handles dicts and lists by converting to JSON strings.

    Args:
        value: Any value from state

    Returns:
        A hashable version of the value
    """
    if isinstance(value, dict):
        # Convert dict to sorted JSON string for consistent hashing
        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value)
    return value

if TYPE_CHECKING:
    from ..core.base import BaseComponent
    from ..core.state import StateManager


# Cache the Vue component function
_vue_component_func = None

# Session state key for Vue's echoed hash (what Vue currently has)
# Used for bidirectional hash confirmation - we only send data when
# Vue's echoed hash doesn't match the current data hash
_VUE_ECHOED_HASH_KEY = "_svc_vue_echoed_hashes"



@st.cache_data(max_entries=10, show_spinner=False)
def _cached_prepare_vue_data(
    _component: 'BaseComponent',
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
    _data_id: int,
    _state_dict: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """
    Cached wrapper for _prepare_vue_data.

    Cache key is based on:
    - component_id: unique key for this component instance
    - filter_state_hashable: hashable version of state values (for cache key only)

    The _component, _data_id, and _state_dict parameters are prefixed with underscore
    so they are not hashed (component instances are not hashable, and state_dict
    may contain unhashable values like dicts).

    Args:
        _component: The component to prepare data for (not hashed)
        component_id: Unique identifier for this component
        filter_state_hashable: Tuple of (identifier, hashable_value) for cache key
        _data_id: id() of the raw data object (not used in cache key)
        _state_dict: Original state dict with actual values (not hashed)

    Returns:
        Tuple of (vue_data dict, data_hash string)
    """
    # Use the original state dict (not the hashable version)
    vue_data = _component._prepare_vue_data(_state_dict)

    # Compute hash before any conversion
    data_hash = _hash_data(vue_data)

    return vue_data, data_hash


def get_vue_component_function():
    """
    Get the Streamlit component function for the Vue frontend.

    Returns:
        The declared Streamlit component function
    """
    global _vue_component_func

    if _vue_component_func is None:
        import streamlit.components.v1 as st_components

        # Check for development mode
        dev_mode = os.environ.get('SVC_DEV_MODE', 'false').lower() == 'true'

        if dev_mode:
            # Development mode: connect to Vite dev server
            dev_url = os.environ.get('SVC_DEV_URL', 'http://localhost:5173')
            _vue_component_func = st_components.declare_component(
                "streamlit_vue_component",
                url=dev_url,
            )
        else:
            # Production mode: use built component
            parent_dir = os.path.dirname(os.path.abspath(__file__))
            build_dir = os.path.join(parent_dir, '..', 'js-component', 'dist')

            if not os.path.exists(build_dir):
                raise RuntimeError(
                    f"Vue component build not found at {build_dir}. "
                    "Please build the Vue component or set SVC_DEV_MODE=true "
                    "for development."
                )

            _vue_component_func = st_components.declare_component(
                "streamlit_vue_component",
                path=build_dir,
            )

    return _vue_component_func


def render_component(
    component: 'BaseComponent',
    state_manager: 'StateManager',
    key: Optional[str] = None,
    height: Optional[int] = None,
) -> Any:
    """
    Render a component in Streamlit.

    This function:
    1. Gets current state from StateManager
    2. Calls component._prepare_vue_data() to get filtered data (cached!)
    3. Computes hash for change detection
    4. Only sends data if hash changed from last render (optimization)
    5. Calls the Vue component with data payload
    6. Updates StateManager from Vue response
    7. Triggers st.rerun() if state changed

    Args:
        component: The component to render
        state_manager: StateManager for cross-component state
        key: Optional unique key for the Streamlit component
        height: Optional height in pixels

    Returns:
        The value returned by the Vue component
    """
    # Get current state
    state = state_manager.get_state_for_vue()

    # Generate unique key if not provided (needed for cache)
    # Use cache_id instead of id(component) since components are recreated each rerun
    if key is None:
        key = f"svc_{component._cache_id}_{hash(str(component._interactivity))}"

    # Extract state keys that affect this component's data for cache key
    # This includes filters and any additional dependencies (e.g., zoom for heatmaps)
    # Uses get_state_dependencies() which can be overridden by subclasses
    state_keys = set(component.get_state_dependencies())

    # Build hashable version for cache key (converts dicts/lists to JSON strings)
    filter_state_hashable = tuple(sorted(
        (k, _make_hashable(state.get(k))) for k in state_keys
    ))

    # Build original state dict for passing to _prepare_vue_data
    # (contains actual values, not JSON strings)
    relevant_state = {k: state.get(k) for k in state_keys}

    # Build component ID for cache (includes type to avoid collisions)
    component_type = component._get_vue_component_name()
    component_id = f"{component_type}:{key}"

    # Get data identity - cache invalidates if raw data object changes
    data_id = id(component._raw_data)

    # Get component data using cached function
    # Cache key: (component_id, filter_state_hashable, data_id)
    # - Filterless components: filter_state=() always → always cache hit
    # - Filtered components: cache hit when filter values unchanged
    vue_data, data_hash = _cached_prepare_vue_data(
        component, component_id, filter_state_hashable, data_id, relevant_state
    )

    component_args = component._get_component_args()

    # Initialize hash cache in session state if needed
    if _VUE_ECHOED_HASH_KEY not in st.session_state:
        st.session_state[_VUE_ECHOED_HASH_KEY] = {}

    # Hash tracking key includes filter state so different filter values have separate tracking
    # This ensures data is re-sent when filters change (e.g., different spectrum selected)
    hash_tracking_key = f"{key}:{filter_state_hashable}"

    # Get Vue's last-echoed hash for this component + filter state
    # This is what Vue reported having in its last response for this exact filter state
    vue_echoed_hash = st.session_state[_VUE_ECHOED_HASH_KEY].get(hash_tracking_key)

    # Send data if Vue's hash doesn't match current hash
    # This handles: first render, data change, browser refresh, Vue hot reload
    # Vue echoes null/None if it has no data, so mismatch triggers send
    # IMPORTANT: Also send data if vue_echoed_hash is None - this means Vue
    # hasn't confirmed receipt yet (e.g., after page navigation destroys Vue component)
    data_changed = (vue_echoed_hash is None) or (vue_echoed_hash != data_hash)

    # Only include full data if hash changed
    if data_changed:
        # Convert any non-pandas data to pandas for Arrow serialization
        # pandas DataFrames are passed through (already optimal for Arrow)
        # Also filter out internal keys (starting with _)
        converted_data = {}
        for data_key, value in vue_data.items():
            if data_key.startswith('_'):
                # Skip metadata keys like _hash, _plotConfig
                continue
            if isinstance(value, pl.LazyFrame):
                converted_data[data_key] = value.collect().to_pandas()
            elif isinstance(value, pl.DataFrame):
                converted_data[data_key] = value.to_pandas()
            else:
                converted_data[data_key] = value
            # pandas DataFrames pass through unchanged (optimal for Arrow)
        data_payload = {
            **converted_data,
            'selection_store': state,
            'hash': data_hash,
            'dataChanged': True,
        }
        # Note: We don't pre-set the hash here anymore. We trust Vue's echo
        # at the end of the render cycle. This ensures we detect when Vue
        # loses its data (e.g., page navigation) and needs it resent.
    else:
        # Data unchanged - only send hash and state, Vue will use cached data
        data_payload = {
            'selection_store': state,
            'hash': data_hash,
            'dataChanged': False,
        }

    # Add height to component args if specified
    if height is not None:
        component_args['height'] = height

    # Component layout: [[{componentArgs: {...}}]]
    components = [[{'componentArgs': component_args}]]

    # Call Vue component
    vue_func = get_vue_component_function()

    kwargs = {
        'components': components,
        'key': key,
        **data_payload,
    }
    if height is not None:
        kwargs['height'] = height

    result = vue_func(**kwargs)

    # Update state from Vue response
    if result is not None:
        # Store Vue's echoed hash for next render comparison
        # ALWAYS update from Vue's echo - if Vue lost its data (page navigation),
        # it echoes None, and we need to know that to resend data next time
        vue_hash = result.get('_vueDataHash')
        st.session_state[_VUE_ECHOED_HASH_KEY][hash_tracking_key] = vue_hash

        # Update state and rerun if state changed
        if state_manager.update_from_vue(result):
            st.rerun()

    return result


def _hash_data(data: Dict[str, Any]) -> str:
    """
    Compute hash of data payload for change detection.

    Uses efficient hashing based on shape and samples for DataFrames,
    avoiding full data serialization.

    Args:
        data: The data dict to hash

    Returns:
        SHA256 hash string
    """
    from ..preprocessing.filtering import compute_dataframe_hash

    hash_parts = []
    for key, value in sorted(data.items()):
        if key.startswith('_'):
            continue  # Skip metadata
        if isinstance(value, pd.DataFrame):
            # Efficient hash for DataFrames
            df_polars = pl.from_pandas(value)
            hash_parts.append(f"{key}:{compute_dataframe_hash(df_polars)}")
        elif isinstance(value, pl.DataFrame):
            hash_parts.append(f"{key}:{compute_dataframe_hash(value)}")
        elif isinstance(value, (list, dict)):
            # For small data, use string repr
            hash_parts.append(f"{key}:{hash(str(value)[:1000])}")
        else:
            hash_parts.append(f"{key}:{hash(str(value))}")

    return hashlib.sha256("|".join(hash_parts).encode()).hexdigest()
