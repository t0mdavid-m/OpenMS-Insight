"""
Tests for compression.py downsampling functions.
"""

import polars as pl
import pytest

from openms_insight.preprocessing.compression import (
    downsample_2d,
    downsample_2d_simple,
    downsample_2d_streaming,
)


def _binned_grid_data() -> pl.LazyFrame:
    """Deterministic 10x10-bin grid for per-bin keep-order assertions.

    Each spatial bin (on a 0..100 grid, bin width 10) holds 5 points with
    well-separated intensities ``{100, 80, 60, 40, 20} + (x_bin + y_bin)``.
    The per-bin offset makes every point's intensity unique across the whole
    frame, and the within-bin coordinates are jittered so no two points share
    identical (x, y) — both properties keep the assertions unambiguous.
    """
    rows = []
    for x_bin in range(10):
        for y_bin in range(10):
            for k, intensity in enumerate([100, 80, 60, 40, 20]):
                rows.append(
                    {
                        "x": x_bin * 10.0 + 1.0 + k * 0.3,
                        "y": y_bin * 10.0 + 1.0 + k * 0.3,
                        "intensity": float(intensity + x_bin + y_bin),
                    }
                )
    return pl.LazyFrame(rows)


def _bin_intensities(result: pl.DataFrame, x_bin: int, y_bin: int) -> list:
    """Sorted intensities of the kept points falling in grid bin (x_bin, y_bin)."""
    cell = result.filter(
        (pl.col("x") >= x_bin * 10.0)
        & (pl.col("x") < (x_bin + 1) * 10.0)
        & (pl.col("y") >= y_bin * 10.0)
        & (pl.col("y") < (y_bin + 1) * 10.0)
    )
    return sorted(cell["intensity"].to_list())


class TestDownsample2dEagerDescending:
    """Regression tests for the eager scipy-binning ``downsample_2d`` path.

    Guards finding ``downsample_2d`` previously had no ``descending`` parameter:
    the eager Heatmap strategy called ``downsample_2d(..., descending=...)`` and
    crashed with ``TypeError``, and even once it accepted the kwarg it had to
    honor ``low_values_on_top`` (descending=False keeps LOWEST per bin). The
    existing suite only exercised the streaming/simple paths, so neither was
    caught. Mirrors the streaming cascading-accuracy tests, but on the eager
    path. scipy is a soft dependency of ``downsample_2d``; skip if unavailable.
    """

    def test_eager_accepts_descending_kwarg_without_error(self):
        """The regression itself: passing ``descending=`` must not raise.

        Before the fix, ``downsample_2d`` had no ``descending`` parameter, so
        this call raised ``TypeError: ... unexpected keyword argument
        'descending'`` and the whole eager strategy was unusable.
        """
        pytest.importorskip("scipy")
        data = _binned_grid_data()

        # Must not raise for either order.
        for descending in (True, False):
            result = downsample_2d(
                data,
                max_points=300,
                x_column="x",
                y_column="y",
                intensity_column="intensity",
                x_bins=10,
                y_bins=10,
                descending=descending,
            ).collect()
            # Downsampling actually happened (500 raw -> 2 points/bin = 200).
            assert 0 < len(result) < 500
            assert result["intensity"].null_count() == 0

    def test_eager_descending_true_keeps_high_per_bin(self):
        """descending=True keeps the highest-intensity points per spatial bin."""
        pytest.importorskip("scipy")
        data = _binned_grid_data()

        result = downsample_2d(
            data,
            max_points=300,  # -> 2 points per bin (the two brightest)
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            descending=True,
        ).collect()

        for x_bin in range(10):
            for y_bin in range(10):
                offset = x_bin + y_bin
                # Two highest intensities for this bin: 100+offset, 80+offset.
                assert _bin_intensities(result, x_bin, y_bin) == sorted(
                    [100.0 + offset, 80.0 + offset]
                ), f"bin ({x_bin}, {y_bin}) did not keep the two highest points"

    def test_eager_descending_false_keeps_low_per_bin(self):
        """descending=False (low_values_on_top) keeps LOWEST points per bin."""
        pytest.importorskip("scipy")
        data = _binned_grid_data()

        result = downsample_2d(
            data,
            max_points=300,  # -> 2 points per bin (the two dimmest)
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            descending=False,
        ).collect()

        for x_bin in range(10):
            for y_bin in range(10):
                offset = x_bin + y_bin
                # Two lowest intensities for this bin: 20+offset, 40+offset.
                assert _bin_intensities(result, x_bin, y_bin) == sorted(
                    [20.0 + offset, 40.0 + offset]
                ), f"bin ({x_bin}, {y_bin}) did not keep the two lowest points"

    def test_eager_descending_flips_which_points_survive(self):
        """High vs low selection are genuinely different (mean separation)."""
        pytest.importorskip("scipy")
        data = _binned_grid_data()

        kept_high = downsample_2d(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            descending=True,
        ).collect()
        kept_low = downsample_2d(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            descending=False,
        ).collect()

        assert len(kept_high) == len(kept_low)
        # The high-selection mean must clearly exceed the low-selection mean.
        assert kept_high["intensity"].mean() > kept_low["intensity"].mean()

    def test_eager_default_is_descending_true(self):
        """Omitting ``descending`` preserves the original high-keeping default."""
        pytest.importorskip("scipy")
        data = _binned_grid_data()

        default = downsample_2d(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
        ).collect()
        explicit_high = downsample_2d(
            data,
            max_points=300,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=10,
            y_bins=10,
            descending=True,
        ).collect()

        assert sorted(default["intensity"].to_list()) == sorted(
            explicit_high["intensity"].to_list()
        )


class TestDownsampleDescendingParameter:
    """Test descending parameter in downsampling functions."""

    def test_simple_descending_true_keeps_high(self):
        """descending=True keeps highest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity", descending=True
        ).collect()

        intensities = result["intensity"].to_list()
        assert 500 in intensities
        assert 400 in intensities
        assert 300 in intensities

    def test_simple_descending_false_keeps_low(self):
        """descending=False keeps lowest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity", descending=False
        ).collect()

        intensities = result["intensity"].to_list()
        assert 100 in intensities
        assert 200 in intensities
        assert 300 in intensities

    def test_simple_default_is_descending_true(self):
        """Default behavior (no descending arg) keeps highest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity"
        ).collect()

        intensities = result["intensity"].to_list()
        # Default should keep highest
        assert 500 in intensities
        assert 400 in intensities
        assert 300 in intensities

    def test_streaming_descending_true_keeps_high(self):
        """descending=True keeps highest values in streaming mode."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
            descending=True,
        ).collect()

        intensities = result["intensity"].to_list()
        # Should keep highest values
        assert 500.0 in intensities
        assert 400.0 in intensities
        assert 300.0 in intensities

    def test_streaming_descending_false_keeps_low(self):
        """descending=False keeps lowest values in streaming mode."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
            descending=False,
        ).collect()

        intensities = result["intensity"].to_list()
        # Should keep lowest values
        assert 100.0 in intensities
        assert 200.0 in intensities
        assert 300.0 in intensities

    def test_streaming_default_is_descending_true(self):
        """Default behavior (no descending arg) keeps highest values in streaming."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
        ).collect()

        intensities = result["intensity"].to_list()
        # Default should keep highest
        assert 500.0 in intensities
        assert 400.0 in intensities
        assert 300.0 in intensities
