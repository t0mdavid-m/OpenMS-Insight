"""Heatmap component using Plotly scattergl."""

from typing import Any, Dict, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.compression import (
    compute_compression_levels,
    downsample_2d,
    downsample_2d_simple,
    downsample_2d_streaming,
    get_data_range,
)
from ..preprocessing.filtering import compute_dataframe_hash, filter_and_collect_cached


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
            cache_id="peaks_heatmap",
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

    _component_type: str = "heatmap"

    def __init__(
        self,
        cache_id: str,
        x_column: str,
        y_column: str,
        data: Optional[pl.LazyFrame] = None,
        intensity_column: str = 'intensity',
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        min_points: int = 20000,
        x_bins: int = 400,
        y_bins: int = 50,
        zoom_identifier: str = 'heatmap_zoom',
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        colorscale: str = 'Portland',
        use_simple_downsample: bool = False,
        use_streaming: bool = True,
        **kwargs
    ):
        """
        Initialize the Heatmap component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            x_column: Name of column for x-axis values
            y_column: Name of column for y-axis values
            data: Polars LazyFrame with heatmap data. Optional if cache exists.
            intensity_column: Name of column for intensity/color values
            filters: Mapping of identifier names to column names for filtering
            interactivity: Mapping of identifier names to column names for clicks.
                When a point is clicked, sets each identifier to the clicked
                point's value in the corresponding column.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
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
            use_streaming: If True (default), use streaming downsampling that
                stays lazy until render time. Reduces memory on init.
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
        self._use_streaming = use_streaming

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
            'intensity_column': self._intensity_column,
            'min_points': self._min_points,
            'x_bins': self._x_bins,
            'y_bins': self._y_bins,
            'use_simple_downsample': self._use_simple_downsample,
            'use_streaming': self._use_streaming,
        }

    def _preprocess(self) -> None:
        """
        Preprocess heatmap data by computing multi-resolution levels.

        This is STAGE 1 processing. In streaming mode (default), levels stay
        as lazy LazyFrames and are only collected at render time. In non-streaming
        mode, levels are eagerly computed for faster rendering but higher memory.
        """
        if self._use_streaming:
            self._preprocess_streaming()
        else:
            self._preprocess_eager()

    def _preprocess_streaming(self) -> None:
        """
        Streaming preprocessing - levels stay lazy until render.

        Builds lazy query plans and collects them for caching.
        """
        # Get data ranges (minimal collect - just 4 values)
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data['x_range'] = x_range
        self._preprocessed_data['y_range'] = y_range

        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data['total'] = total

        # Compute target sizes for levels
        level_sizes = compute_compression_levels(self._min_points, total)
        self._preprocessed_data['level_sizes'] = level_sizes

        # Build and collect each level
        self._preprocessed_data['levels'] = []

        for i, size in enumerate(level_sizes):
            if self._use_simple_downsample:
                level = downsample_2d_simple(
                    self._raw_data,
                    max_points=size,
                    intensity_column=self._intensity_column,
                )
            else:
                level = downsample_2d_streaming(
                    self._raw_data,
                    max_points=size,
                    x_column=self._x_column,
                    y_column=self._y_column,
                    intensity_column=self._intensity_column,
                    x_bins=self._x_bins,
                    y_bins=self._y_bins,
                    x_range=x_range,
                    y_range=y_range,
                )
            # Collect and store as DataFrame for caching
            # Base class will serialize these to parquet
            self._preprocessed_data[f'level_{i}'] = level.collect()

        # Store number of levels for reconstruction
        self._preprocessed_data['num_levels'] = len(level_sizes)

    def _preprocess_eager(self) -> None:
        """
        Eager preprocessing - levels are computed upfront.

        Uses more memory at init but faster rendering. Uses scipy-based
        downsampling for better spatial distribution.
        """
        # Get data ranges
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data['x_range'] = x_range
        self._preprocessed_data['y_range'] = y_range

        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data['total'] = total

        # Compute compression level target sizes
        level_sizes = compute_compression_levels(self._min_points, total)
        self._preprocessed_data['level_sizes'] = level_sizes

        # Build levels from largest to smallest
        if level_sizes:
            current = self._raw_data

            for i, size in enumerate(reversed(level_sizes)):
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
                # Collect for caching - store with reversed index
                level_idx = len(level_sizes) - 1 - i
                if isinstance(downsampled, pl.LazyFrame):
                    self._preprocessed_data[f'level_{level_idx}'] = downsampled.collect()
                else:
                    self._preprocessed_data[f'level_{level_idx}'] = downsampled
                current = downsampled

        # Store number of levels for reconstruction
        self._preprocessed_data['num_levels'] = len(level_sizes)

    def _get_levels(self) -> list:
        """
        Get compression levels list for rendering.

        Reconstructs the levels list from preprocessed data,
        adding full resolution at the end.
        """
        num_levels = self._preprocessed_data.get('num_levels', 0)
        levels = []

        for i in range(num_levels):
            level_data = self._preprocessed_data.get(f'level_{i}')
            if level_data is not None:
                levels.append(level_data)

        # Add full resolution at end (if raw data available)
        if self._raw_data is not None:
            levels.append(self._raw_data)

        return levels

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
            Filtered Polars DataFrame at appropriate resolution
        """
        x0, x1 = zoom['xRange']
        y0, y1 = zoom['yRange']

        levels = self._get_levels()
        last_filtered = None

        for level_data in levels:
            # Ensure we have a LazyFrame for filtering
            if isinstance(level_data, pl.DataFrame):
                level_data = level_data.lazy()

            # Filter to zoom range
            filtered_lazy = level_data.filter(
                (pl.col(self._x_column) >= x0) &
                (pl.col(self._x_column) <= x1) &
                (pl.col(self._y_column) >= y0) &
                (pl.col(self._y_column) <= y1)
            )

            # Apply component filters if any
            if self._filters:
                # filter_and_collect_cached returns (pandas DataFrame, hash)
                # We need Polars DataFrame for further processing
                df_pandas, _ = filter_and_collect_cached(
                    filtered_lazy,
                    self._filters,
                    state,
                )
                filtered = pl.from_pandas(df_pandas)
            else:
                filtered = filtered_lazy.collect()

            count = len(filtered)
            last_filtered = filtered

            if count >= self._min_points:
                # This level has enough detail
                if count > self._min_points * 2:
                    # Still too many - downsample further
                    x_range = self._preprocessed_data.get('x_range')
                    y_range = self._preprocessed_data.get('y_range')
                    if self._use_streaming or self._use_simple_downsample:
                        if self._use_simple_downsample:
                            return downsample_2d_simple(
                                filtered.lazy(),
                                max_points=self._min_points,
                                intensity_column=self._intensity_column,
                            ).collect()
                        else:
                            return downsample_2d_streaming(
                                filtered.lazy(),
                                max_points=self._min_points,
                                x_column=self._x_column,
                                y_column=self._y_column,
                                intensity_column=self._intensity_column,
                                x_bins=self._x_bins,
                                y_bins=self._y_bins,
                                x_range=x_range,
                                y_range=y_range,
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
        Returns pandas DataFrame for efficient Arrow serialization.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with heatmapData (pandas DataFrame) and _hash for change detection
        """
        zoom = state.get(self._zoom_identifier)

        # Build columns to select
        columns_to_select = [
            self._x_column,
            self._y_column,
            self._intensity_column,
        ]
        # Include columns needed for interactivity
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include filter columns
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)

        if self._is_no_zoom(zoom):
            # No zoom - use smallest level
            levels = self._get_levels()
            if not levels:
                # No levels available
                return {'heatmapData': pl.DataFrame().to_pandas(), '_hash': ''}

            data = levels[0]

            # Ensure we have a LazyFrame
            if isinstance(data, pl.DataFrame):
                data = data.lazy()

            # Apply filters if any - returns (pandas DataFrame, hash)
            if self._filters:
                df_pandas, data_hash = filter_and_collect_cached(
                    data,
                    self._filters,
                    state,
                    columns=columns_to_select,
                )
            else:
                df_polars = data.select(columns_to_select).collect()
                data_hash = compute_dataframe_hash(df_polars)
                df_pandas = df_polars.to_pandas()
        else:
            # Zoomed - select appropriate level
            df_polars = self._select_level_for_zoom(zoom, state)
            # Select only needed columns
            available_cols = [c for c in columns_to_select if c in df_polars.columns]
            df_polars = df_polars.select(available_cols)
            data_hash = compute_dataframe_hash(df_polars)
            df_pandas = df_polars.to_pandas()

        return {
            'heatmapData': df_pandas,
            '_hash': data_hash,
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
