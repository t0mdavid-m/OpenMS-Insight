"""Bridge between Python components and Vue frontend."""

import hashlib
import os
import pickle
from typing import TYPE_CHECKING, Any, Dict, Optional

import pandas as pd
import polars as pl
import streamlit as st

if TYPE_CHECKING:
    from ..core.base import BaseComponent
    from ..core.state import StateManager


# Cache the Vue component function
_vue_component_func = None

# Session state key for caching last data hash per component
_LAST_HASH_KEY = "_svc_last_hashes"


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
    import time
    t0 = time.perf_counter()

    # Get current state
    state = state_manager.get_state_for_vue()
    t1 = time.perf_counter()

    # Get component data and configuration
    vue_data = component._prepare_vue_data(state)
    t2 = time.perf_counter()

    component_args = component._get_component_args()
    t3 = time.perf_counter()

    # Use precomputed hash if available, otherwise compute it
    if '_hash' in vue_data:
        data_hash = vue_data.pop('_hash')
    else:
        # Need to compute hash before conversion
        data_hash = _hash_data(vue_data)
    t4 = time.perf_counter()

    # Generate unique key if not provided
    if key is None:
        key = f"svc_{id(component)}_{hash(str(component._interactivity))}"

    # Initialize hash cache in session state if needed
    if _LAST_HASH_KEY not in st.session_state:
        st.session_state[_LAST_HASH_KEY] = {}

    # Check if data changed from last render
    last_hash = st.session_state[_LAST_HASH_KEY].get(key)
    data_changed = last_hash != data_hash

    # Only include full data if hash changed
    if data_changed:
        # Convert any non-pandas data to pandas for Arrow serialization
        # pandas DataFrames are passed through (already optimal for Arrow)
        for data_key, value in vue_data.items():
            if data_key.startswith('_'):
                # Skip metadata keys like _hash, _plotConfig
                continue
            if isinstance(value, pl.LazyFrame):
                vue_data[data_key] = value.collect().to_pandas()
            elif isinstance(value, pl.DataFrame):
                vue_data[data_key] = value.to_pandas()
            # pandas DataFrames pass through unchanged (optimal for Arrow)
        # Update cached hash
        st.session_state[_LAST_HASH_KEY][key] = data_hash
        data_payload = {
            **vue_data,
            'selection_store': state,
            'hash': data_hash,
            'dataChanged': True,
        }
    else:
        # Data unchanged - only send hash and state, Vue will use cached data
        data_payload = {
            'selection_store': state,
            'hash': data_hash,
            'dataChanged': False,
        }
    t5 = time.perf_counter()

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
    t6 = time.perf_counter()

    result = vue_func(**kwargs)
    t7 = time.perf_counter()

    # Update state from Vue response
    if result is not None:
        if state_manager.update_from_vue(result):
            st.rerun()

    t8 = time.perf_counter()
    comp_name = component_args.get('componentType', 'unknown')
    changed_str = "CHANGED" if data_changed else "cached"
    import sys
    print(f"[TIMING {comp_name}] state:{(t1-t0)*1000:.1f}ms prepare:{(t2-t1)*1000:.1f}ms args:{(t3-t2)*1000:.1f}ms hash:{(t4-t3)*1000:.1f}ms convert:{(t5-t4)*1000:.1f}ms build:{(t6-t5)*1000:.1f}ms vue_call:{(t7-t6)*1000:.1f}ms update:{(t8-t7)*1000:.1f}ms [{changed_str}]", file=sys.stderr, flush=True)

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
