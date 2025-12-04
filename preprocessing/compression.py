"""Compression utilities for large 2D datasets (heatmaps).

This module provides functions for multi-resolution downsampling of 2D scatter
data, enabling efficient visualization of datasets with millions of points.
"""

from typing import List, Optional, Union

import numpy as np
import polars as pl

try:
    from scipy.stats import binned_statistic_2d
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def compute_compression_levels(min_size: int, total: int) -> List[int]:
    """
    Compute logarithmically-spaced compression level target sizes.

    Given a minimum target size and total data size, computes intermediate
    compression levels at powers of 10.

    Args:
        min_size: Minimum/smallest compression level size (e.g., 20000)
        total: Total number of data points

    Returns:
        List of target sizes, smallest first. Empty if total <= min_size.

    Examples:
        >>> compute_compression_levels(20000, 1_000_000)
        [20000, 200000]
        >>> compute_compression_levels(20000, 50_000)
        [20000]
        >>> compute_compression_levels(20000, 15_000)
        []
    """
    if total <= min_size:
        return []

    # Compute powers of 10 between min and total
    min_power = int(np.log10(min_size))
    max_power = int(np.log10(total))

    if min_power >= max_power:
        return []

    # Generate levels at each power of 10, scaled by the fractional part
    scale_factor = int(10 ** (np.log10(min_size) % 1))
    levels = np.logspace(
        min_power,
        max_power,
        max_power - min_power + 1,
        dtype='int'
    ) * scale_factor

    # Filter out levels >= total
    levels = levels[levels < total]

    return levels.tolist()


def downsample_2d(
    data: Union[pl.LazyFrame, pl.DataFrame],
    max_points: int = 20000,
    x_column: str = 'x',
    y_column: str = 'y',
    intensity_column: str = 'intensity',
    x_bins: int = 400,
    y_bins: int = 50,
) -> pl.LazyFrame:
    """
    Downsample 2D scatter data while preserving high-intensity points.

    Uses 2D binning to spatially partition data, then keeps the top N
    highest-intensity points per bin. This preserves visually important
    features (peaks) while reducing total point count.

    Args:
        data: Input data as Polars LazyFrame or DataFrame
        max_points: Maximum number of points to keep
        x_column: Name of x-axis column
        y_column: Name of y-axis column
        intensity_column: Name of intensity/value column for ranking
        x_bins: Number of bins along x-axis
        y_bins: Number of bins along y-axis

    Returns:
        Downsampled data as Polars LazyFrame

    Raises:
        ImportError: If scipy is not installed
        ValueError: If x_bins * y_bins > max_points
    """
    if not HAS_SCIPY:
        raise ImportError(
            "scipy is required for downsample_2d. "
            "Install with: pip install scipy"
        )

    if (x_bins * y_bins) > max_points:
        raise ValueError(
            f"Number of bins ({x_bins * y_bins}) exceeds max_points ({max_points}). "
            "Reduce x_bins or y_bins."
        )

    # Ensure we're working with a LazyFrame
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Sort by intensity (descending) to prioritize high-intensity points
    sorted_data = (
        data
        .sort([x_column, intensity_column], descending=[False, True])
        .with_columns([
            pl.int_range(pl.len()).over(x_column).alias('_rank')
        ])
        .sort(['_rank', intensity_column], descending=[False, True])
    )

    # Collect for scipy binning (requires numpy arrays)
    collected = sorted_data.collect()

    total_count = len(collected)
    if total_count <= max_points:
        # No downsampling needed
        return collected.drop('_rank').lazy()

    # Extract arrays for scipy
    x_array = collected[x_column].to_numpy()
    y_array = collected[y_column].to_numpy()
    intensity_array = collected[intensity_column].to_numpy()

    # Compute 2D bins
    count, _, _, mapping = binned_statistic_2d(
        x_array, y_array, intensity_array, 'count',
        bins=[x_bins, y_bins],
        expand_binnumbers=True
    )

    # Add bin indices to dataframe
    binned_data = (
        collected.lazy()
        .with_columns([
            pl.Series('_x_bin', mapping[0] - 1),  # scipy uses 1-based indexing
            pl.Series('_y_bin', mapping[1] - 1)
        ])
    )

    # Compute max peaks per bin to stay under limit
    counted_peaks = 0
    max_peaks_per_bin = -1
    new_count = 0

    while (counted_peaks + new_count) < max_points:
        max_peaks_per_bin += 1
        counted_peaks += new_count
        new_count = np.sum(count.flatten() >= (max_peaks_per_bin + 1))

        if counted_peaks >= total_count:
            break

    # Keep top N peaks per bin
    result = (
        binned_data
        .group_by(['_x_bin', '_y_bin'])
        .head(max_peaks_per_bin)
        .sort(intensity_column)
        .drop(['_rank', '_x_bin', '_y_bin'])
    )

    return result


def downsample_2d_simple(
    data: Union[pl.LazyFrame, pl.DataFrame],
    max_points: int = 20000,
    intensity_column: str = 'intensity',
) -> pl.LazyFrame:
    """
    Simple downsampling by keeping highest-intensity points.

    A simpler alternative to downsample_2d that doesn't require scipy.
    Less spatially aware but still preserves important peaks.

    Args:
        data: Input data as Polars LazyFrame or DataFrame
        max_points: Maximum number of points to keep
        intensity_column: Name of intensity column for ranking

    Returns:
        Downsampled data as Polars LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return (
        data
        .sort(intensity_column, descending=True)
        .head(max_points)
    )
