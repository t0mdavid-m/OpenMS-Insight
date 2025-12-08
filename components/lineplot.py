"""Line plot component using Plotly.js."""

from typing import Any, Dict, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


@register_component("lineplot")
class LinePlot(BaseComponent):
    """
    Interactive stick plot component using Plotly.js.

    Features:
    - Stick-style peak visualization (vertical lines from baseline)
    - Highlighting of selected data points
    - Annotations with labels (mass labels, charge states, etc.)
    - Zoom controls with auto-fit to highlighted data
    - SVG export
    - Click-to-select peaks with gold highlighting
    - Cross-component linking via filters and interactivity

    LinePlots can have separate `filters` and `interactivity` mappings:
    - `filters`: Which selections filter this plot's data
    - `interactivity`: What selection is set when a peak is clicked

    Example:
        # Plot filters by spectrum, clicking selects a peak
        plot = LinePlot(
            cache_id="peaks_plot",
            data=peaks_df,
            filters={'spectrum': 'scan_id'},
            interactivity={'my_selection': 'mass'},
            x_column='mass',
            y_column='intensity',
        )
    """

    _component_type: str = "lineplot"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        x_column: str = 'x',
        y_column: str = 'y',
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        highlight_column: Optional[str] = None,
        annotation_column: Optional[str] = None,
        styling: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize the LinePlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with plot data. Optional if cache exists.
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, plot shows only data where
                scan_id equals the selected value.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'my_selection': 'mass'}
                When a peak is clicked, sets 'my_selection' to that peak's mass.
                The selected peak is highlighted in gold (selectedColor).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            x_column: Column name for x-axis values
            y_column: Column name for y-axis values
            title: Plot title
            x_label: X-axis label (defaults to x_column)
            y_label: Y-axis label (defaults to y_column)
            highlight_column: Optional column name containing boolean/int
                              indicating which points to highlight
            annotation_column: Optional column name containing text annotations
                               to display on highlighted points
            styling: Style configuration dict with keys:
                - highlightColor: Color for highlighted points (default: '#E4572E')
                - selectedColor: Color for clicked/selected peak (default: '#F3A712')
                - unhighlightedColor: Color for normal points (default: 'lightblue')
                - annotationBackground: Background color for annotations
            config: Additional Plotly config options
            **kwargs: Additional configuration options
        """
        self._x_column = x_column
        self._y_column = y_column
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._highlight_column = highlight_column
        self._annotation_column = annotation_column
        self._styling = styling or {}
        self._plot_config = config or {}

        super().__init__(
            cache_id=cache_id,
            data=data,
            filters=filters,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            **kwargs
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            'x_column': self._x_column,
            'y_column': self._y_column,
            'highlight_column': self._highlight_column,
            'annotation_column': self._annotation_column,
        }

    def _validate_mappings(self) -> None:
        """Validate columns exist in data schema."""
        super()._validate_mappings()

        schema = self._raw_data.collect_schema()
        column_names = schema.names()

        # Validate x and y columns exist
        for col_name, col_label in [(self._x_column, 'x_column'),
                                     (self._y_column, 'y_column')]:
            if col_name not in column_names:
                raise ValueError(
                    f"{col_label} '{col_name}' not found in data. "
                    f"Available columns: {column_names}"
                )

        # Validate optional columns if specified
        if self._highlight_column and self._highlight_column not in column_names:
            raise ValueError(
                f"highlight_column '{self._highlight_column}' not found in data. "
                f"Available columns: {column_names}"
            )

        if self._annotation_column and self._annotation_column not in column_names:
            raise ValueError(
                f"annotation_column '{self._annotation_column}' not found in data. "
                f"Available columns: {column_names}"
            )

    def _preprocess(self) -> None:
        """
        Preprocess plot data.

        Collects the LazyFrame for caching by base class.
        """
        # Store configuration in preprocessed data for serialization
        self._preprocessed_data['plot_config'] = {
            'x_column': self._x_column,
            'y_column': self._y_column,
            'highlight_column': self._highlight_column,
            'annotation_column': self._annotation_column,
        }

        # Collect data for caching (filter happens at render time)
        # Base class will serialize this to parquet
        self._preprocessed_data['data'] = self._raw_data.collect()

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return 'PlotlyLineplotUnified'

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return 'plotData'

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare plot data for Vue component.

        LinePlots filter based on filters mapping if provided.

        Sends data as a pandas DataFrame for efficient Arrow serialization.
        Vue parses the Arrow table and extracts column arrays for rendering.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with plotData (pandas DataFrame) and _hash for change detection
        """
        # Build list of columns to select (projection pushdown for efficiency)
        columns_to_select = [self._x_column, self._y_column]
        if self._highlight_column:
            columns_to_select.append(self._highlight_column)
        if self._annotation_column:
            columns_to_select.append(self._annotation_column)
        # Include columns needed for interactivity (e.g., peak_id)
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include filter columns for filtering to work
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)

        # Get cached data (DataFrame or LazyFrame)
        data = self._preprocessed_data.get('data')
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
            columns=columns_to_select,
        )

        # Send as DataFrame for Arrow serialization (efficient binary transfer)
        # Vue will parse and extract columns using the config
        return {
            'plotData': df_pandas,
            '_hash': data_hash,
            # Config tells Vue which columns map to x, y, etc.
            '_plotConfig': {
                'xColumn': self._x_column,
                'yColumn': self._y_column,
                'highlightColumn': self._highlight_column,
                'annotationColumn': self._annotation_column,
                'interactivityColumns': {
                    col: col for col in (self._interactivity.values() if self._interactivity else [])
                },
            }
        }

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all plot configuration for Vue
        """
        # Default styling
        default_styling = {
            'highlightColor': '#E4572E',
            'selectedColor': '#F3A712',
            'unhighlightedColor': 'lightblue',
            'highlightHiddenColor': '#1f77b4',
            'annotationColors': {
                'massButton': '#E4572E',
                'selectedMassButton': '#F3A712',
                'sequenceArrow': '#E4572E',
                'selectedSequenceArrow': '#F3A712',
                'background': '#f0f0f0',
                'buttonHover': '#e0e0e0',
            }
        }

        # Merge user styling with defaults
        styling = {**default_styling, **self._styling}
        if 'annotationColors' in self._styling:
            styling['annotationColors'] = {
                **default_styling['annotationColors'],
                **self._styling['annotationColors']
            }

        args: Dict[str, Any] = {
            'componentType': self._get_vue_component_name(),
            'title': self._title or '',
            'xLabel': self._x_label,
            'yLabel': self._y_label,
            'styling': styling,
            'config': self._plot_config,
            # Pass interactivity for click handling (sets selection on peak click)
            'interactivity': self._interactivity,
            # Column mappings for Arrow data parsing in Vue
            'xColumn': self._x_column,
            'yColumn': self._y_column,
            'highlightColumn': self._highlight_column,
            'annotationColumn': self._annotation_column,
        }

        # Add any extra config options
        args.update(self._config)

        return args

    def with_styling(
        self,
        highlight_color: Optional[str] = None,
        selected_color: Optional[str] = None,
        unhighlighted_color: Optional[str] = None,
    ) -> 'LinePlot':
        """
        Update plot styling.

        Args:
            highlight_color: Color for highlighted points
            selected_color: Color for selected points
            unhighlighted_color: Color for unhighlighted points

        Returns:
            Self for method chaining
        """
        if highlight_color:
            self._styling['highlightColor'] = highlight_color
        if selected_color:
            self._styling['selectedColor'] = selected_color
        if unhighlighted_color:
            self._styling['unhighlightedColor'] = unhighlighted_color
        return self

    def with_annotations(
        self,
        background_color: Optional[str] = None,
        button_color: Optional[str] = None,
        selected_button_color: Optional[str] = None,
    ) -> 'LinePlot':
        """
        Configure annotation styling.

        Args:
            background_color: Background color for annotation boxes
            button_color: Color for annotation buttons
            selected_button_color: Color for selected annotation buttons

        Returns:
            Self for method chaining
        """
        if 'annotationColors' not in self._styling:
            self._styling['annotationColors'] = {}

        if background_color:
            self._styling['annotationColors']['background'] = background_color
        if button_color:
            self._styling['annotationColors']['massButton'] = button_color
        if selected_button_color:
            self._styling['annotationColors']['selectedMassButton'] = selected_button_color

        return self
