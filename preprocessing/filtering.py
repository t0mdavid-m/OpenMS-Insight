"""Data filtering utilities for selection-based filtering."""

from typing import Any, Dict, List, Optional, Tuple, Union

import polars as pl
import streamlit as st


def _make_cache_key(
    filters: Dict[str, str],
    state: Dict[str, Any],
) -> Tuple[Tuple[str, Any], ...]:
    """
    Create a hashable cache key from filters and state.

    Only includes state values for identifiers that are in filters,
    so cache is invalidated only when relevant selections change.

    Args:
        filters: Mapping of identifier names to column names
        state: Current selection state

    Returns:
        Tuple of (identifier, value) pairs for use as cache key
    """
    relevant_state = []
    for identifier in sorted(filters.keys()):
        value = state.get(identifier)
        relevant_state.append((identifier, value))
    return tuple(relevant_state)


@st.cache_data(ttl=300, max_entries=100)
def _cached_filter_and_collect(
    _data: pl.LazyFrame,
    filters_tuple: Tuple[Tuple[str, str], ...],
    state_tuple: Tuple[Tuple[str, Any], ...],
    columns_tuple: Optional[Tuple[str, ...]] = None,
) -> pl.DataFrame:
    """
    Filter data and collect with caching.

    This function is cached by Streamlit, so repeated calls with the same
    filter state will return cached results without re-executing the query.

    Args:
        _data: LazyFrame to filter (underscore prefix tells st.cache_data to hash by id)
        filters_tuple: Tuple of (identifier, column) pairs from filters dict
        state_tuple: Tuple of (identifier, value) pairs for current selection state
        columns_tuple: Optional tuple of column names to select (projection)

    Returns:
        Collected DataFrame with filters applied
    """
    data = _data
    filters = dict(filters_tuple)
    state = dict(state_tuple)

    # Apply filters
    for identifier, column in filters.items():
        selected_value = state.get(identifier)
        if selected_value is not None:
            data = data.filter(pl.col(column) == selected_value)

    # Apply column projection if specified
    if columns_tuple:
        data = data.select(list(columns_tuple))

    return data.collect()


def filter_and_collect_cached(
    data: Union[pl.LazyFrame, pl.DataFrame],
    filters: Dict[str, str],
    state: Dict[str, Any],
    columns: Optional[List[str]] = None,
) -> pl.DataFrame:
    """
    Filter data based on selection state and collect, with caching.

    This is the recommended function for components that need filtered data.
    Results are cached based on filter state, so interactions that don't
    change the filter values (e.g., clicking within already-filtered data)
    will return cached results instantly.

    Args:
        data: The data to filter (LazyFrame or DataFrame)
        filters: Mapping of identifier names to column names for filtering
        state: Current selection state with identifier values
        columns: Optional list of column names to select (projection pushdown)

    Returns:
        Collected DataFrame with filters and optional projection applied
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Convert to tuples for caching (dicts aren't hashable)
    filters_tuple = tuple(sorted(filters.items()))
    state_tuple = _make_cache_key(filters, state)
    columns_tuple = tuple(columns) if columns else None

    return _cached_filter_and_collect(
        data,
        filters_tuple,
        state_tuple,
        columns_tuple,
    )


def filter_by_selection(
    data: Union[pl.LazyFrame, pl.DataFrame],
    interactivity: Dict[str, str],
    state: Dict[str, Any],
) -> pl.LazyFrame:
    """
    Filter data based on selection state and interactivity mapping.

    For each identifier in the interactivity mapping, if there's a
    corresponding selection in state, filter the data to rows where
    the mapped column equals the selected value.

    Args:
        data: The data to filter (LazyFrame or DataFrame)
        interactivity: Mapping of identifier names to column names
        state: Current selection state with identifier values

    Returns:
        Filtered LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    for identifier, column in interactivity.items():
        selected_value = state.get(identifier)
        if selected_value is not None:
            data = data.filter(pl.col(column) == selected_value)

    return data


def filter_by_index(
    data: Union[pl.LazyFrame, pl.DataFrame],
    index_column: str,
    index_value: Any,
) -> pl.LazyFrame:
    """
    Filter data to a single row by index value.

    Args:
        data: The data to filter
        index_column: Name of the index column
        index_value: The index value to filter to

    Returns:
        Filtered LazyFrame (typically 1 row)
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return data.filter(pl.col(index_column) == index_value)


def filter_by_range(
    data: Union[pl.LazyFrame, pl.DataFrame],
    x_column: str,
    y_column: str,
    x_range: tuple,
    y_range: tuple,
) -> pl.LazyFrame:
    """
    Filter data within x/y range bounds.

    Args:
        data: The data to filter
        x_column: Name of the x-axis column
        y_column: Name of the y-axis column
        x_range: Tuple of (min, max) for x-axis
        y_range: Tuple of (min, max) for y-axis

    Returns:
        Filtered LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return data.filter(
        (pl.col(x_column) >= x_range[0]) &
        (pl.col(x_column) <= x_range[1]) &
        (pl.col(y_column) >= y_range[0]) &
        (pl.col(y_column) <= y_range[1])
    )


def slice_by_row_index(
    data: Union[pl.LazyFrame, pl.DataFrame],
    row_index: Optional[int],
) -> pl.DataFrame:
    """
    Slice data to a single row by row position.

    Args:
        data: The data to slice
        row_index: The row index (position) to extract

    Returns:
        DataFrame with single row, or empty DataFrame if index is None
    """
    if row_index is None:
        # Return empty DataFrame with same schema
        if isinstance(data, pl.LazyFrame):
            return data.head(0).collect()
        return data.head(0)

    # For LazyFrames, add slice to query plan before collecting
    # This allows Polars to optimize and avoid materializing all rows
    if isinstance(data, pl.LazyFrame):
        # Note: We can't check bounds without collecting, so we slice optimistically
        # and return empty if result is empty
        return data.slice(row_index, 1).collect()

    # For DataFrames, check bounds first
    if row_index < 0 or row_index >= len(data):
        return data.head(0)

    return data.slice(row_index, 1)
