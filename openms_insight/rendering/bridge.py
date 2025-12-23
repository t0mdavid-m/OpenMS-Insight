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

# Session state key for per-component data cache
# Each component stores exactly one entry (current filter state)
_COMPONENT_DATA_CACHE_KEY = "_svc_component_data_cache"

# Session state key for component annotations (from Vue)
# Stores annotation dataframes returned by components like SequenceView
_COMPONENT_ANNOTATIONS_KEY = "_svc_component_annotations"


def _get_component_cache() -> Dict[str, Any]:
    """Get per-component data cache from session state."""
    if _COMPONENT_DATA_CACHE_KEY not in st.session_state:
        st.session_state[_COMPONENT_DATA_CACHE_KEY] = {}
    return st.session_state[_COMPONENT_DATA_CACHE_KEY]


def clear_component_cache() -> None:
    """
    Clear all per-component cached data.

    Call this when loading a new file to ensure fresh data is sent to Vue.
    """
    if _COMPONENT_DATA_CACHE_KEY in st.session_state:
        st.session_state[_COMPONENT_DATA_CACHE_KEY].clear()


def _store_component_annotations(
    component_key: str, annotations: Dict[str, Any]
) -> None:
    """
    Store annotations returned by a Vue component.

    Args:
        component_key: Unique key for the component
        annotations: Dict with annotation arrays (e.g., peak_id, highlight_color, annotation)
    """
    if _COMPONENT_ANNOTATIONS_KEY not in st.session_state:
        st.session_state[_COMPONENT_ANNOTATIONS_KEY] = {}
    st.session_state[_COMPONENT_ANNOTATIONS_KEY][component_key] = annotations


def get_component_annotations(component_key: Optional[str]) -> Optional[pl.DataFrame]:
    """
    Get annotations stored by a Vue component.

    Args:
        component_key: Unique key for the component

    Returns:
        Polars DataFrame with annotations, or None if not available
    """
    if component_key is None:
        return None

    if _COMPONENT_ANNOTATIONS_KEY not in st.session_state:
        return None

    annotations = st.session_state[_COMPONENT_ANNOTATIONS_KEY].get(component_key)
    if annotations is None:
        return None

    # Convert to DataFrame
    try:
        # annotations should be a dict with arrays: {peak_id: [...], highlight_color: [...], annotation: [...]}
        return pl.DataFrame(annotations)
    except Exception:
        return None


def clear_component_annotations() -> None:
    """Clear all component annotations."""
    if _COMPONENT_ANNOTATIONS_KEY in st.session_state:
        st.session_state[_COMPONENT_ANNOTATIONS_KEY].clear()


