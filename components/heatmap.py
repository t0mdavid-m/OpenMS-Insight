"""Heatmap component using Plotly scattergl."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import polars as pl
import streamlit as st

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

# Default cache directory for heatmap levels
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "streamlit_vue_components" / "heatmap_levels"


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
        use_streaming: bool = True,
        cache_dir: Optional[Union[str, Path]] = None,
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
            use_streaming: If True (default), use streaming downsampling that
                stays lazy until render time. Reduces memory on init.
            cache_dir: Directory for caching computed levels to disk. Levels are
                written after first computation and loaded on subsequent runs.
                Set to None to disable disk caching. Default: ~/.cache/streamlit_vue_components/heatmap_levels
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
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR

        super().__init__(
            data,
            filters=filters,
            interactivity=interactivity,
            **kwargs
        )

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

        # Store config for serialization
        self._preprocessed_data['config'] = {
            'x_column': self._x_column,
            'y_column': self._y_column,
            'intensity_column': self._intensity_column,
            'min_points': self._min_points,
            'zoom_identifier': self._zoom_identifier,
        }

    def _get_cache_path(self, level_index: int) -> Path:
        """Get the cache file path for a specific level."""
        return self._cache_dir / f"level_{level_index}.parquet"

    def _get_metadata_path(self) -> Path:
        """Get the metadata file path."""
        return self._cache_dir / "metadata.json"

    def _clear_cache(self) -> None:
        """Clear the disk cache directory."""
        if self._cache_dir.exists():
            for f in self._cache_dir.glob("*.parquet"):
                f.unlink()
            metadata_path = self._get_metadata_path()
            if metadata_path.exists():
                metadata_path.unlink()

    def _load_cached_levels(self) -> bool:
        """
        Try to load levels from disk cache.

        Returns:
            True if cache was loaded successfully, False otherwise.
        """
        metadata_path = self._get_metadata_path()
        if not metadata_path.exists():
            return False

        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            # Check if cache is valid (same configuration)
            if (metadata.get('min_points') != self._min_points or
                metadata.get('x_bins') != self._x_bins or
                metadata.get('y_bins') != self._y_bins or
                metadata.get('x_column') != self._x_column or
                metadata.get('y_column') != self._y_column or
                metadata.get('intensity_column') != self._intensity_column):
                return False

            level_sizes = metadata.get('level_sizes', [])
            x_range = tuple(metadata.get('x_range', []))
            y_range = tuple(metadata.get('y_range', []))
            total = metadata.get('total', 0)

            # Load levels from parquet files
            levels = []
            for i in range(len(level_sizes)):
                cache_path = self._get_cache_path(i)
                if not cache_path.exists():
                    return False
                # Load as LazyFrame for consistency
                levels.append(pl.scan_parquet(cache_path))

            # Store loaded data
            self._preprocessed_data['levels'] = levels
            # Add full resolution at end (not cached)
            self._preprocessed_data['levels'].append(self._raw_data)
            self._preprocessed_data['x_range'] = x_range
            self._preprocessed_data['y_range'] = y_range
            self._preprocessed_data['total'] = total
            self._preprocessed_data['level_sizes'] = level_sizes

            return True
        except (json.JSONDecodeError, KeyError, OSError):
            return False

    def _save_levels_to_cache(self) -> None:
        """Save computed levels to disk cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Save each level (excluding full resolution which is last)
        levels = self._preprocessed_data.get('levels', [])
        level_sizes = self._preprocessed_data.get('level_sizes', [])

        for i, level in enumerate(levels[:-1]):  # Skip full resolution
            cache_path = self._get_cache_path(i)
            # Collect if lazy and save
            if isinstance(level, pl.LazyFrame):
                level.collect().write_parquet(cache_path)
            else:
                level.write_parquet(cache_path)

        # Save metadata
        metadata = {
            'min_points': self._min_points,
            'x_bins': self._x_bins,
            'y_bins': self._y_bins,
            'x_column': self._x_column,
            'y_column': self._y_column,
            'intensity_column': self._intensity_column,
            'level_sizes': level_sizes,
            'x_range': list(self._preprocessed_data.get('x_range', ())),
            'y_range': list(self._preprocessed_data.get('y_range', ())),
            'total': self._preprocessed_data.get('total', 0),
        }

        with open(self._get_metadata_path(), 'w') as f:
            json.dump(metadata, f)

    def _preprocess_streaming(self) -> None:
        """
        Streaming preprocessing - levels stay lazy until render.

        Attempts to load from disk cache first. If not available,
        builds lazy query plans and saves to cache on first collection.
        """
        # Try loading from cache first
        if self._load_cached_levels():
            return

        # Clear any stale cache
        self._clear_cache()

        # Get data ranges (minimal collect - just 4 values)
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data['x_range'] = x_range
        self._preprocessed_data['y_range'] = y_range

        # Estimate total from schema if possible, otherwise use a scan
        # For parquet files this is very fast (metadata only)
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data['total'] = total

        # Compute target sizes for levels
        level_sizes = compute_compression_levels(self._min_points, total)
        self._preprocessed_data['level_sizes'] = level_sizes

        # Build lazy query plans for each level (NO collection here!)
        self._preprocessed_data['levels'] = []

        for size in level_sizes:
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
            self._preprocessed_data['levels'].append(level)

        # Add full resolution at end
        self._preprocessed_data['levels'].append(self._raw_data)

        # Save levels to cache (this collects them once)
        self._save_levels_to_cache()

        # Replace lazy levels with cached parquet scans for future reads
        for i in range(len(level_sizes)):
            cache_path = self._get_cache_path(i)
            if cache_path.exists():
                self._preprocessed_data['levels'][i] = pl.scan_parquet(cache_path)

    def _preprocess_eager(self) -> None:
        """
        Eager preprocessing - levels are computed upfront.

        Uses more memory at init but faster rendering. Uses scipy-based
        downsampling for better spatial distribution.
        """
        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data['total'] = total

        # Compute compression level target sizes
        level_sizes = compute_compression_levels(self._min_points, total)
        self._preprocessed_data['level_sizes'] = level_sizes

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

        levels = self._preprocessed_data['levels']
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
                    if self._use_streaming:
                        # Use streaming downsample
                        x_range = self._preprocessed_data.get('x_range')
                        y_range = self._preprocessed_data.get('y_range')
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
                    elif self._use_simple_downsample:
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
            data = self._preprocessed_data['levels'][0]

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
