"""Tests for optimal bin computation in heatmap."""

import pytest

from openms_insight.preprocessing.compression import compute_optimal_bins


class TestComputeOptimalBins:
    """Tests for compute_optimal_bins function."""

    def test_square_aspect_ratio(self):
        """1:1 aspect ratio should give equal x/y bins."""
        x_bins, y_bins = compute_optimal_bins(10000, (0, 100), (0, 100))
        assert x_bins == y_bins
        assert x_bins * y_bins == pytest.approx(10000, rel=0.1)

    def test_wide_aspect_ratio(self):
        """10:1 aspect ratio should give more x bins than y bins."""
        x_bins, y_bins = compute_optimal_bins(10000, (0, 1000), (0, 100))
        assert x_bins > y_bins
        # Should roughly match aspect ratio
        assert x_bins / y_bins == pytest.approx(10, rel=0.5)
        # Product should be close to target
        assert x_bins * y_bins == pytest.approx(10000, rel=0.2)

    def test_tall_aspect_ratio(self):
        """1:10 aspect ratio should give more y bins than x bins."""
        x_bins, y_bins = compute_optimal_bins(10000, (0, 100), (0, 1000))
        assert y_bins > x_bins
        # Should roughly match aspect ratio
        assert y_bins / x_bins == pytest.approx(10, rel=0.5)
        # Product should be close to target
        assert x_bins * y_bins == pytest.approx(10000, rel=0.2)

    def test_different_target_points(self):
        """Different target points should scale bins proportionally."""
        x_bins_10k, y_bins_10k = compute_optimal_bins(10000, (0, 100), (0, 100))
        x_bins_40k, y_bins_40k = compute_optimal_bins(40000, (0, 100), (0, 100))

        # 4x more points should give roughly 2x more bins per dimension
        assert x_bins_40k == pytest.approx(x_bins_10k * 2, rel=0.1)
        assert y_bins_40k == pytest.approx(y_bins_10k * 2, rel=0.1)

    def test_extreme_aspect_ratio_clamped(self):
        """Extreme aspect ratios should be clamped to avoid pathological bins."""
        # 1000:1 aspect - should be clamped to 20:1
        x_bins, y_bins = compute_optimal_bins(10000, (0, 100000), (0, 100))
        # Even with extreme aspect, bins should be reasonable
        assert x_bins >= 1
        assert y_bins >= 1
        # Clamped aspect ratio of 20 means x_bins/y_bins <= 20
        assert x_bins / y_bins <= 25  # Allow some tolerance

    def test_small_target_points(self):
        """Small target should still give at least 1 bin per dimension."""
        x_bins, y_bins = compute_optimal_bins(4, (0, 100), (0, 100))
        assert x_bins >= 1
        assert y_bins >= 1
        assert x_bins == y_bins  # 1:1 aspect

    def test_edge_case_zero_y_span(self):
        """Zero y span should not cause division by zero."""
        x_bins, y_bins = compute_optimal_bins(10000, (0, 100), (50, 50))
        assert x_bins >= 1
        assert y_bins >= 1

    def test_edge_case_zero_x_span(self):
        """Zero x span should not cause division by zero."""
        x_bins, y_bins = compute_optimal_bins(10000, (50, 50), (0, 100))
        assert x_bins >= 1
        assert y_bins >= 1

    def test_negative_ranges(self):
        """Negative value ranges should work correctly."""
        x_bins, y_bins = compute_optimal_bins(10000, (-100, 100), (-50, 50))
        # 200:100 = 2:1 aspect
        assert x_bins > y_bins
        assert x_bins / y_bins == pytest.approx(2, rel=0.3)

    def test_real_world_ms_data_ranges(self):
        """Test with realistic mass spectrometry data ranges."""
        # Typical RT (0-60 min) vs m/z (100-2000) ranges
        x_bins, y_bins = compute_optimal_bins(10000, (0, 60), (100, 2000))
        # Aspect ratio is 60:1900 ≈ 1:31, so y_bins should dominate
        assert y_bins > x_bins
        assert x_bins * y_bins == pytest.approx(10000, rel=0.2)
