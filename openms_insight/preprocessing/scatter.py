"""Shared utilities for scatter-based components (Heatmap, VolcanoPlot)."""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import polars as pl

from .filtering import compute_dataframe_hash, filter_and_collect_cached


def build_scatter_columns(
    x_column: str,
    y_column: str,
    value_column: str,
    interactivity: Optional[Dict[str, str]] = None,
    filters: Optional[Dict[str, str]] = None,
    extra_columns: Optional[List[str]] = None,
) -> List[str]:
    """
    Build list of columns needed for scatter-based component.

    Includes x, y, value columns plus any columns needed for
    interactivity and filtering.

    Args:
        x_column: Name of x-axis column
        y_column: Name of y-axis column
        value_column: Name of value column (intensity, -log10(pvalue), etc.)
        interactivity: Mapping of identifier names to column names for clicks
        filters: Mapping of identifier names to column names for filtering
        extra_columns: Additional columns to include (e.g., label_column)

    Returns:
        List of unique column names to select
    """
    columns = [x_column, y_column, value_column]

    # Include columns needed for interactivity
    if interactivity:
        for col in interactivity.values():
            if col not in columns:
                columns.append(col)

    # Include filter columns
    if filters:
        for col in filters.values():
            if col not in columns:
                columns.append(col)

    # Include extra columns (e.g., label column for VolcanoPlot)
    if extra_columns:
        for col in extra_columns:
            if col and col not in columns:
                columns.append(col)

    return columns


def prepare_scatter_data(
    data: pl.LazyFrame,
    x_column: str,
    y_column: str,
    value_column: str,
    filters: Optional[Dict[str, str]],
    state: Dict[str, Any],
    filter_defaults: Optional[Dict[str, Any]] = None,
    interactivity: Optional[Dict[str, str]] = None,
    extra_columns: Optional[List[str]] = None,
    sort_by_value: bool = True,
    sort_ascending: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """
    Prepare scatter data for Vue component.

    Common data preparation for scatter-based components (Heatmap, VolcanoPlot).
    Applies filters, selects columns, optionally sorts, and returns pandas
    DataFrame with hash for change detection.

    Args:
        data: LazyFrame with scatter data
        x_column: Name of x-axis column
        y_column: Name of y-axis column
        value_column: Name of value column (intensity, -log10(pvalue), etc.)
        filters: Mapping of identifier names to column names for filtering
        state: Current selection state from StateManager
        filter_defaults: Optional default values for filters when state is None
        interactivity: Mapping of identifier names to column names for clicks
        extra_columns: Additional columns to include (e.g., label_column)
        sort_by_value: If True, sort by value_column (default: True)
        sort_ascending: Sort order - True for ascending (default: True)
            Ascending puts high values on top in scatter plots.

    Returns:
        Tuple of (pandas DataFrame, hash string for change detection)
    """
    # Build columns to select
    columns = build_scatter_columns(
        x_column=x_column,
        y_column=y_column,
        value_column=value_column,
        interactivity=interactivity,
        filters=filters,
        extra_columns=extra_columns,
    )

    # Apply filters if any
    if filters:
        df_pandas, data_hash = filter_and_collect_cached(
            data,
            filters,
            state,
            columns=columns,
            filter_defaults=filter_defaults,
        )

        # Sort by value column so high-value points are drawn on top
        if sort_by_value and len(df_pandas) > 0 and value_column in df_pandas.columns:
            df_pandas = df_pandas.sort_values(
                value_column, ascending=sort_ascending
            ).reset_index(drop=True)

        return df_pandas, data_hash
    else:
        # No filters - just select columns and collect
        schema_names = data.collect_schema().names()
        available_cols = [c for c in columns if c in schema_names]
        df_polars = data.select(available_cols).collect()

        # Sort by value column
        if sort_by_value and len(df_polars) > 0 and value_column in df_polars.columns:
            df_polars = df_polars.sort(value_column, descending=not sort_ascending)

        data_hash = compute_dataframe_hash(df_polars)
        df_pandas = df_polars.to_pandas()

        return df_pandas, data_hash
