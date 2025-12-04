"""Bridge between Python components and Vue frontend."""

import hashlib
import os
import pickle
from typing import TYPE_CHECKING, Any, Dict, Optional

import polars as pl
import streamlit as st

if TYPE_CHECKING:
    from ..core.base import BaseComponent
    from ..core.state import StateManager


# Cache the Vue component function
_vue_component_func = None


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
    2. Calls component._prepare_vue_data() to get filtered data
    3. Computes hash for change detection
    4. Calls the Vue component with data payload
    5. Updates StateManager from Vue response
    6. Triggers st.rerun() if state changed

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

    # Get component data and configuration
    vue_data = component._prepare_vue_data(state)
    component_args = component._get_component_args()

    # Convert any DataFrames to pandas for Arrow serialization
    for data_key, value in vue_data.items():
        if isinstance(value, pl.LazyFrame):
            vue_data[data_key] = value.collect().to_pandas()
        elif isinstance(value, pl.DataFrame):
            vue_data[data_key] = value.to_pandas()

    # Build the full data payload
    data_payload = {
        **vue_data,
        'selection_store': state,
        'hash': _hash_data(vue_data),
    }

    # Component layout: [[{componentArgs: {...}}]]
    components = [[{'componentArgs': component_args}]]

    # Generate unique key if not provided
    if key is None:
        key = f"svc_{id(component)}_{hash(str(component._interactivity))}"

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
        if state_manager.update_from_vue(result):
            st.rerun()

    return result


def _hash_data(data: Dict[str, Any]) -> str:
    """
    Compute hash of data payload for change detection.

    This helps the Vue component avoid unnecessary re-renders when
    the data hasn't actually changed.

    Args:
        data: The data dict to hash

    Returns:
        SHA256 hash string
    """
    try:
        serialized = pickle.dumps(data)
        return hashlib.sha256(serialized).hexdigest()
    except Exception:
        # Fallback for non-picklable data
        return hashlib.sha256(str(data).encode()).hexdigest()
