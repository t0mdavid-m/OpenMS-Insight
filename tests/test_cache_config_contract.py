"""Contract test: cache config must include all configuration parameters.

This test ensures that _get_cache_config() and _restore_cache_config() handle
all component parameters that affect behavior, preventing bugs where parameters
are lost when reconstructing from cache.
"""

import pytest

from openms_insight import Heatmap


class TestHeatmapCacheConfig:
    """Test that Heatmap cache config includes all necessary parameters."""

    def test_cache_config_includes_log_scale(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """log_scale must be stored and restored from cache."""
        # Create with non-default value
        heatmap = Heatmap(
            cache_id="test_heatmap_log_scale",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            log_scale=False,  # Non-default (default is True)
        )

        # Verify it's in cache config
        config = heatmap._get_cache_config()
        assert "log_scale" in config, "log_scale missing from cache config"
        assert config["log_scale"] is False

        # Verify restoration works
        heatmap2 = Heatmap(
            cache_id="test_heatmap_log_scale_restore",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_cache_config(config)
        assert heatmap2._log_scale is False, "log_scale not restored from cache"

    def test_cache_config_includes_intensity_label(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """intensity_label must be stored and restored from cache."""
        # Create with non-default value
        heatmap = Heatmap(
            cache_id="test_heatmap_intensity_label",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            intensity_label="Score",  # Non-default (default is None)
        )

        # Verify it's in cache config
        config = heatmap._get_cache_config()
        assert "intensity_label" in config, "intensity_label missing from cache config"
        assert config["intensity_label"] == "Score"

        # Verify restoration works
        heatmap2 = Heatmap(
            cache_id="test_heatmap_intensity_label_restore",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_cache_config(config)
        assert heatmap2._intensity_label == "Score", (
            "intensity_label not restored from cache"
        )

    def test_cache_config_roundtrip_preserves_all_params(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """All cache config parameters should survive a save/restore cycle."""
        # Create with various non-default values
        heatmap = Heatmap(
            cache_id="test_heatmap_roundtrip",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=5000,
            title="Test Heatmap",
            x_label="RT (min)",
            y_label="m/z",
            colorscale="Viridis",
            log_scale=False,
            intensity_label="Score",
        )

        config = heatmap._get_cache_config()

        # Create new instance and restore
        heatmap2 = Heatmap(
            cache_id="test_heatmap_roundtrip2",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_cache_config(config)

        # Verify all params restored
        assert heatmap2._min_points == 5000
        assert heatmap2._title == "Test Heatmap"
        assert heatmap2._x_label == "RT (min)"
        assert heatmap2._y_label == "m/z"
        assert heatmap2._colorscale == "Viridis"
        assert heatmap2._log_scale is False
        assert heatmap2._intensity_label == "Score"


class TestCacheConfigCompleteness:
    """Test that _get_cache_config keys match _restore_cache_config handling."""

    @pytest.mark.parametrize(
        "ComponentClass,data_fixture,extra_kwargs",
        [
            (
                Heatmap,
                "sample_heatmap_data",
                {
                    "x_column": "retention_time",
                    "y_column": "mz",
                    "intensity_column": "intensity",
                },
            ),
        ],
    )
    def test_all_cache_config_keys_are_restored(
        self,
        mock_streamlit,
        temp_cache_dir,
        request,
        ComponentClass,
        data_fixture,
        extra_kwargs,
    ):
        """Every key in _get_cache_config should be handled by _restore_cache_config."""
        data = request.getfixturevalue(data_fixture)

        component = ComponentClass(
            cache_id=f"test_{ComponentClass.__name__}_cache_keys",
            data=data,
            cache_path=str(temp_cache_dir),
            **extra_kwargs,
        )

        config = component._get_cache_config()

        # Create fresh instance
        component2 = ComponentClass(
            cache_id=f"test_{ComponentClass.__name__}_cache_keys2",
            data=data,
            cache_path=str(temp_cache_dir),
            **extra_kwargs,
        )

        # Restore config
        component2._restore_cache_config(config)

        # Get config again - should match original
        config2 = component2._get_cache_config()

        # All keys from original config should be in restored config
        for key in config:
            assert key in config2, f"Key '{key}' not restored by _restore_cache_config"
            assert config[key] == config2[key], (
                f"Key '{key}' value mismatch after restore"
            )
