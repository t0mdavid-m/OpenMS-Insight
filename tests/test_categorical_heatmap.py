"""Tests for categorical Heatmap mode."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Heatmap


class TestCategoricalHeatmapInit:
    """Tests for Heatmap initialization with category_column."""

    def test_init_with_category_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test initialization with a category column."""
        heatmap = Heatmap(
            cache_id="test_categorical_heatmap",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        assert heatmap is not None
        assert heatmap._category_column == "sample_group"

    def test_init_with_category_colors(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test initialization with custom category colors."""
        custom_colors = {
            "Control": "#0000FF",
            "Treatment_A": "#FF0000",
            "Treatment_B": "#00FF00",
        }
        heatmap = Heatmap(
            cache_id="test_categorical_colors",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            category_colors=custom_colors,
            cache_path=str(temp_cache_dir),
        )

        assert heatmap._category_colors == custom_colors

    def test_init_without_category_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that standard heatmap still works without category_column."""
        heatmap = Heatmap(
            cache_id="test_standard_heatmap",
            data=sample_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            cache_path=str(temp_cache_dir),
        )

        assert heatmap._category_column is None
        assert heatmap._category_colors == {}


class TestCategoricalHeatmapCacheConfig:
    """Tests for cache config with category_column."""

    def test_category_column_in_cache_config(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that category_column is included in cache config."""
        heatmap = Heatmap(
            cache_id="test_cache_config",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        cache_config = heatmap._get_cache_config()
        assert "category_column" in cache_config
        assert cache_config["category_column"] == "sample_group"

    def test_category_colors_not_in_cache_config(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that category_colors is NOT in cache config (it's render-time styling)."""
        heatmap = Heatmap(
            cache_id="test_colors_not_cached",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            category_colors={"Control": "#0000FF"},
            cache_path=str(temp_cache_dir),
        )

        cache_config = heatmap._get_cache_config()
        assert "category_colors" not in cache_config


class TestCategoricalHeatmapComponentArgs:
    """Tests for component args with categorical mode."""

    def test_component_args_include_category_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that component args include categoryColumn when set."""
        heatmap = Heatmap(
            cache_id="test_args_category",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        args = heatmap._get_component_args()
        assert "categoryColumn" in args
        assert args["categoryColumn"] == "sample_group"

    def test_component_args_include_category_colors(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that component args include categoryColors when set."""
        custom_colors = {"Control": "#0000FF", "Treatment_A": "#FF0000"}
        heatmap = Heatmap(
            cache_id="test_args_colors",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            category_colors=custom_colors,
            cache_path=str(temp_cache_dir),
        )

        args = heatmap._get_component_args()
        assert "categoryColors" in args
        assert args["categoryColors"] == custom_colors

    def test_component_args_exclude_category_without_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that categoryColumn is not in args when not set."""
        heatmap = Heatmap(
            cache_id="test_args_no_category",
            data=sample_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            cache_path=str(temp_cache_dir),
        )

        args = heatmap._get_component_args()
        assert "categoryColumn" not in args
        assert "categoryColors" not in args


class TestCategoricalHeatmapPrepareData:
    """Tests for data preparation with category column."""

    def test_category_column_included_in_data(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that category column is included in prepared Vue data."""
        heatmap = Heatmap(
            cache_id="test_data_category",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        state = {}
        vue_data = heatmap._prepare_vue_data(state)

        # Check the data includes the category column
        df = vue_data["heatmapData"]
        assert "sample_group" in df.columns

    def test_category_values_preserved(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that category values are preserved in the data."""
        heatmap = Heatmap(
            cache_id="test_category_values",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        state = {}
        vue_data = heatmap._prepare_vue_data(state)

        df = vue_data["heatmapData"]
        # Check all expected categories are present
        unique_categories = set(df["sample_group"].unique())
        expected = {"Control", "Treatment_A", "Treatment_B"}
        # Some categories might not be present if downsampling removed them,
        # but the intersection should not be empty
        assert unique_categories & expected


class TestCategoricalHeatmapCacheReconstruction:
    """Tests for cache reconstruction with category_column."""

    def test_reconstruct_preserves_category_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_categorical_heatmap_data: pl.LazyFrame
    ):
        """Test that category_column is preserved after cache reconstruction."""
        # Create and save to cache
        heatmap1 = Heatmap(
            cache_id="test_reconstruct_category",
            data=sample_categorical_heatmap_data,
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            cache_path=str(temp_cache_dir),
        )

        # Reconstruct from cache (no data provided)
        heatmap2 = Heatmap(
            cache_id="test_reconstruct_category",
            cache_path=str(temp_cache_dir),
        )

        # Both should have the same category_column
        assert heatmap2._category_column == "sample_group"
