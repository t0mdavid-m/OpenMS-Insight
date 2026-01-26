"""Bridge between Python components and Vue frontend."""

import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import pandas as pd
import polars as pl
import streamlit as st

# Configure debug logging for hash tracking
_DEBUG_HASH_TRACKING = os.environ.get("SVC_DEBUG_HASH", "").lower() == "true"
# Debug logging for page navigation / state sync issues
_DEBUG_STATE_SYNC = os.environ.get("SVC_DEBUG_STATE", "").lower() == "true"
_logger = logging.getLogger(__name__)


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

# Session state key for batch resend flag
# When any component requests data (e.g., after page navigation), we clear
# ALL hashes on the next render so all components get data in one rerun
_BATCH_RESEND_KEY = "_svc_batch_resend"


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


def _compute_annotation_hash(component: "BaseComponent") -> Optional[str]:
    """
    Compute hash of component's dynamic annotations, if any.

    Args:
        component: The component to check for annotations

    Returns:
        Short hash string if annotations exist, None otherwise
    """
    annotations = getattr(component, "_dynamic_annotations", None)
    if annotations is None:
        return None
    # Hash the sorted keys (sufficient for change detection)
    return hashlib.md5(str(sorted(annotations.keys())).encode()).hexdigest()[:8]


def _get_cached_vue_data(
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
) -> Optional[Tuple[Dict[str, Any], str, Optional[str]]]:
    """
    Get cached Vue data for component if filter state matches.

    Each component has exactly one cached entry. If filter state changed,
    returns None (cache miss).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state (for cache validation)

    Returns:
        Tuple of (vue_data, data_hash, annotation_hash) if cache hit, None otherwise
    """
    cache = _get_component_cache()
    if component_id in cache:
        entry = cache[component_id]
        # Support both old (3-tuple) and new (4-tuple) format
        if len(entry) == 4:
            cached_state, vue_data, data_hash, ann_hash = entry
        else:
            cached_state, vue_data, data_hash = entry
            ann_hash = None
        if cached_state == filter_state_hashable:
            return (vue_data, data_hash, ann_hash)
    return None


