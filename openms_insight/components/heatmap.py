"""Heatmap component using Plotly scattergl."""

from typing import Any, Dict, List, Optional, Tuple

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
        data_path: Optional[str] = None,
        intensity_column: str = 'intensity',
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
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
        categorical_filters: Optional[List[str]] = None,
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
            data_path: Path to parquet file (preferred for large datasets).
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
            categorical_filters: List of filter identifiers that should have
                per-value compression levels. This ensures constant point counts
                are sent to the client regardless of filter selection. Should be
                used for filters with a small number of unique values (<20).
                Example: ['im_dimension'] for ion mobility filtering.
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
        self._categorical_filters = categorical_filters or []

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
            x_column=x_column,
            y_column=y_column,
            intensity_column=intensity_column,
            min_points=min_points,
            x_bins=x_bins,
            y_bins=y_bins,
            zoom_identifier=zoom_identifier,
            title=title,
            x_label=x_label,
            y_label=y_label,
            colorscale=colorscale,
            use_simple_downsample=use_simple_downsample,
            use_streaming=use_streaming,
            categorical_filters=categorical_filters,
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
            'categorical_filters': sorted(self._categorical_filters),
        }

    def get_state_dependencies(self) -> list:
        """
        Return list of state keys that affect this component's data.

        Heatmaps depend on both filters (like other components) and
        the zoom state, which determines which resolution level is used.

        Returns:
            List of state identifier keys including zoom_identifier
        """
        deps = list(self._filters.keys()) if self._filters else []
        deps.append(self._zoom_identifier)
        return deps

    def _preprocess(self) -> None:
        """
        Preprocess heatmap data by computing multi-resolution levels.

        This is STAGE 1 processing. In streaming mode (default), levels stay
        as lazy LazyFrames and are only collected at render time. In non-streaming
        mode, levels are eagerly computed for faster rendering but higher memory.

        If categorical_filters is specified, creates separate compression levels
        for each unique value of those filters, ensuring constant point counts
        regardless of filter selection.
        """
        if self._categorical_filters:
            self._preprocess_with_categorical_filters()
        elif self._use_streaming:
            self._preprocess_streaming()
        else:
            self._preprocess_eager()

    def _preprocess_with_categorical_filters(self) -> None:
        """
        Preprocess with per-filter-value compression levels.

        For each unique value of each categorical filter, creates separate
        compression levels. This ensures that when a filter is applied at
        render time, the resulting data has ~min_points regardless of the
        filter value selected.

        Example: For im_dimension with values [0, 1, 2, 3], creates:
        - cat_level_im_dimension_0_0: 20K points with im_id=0
        - cat_level_im_dimension_0_1: 20K points with im_id=1
        - etc.
        """
        import sys

        # Get data ranges (for the full dataset)
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

        # Store metadata about categorical filters
        self._preprocessed_data['has_categorical_filters'] = True
        self._preprocessed_data['categorical_filter_values'] = {}

        # Process each categorical filter
        for filter_id in self._categorical_filters:
            if filter_id not in self._filters:
                print(f"[HEATMAP] Warning: categorical_filter '{filter_id}' not in filters, skipping", file=sys.stderr)
                continue

            column_name = self._filters[filter_id]

            # Get unique values for this filter
            unique_values = (
                self._raw_data
                .select(pl.col(column_name))
                .unique()
                .collect()
                .to_series()
                .to_list()
            )
            unique_values = sorted([v for v in unique_values if v is not None and v >= 0])

            print(f"[HEATMAP] Categorical filter '{filter_id}' ({column_name}): {len(unique_values)} unique values", file=sys.stderr)

            self._preprocessed_data['categorical_filter_values'][filter_id] = unique_values

            # Create compression levels for each filter value
            for filter_value in unique_values:
                # Filter data to this value
                filtered_data = self._raw_data.filter(pl.col(column_name) == filter_value)
                filtered_total = filtered_data.select(pl.len()).collect().item()

                # Compute level sizes for this filtered subset
                level_sizes = compute_compression_levels(self._min_points, filtered_total)

                print(f"[HEATMAP]   Value {filter_value}: {filtered_total:,} pts → levels {level_sizes}", file=sys.stderr)

                # Store level sizes for this filter value
                self._preprocessed_data[f'cat_level_sizes_{filter_id}_{filter_value}'] = level_sizes

                # Build each compressed level
                for level_idx, target_size in enumerate(level_sizes):
                    # If target size equals total, skip downsampling - use all data
                    if target_size >= filtered_total:
                        level = filtered_data
                    elif self._use_simple_downsample:
                        level = downsample_2d_simple(
                            filtered_data,
                            max_points=target_size,
                            intensity_column=self._intensity_column,
                        )
                    else:
                        level = downsample_2d_streaming(
                            filtered_data,
                            max_points=target_size,
                            x_column=self._x_column,
                            y_column=self._y_column,
                            intensity_column=self._intensity_column,
                            x_bins=self._x_bins,
                            y_bins=self._y_bins,
                            x_range=x_range,
                            y_range=y_range,
                        )

                    # Store LazyFrame for streaming to disk
                    level_key = f'cat_level_{filter_id}_{filter_value}_{level_idx}'
                    self._preprocessed_data[level_key] = level  # Keep lazy

                # Add full resolution as final level (for zoom fallback)
                num_compressed = len(level_sizes)
                full_res_key = f'cat_level_{filter_id}_{filter_value}_{num_compressed}'
                self._preprocessed_data[full_res_key] = filtered_data
                self._preprocessed_data[f'cat_num_levels_{filter_id}_{filter_value}'] = num_compressed + 1

        # Also create global levels for when no categorical filter is selected
        # (fallback to standard behavior)
        level_sizes = compute_compression_levels(self._min_points, total)
        self._preprocessed_data['level_sizes'] = level_sizes

        for i, size in enumerate(level_sizes):
            # If target size equals total, skip downsampling - use all data
            if size >= total:
                level = self._raw_data
            elif self._use_simple_downsample:
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
            self._preprocessed_data[f'level_{i}'] = level  # Keep lazy

        # Add full resolution as final level (for zoom fallback)
        num_compressed = len(level_sizes)
        self._preprocessed_data[f'level_{num_compressed}'] = self._raw_data
        self._preprocessed_data['num_levels'] = num_compressed + 1

    def _preprocess_streaming(self) -> None:
        """
        Streaming preprocessing - levels stay lazy through caching.

        Builds lazy query plans that are streamed to disk via sink_parquet().
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
            # If target size equals total, skip downsampling - use all data
            if size >= total:
                level = self._raw_data
            elif self._use_simple_downsample:
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
            # Store LazyFrame for streaming to disk
            # Base class will use sink_parquet() to stream without full materialization
            self._preprocessed_data[f'level_{i}'] = level  # Keep lazy

        # Add full resolution as final level (for zoom fallback)
        num_compressed = len(level_sizes)
        self._preprocessed_data[f'level_{num_compressed}'] = self._raw_data

        # Store number of levels for reconstruction (includes full resolution)
        self._preprocessed_data['num_levels'] = num_compressed + 1

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
                # If target size equals total, skip downsampling - use all data
                if size >= total:
                    downsampled = current
                elif self._use_simple_downsample:
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
                # Store LazyFrame for streaming to disk
                level_idx = len(level_sizes) - 1 - i
                if isinstance(downsampled, pl.LazyFrame):
                    self._preprocessed_data[f'level_{level_idx}'] = downsampled  # Keep lazy
                else:
                    # DataFrame from downsample_2d - convert back to lazy
                    self._preprocessed_data[f'level_{level_idx}'] = downsampled.lazy()
                current = downsampled

        # Add full resolution as final level (for zoom fallback)
        num_compressed = len(level_sizes)
        self._preprocessed_data[f'level_{num_compressed}'] = self._raw_data

        # Store number of levels for reconstruction (includes full resolution)
        self._preprocessed_data['num_levels'] = num_compressed + 1

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

        return levels

    def _get_categorical_levels(
        self,
        filter_id: str,
        filter_value: Any,
    ) -> Tuple[list, Optional[pl.LazyFrame]]:
        """
        Get compression levels for a specific categorical filter value.

        Args:
            filter_id: The filter identifier (e.g., 'im_dimension')
            filter_value: The filter value to get levels for (e.g., 0)

        Returns:
            Tuple of (levels list, filtered raw data for full resolution)
            Returns ([], None) if no categorical levels exist for this filter
        """
        # Check if we have categorical levels for this filter/value
        num_levels_key = f'cat_num_levels_{filter_id}_{filter_value}'
        num_levels = self._preprocessed_data.get(num_levels_key, 0)

        if num_levels == 0:
            return [], None

        levels = []
        for i in range(num_levels):
            level_key = f'cat_level_{filter_id}_{filter_value}_{i}'
            level_data = self._preprocessed_data.get(level_key)
            if level_data is not None:
                levels.append(level_data)

        return levels, None  # Full resolution included in cached levels

    def _get_levels_for_state(self, state: Dict[str, Any]) -> Tuple[list, Optional[pl.LazyFrame]]:
        """
        Get appropriate compression levels based on current filter state.

        If categorical_filters are configured and a matching filter value is
        selected in state, returns the per-value levels. Otherwise returns
        the global levels.

        Args:
            state: Current selection state

        Returns:
            Tuple of (levels list, raw data for full resolution)
        """
        # Check if we have categorical filters and a selected value
        if self._preprocessed_data.get('has_categorical_filters'):
            cat_filter_values = self._preprocessed_data.get('categorical_filter_values', {})

            for filter_id in self._categorical_filters:
                if filter_id not in cat_filter_values:
                    continue

                selected_value = state.get(filter_id)
                if selected_value is None:
                    continue

                # Convert float to int if needed (JS numbers come as floats)
                if isinstance(selected_value, float) and selected_value.is_integer():
                    selected_value = int(selected_value)

                # Check if this value has per-filter levels
                if selected_value in cat_filter_values[filter_id]:
                    levels, filtered_raw = self._get_categorical_levels(filter_id, selected_value)
                    if levels:
                        return levels, filtered_raw

        # Fall back to global levels
        return self._get_levels(), self._raw_data

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
        state: Dict[str, Any],
        levels: list,
        filtered_raw: Optional[pl.LazyFrame],
        non_categorical_filters: Dict[str, str],
    ) -> pl.DataFrame:
        """
        Select appropriate resolution level based on zoom range.

        Iterates from smallest to largest resolution, finding the smallest
        level that has at least min_points in the zoomed view.

        Args:
            zoom: Zoom state with xRange and yRange
            state: Full selection state for applying filters
            levels: List of compression levels to use
            filtered_raw: Filtered raw data for full resolution (optional)
            non_categorical_filters: Filters to apply (excluding categorical ones)

        Returns:
            Filtered Polars DataFrame at appropriate resolution
        """
        import sys
        x0, x1 = zoom['xRange']
        y0, y1 = zoom['yRange']

        # Add raw data as final level if available
        all_levels = list(levels)
        if filtered_raw is not None:
            all_levels.append(filtered_raw)

        last_filtered = None

        for level_idx, level_data in enumerate(all_levels):
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

            # Apply non-categorical filters if any
            if non_categorical_filters:
                # filter_and_collect_cached returns (pandas DataFrame, hash)
                # We need Polars DataFrame for further processing
                df_pandas, _ = filter_and_collect_cached(
                    filtered_lazy,
                    non_categorical_filters,
                    state,
                    filter_defaults=self._filter_defaults,
                )
                filtered = pl.from_pandas(df_pandas)
            else:
                filtered = filtered_lazy.collect()

            count = len(filtered)
            last_filtered = filtered
            print(f"[HEATMAP] Level {level_idx}: {count} pts in zoom range", file=sys.stderr)

            if count >= self._min_points:
                # This level has enough detail
                if count > self._min_points:
                    # Over limit - downsample to stay at/under max
                    # Use ZOOM range for binning (not global) to avoid sparse bins
                    zoom_x_range = (x0, x1)
                    zoom_y_range = (y0, y1)
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
                                x_range=zoom_x_range,
                                y_range=zoom_y_range,
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
        If categorical_filters are configured, uses per-filter-value levels
        to ensure constant point counts regardless of filter selection.

        Returns pandas DataFrame for efficient Arrow serialization.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with heatmapData (pandas DataFrame) and _hash for change detection
        """
        import sys
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

        # Get levels based on current state (may use per-filter levels)
        levels, filtered_raw = self._get_levels_for_state(state)
        level_sizes = [len(l) if isinstance(l, pl.DataFrame) else '?' for l in levels]

        # Determine which filters still need to be applied at render time
        # (filters not in categorical_filters need runtime application)
        non_categorical_filters = {}
        if self._filters:
            for filter_id, column in self._filters.items():
                if filter_id not in self._categorical_filters:
                    non_categorical_filters[filter_id] = column

        if self._is_no_zoom(zoom):
            # No zoom - use smallest level
            if not levels:
                # No levels available
                print(f"[HEATMAP] No levels available", file=sys.stderr)
                return {'heatmapData': pl.DataFrame().to_pandas(), '_hash': ''}

            data = levels[0]
            using_cat = self._preprocessed_data.get('has_categorical_filters', False)
            print(f"[HEATMAP] No zoom → level 0 ({level_sizes[0]} pts), levels={level_sizes}, categorical={using_cat}", file=sys.stderr)

            # Ensure we have a LazyFrame
            if isinstance(data, pl.DataFrame):
                data = data.lazy()

            # Apply non-categorical filters if any - returns (pandas DataFrame, hash)
            if non_categorical_filters:
                df_pandas, data_hash = filter_and_collect_cached(
                    data,
                    non_categorical_filters,
                    state,
                    columns=columns_to_select,
                    filter_defaults=self._filter_defaults,
                )
                # Sort by intensity ascending so high-intensity points are drawn on top
                df_pandas = df_pandas.sort_values(self._intensity_column).reset_index(drop=True)
            else:
                # No filters to apply - levels already filtered by categorical filter
                schema_names = data.collect_schema().names()
                available_cols = [c for c in columns_to_select if c in schema_names]
                df_polars = data.select(available_cols).collect()
                # Sort by intensity ascending so high-intensity points are drawn on top
                df_polars = df_polars.sort(self._intensity_column)
                data_hash = compute_dataframe_hash(df_polars)
                df_pandas = df_polars.to_pandas()
        else:
            # Zoomed - select appropriate level
            print(f"[HEATMAP] Zoom {zoom} → selecting level...", file=sys.stderr)
            df_polars = self._select_level_for_zoom(
                zoom, state, levels, filtered_raw, non_categorical_filters
            )
            # Select only needed columns
            available_cols = [c for c in columns_to_select if c in df_polars.columns]
            df_polars = df_polars.select(available_cols)
            # Sort by intensity ascending so high-intensity points are drawn on top
            df_polars = df_polars.sort(self._intensity_column)
            print(f"[HEATMAP] Selected {len(df_polars)} pts for zoom, levels={level_sizes}", file=sys.stderr)
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
