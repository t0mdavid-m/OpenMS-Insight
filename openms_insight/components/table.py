"""Table component using Tabulator.js."""

import logging
import re
from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import compute_dataframe_hash

logger = logging.getLogger(__name__)

# Numeric data types for dtype checking
NUMERIC_DTYPES = (
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
)

# Session state key for tracking last rendered selection per table component
_LAST_SELECTION_KEY = "_svc_table_last_selection"
# Session state key for tracking last sort/filter state per table component
_LAST_SORT_FILTER_KEY = "_svc_table_last_sort_filter"


@register_component("table")
class Table(BaseComponent):
    """
    Interactive table component using Tabulator.js.

    Features:
    - Column definitions with formatters, sorters, tooltips
    - Row selection with cross-component linking
    - Filtering dialog (categorical, numeric, text)
    - Go-to functionality for navigation by field value
    - CSV download
    - Automatic column type detection

    Tables can have separate `filters` and `interactivity` mappings:
    - `filters`: Which selections filter this table's data
    - `interactivity`: What selection is set when a row is clicked

    Example:
        # Master table - shows all data, clicking sets 'spectrum' selection
        master_table = Table(
            cache_id="spectra_table",
            data=spectra_df,
            interactivity={'spectrum': 'scan_id'},
        )

        # Detail table - filters by 'spectrum', clicking sets 'peak' selection
        detail_table = Table(
            cache_id="peaks_table",
            data=peaks_df,
            filters={'spectrum': 'scan_id'},
            interactivity={'peak': 'mass'},
        )
    """

    _component_type: str = "table"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        column_definitions: Optional[List[Dict[str, Any]]] = None,
        title: Optional[str] = None,
        index_field: str = "id",
        go_to_fields: Optional[List[str]] = None,
        layout: str = "fitDataFill",
        default_row: int = 0,
        initial_sort: Optional[List[Dict[str, Any]]] = None,
        pagination: bool = True,
        page_size: int = 100,
        pagination_identifier: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the Table component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with table data. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, table shows only rows where
                scan_id equals the selected value.
            filter_defaults: Default values for filters when state is None.
                Example: {'identification': -1}
                When 'identification' selection is None, filter uses -1 instead.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'peak': 'mass'}
                When a row is clicked, sets 'peak' selection to that row's mass.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            column_definitions: List of Tabulator column definition dicts.
                Each dict can contain:
                - field: Column field name (required)
                - title: Display title (defaults to field name)
                - sorter: 'number', 'string', 'alphanum', 'boolean', 'date', etc.
                - formatter: 'money', 'progress', 'star', 'tickCross', etc.
                - formatterParams: Dict of formatter parameters
                - headerTooltip: True or tooltip string
                - hozAlign: 'left', 'center', 'right'
                - width: Column width (number or string like '100px')
                If None, auto-generates from data schema.
            title: Table title displayed above the table
            index_field: Field used as row index for selection (default: 'id')
            go_to_fields: List of field names for "Go to" navigation feature
            layout: Tabulator layout mode ('fitData', 'fitDataFill', 'fitColumns', etc.)
            default_row: Default row to select on load (-1 for none)
            initial_sort: List of sort configurations like [{'column': 'field', 'dir': 'asc'}]
            pagination: Enable pagination for large tables (default: True).
                When enabled, uses server-side pagination where only the current
                page of data is sent to the frontend, dramatically reducing browser
                memory usage for large datasets.
            page_size: Number of rows per page when pagination is enabled (default: 100)
            pagination_identifier: State key for storing pagination state (page, sort,
                filters). Default: "{cache_id}_page". Used by StateManager to track
                pagination state across reruns.
            **kwargs: Additional configuration options
        """
        self._column_definitions = column_definitions
        self._title = title
        self._index_field = index_field
        self._go_to_fields = go_to_fields
        self._layout = layout
        self._default_row = default_row
        self._initial_sort = initial_sort
        self._pagination = pagination
        self._page_size = page_size
        # Default pagination identifier based on cache_id
        self._pagination_identifier = pagination_identifier or f"{cache_id}_page"

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Pass component-specific params for subprocess recreation
            column_definitions=column_definitions,
            title=title,
            index_field=index_field,
            go_to_fields=go_to_fields,
            layout=layout,
            default_row=default_row,
            initial_sort=initial_sort,
            pagination=pagination,
            page_size=page_size,
            pagination_identifier=self._pagination_identifier,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            "column_definitions": self._column_definitions,
            "index_field": self._index_field,
            "title": self._title,
            "go_to_fields": self._go_to_fields,
            "layout": self._layout,
            "default_row": self._default_row,
            "initial_sort": self._initial_sort,
            "pagination": self._pagination,
            "page_size": self._page_size,
            "pagination_identifier": self._pagination_identifier,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._column_definitions = config.get("column_definitions")
        self._index_field = config.get("index_field", "id")
        self._title = config.get("title")
        self._go_to_fields = config.get("go_to_fields")
        self._layout = config.get("layout", "fitDataFill")
        self._default_row = config.get("default_row", 0)
        self._initial_sort = config.get("initial_sort")
        self._pagination = config.get("pagination", True)
        self._page_size = config.get("page_size", 100)
        self._pagination_identifier = config.get(
            "pagination_identifier", f"{self._cache_id}_page"
        )

    def get_state_dependencies(self) -> List[str]:
        """
        Return list of state keys that affect this component's data.

        Tables depend on:
        - filters (for data filtering)
        - pagination state (for page, sort, and column filters)
        - interactivity identifiers (for page navigation to selected row)

        Returns:
            List of state identifier keys
        """
        deps = list(self._filters.keys()) if self._filters else []
        deps.append(self._pagination_identifier)
        # Include interactivity identifiers for page navigation
        if self._interactivity:
            deps.extend(self._interactivity.keys())
        return deps

    def get_initial_selection(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Compute the initial selection for this table WITHOUT triggering Vue updates.

        Only returns a value on INITIAL LOAD when:
        - Table has interactivity configured
        - default_row >= 0 (not disabled)
        - No selection already exists for any interactivity identifier
        - Not awaiting a required filter value
        - No pagination state exists yet (truly initial load, not page navigation)

        This is safe because:
        - We compute from the same data _prepare_vue_data() returns
        - Initial load always shows page 1 with default sort
        - No user-applied column filters exist yet

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict mapping identifier names to their initial values,
            or None if no initial selection should be set.
        """
        # Skip if no interactivity or default_row disabled
        if not self._interactivity or self._default_row < 0:
            return None

        # Skip if selection already exists for ANY interactivity identifier
        for identifier in self._interactivity.keys():
            if state.get(identifier) is not None:
                return None

        # Skip if NOT initial load (pagination state exists = user already interacted)
        # This ensures we only pre-compute for the true first render
        pagination_state = state.get(self._pagination_identifier)
        if pagination_state is not None:
            return None

        # Skip if awaiting required filter (no data to select from)
        for identifier in self._filters.keys():
            filter_value = state.get(identifier)
            has_default = self._filter_defaults and identifier in self._filter_defaults
            if filter_value is None and not has_default:
                return None

        # Get first page data and extract default row values
        try:
            vue_data = self._prepare_vue_data(state)
            table_data = vue_data.get("tableData")
            if table_data is None or len(table_data) == 0:
                return None

            # Clamp to available rows
            default_idx = min(self._default_row, len(table_data) - 1)
            if default_idx < 0:
                return None

            result = {}
            for identifier, column in self._interactivity.items():
                if column in table_data.columns:
                    value = table_data[column].iloc[default_idx]
                    # Convert numpy types to Python types for JSON serialization
                    if hasattr(value, "item"):
                        value = value.item()
                    result[identifier] = value

            return result if result else None

        except Exception:
            # If anything fails, let Vue handle it normally
            return None

    def _preprocess(self) -> None:
        """
        Preprocess table data.

        Sorts by filter columns for efficient predicate pushdown, then
        collects the LazyFrame and generates column definitions if needed.
        Also computes column metadata for server-side filtering in filter dialogs.
        Data is cached by base class for fast subsequent loads.
        """
        data = self._raw_data

        # Sort by filter columns for efficient predicate pushdown.
        # This clusters identical filter values together, enabling Polars
        # to skip row groups that don't contain the target value when
        # filtering by selection state.
        if self._filters:
            sort_columns = list(self._filters.values())
            data = data.sort(sort_columns)

        # Collect schema for auto-generating column definitions if needed
        schema = data.collect_schema()

        if self._column_definitions is None:
            # Auto-generate column definitions from schema
            self._column_definitions = []
            for name, dtype in zip(schema.names(), schema.dtypes()):
                col_def: Dict[str, Any] = {
                    "field": name,
                    "title": name.replace("_", " ").title(),
                    "headerTooltip": True,
                }
                # Set sorter based on data type
                if dtype in (
                    pl.Int8,
                    pl.Int16,
                    pl.Int32,
                    pl.Int64,
                    pl.UInt8,
                    pl.UInt16,
                    pl.UInt32,
                    pl.UInt64,
                    pl.Float32,
                    pl.Float64,
                ):
                    col_def["sorter"] = "number"
                    col_def["hozAlign"] = "right"
                elif dtype == pl.Boolean:
                    col_def["sorter"] = "boolean"
                elif dtype in (pl.Date, pl.Datetime, pl.Time):
                    col_def["sorter"] = "date"
                else:
                    col_def["sorter"] = "string"

                self._column_definitions.append(col_def)

        # Store column definitions in preprocessed data for serialization
        self._preprocessed_data["column_definitions"] = self._column_definitions

        # Compute column metadata for server-side filter dialogs
        # This is computed once at preprocessing time and cached
        column_metadata: Dict[str, Dict[str, Any]] = {}
        for name, dtype in zip(schema.names(), schema.dtypes()):
            meta: Dict[str, Any] = {}

            if dtype in (
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
                pl.Float32,
                pl.Float64,
            ):
                # Numeric column - compute min/max and unique count
                stats = data.select(
                    [
                        pl.col(name).min().alias("min"),
                        pl.col(name).max().alias("max"),
                        pl.col(name).n_unique().alias("n_unique"),
                    ]
                ).collect()
                min_val = stats["min"][0]
                max_val = stats["max"][0]
                n_unique = stats["n_unique"][0]

                # If few unique values, treat as categorical
                if n_unique is not None and n_unique <= 10:
                    meta["type"] = "categorical"
                    unique_vals = (
                        data.select(pl.col(name))
                        .unique()
                        .sort(name)
                        .collect()
                        .to_series()
                        .to_list()
                    )
                    meta["unique_values"] = [v for v in unique_vals if v is not None][
                        :100
                    ]
                else:
                    meta["type"] = "numeric"
                    if min_val is not None:
                        meta["min"] = float(min_val)
                    if max_val is not None:
                        meta["max"] = float(max_val)
            elif dtype == pl.Utf8:
                # String column - check unique count
                n_unique = data.select(pl.col(name).n_unique()).collect().item()
                if n_unique is not None and n_unique <= 50:
                    meta["type"] = "categorical"
                    unique_vals = (
                        data.select(pl.col(name))
                        .unique()
                        .sort(name, nulls_last=True)
                        .collect()
                        .to_series()
                        .to_list()
                    )
                    meta["unique_values"] = [
                        v for v in unique_vals if v is not None and v != ""
                    ][:100]
                else:
                    meta["type"] = "text"
            elif dtype == pl.Boolean:
                meta["type"] = "categorical"
                meta["unique_values"] = [True, False]
            else:
                meta["type"] = "text"

            column_metadata[name] = meta

        self._preprocessed_data["column_metadata"] = column_metadata

        # Auto-detect go-to fields if not explicitly provided
        if self._go_to_fields is None:
            self._go_to_fields = self._auto_detect_go_to_fields(data)
        elif self._go_to_fields == []:
            # Explicitly disabled - keep empty list
            pass
        # else: use user-provided list as-is

        # Store LazyFrame for streaming to disk (filter happens at render time)
        # Base class will use sink_parquet() to stream without full materialization
        self._preprocessed_data["data"] = data  # Keep lazy

    def _auto_detect_go_to_fields(self, data: pl.LazyFrame) -> List[str]:
        """
        Auto-detect columns suitable for go-to navigation.

        Criteria:
        - Integer or String (Utf8) type only (excludes Float)
        - 100% unique values (no duplicates)
        - Samples first 10,000 rows for performance

        Args:
            data: LazyFrame to analyze for unique columns

        Returns:
            List of column names in original schema order
        """
        schema = data.collect_schema()
        sample = data.head(10000)

        candidates = []
        for col_name in schema.names():
            dtype = schema[col_name]

            # Only Integer and String types (exclude Float)
            if dtype not in (
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
                pl.Utf8,
            ):
                continue

            # Check 100% uniqueness in sample
            stats = sample.select(
                [
                    pl.col(col_name).len().alias("count"),
                    pl.col(col_name).n_unique().alias("n_unique"),
                ]
            ).collect()

            count = stats["count"][0]
            n_unique = stats["n_unique"][0]

            # Must be 100% unique (count == n_unique)
            if count > 0 and count == n_unique:
                candidates.append(col_name)

        return candidates

    def _get_columns_to_select(self) -> Optional[List[str]]:
        """Get list of columns needed for this table."""
        if not self._column_definitions:
            return None

        columns_to_select = [
            col_def["field"]
            for col_def in self._column_definitions
            if "field" in col_def
        ]
        # Always include index field for row identification
        if self._index_field and self._index_field not in columns_to_select:
            columns_to_select.append(self._index_field)
        # Include columns needed for interactivity
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include columns needed for filtering
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)

        return columns_to_select if columns_to_select else None

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "TabulatorTable"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "tableData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare table data for Vue component with server-side pagination.

        Implements streaming pagination where only the current page of data
        is sent to the frontend. Handles server-side sorting, column filtering,
        and cross-component selection navigation.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with tableData (pandas DataFrame), _hash, _pagination metadata,
            and optional _navigate_to_page/_target_row_index for selection navigation
        """
        import time

        logger.info(f"[Table._prepare_vue_data] ===== START ===== ts={time.time()}")
        logger.info(f"[Table._prepare_vue_data] cache_id={self._cache_id}")
        logger.info(
            f"[Table._prepare_vue_data] pagination_identifier={self._pagination_identifier}"
        )
        pagination_state_for_log = state.get(self._pagination_identifier)
        logger.info(
            f"[Table._prepare_vue_data] pagination_state={pagination_state_for_log}"
        )

        # Get columns to select for projection pushdown
        columns = self._get_columns_to_select()

        # Get cached data (DataFrame or LazyFrame)
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data

        # Ensure we have a LazyFrame for filtering
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Apply column projection first for efficiency
        if columns:
            schema_names = data.collect_schema().names()
            available_cols = [c for c in columns if c in schema_names]
            if available_cols:
                data = data.select(available_cols)

        # Apply cross-component filters (from self._filters)
        for identifier, column in self._filters.items():
            selected_value = state.get(identifier)
            # Apply default if value is None and default exists
            if (
                selected_value is None
                and self._filter_defaults
                and identifier in self._filter_defaults
            ):
                selected_value = self._filter_defaults[identifier]

            if selected_value is None:
                # No selection for this filter - return empty DataFrame
                df_polars = data.head(0).collect()
                data_hash = compute_dataframe_hash(df_polars)
                return {
                    "tableData": df_polars.to_pandas(),
                    "_hash": data_hash,
                    "_pagination": {
                        "page": 1,
                        "page_size": self._page_size,
                        "total_rows": 0,
                        "total_pages": 0,
                    },
                }

            # Convert float to int for integer columns (JS numbers come as floats)
            if isinstance(selected_value, float) and selected_value.is_integer():
                selected_value = int(selected_value)
            data = data.filter(pl.col(column) == selected_value)

        # Get pagination state
        pagination_state = state.get(self._pagination_identifier)
        if pagination_state is None:
            pagination_state = {}

        page = pagination_state.get("page", 1)
        page_size = pagination_state.get("page_size", self._page_size)
        sort_column = pagination_state.get("sort_column")
        sort_dir = pagination_state.get("sort_dir", "asc")
        column_filters = pagination_state.get("column_filters", [])
        go_to_request = pagination_state.get("go_to_request")

        # Apply column filters from filter dialog
        for col_filter in column_filters:
            field = col_filter.get("field")
            filter_type = col_filter.get("type")
            value = col_filter.get("value")

            if not field or value is None:
                continue

            if filter_type == "in" and isinstance(value, list):
                # Categorical filter - match any of the values
                data = data.filter(pl.col(field).is_in(value))
            elif filter_type == ">=":
                data = data.filter(pl.col(field) >= value)
            elif filter_type == "<=":
                data = data.filter(pl.col(field) <= value)
            elif filter_type == "regex":
                # Text search with regex - invalid patterns match nothing
                try:
                    re.compile(value)
                    data = data.filter(pl.col(field).str.contains(value, literal=False))
                except re.error:
                    # Invalid regex pattern - filter to empty result
                    data = data.filter(pl.lit(False))

        # Apply server-side sort
        if sort_column:
            descending = sort_dir == "desc"
            data = data.sort(sort_column, descending=descending)

        # Get total row count (after filters, before pagination)
        total_rows = data.select(pl.len()).collect().item()
        total_pages = max(1, (total_rows + page_size - 1) // page_size)

        # Handle go-to request (server-side search for row by field value)
        navigate_to_page = None
        target_row_index = None
        go_to_not_found = False

        if go_to_request:
            go_to_field = go_to_request.get("field")
            go_to_value = go_to_request.get("value")
            if go_to_field and go_to_value is not None:
                # Only convert to numeric if the target column is numeric
                schema = data.collect_schema()
                if go_to_field in schema and schema[go_to_field] in NUMERIC_DTYPES:
                    try:
                        go_to_value = float(go_to_value)
                        if go_to_value.is_integer():
                            go_to_value = int(go_to_value)
                    except (ValueError, TypeError):
                        # Non-numeric string for numeric column - mark as not found
                        go_to_not_found = True
                # If column is string (Utf8), keep go_to_value as-is

                # Only search if we have a valid value (not already marked as not found)
                if not go_to_not_found:
                    # Find the row with row_number
                    search_result = (
                        data.with_row_index("_row_num")
                        .filter(pl.col(go_to_field) == go_to_value)
                        .select("_row_num")
                        .head(1)
                        .collect()
                    )

                    if len(search_result) > 0:
                        row_num = search_result["_row_num"][0]
                        target_page = (row_num // page_size) + 1
                        navigate_to_page = target_page
                        target_row_index = row_num % page_size
                        page = target_page  # Jump to target page
                    else:
                        # Row not found - set flag for Vue to show "not found" feedback
                        go_to_not_found = True

        # === Selection and Sort/Filter based navigation ===
        # PURPOSE: When user sorts/filters, find where the selected row ended up and navigate there
        if self._interactivity and self._pagination:
            import json

            import streamlit as st

            # Initialize tracking dicts (per-component storage)
            if _LAST_SELECTION_KEY not in st.session_state:
                st.session_state[_LAST_SELECTION_KEY] = {}
            if _LAST_SORT_FILTER_KEY not in st.session_state:
                st.session_state[_LAST_SORT_FILTER_KEY] = {}

            component_key = self._cache_id  # Unique key for this table instance

            # Get PREVIOUS states (from last render)
            last_selections = st.session_state[_LAST_SELECTION_KEY].get(
                component_key, {}
            )
            last_sort_filter = st.session_state[_LAST_SORT_FILTER_KEY].get(
                component_key, {}
            )

            # Build CURRENT selection state
            current_selections = {}
            for identifier in self._interactivity.keys():
                current_selections[identifier] = state.get(identifier)

            # Build CURRENT sort/filter state
            # Use JSON for column_filters to enable deep comparison of nested dicts
            current_sort_filter = {
                "sort_column": sort_column,
                "sort_dir": sort_dir,
                "column_filters_json": json.dumps(column_filters, sort_keys=True),
            }

            # DETECT what changed by comparing current vs previous
            selection_changed = current_selections != last_selections
            sort_filter_changed = current_sort_filter != last_sort_filter

            # CRITICAL: Update tracking state AFTER detecting changes
            # This prevents infinite loops: next render will see no change
            st.session_state[_LAST_SELECTION_KEY][component_key] = current_selections
            st.session_state[_LAST_SORT_FILTER_KEY][component_key] = current_sort_filter

            # DECIDE whether to navigate
            # - Don't override go_to navigation (user explicitly requested a row)
            # - Navigate if selection changed (find new selection's page)
            # - Navigate if sort/filter changed AND we have a selection (find existing selection's new page)
            should_navigate = False
            if navigate_to_page is None:
                if selection_changed:
                    should_navigate = True
                elif sort_filter_changed and any(
                    v is not None for v in current_selections.values()
                ):
                    should_navigate = True

            if should_navigate:
                for identifier, column in self._interactivity.items():
                    selected_value = state.get(identifier)
                    if selected_value is not None:
                        # Type conversion based on column dtype (same logic as go-to)
                        schema = data.collect_schema()
                        if column in schema:
                            col_dtype = schema[column]
                            if col_dtype in NUMERIC_DTYPES:
                                # Column is numeric - convert value to numeric if possible
                                if isinstance(selected_value, str):
                                    try:
                                        selected_value = float(selected_value)
                                        if selected_value.is_integer():
                                            selected_value = int(selected_value)
                                    except (ValueError, TypeError):
                                        pass
                                elif (
                                    isinstance(selected_value, float)
                                    and selected_value.is_integer()
                                ):
                                    selected_value = int(selected_value)
                            else:
                                # Column is string - convert value to string
                                if not isinstance(selected_value, str):
                                    selected_value = str(selected_value)

                        # SEARCH for the selected row in the sorted/filtered data
                        # with_row_index adds position so we know which page it's on
                        search_result = (
                            data.with_row_index("_row_num")
                            .filter(pl.col(column) == selected_value)
                            .select("_row_num")
                            .head(1)
                            .collect()
                        )

                        if len(search_result) > 0:
                            # ROW FOUND - update page in pagination state if needed
                            row_num = search_result["_row_num"][0]
                            target_page = (row_num // page_size) + 1
                            if target_page != page:
                                # Update pagination state directly (same as Vue would)
                                from openms_insight.core.state import (
                                    get_default_state_manager,
                                )

                                state_manager = get_default_state_manager()
                                updated_pagination = {
                                    **pagination_state,
                                    "page": target_page,
                                }
                                state_manager.set_selection(
                                    self._pagination_identifier, updated_pagination
                                )
                                navigate_to_page = target_page
                                target_row_index = row_num % page_size
                                page = target_page  # Use new page for slicing
                        else:
                            # ROW NOT FOUND - it was filtered out
                            # Update selection to first row's value AND set page to 1
                            if sort_filter_changed and not selection_changed:
                                first_row_result = (
                                    data.select(pl.col(column)).head(1).collect()
                                )
                                if len(first_row_result) > 0:
                                    first_value = first_row_result[column][0]
                                    if hasattr(first_value, "item"):
                                        first_value = first_value.item()

                                    from openms_insight.core.state import (
                                        get_default_state_manager,
                                    )

                                    state_manager = get_default_state_manager()

                                    # Update selection to first row
                                    state_manager.set_selection(identifier, first_value)

                                    # Update pagination state to page 1
                                    updated_pagination = {
                                        **pagination_state,
                                        "page": 1,
                                    }
                                    state_manager.set_selection(
                                        self._pagination_identifier, updated_pagination
                                    )
                                    page = 1  # Use page 1 for slicing
                        break

        # Clamp page to valid range
        page = max(1, min(page, total_pages))

        # Slice to current page
        offset = (page - 1) * page_size
        df_polars = data.slice(offset, page_size).collect()

        # Compute hash for change detection
        data_hash = compute_dataframe_hash(df_polars)

        # Build result
        result: Dict[str, Any] = {
            "tableData": df_polars.to_pandas(),
            "_hash": data_hash,
            "_pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": total_pages,
                "sort_column": sort_column,
                "sort_dir": sort_dir,
            },
        }

        if navigate_to_page is not None:
            result["_navigate_to_page"] = navigate_to_page
        if target_row_index is not None:
            result["_target_row_index"] = target_row_index
        if go_to_not_found:
            result["_go_to_not_found"] = True

        logger.info(
            f"[Table._prepare_vue_data] Returning: page={page}, total_rows={total_rows}, data_rows={len(df_polars)}"
        )
        logger.info(
            f"[Table._prepare_vue_data] hash={data_hash[:8] if data_hash else 'None'}"
        )
        return result

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all table configuration for Vue
        """
        # Get column definitions (may have been loaded from cache)
        column_defs = self._column_definitions
        if column_defs is None:
            column_defs = self._preprocessed_data.get("column_definitions", [])

        # Get column metadata for filter dialogs (computed during preprocessing)
        column_metadata = self._preprocessed_data.get("column_metadata", {})

        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "columnDefinitions": column_defs,
            "tableIndexField": self._index_field,
            "tableLayoutParam": self._layout,
            "defaultRow": self._default_row,
            # Pass interactivity so Vue knows which identifier to update on row click
            "interactivity": self._interactivity,
            # Pagination settings - always use server-side pagination
            "pagination": self._pagination,
            "pageSize": self._page_size,
            "paginationIdentifier": self._pagination_identifier,
            # Column metadata for filter dialogs (precomputed unique values, min/max)
            "columnMetadata": column_metadata,
        }

        if self._title:
            args["title"] = self._title

        if self._go_to_fields:
            args["goToFields"] = self._go_to_fields

        if self._initial_sort:
            args["initialSort"] = self._initial_sort

        # Add any extra config options
        args.update(self._config)

        return args

    def with_column_formatter(
        self,
        field: str,
        formatter: str,
        formatter_params: Optional[Dict[str, Any]] = None,
    ) -> "Table":
        """
        Add or update a column formatter.

        Args:
            field: Column field name
            formatter: Tabulator formatter name
            formatter_params: Optional formatter parameters

        Returns:
            Self for method chaining
        """
        for col_def in self._column_definitions or []:
            if col_def.get("field") == field:
                col_def["formatter"] = formatter
                if formatter_params:
                    col_def["formatterParams"] = formatter_params
                break
        return self

    def with_money_format(
        self,
        field: str,
        precision: int = 2,
        symbol: str = "",
        thousand: str = ",",
        decimal: str = ".",
    ) -> "Table":
        """
        Format a column as currency/money.

        Args:
            field: Column field name
            precision: Number of decimal places
            symbol: Currency symbol (default: none)
            thousand: Thousands separator
            decimal: Decimal separator

        Returns:
            Self for method chaining
        """
        return self.with_column_formatter(
            field,
            "money",
            {
                "precision": precision,
                "symbol": symbol,
                "thousand": thousand,
                "decimal": decimal,
            },
        )

    def with_progress_bar(
        self,
        field: str,
        min_val: float = 0,
        max_val: float = 100,
        color: Optional[str] = None,
    ) -> "Table":
        """
        Format a column as a progress bar.

        Args:
            field: Column field name
            min_val: Minimum value
            max_val: Maximum value
            color: Bar color (CSS color string)

        Returns:
            Self for method chaining
        """
        params: Dict[str, Any] = {"min": min_val, "max": max_val}
        if color:
            params["color"] = color
        return self.with_column_formatter(field, "progress", params)
