"""Tests for heatmap cascading preprocessing accuracy.

These tests verify that cascading downsampling (building smaller levels from
larger levels) produces identical results to building each level from raw data.

The key insight: if the downsampling algorithm keeps TOP N highest-intensity
points per spatial bin, then cascading should preserve accuracy because:
- Level 0 already has the highest-intensity points from each bin
- Level 1 selecting from Level 0 gets the same points as selecting from raw
"""

from pathlib import Path

import polars as pl
import pytest

from openms_insight.preprocessing.compression import (
    compute_compression_levels,
    downsample_2d_streaming,
    get_data_range,
)


@pytest.fixture
def deterministic_heatmap_data() -> pl.LazyFrame:
    """Create deterministic heatmap data for testing.

    Creates data where we know exactly which points should survive downsampling:
    - 100 bins (10x10)
    - Each bin has points with intensities 100, 80, 60, 40, 20
    - After downsampling to 1 point per bin, we should have the 100s
    - After downsampling to 2 points per bin, we should have 100s and 80s
    """
    data = []
    point_id = 0

    for x_bin in range(10):
        for y_bin in range(10):
            # Create 5 points per bin with known intensities
            for intensity in [100, 80, 60, 40, 20]:
                data.append(
                    {
                        "x": x_bin * 10.0 + 0.5,  # Center of bin
                        "y": y_bin * 10.0 + 0.5,
                        "intensity": float(intensity + x_bin + y_bin),  # Unique per bin
                        "point_id": point_id,
                    }
                )
                point_id += 1

    return pl.LazyFrame(data)


@pytest.fixture
def large_heatmap_data() -> pl.LazyFrame:
    """Create larger heatmap data for realistic testing."""
    import random

    random.seed(42)

    n_points = 50000
    data = {
        "x": [random.uniform(0, 100) for _ in range(n_points)],
        "y": [random.uniform(0, 100) for _ in range(n_points)],
        "intensity": [random.uniform(1, 10000) for _ in range(n_points)],
    }

    return pl.LazyFrame(data)