def _set_cached_vue_data(
    component_id: str,
    filter_state_hashable: Tuple[Tuple[str, Any], ...],
    vue_data: Dict[str, Any],
    data_hash: str,
    ann_hash: Optional[str] = None,
) -> None:
    """
    Cache Vue data for component, replacing any previous entry.

    Each component stores exactly one entry, so memory = O(num_components).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state
        vue_data: Data to cache
        data_hash: Hash of the data
        ann_hash: Hash of dynamic annotations (if any)
    """
    cache = _get_component_cache()
    cache[component_id] = (filter_state_hashable, vue_data, data_hash, ann_hash)


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

    if _DEBUG_HASH_TRACKING:
        cache_hit = cached is not None
        _logger.warning(
            f"[CacheDebug] {component._cache_id}: cache_hit={cache_hit}"
        )

    if cached is not None:
        cached_data, cached_hash, _ = cached  # Ignore cached annotation hash here

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

    # Compute annotation hash for cache storage
    ann_hash = _compute_annotation_hash(component)

    if has_dynamic_annotations:
        # Store BASE data (without dynamic annotation columns) in cache
        if hasattr(component, "_strip_dynamic_columns"):
            base_data = component._strip_dynamic_columns(vue_data)
        else:
            # Fallback: store without _plotConfig (may have stale column refs)
            base_data = {k: v for k, v in vue_data.items() if k != "_plotConfig"}
        base_hash = _hash_data(base_data)
        _set_cached_vue_data(component_id, filter_state_hashable, base_data, base_hash, ann_hash)

        # Return full data with annotations
        data_hash = _hash_data(vue_data)
        return vue_data, data_hash
    else:
        # Store complete data in cache
        data_hash = _hash_data(vue_data)
        _set_cached_vue_data(component_id, filter_state_hashable, vue_data, data_hash, ann_hash)
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

    This function uses a two-phase approach to handle state synchronization:

    Phase 1: Call vue_func with CACHED data to get Vue's request
    Phase 2: Apply Vue's request, then prepare UPDATED data for next render

    This order is critical because Vue's request (e.g., page change, sort) is only
    available after calling vue_func(). By calling it first with cached data, we:
    1. Get Vue's request immediately
    2. Apply it to state BEFORE preparing data
    3. Prepare correct data for the next render
    4. Rerun to send the correct data

    Args:
        component: The component to render
        state_manager: StateManager for cross-component state
        key: Optional unique key for the Streamlit component
        height: Optional height in pixels

    Returns:
        The value returned by the Vue component
    """
    # === PHASE 0: Generate key and get component info ===
    if key is None:
        interactivity_str = json.dumps(component._interactivity or {}, sort_keys=True)
        key = f"svc_{component._cache_id}_{hashlib.md5(interactivity_str.encode()).hexdigest()[:8]}"

    component_type = component._get_vue_component_name()
    component_id = f"{component_type}:{key}"
    component_args = component._get_component_args()
    if height is not None:
        component_args["height"] = height

    # Batch resend: if any component requested data in previous run, clear ALL hashes
    if st.session_state.get(_BATCH_RESEND_KEY):
        st.session_state[_VUE_ECHOED_HASH_KEY] = {}
        st.session_state.pop(_BATCH_RESEND_KEY, None)

    # Initialize hash cache in session state if needed
    if _VUE_ECHOED_HASH_KEY not in st.session_state:
        st.session_state[_VUE_ECHOED_HASH_KEY] = {}

    # === PHASE 1: Get CACHED data from previous render ===
    cache = _get_component_cache()
    cached_entry = cache.get(component_id)

    # Get current state for initial render (may be stale until we apply Vue's request)
    initial_state = state_manager.get_state_for_vue()

    # Pre-compute initial selections BEFORE Vue renders (for first render only)
    if hasattr(component, "get_initial_selection"):
        initial_selection = component.get_initial_selection(initial_state)
        if initial_selection:
            for identifier, value in initial_selection.items():
                state_manager.set_selection(identifier, value)
            initial_state = state_manager.get_state_for_vue()

    # Compute current filter state for cache validity check
    # This tells us what state the component SHOULD have data for
    state_keys = set(component.get_state_dependencies())
    current_filter_state = tuple(
        sorted((k, _make_hashable(initial_state.get(k))) for k in state_keys)
    )

    # Check if cached data is VALID for current state
    # KEY FIX: Only send data when cache matches current state
    # - Before: Always sent cached data, even if stale (page 38 when Vue wants page 1)
    # - Now: Only send if cache matches current state AND annotation state matches
    cache_valid = False
    current_ann_hash = _compute_annotation_hash(component)

    if cached_entry is not None:
        # Support both old (3-tuple) and new (4-tuple) cache format
        if len(cached_entry) == 4:
            cached_state, cached_data, cached_hash, cached_ann_hash = cached_entry
        else:
            cached_state, cached_data, cached_hash = cached_entry
            cached_ann_hash = None

        # Cache valid only if BOTH filter state AND annotation state match
        filter_state_matches = (cached_state == current_filter_state)
        ann_state_matches = (cached_ann_hash == current_ann_hash)
        cache_valid = filter_state_matches and ann_state_matches

        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase1: cache_valid={cache_valid}, "
                f"filter_match={filter_state_matches}, ann_match={ann_state_matches}, "
                f"cached_ann={cached_ann_hash}, current_ann={current_ann_hash}"
            )

    # Build payload - only send data if cache is valid for current state
    if cache_valid:
        # Cache HIT - send cached data (it's correct for current state)
        data_payload = {
            **cached_data,
            "selection_store": initial_state,
            "hash": cached_hash,
            "dataChanged": True,
            "awaitingFilter": False,
        }
        if _DEBUG_STATE_SYNC:
            # Log pagination state for debugging
            pagination_key = next((k for k in state_keys if "page" in k.lower()), None)
            if pagination_key:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase1: Cache HIT, "
                    f"sending data with hash={cached_hash[:8]}, "
                    f"pagination={initial_state.get(pagination_key)}"
                )
    else:
        # Cache MISS (no cache, or state mismatch) - don't send stale data
        # Vue will show loading or use its local cache
        data_payload = {
            "selection_store": initial_state,
            "hash": "",
            "dataChanged": False,
            "awaitingFilter": False,
        }
        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase1: Cache MISS, "
                f"not sending data (cached_entry={cached_entry is not None})"
            )

    # Component layout: [[{componentArgs: {...}}]]
    components = [[{"componentArgs": component_args}]]

    # === PHASE 2: Call vue_func to get Vue's request ===
    vue_func = get_vue_component_function()

    kwargs = {
        "components": components,
        "key": key,
        **data_payload,
    }
    if height is not None:
        kwargs["height"] = height

    if _DEBUG_STATE_SYNC:
        _logger.warning(
            f"[Bridge:{component._cache_id}] Phase2: Calling vue_func to get request"
        )

    result = vue_func(**kwargs)

    # === PHASE 3: Apply Vue's request FIRST ===
    state_changed = False
    if result is not None:
        # Debug logging: what we received from Vue
        if _DEBUG_STATE_SYNC:
            vue_counter = result.get("counter")
            vue_keys = [k for k in result.keys() if not k.startswith("_")]
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase3: Received counter={vue_counter}, "
                f"keys={vue_keys}, _requestData={result.get('_requestData', False)}"
            )

        # Store Vue's echoed hash
        vue_hash = result.get("_vueDataHash")
        if vue_hash is not None:
            st.session_state[_VUE_ECHOED_HASH_KEY][key] = vue_hash

        # Apply Vue's state update FIRST - this is the key fix!
        state_changed = state_manager.update_from_vue(result)

        # Check if Vue is requesting data resend
        if result.get("_requestData", False):
            st.session_state[_BATCH_RESEND_KEY] = True

    # === PHASE 4: Get UPDATED state and prepare data ===
    # Now state reflects Vue's request (e.g., new page number after click)
    state = state_manager.get_state_for_vue()

    # Check if component has required filters without values
    filters = getattr(component, "_filters", None) or {}
    filter_defaults = getattr(component, "_filter_defaults", None) or {}

    awaiting_filter = False
    for identifier in filters.keys():
        if state.get(identifier) is None and identifier not in filter_defaults:
            awaiting_filter = True
            break

    if not awaiting_filter:
        # Extract state keys that affect this component's data
        state_keys = set(component.get_state_dependencies())
        relevant_state = {k: state.get(k) for k in state_keys}

        # Build hashable version for cache key
        filter_state_hashable = tuple(
            sorted((k, _make_hashable(state.get(k))) for k in state_keys)
        )

        if _DEBUG_HASH_TRACKING:
            _logger.warning(
                f"[CacheKey] {component._cache_id}: state_keys={list(state_keys)}"
            )
            for k in state_keys:
                if "page" in k.lower():
                    _logger.warning(
                        f"[CacheKey] {component._cache_id}: {k}={state.get(k)}"
                    )

        # Prepare data with UPDATED state (includes Vue's request)
        # This may also call set_selection() to override (e.g., sort resets page)
        vue_data, data_hash = _prepare_vue_data_cached(
            component, component_id, filter_state_hashable, relevant_state
        )

        # Check if Python overrode state during _prepare_vue_data
        # (e.g., table.py sets page to last page after sort)
        final_state = state_manager.get_state_for_vue()
        if final_state != state:
            state_changed = True
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase4: Python overrode state"
                )
    else:
        vue_data = {}
        data_hash = "awaiting_filter"
        filter_state_hashable = ()

    _logger.info(f"[bridge] Phase4: {component._cache_id} prepared data, hash={data_hash[:8] if data_hash else 'None'}")

    # === PHASE 5: Cache data for next render ===
    if vue_data:
        # Convert for caching (Arrow serialization requires pandas)
        converted_data = {}
        for data_key, value in vue_data.items():
            if data_key == "_hash":
                continue
            if isinstance(value, pl.LazyFrame):
                converted_data[data_key] = value.collect().to_pandas()
            elif isinstance(value, pl.DataFrame):
                converted_data[data_key] = value.to_pandas()
            else:
                converted_data[data_key] = value

        # Store in cache for next render (include annotation hash for validity check)
        cache[component_id] = (filter_state_hashable, converted_data, data_hash, current_ann_hash)

        # If cache was invalid at Phase 1, we didn't send data to Vue (dataChanged=False).
        # Trigger a rerun so the newly cached data gets sent on the next render.
        # This handles cross-component filter changes where the affected component
        # needs to receive updated data (e.g., new total_rows/total_pages).
        if not cache_valid:
            state_changed = True
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase5: Cache was invalid, "
                    f"triggering rerun to send newly cached data"
                )

        if _DEBUG_STATE_SYNC:
            # Log what we're caching for debugging
            pagination_key = next((k for k, v in filter_state_hashable if "page" in k.lower()), None)
            if pagination_key:
                pagination_val = next((v for k, v in filter_state_hashable if k == pagination_key), None)
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase5: Cached data with hash={data_hash[:8]}, "
                    f"filter_state includes {pagination_key}={pagination_val}"
                )

    # Handle annotations from Vue (e.g., from SequenceView)
    if result is not None:
        annotations = result.get("_annotations")
        annotations_changed = False

        if annotations is not None:
            peak_ids = annotations.get("peak_id", [])
            new_hash = hash(tuple(peak_ids)) if peak_ids else 0

            ann_hash_key = f"_svc_ann_hash_{key}"
            old_hash = st.session_state.get(ann_hash_key)

            if old_hash != new_hash:
                annotations_changed = True
                st.session_state[ann_hash_key] = new_hash

            _store_component_annotations(key, annotations)
        else:
            ann_hash_key = f"_svc_ann_hash_{key}"
            if st.session_state.get(ann_hash_key) is not None:
                annotations_changed = True
                st.session_state[ann_hash_key] = None

        if annotations_changed:
            state_changed = True

    # === PHASE 6: Rerun if state changed ===
    # This will send the UPDATED data (now in cache) to Vue
    if state_changed:
        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase6: RERUN triggered, "
                f"next render will have cache HIT"
            )
        st.rerun()
    elif _DEBUG_STATE_SYNC:
        _logger.warning(
            f"[Bridge:{component._cache_id}] Phase6: No rerun needed, state_changed=False"
        )

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
        # Skip internal metadata but NOT dynamic annotation columns or pagination
        if key.startswith("_") and not key.startswith("_dynamic") and not key.startswith("_pagination"):
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