def _get_cached_vue_data(
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    Get cached Vue data for component if filter state matches.

    Each component has exactly one cached entry. If filter state changed,
    returns None (cache miss).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state (for cache validation)

    Returns:
        Tuple of (vue_data, data_hash) if cache hit, None otherwise
    """
    cache = _get_component_cache()
    if component_id in cache:
        cached_state, vue_data, data_hash = cache[component_id]
        if cached_state == filter_state_hashable:
            return (vue_data, data_hash)
    return None


def _set_cached_vue_data(
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
    vue_data: Dict[str, Any],
    data_hash: str,
) -> None:
    """
    Cache Vue data for component, replacing any previous entry.

    Each component stores exactly one entry, so memory = O(num_components).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state
        vue_data: Data to cache
        data_hash: Hash of the data
    """
    cache = _get_component_cache()
    cache[component_id] = (filter_state_hashable, vue_data, data_hash)


def _prepare_vue_data_cached(
    component: "BaseComponent",
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
    state_dict: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """
    Prepare Vue data with per-component caching.

    Each component caches exactly one entry (its current filter state).
    When filter state changes, old entry is replaced - memory stays bounded.

    For components with dynamic annotations (e.g., LinePlot linked to SequenceView):
    - Cache stores BASE data (without annotation columns)
    - Annotations are re-applied fresh each render (cheap operation)
    - Final hash reflects current annotation state

    Args:
        component: The component to prepare data for
        component_id: Unique identifier for this component
        filter_state_hashable: Hashable version of filter state (for cache key)
        state_dict: Original state dict with actual values

    Returns:
        Tuple of (vue_data dict, data_hash string)
    """
    # Check if component has dynamic annotations (e.g., LinePlot linked to SequenceView)
    has_dynamic_annotations = (
        getattr(component, "_dynamic_annotations", None) is not None
    )

    # Try cache first (works for ALL components now)
    cached = _get_cached_vue_data(component_id, filter_state_hashable)

    if cached is not None:
        cached_data, cached_hash = cached

        if has_dynamic_annotations:
            # Cache hit but need to re-apply annotations (they may have changed)
            # Use component method to apply fresh annotations to cached base data
            if hasattr(component, "_apply_fresh_annotations"):
                # Shallow copy to avoid mutating cache
                vue_data = component._apply_fresh_annotations(dict(cached_data))
                # Hash final data (includes new annotations)
                data_hash = _hash_data(vue_data)
                return vue_data, data_hash
            else:
                # Fallback: recompute if component doesn't support fresh annotations
                vue_data = component._prepare_vue_data(state_dict)
                data_hash = _hash_data(vue_data)
                return vue_data, data_hash
        else:
            # No dynamic annotations - return cached as-is
            return cached_data, cached_hash

    # Cache miss - compute data
    vue_data = component._prepare_vue_data(state_dict)

    if has_dynamic_annotations:
        # Store BASE data (without dynamic annotation columns) in cache
        if hasattr(component, "_strip_dynamic_columns"):
            base_data = component._strip_dynamic_columns(vue_data)
        else:
            # Fallback: store without _plotConfig (may have stale column refs)
            base_data = {k: v for k, v in vue_data.items() if k != "_plotConfig"}
        base_hash = _hash_data(base_data)
        _set_cached_vue_data(component_id, filter_state_hashable, base_data, base_hash)

        # Return full data with annotations
        data_hash = _hash_data(vue_data)
        return vue_data, data_hash
    else:
        # Store complete data in cache
        data_hash = _hash_data(vue_data)
        _set_cached_vue_data(component_id, filter_state_hashable, vue_data, data_hash)
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
        dev_mode = os.environ.get("SVC_DEV_MODE", "false").lower() == "true"

        if dev_mode:
            # Development mode: connect to Vite dev server
            dev_url = os.environ.get("SVC_DEV_URL", "http://localhost:5173")
            _vue_component_func = st_components.declare_component(
                "streamlit_vue_component",
                url=dev_url,
            )
        else:
            # Production mode: use built component
            parent_dir = os.path.dirname(os.path.abspath(__file__))
            build_dir = os.path.join(parent_dir, "..", "js-component", "dist")

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
    component: "BaseComponent",
    state_manager: "StateManager",
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

    # Check if component has required filters without values
    # Don't send potentially huge unfiltered datasets - wait for filter selection
    filters = getattr(component, "_filters", None) or {}
    filter_defaults = getattr(component, "_filter_defaults", None) or {}

    awaiting_filter = False
    if filters:
        # Check each filter - if no value AND no default, we're waiting
        for identifier in filters.keys():
            filter_value = state.get(identifier)
            has_default = identifier in filter_defaults
            if filter_value is None and not has_default:
                awaiting_filter = True
                break

    # Extract state keys that affect this component's data for cache key
    # This includes filters and any additional dependencies (e.g., zoom for heatmaps)
    # Uses get_state_dependencies() which can be overridden by subclasses
    state_keys = set(component.get_state_dependencies())

    # Build hashable version for cache key (converts dicts/lists to JSON strings)
    filter_state_hashable = tuple(
        sorted((k, _make_hashable(state.get(k))) for k in state_keys)
    )

    # Build original state dict for passing to _prepare_vue_data
    # (contains actual values, not JSON strings)
    relevant_state = {k: state.get(k) for k in state_keys}

    # Build component ID for cache (includes type to avoid collisions)
    component_type = component._get_vue_component_name()
    component_id = f"{component_type}:{key}"

    # Skip data preparation if awaiting required filter selection
    # This prevents sending huge unfiltered datasets
    if awaiting_filter:
        vue_data = {}
        data_hash = "awaiting_filter"
    else:
        # Get component data using per-component cache
        # Each component stores exactly one entry (current filter state)
        # - Filterless components: filter_state=() always → always cache hit
        # - Filtered components: cache hit when filter values unchanged
        vue_data, data_hash = _prepare_vue_data_cached(
            component, component_id, filter_state_hashable, relevant_state
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
    # NOTE: Hash now correctly reflects annotation state (annotations included in hash),
    # so normal comparison works for all components including those with dynamic annotations
    data_changed = (vue_echoed_hash is None) or (vue_echoed_hash != data_hash)

    # Only include full data if hash changed
    if data_changed:
        # Convert any non-pandas data to pandas for Arrow serialization
        # pandas DataFrames are passed through (already optimal for Arrow)
        # Filter out _hash (internal metadata) but keep _plotConfig (needed by Vue)
        converted_data = {}
        for data_key, value in vue_data.items():
            if data_key == "_hash":
                # Skip internal hash metadata
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
            "selection_store": state,
            "hash": data_hash,
            "dataChanged": True,
            "awaitingFilter": awaiting_filter,
        }
        # Note: We don't pre-set the hash here anymore. We trust Vue's echo
        # at the end of the render cycle. This ensures we detect when Vue
        # loses its data (e.g., page navigation) and needs it resent.
    else:
        # Data unchanged - only send hash and state, Vue will use cached data
        data_payload = {
            "selection_store": state,
            "hash": data_hash,
            "dataChanged": False,
            "awaitingFilter": awaiting_filter,
        }

    # Add height to component args if specified
    if height is not None:
        component_args["height"] = height

    # Component layout: [[{componentArgs: {...}}]]
    components = [[{"componentArgs": component_args}]]

    # Call Vue component
    vue_func = get_vue_component_function()

    kwargs = {
        "components": components,
        "key": key,
        **data_payload,
    }
    if height is not None:
        kwargs["height"] = height

    result = vue_func(**kwargs)

    # Update state from Vue response
    if result is not None:
        # Store Vue's echoed hash for next render comparison
        # ALWAYS update from Vue's echo - if Vue lost its data (page navigation),
        # it echoes None, and we need to know that to resend data next time
        vue_hash = result.get("_vueDataHash")
        st.session_state[_VUE_ECHOED_HASH_KEY][hash_tracking_key] = vue_hash

        # Capture annotations from Vue (e.g., from SequenceView)
        # Use hash-based change detection for robustness
        annotations = result.get("_annotations")
        annotations_changed = False

        if annotations is not None:
            # Compute hash of new annotations
            peak_ids = annotations.get("peak_id", [])
            new_hash = hash(tuple(peak_ids)) if peak_ids else 0

            # Compare with stored hash
            ann_hash_key = f"_svc_ann_hash_{key}"
            old_hash = st.session_state.get(ann_hash_key)

            if old_hash != new_hash:
                annotations_changed = True
                st.session_state[ann_hash_key] = new_hash

            _store_component_annotations(key, annotations)
        else:
            # Annotations cleared - check if we had annotations before
            ann_hash_key = f"_svc_ann_hash_{key}"
            if st.session_state.get(ann_hash_key) is not None:
                annotations_changed = True
                st.session_state[ann_hash_key] = None

        # Update state and rerun if state changed OR annotations changed
        # Hash comparison will naturally detect changes on the next render
        state_changed = state_manager.update_from_vue(result)
        if state_changed or annotations_changed:
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
        # Skip internal metadata but NOT dynamic annotation columns
        if key.startswith("_") and not key.startswith("_dynamic"):
            continue
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
