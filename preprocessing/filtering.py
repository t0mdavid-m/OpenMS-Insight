"""Data filtering utilities for selection-based filtering."""

from typing import Any, Dict, Optional, Union

import polars as pl


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
    if isinstance(data, pl.LazyFrame):
        data = data.collect()

    if row_index is None:
        return data.head(0)

    if row_index < 0 or row_index >= len(data):
        return data.head(0)

    return data.slice(row_index, 1)
