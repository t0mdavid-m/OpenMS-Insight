"""Table component using Tabulator.js."""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


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
                Pagination dramatically improves performance for tables with
                thousands of rows by only rendering one page at a time.
            page_size: Number of rows per page when pagination is enabled (default: 100)
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

    def _get_row_group_size(self) -> int:
        """
        Get optimal row group size for parquet writing.

        Filtered tables use smaller row groups (10K) for better predicate
        pushdown granularity - this allows Polars to skip row groups that
        don't contain the filter value. Master tables (no filters) use
        larger groups (50K) since we read all data anyway.

        Returns:
            Number of rows per row group
        """
        if self._filters:
            return 10_000  # Smaller groups for better filter performance
        return 50_000  # Larger groups for master tables

    def _preprocess(self) -> None:
        """
        Preprocess table data.

        Sorts by filter columns for efficient predicate pushdown, then
        collects the LazyFrame and generates column definitions if needed.
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

        # Store LazyFrame for streaming to disk (filter happens at render time)
        # Base class will use sink_parquet() to stream without full materialization
        self._preprocessed_data["data"] = data  # Keep lazy

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
        Prepare table data for Vue component.

        Returns pandas DataFrame for efficient Arrow serialization to frontend.
        Data is filtered based on current selection state.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with tableData (pandas DataFrame) and _hash keys
        """
        # Get columns to select for projection pushdown
        columns = self._get_columns_to_select()

        # Get cached data (DataFrame or LazyFrame)
        data = self._preprocessed_data.get("data")
        if data is None:
            # Fallback to raw data if available
            data = self._raw_data

        # Ensure we have a LazyFrame for filtering
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Use cached filter+collect - returns (pandas DataFrame, hash)
        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=columns,
            filter_defaults=self._filter_defaults,
        )

        return {"tableData": df_pandas, "_hash": data_hash}

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

        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "columnDefinitions": column_defs,
            "tableIndexField": self._index_field,
            "tableLayoutParam": self._layout,
            "defaultRow": self._default_row,
            # Pass interactivity so Vue knows which identifier to update on row click
            "interactivity": self._interactivity,
            # Pagination settings
            "pagination": self._pagination,
            "pageSize": self._page_size,
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
