"""Tests for VolcanoPlot component."""

import math
from pathlib import Path

import polars as pl
import pytest

from openms_insight import VolcanoPlot


class TestVolcanoPlotInit:
    """Tests for VolcanoPlot initialization."""

    def test_init_with_lazyframe(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test initialization with a LazyFrame."""
        volcano = VolcanoPlot(
            cache_id="test_volcano",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        assert volcano is not None
        assert volcano._log2fc_column == "log2FC"
        assert volcano._pvalue_column == "pvalue"

    def test_init_with_label_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test initialization with label column."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_labels",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            label_column="protein_name",
            cache_path=str(temp_cache_dir),
        )

        assert volcano._label_column == "protein_name"

    def test_init_missing_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test initialization fails with missing column (via filter mapping validation)."""
        # Mapping validation catches missing columns for filter/interactivity columns
        with pytest.raises(ValueError, match="not found in data"):
            VolcanoPlot(
                cache_id="test_volcano_missing",
                data=sample_volcanoplot_data,
                log2fc_column="log2FC",
                pvalue_column="pvalue",
                filters={"missing": "nonexistent_column"},
                cache_path=str(temp_cache_dir),
            )


class TestVolcanoPlotPreprocessing:
    """Tests for VolcanoPlot preprocessing."""

    def test_neglog10_computation(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test that -log10(pvalue) is correctly computed."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_neglog10",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        # Access preprocessed data (may be DataFrame or LazyFrame)
        data = volcano._preprocessed_data["volcanoData"]
        if isinstance(data, pl.LazyFrame):
            df = data.collect()
        else:
            df = data

        # Check -log10(pvalue) column exists
        assert "_neglog10_pvalue" in df.columns

        # Verify computation for first few rows
        original = sample_volcanoplot_data.collect()
        for i in range(min(5, len(df))):
            pvalue = original["pvalue"][i]
            expected_neglog10 = -math.log10(pvalue) if pvalue > 0 else 0
            actual_neglog10 = df["_neglog10_pvalue"][i]
            assert abs(expected_neglog10 - actual_neglog10) < 1e-6

    def test_cache_creation(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test that cache files are created."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_cache",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        cache_dir = temp_cache_dir / "test_volcano_cache"
        assert cache_dir.exists()

        # Check for manifest or preprocessed directory
        preprocessed_dir = cache_dir / "preprocessed"
        assert preprocessed_dir.exists() or (cache_dir / "manifest.json").exists()


class TestVolcanoPlotThresholds:
    """Tests for render-time thresholds."""

    def test_thresholds_not_in_cache_hash(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test that thresholds don't affect cache invalidation."""
        # Create first volcano
        volcano1 = VolcanoPlot(
            cache_id="test_volcano_thresh1",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        # Get config hash inputs
        hash_inputs = volcano1._get_component_config_hash_inputs()

        # Verify thresholds are not in the hash inputs
        assert "fc_threshold" not in hash_inputs
        assert "p_threshold" not in hash_inputs

    def test_call_with_thresholds(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test that thresholds are passed via __call__."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_call",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        # Set thresholds via internal attributes (simulating __call__ behavior)
        volcano._current_fc_threshold = 1.5
        volcano._current_p_threshold = 0.01
        volcano._current_max_labels = 20

        # Check component args include thresholds
        args = volcano._get_component_args()
        assert args["fcThreshold"] == 1.5
        assert args["pThreshold"] == 0.01
        assert args["maxLabels"] == 20


class TestVolcanoPlotFiltering:
    """Tests for filtering functionality."""

    def test_filter_by_comparison(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test filtering by comparison identifier."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_filter",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            filters={"comparison": "comparison_id"},
            cache_path=str(temp_cache_dir),
        )

        # Prepare data with filter applied
        state = {"comparison": "A_vs_B"}
        vue_data, data_hash = volcano._prepare_vue_data(state)

        # All returned rows should be A_vs_B
        df = vue_data["volcanoData"]
        if "comparison_id" in df.columns:
            assert all(df["comparison_id"] == "A_vs_B")


class TestVolcanoPlotComponentArgs:
    """Tests for component args generation."""

    def test_component_args_structure(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test that component args have correct structure."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_args",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            label_column="protein_name",
            title="My Volcano Plot",
            up_color="#FF0000",
            down_color="#0000FF",
            ns_color="#808080",
            cache_path=str(temp_cache_dir),
        )

        args = volcano._get_component_args()

        assert args["log2fcColumn"] == "log2FC"
        assert args["neglog10pColumn"] == "_neglog10_pvalue"
        assert args["pvalueColumn"] == "pvalue"
        assert args["labelColumn"] == "protein_name"
        assert args["title"] == "My Volcano Plot"
        assert args["upColor"] == "#FF0000"
        assert args["downColor"] == "#0000FF"
        assert args["nsColor"] == "#808080"

    def test_vue_component_name(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test Vue component name."""
        volcano = VolcanoPlot(
            cache_id="test_volcano_vue",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        assert volcano._get_vue_component_name() == "PlotlyVolcano"
        assert volcano._get_data_key() == "volcanoData"


class TestVolcanoPlotCacheReconstruction:
    """Tests for cache reconstruction."""

    def test_reconstruct_from_cache(
        self, mock_streamlit, temp_cache_dir: Path, sample_volcanoplot_data: pl.LazyFrame
    ):
        """Test reconstructing volcano plot from cache."""
        # Create and save to cache
        volcano1 = VolcanoPlot(
            cache_id="test_volcano_reconstruct",
            data=sample_volcanoplot_data,
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            cache_path=str(temp_cache_dir),
        )

        # Reconstruct from cache (no data provided)
        volcano2 = VolcanoPlot(
            cache_id="test_volcano_reconstruct",
            cache_path=str(temp_cache_dir),
        )

        # Both should have same preprocessed data
        data1 = volcano1._preprocessed_data["volcanoData"]
        data2 = volcano2._preprocessed_data["volcanoData"]

        # Handle LazyFrame if necessary
        df1 = data1.collect() if isinstance(data1, pl.LazyFrame) else data1
        df2 = data2.collect() if isinstance(data2, pl.LazyFrame) else data2

        assert len(df1) == len(df2)
        assert df1["log2FC"].to_list() == df2["log2FC"].to_list()