class TestDownsampleCascadingAccuracy:
    """Tests that cascading downsampling produces same results as from-scratch."""

    def test_single_cascade_step_equivalence(
        self, deterministic_heatmap_data: pl.LazyFrame
    ):
        """Test that cascading one step produces same results as from-scratch."""
        data = deterministic_heatmap_data
        x_range, y_range = get_data_range(data, "x", "y")

        # From scratch: downsample raw data to 200 points
        from_scratch = downsample_2d_streaming(
            data,
            max_points=200,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Cascading: first downsample to 400, then to 200
        intermediate = downsample_2d_streaming(
            data,
            max_points=400,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )

        cascaded = downsample_2d_streaming(
            intermediate,
            max_points=200,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Should have same points (by intensity values)
        scratch_intensities = set(from_scratch["intensity"].to_list())
        cascade_intensities = set(cascaded["intensity"].to_list())

        assert scratch_intensities == cascade_intensities, (
            f"Intensity mismatch: scratch has {len(scratch_intensities)} unique, "
            f"cascade has {len(cascade_intensities)} unique"
        )

    def test_multi_step_cascade_equivalence(
        self, deterministic_heatmap_data: pl.LazyFrame
    ):
        """Test multiple cascade steps produce same results as from-scratch."""
        data = deterministic_heatmap_data
        x_range, y_range = get_data_range(data, "x", "y")

        # Target: 100 points (1 per bin)
        target_points = 100

        # From scratch
        from_scratch = downsample_2d_streaming(
            data,
            max_points=target_points,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Cascading: 500 -> 300 -> 100
        level_500 = downsample_2d_streaming(
            data,
            max_points=500,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )

        level_300 = downsample_2d_streaming(
            level_500,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )

        cascaded = downsample_2d_streaming(
            level_300,
            max_points=target_points,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Compare intensities
        scratch_intensities = sorted(from_scratch["intensity"].to_list())
        cascade_intensities = sorted(cascaded["intensity"].to_list())

        assert scratch_intensities == cascade_intensities, (
            "Multi-step cascade produced different results than from-scratch"
        )

    def test_cascade_preserves_highest_intensity_per_bin(
        self, deterministic_heatmap_data: pl.LazyFrame
    ):
        """Verify that the highest intensity point per bin survives cascading."""
        data = deterministic_heatmap_data
        x_range, y_range = get_data_range(data, "x", "y")

        # Downsample to 100 points (1 per bin) via cascade
        level_300 = downsample_2d_streaming(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )

        final = downsample_2d_streaming(
            level_300,
            max_points=100,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Each bin should have the point with intensity 100 + x_bin + y_bin
        # Since we have 10x10 bins, check a few
        for x_bin in range(10):
            for y_bin in range(10):
                # Expected max intensity for this bin
                expected_max = 100.0 + x_bin + y_bin

                # Find point in final data that's in this bin
                bin_points = final.filter(
                    (pl.col("x") >= x_bin * 10.0)
                    & (pl.col("x") < (x_bin + 1) * 10.0)
                    & (pl.col("y") >= y_bin * 10.0)
                    & (pl.col("y") < (y_bin + 1) * 10.0)
                )

                assert len(bin_points) >= 1, f"No points in bin ({x_bin}, {y_bin})"

                actual_max = bin_points["intensity"].max()
                assert actual_max == expected_max, (
                    f"Bin ({x_bin}, {y_bin}): expected max {expected_max}, got {actual_max}"
                )

    def test_large_data_cascade_equivalence(self, large_heatmap_data: pl.LazyFrame):
        """Test cascading with larger, more realistic data."""
        data = large_heatmap_data
        x_range, y_range = get_data_range(data, "x", "y")

        # From scratch: downsample to 5000 points
        from_scratch = downsample_2d_streaming(
            data,
            max_points=5000,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=100,
            y_bins=50,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Cascading: 20000 -> 5000
        level_20k = downsample_2d_streaming(
            data,
            max_points=20000,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=100,
            y_bins=50,
            x_range=x_range,
            y_range=y_range,
        )

        cascaded = downsample_2d_streaming(
            level_20k,
            max_points=5000,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=100,
            y_bins=50,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Compare sizes
        assert len(from_scratch) == len(cascaded), (
            f"Size mismatch: scratch={len(from_scratch)}, cascade={len(cascaded)}"
        )

        # Compare intensity distributions (should be very similar)
        scratch_mean = from_scratch["intensity"].mean()
        cascade_mean = cascaded["intensity"].mean()

        # Allow small tolerance due to floating point
        assert abs(scratch_mean - cascade_mean) < 1.0, (
            f"Mean intensity differs: scratch={scratch_mean}, cascade={cascade_mean}"
        )


class TestCompressionLevels:
    """Tests for compression level computation."""

    def test_compression_levels_small_data(self):
        """Small data should return single level with all data."""
        levels = compute_compression_levels(20000, 15000)
        assert levels == [15000]

    def test_compression_levels_medium_data(self):
        """Medium data should return appropriate levels."""
        levels = compute_compression_levels(20000, 50000)
        assert levels == [20000]

    def test_compression_levels_large_data(self):
        """Large data should return multiple levels."""
        levels = compute_compression_levels(20000, 1000000)
        assert 20000 in levels
        assert all(size < 1000000 for size in levels)


class TestCascadeViaParquet:
    """Tests for cascading via parquet (simulating actual heatmap behavior)."""

    def test_cascade_via_parquet_roundtrip(
        self, temp_cache_dir: Path, deterministic_heatmap_data: pl.LazyFrame
    ):
        """Test that cascading through parquet files preserves accuracy."""
        data = deterministic_heatmap_data
        x_range, y_range = get_data_range(data, "x", "y")

        # From scratch
        from_scratch = downsample_2d_streaming(
            data,
            max_points=100,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        ).collect()

        # Cascade via parquet
        level_300_path = temp_cache_dir / "level_300.parquet"
        level_100_path = temp_cache_dir / "level_100.parquet"

        # Build and save level 300
        level_300 = downsample_2d_streaming(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )
        level_300.sink_parquet(level_300_path)

        # Read back and build level 100
        level_300_read = pl.scan_parquet(level_300_path)
        level_100 = downsample_2d_streaming(
            level_300_read,
            max_points=100,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            x_range=x_range,
            y_range=y_range,
        )
        level_100.sink_parquet(level_100_path)

        # Read final result
        cascaded = pl.read_parquet(level_100_path)

        # Compare
        scratch_intensities = sorted(from_scratch["intensity"].to_list())
        cascade_intensities = sorted(cascaded["intensity"].to_list())

        assert scratch_intensities == cascade_intensities, (
            "Cascade via parquet produced different results"
        )
