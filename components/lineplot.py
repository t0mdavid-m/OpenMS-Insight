"""Line plot component using Plotly.js."""

from typing import Any, Dict, List, Optional, Union

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
            data=peaks_df,
            filters={'spectrum': 'scan_id'},
            interactivity={'my_selection': 'mass'},
            x_column='mass',
            y_column='intensity',
        )
    """

    def __init__(
        self,
        data: pl.LazyFrame,
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
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
            data: Polars LazyFrame with plot data
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, plot shows only data where
                scan_id equals the selected value.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'my_selection': 'mass'}
                When a peak is clicked, sets 'my_selection' to that peak's mass.
                The selected peak is highlighted in gold (selectedColor).
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
            data,
            filters=filters,
            interactivity=interactivity,
            **kwargs
        )

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

        For line plots, we collect the data and prepare it for Vue rendering.
        """
        # Store configuration in preprocessed data for serialization
        self._preprocessed_data['plot_config'] = {
            'x_column': self._x_column,
            'y_column': self._y_column,
            'highlight_column': self._highlight_column,
            'annotation_column': self._annotation_column,
        }

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

        Sends raw x/y values to Vue, which converts them to stick plot format.
        This reduces data transfer size by 3x. Results are cached based on filter state.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with plot data for Vue (x_values, y_values, highlight_mask, annotations)
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

        # Use cached filter+collect for efficiency
        # Cache key is based on filter state, so interactions that don't
        # change filters (e.g., clicking a peak) hit cache
        df = filter_and_collect_cached(
            self._raw_data,
            self._filters,
            state,
            columns=columns_to_select,
        )

        # Get x and y values (raw, not triplicated - Vue will create stick format)
        x_values = df[self._x_column].to_list()
        y_values = df[self._y_column].to_list()

        # Get highlighting data
        highlight_mask = None
        if self._highlight_column and self._highlight_column in df.columns:
            highlight_mask = df[self._highlight_column].to_list()

        # Get annotations
        annotations = None
        if self._annotation_column and self._annotation_column in df.columns:
            annotations = df[self._annotation_column].to_list()

        # Build the data payload
        plot_data = {
            'x_values': x_values,
            'y_values': y_values,
        }

        if highlight_mask is not None:
            plot_data['highlight_mask'] = highlight_mask

        if annotations is not None:
            plot_data['annotations'] = annotations

        # Include interactivity column values (e.g., peak_id for each point)
        if self._interactivity:
            for identifier, col in self._interactivity.items():
                if col in df.columns:
                    plot_data[f'interactivity_{col}'] = df[col].to_list()

        return {
            'plotData': plot_data,
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
            # Pass x_column name so Vue knows click sets x value
            'xColumn': self._x_column,
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
