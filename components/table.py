"""Table component using Tabulator.js."""

from typing import Any, Dict, List, Optional, Union

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_by_selection


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

    By default, tables show ALL data and set selection on row click.
    Use `filters_on_selection=True` to make the table filter its data
    based on the current selection state (like LinePlot does).

    Example:
        # Master table - shows all data, sets selection
        master_table = Table(
            data=spectra_df,
            interactivity={'spectrum': 'scan_id'},
        )

        # Detail table - filters based on selection
        detail_table = Table(
            data=peaks_df,
            interactivity={'spectrum': 'scan_id'},
            filters_on_selection=True,
        )
    """

    def __init__(
        self,
        data: pl.LazyFrame,
        interactivity: Dict[str, str],
        column_definitions: Optional[List[Dict[str, Any]]] = None,
        title: Optional[str] = None,
        index_field: str = 'id',
        go_to_fields: Optional[List[str]] = None,
        layout: str = 'fitDataFill',
        default_row: int = 0,
        initial_sort: Optional[List[Dict[str, Any]]] = None,
        filters_on_selection: bool = False,
        **kwargs
    ):
        """
        Initialize the Table component.

        Args:
            data: Polars LazyFrame with table data
            interactivity: Mapping of identifier names to column names.
                When a row is clicked, the component updates the selection
                for each identifier with the value from the mapped column.
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
            filters_on_selection: If True, filter data based on current selection
                state (like LinePlot). If False (default), show all data.
            **kwargs: Additional configuration options
        """
        self._column_definitions = column_definitions
        self._title = title
        self._index_field = index_field
        self._go_to_fields = go_to_fields
        self._layout = layout
        self._default_row = default_row
        self._initial_sort = initial_sort
        self._filters_on_selection = filters_on_selection

        super().__init__(
            data,
            interactivity=interactivity,
            **kwargs
        )

    def _preprocess(self) -> None:
        """
        Preprocess table data.

        For tables, we store the full data and let Vue handle filtering.
        The interactivity-based filtering happens at render time based on state.
        """
        # Collect schema for auto-generating column definitions if needed
        schema = self._raw_data.collect_schema()

        if self._column_definitions is None:
            # Auto-generate column definitions from schema
            self._column_definitions = []
            for name, dtype in zip(schema.names(), schema.dtypes()):
                col_def: Dict[str, Any] = {
                    'field': name,
                    'title': name.replace('_', ' ').title(),
                    'headerTooltip': True,
                }
                # Set sorter based on data type
                if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                             pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                             pl.Float32, pl.Float64):
                    col_def['sorter'] = 'number'
                    col_def['hozAlign'] = 'right'
                elif dtype == pl.Boolean:
                    col_def['sorter'] = 'boolean'
                elif dtype in (pl.Date, pl.Datetime, pl.Time):
                    col_def['sorter'] = 'date'
                else:
                    col_def['sorter'] = 'string'

                self._column_definitions.append(col_def)

        # Store column definitions in preprocessed data for serialization
        self._preprocessed_data['column_definitions'] = self._column_definitions

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return 'TabulatorTable'

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return 'tableData'

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare table data for Vue component.

        If filters_on_selection is True, filters data based on selection state.
        Otherwise, shows all data.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with tableData key containing the data
        """
        if self._filters_on_selection:
            # Filter based on selection state (like LinePlot)
            filtered_data = filter_by_selection(
                self._raw_data,
                self._interactivity,
                state
            )
            df = filtered_data.collect()
        else:
            # Show all data (default behavior)
            df = self._raw_data.collect()

        # Convert to list of dicts for JSON serialization
        table_data = df.to_dicts()

        return {
            'tableData': table_data,
        }

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all table configuration for Vue
        """
        args: Dict[str, Any] = {
            'componentType': self._get_vue_component_name(),
            'columnDefinitions': self._column_definitions,
            'tableIndexField': self._index_field,
            'tableLayoutParam': self._layout,
            'defaultRow': self._default_row,
            # Pass interactivity so Vue knows which identifier to update on row click
            'interactivity': self._interactivity,
        }

        if self._title:
            args['title'] = self._title

        if self._go_to_fields:
            args['goToFields'] = self._go_to_fields

        if self._initial_sort:
            args['initialSort'] = self._initial_sort

        # Add any extra config options
        args.update(self._config)

        return args

    def with_column_formatter(
        self,
        field: str,
        formatter: str,
        formatter_params: Optional[Dict[str, Any]] = None
    ) -> 'Table':
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
            if col_def.get('field') == field:
                col_def['formatter'] = formatter
                if formatter_params:
                    col_def['formatterParams'] = formatter_params
                break
        return self

    def with_money_format(
        self,
        field: str,
        precision: int = 2,
        symbol: str = '',
        thousand: str = ',',
        decimal: str = '.'
    ) -> 'Table':
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
            'money',
            {
                'precision': precision,
                'symbol': symbol,
                'thousand': thousand,
                'decimal': decimal,
            }
        )

    def with_progress_bar(
        self,
        field: str,
        min_val: float = 0,
        max_val: float = 100,
        color: Optional[str] = None
    ) -> 'Table':
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
        params: Dict[str, Any] = {'min': min_val, 'max': max_val}
        if color:
            params['color'] = color
        return self.with_column_formatter(field, 'progress', params)
