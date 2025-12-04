"""Heatmap component using Plotly scattergl."""

from typing import Any, Dict, List, Optional, Union

import polars as pl
import streamlit as st

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.compression import (
    compute_compression_levels,
    downsample_2d,
    downsample_2d_simple,
)
from ..preprocessing.filtering import filter_and_collect_cached


# Cache key only includes zoom state (not other selections)
def _make_zoom_cache_key(zoom: Optional[Dict[str, Any]]) -> tuple:
    """Create hashable cache key from zoom state."""
    if zoom is None:
        return (None,)
    return (
        ('x0', zoom.get('xRange', [-1, -1])[0]),
        ('x1', zoom.get('xRange', [-1, -1])[1]),
        ('y0', zoom.get('yRange', [-1, -1])[0]),
        ('y1', zoom.get('yRange', [-1, -1])[1]),
    )


@register_component("heatmap")
class Heatmap(BaseComponent):
    """
    Interactive 2D scatter/heatmap component using Plotly scattergl.

    Designed for large datasets (millions of points) using multi-resolution
    preprocessing with zoom-based level selection. Points are colored by
    intensity using a log-scale colormap.

    Features:
    - Multi-resolution downsampling for large datasets
    - Zoom-based automatic level selection
    - Click-to-select with cross-component linking
    - Log-scale intensity colormap
    - SVG export

    Example:
        heatmap = Heatmap(
            data=peaks_df,
            x_column='retention_time',
            y_column='mass',
            intensity_column='intensity',
            interactivity={
                'spectrum': 'scan_id',
                'peak': 'mass',
            },
            title="Peak Heatmap",
        )
        heatmap(state_manager=state_manager)
    """

    def __init__(
        self,
        data: pl.LazyFrame,
        x_column: str,
        y_column: str,
        intensity_column: str = 'intensity',
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        min_points: int = 20000,
        x_bins: int = 400,
        y_bins: int = 50,
        zoom_identifier: str = 'heatmap_zoom',
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        colorscale: str = 'Portland',
        use_simple_downsample: bool = False,
        **kwargs
    ):
        """
        Initialize the Heatmap component.

        Args:
            data: Polars LazyFrame with heatmap data
            x_column: Name of column for x-axis values
            y_column: Name of column for y-axis values
            intensity_column: Name of column for intensity/color values
            filters: Mapping of identifier names to column names for filtering
            interactivity: Mapping of identifier names to column names for clicks.
                When a point is clicked, sets each identifier to the clicked
                point's value in the corresponding column.
            min_points: Target size for smallest compression level and
                threshold for level selection (default: 20000)
            x_bins: Number of bins along x-axis for downsampling (default: 400)
            y_bins: Number of bins along y-axis for downsampling (default: 50)
            zoom_identifier: State key for storing zoom range (default: 'heatmap_zoom')
            title: Heatmap title displayed above the plot
            x_label: X-axis label (defaults to x_column)
            y_label: Y-axis label (defaults to y_column)
            colorscale: Plotly colorscale name (default: 'Portland')
            use_simple_downsample: If True, use simple top-N downsampling instead
                of spatial binning (doesn't require scipy)
            **kwargs: Additional configuration options
        """
        self._x_column = x_column
        self._y_column = y_column
        self._intensity_column = intensity_column
        self._min_points = min_points
        self._x_bins = x_bins
        self._y_bins = y_bins
        self._zoom_identifier = zoom_identifier
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._colorscale = colorscale
        self._use_simple_downsample = use_simple_downsample

        super().__init__(
            data,
            filters=filters,
            interactivity=interactivity,
            **kwargs
        )

    def _preprocess(self) -> None:
        """
        Preprocess heatmap data by computing multi-resolution levels.

        This is STAGE 1 processing - expensive but only done once at
        component creation. Creates downsampled versions at logarithmically
        spaced sizes for efficient zoom-based rendering.
        """
        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()

        # Compute compression level target sizes
        level_sizes = compute_compression_levels(self._min_points, total)

        # Build levels from largest to smallest, storing smallest first
        self._preprocessed_data['levels'] = []

        if level_sizes:
            current = self._raw_data

            for size in reversed(level_sizes):
                if self._use_simple_downsample:
                    downsampled = downsample_2d_simple(
                        current,
                        max_points=size,
                        intensity_column=self._intensity_column,
                    )
                else:
                    downsampled = downsample_2d(
                        current,
                        max_points=size,
                        x_column=self._x_column,
                        y_column=self._y_column,
                        intensity_column=self._intensity_column,
                        x_bins=self._x_bins,
                        y_bins=self._y_bins,
                    )
                # Insert at beginning (smallest first)
                self._preprocessed_data['levels'].insert(0, downsampled)
                current = downsampled

        # Add full resolution at end
        self._preprocessed_data['levels'].append(self._raw_data)

        # Store config for serialization
        self._preprocessed_data['config'] = {
            'x_column': self._x_column,
            'y_column': self._y_column,
            'intensity_column': self._intensity_column,
            'min_points': self._min_points,
            'zoom_identifier': self._zoom_identifier,
        }

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return 'PlotlyHeatmap'

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return 'heatmapData'

    def _is_no_zoom(self, zoom: Optional[Dict[str, Any]]) -> bool:
        """Check if zoom state represents no zoom (full view)."""
        if zoom is None:
            return True
        x_range = zoom.get('xRange', [-1, -1])
        y_range = zoom.get('yRange', [-1, -1])
        return (
            x_range[0] < 0 and x_range[1] < 0 and
            y_range[0] < 0 and y_range[1] < 0
        )

    def _select_level_for_zoom(
        self,
        zoom: Dict[str, Any],
        state: Dict[str, Any]
    ) -> pl.DataFrame:
        """
        Select appropriate resolution level based on zoom range.

        Iterates from smallest to largest resolution, finding the smallest
        level that has at least min_points in the zoomed view.

        Args:
            zoom: Zoom state with xRange and yRange
            state: Full selection state for applying filters

        Returns:
            Filtered DataFrame at appropriate resolution
        """
        x0, x1 = zoom['xRange']
        y0, y1 = zoom['yRange']

        levels = self._preprocessed_data['levels']
        last_filtered = None

        for level_data in levels:
            # Filter to zoom range
            filtered = level_data.filter(
                (pl.col(self._x_column) >= x0) &
                (pl.col(self._x_column) <= x1) &
                (pl.col(self._y_column) >= y0) &
                (pl.col(self._y_column) <= y1)
            )

            # Apply component filters if any
            if self._filters:
                filtered = filter_and_collect_cached(
                    filtered,
                    self._filters,
                    state,
                )
            else:
                filtered = filtered.collect()

            count = len(filtered)
            last_filtered = filtered

            if count >= self._min_points:
                # This level has enough detail
                if count > self._min_points * 2:
                    # Still too many - downsample
                    if self._use_simple_downsample:
                        return downsample_2d_simple(
                            filtered.lazy(),
                            max_points=self._min_points,
                            intensity_column=self._intensity_column,
                        ).collect()
                    else:
                        return downsample_2d(
                            filtered.lazy(),
                            max_points=self._min_points,
                            x_column=self._x_column,
                            y_column=self._y_column,
                            intensity_column=self._intensity_column,
                            x_bins=self._x_bins,
                            y_bins=self._y_bins,
                        ).collect()
                return filtered

        # Even largest level has fewer points than threshold
        return last_filtered if last_filtered is not None else pl.DataFrame()

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare heatmap data for Vue component.

        Selects appropriate resolution level based on zoom state.
        This is STAGE 2 processing - fast, happens every render.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with heatmapData key containing the data
        """
        zoom = state.get(self._zoom_identifier)

        if self._is_no_zoom(zoom):
            # No zoom - use smallest level
            data = self._preprocessed_data['levels'][0]

            # Apply filters if any
            if self._filters:
                df = filter_and_collect_cached(
                    data,
                    self._filters,
                    state,
                )
            else:
                df = data.collect()
        else:
            # Zoomed - select appropriate level
            df = self._select_level_for_zoom(zoom, state)

        # Build columns to include
        columns_to_send = [
            self._x_column,
            self._y_column,
            self._intensity_column,
        ]

        # Include columns needed for interactivity
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_send and col in df.columns:
                    columns_to_send.append(col)

        # Select only needed columns and convert to list of dicts
        df_selected = df.select([c for c in columns_to_send if c in df.columns])
        heatmap_data = df_selected.to_dicts()

        return {
            'heatmapData': heatmap_data,
        }

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all heatmap configuration for Vue
        """
        args: Dict[str, Any] = {
            'componentType': self._get_vue_component_name(),
            'xColumn': self._x_column,
            'yColumn': self._y_column,
            'intensityColumn': self._intensity_column,
            'xLabel': self._x_label,
            'yLabel': self._y_label,
            'colorscale': self._colorscale,
            'zoomIdentifier': self._zoom_identifier,
            'interactivity': self._interactivity,
        }

        if self._title:
            args['title'] = self._title

        # Add any extra config options
        args.update(self._config)

        return args

    def with_styling(
        self,
        colorscale: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> 'Heatmap':
        """
        Update heatmap styling.

        Args:
            colorscale: Plotly colorscale name
            x_label: X-axis label
            y_label: Y-axis label

        Returns:
            Self for method chaining
        """
        if colorscale is not None:
            self._colorscale = colorscale
        if x_label is not None:
            self._x_label = x_label
        if y_label is not None:
            self._y_label = y_label
        return self
