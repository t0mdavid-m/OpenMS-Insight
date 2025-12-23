"""Tests for subprocess preprocessing behavior.

When data_path is provided instead of data, preprocessing should run in a
subprocess to ensure memory is released after cache creation.
"""

from pathlib import Path
from unittest.mock import patch

import polars as pl

from openms_insight.components.heatmap import Heatmap
from openms_insight.components.lineplot import LinePlot
from openms_insight.components.sequenceview import SequenceView
from openms_insight.components.table import Table


class TestTableSubprocessPreprocessing:
    """Tests for Table subprocess preprocessing."""

    def test_table_with_data_path_creates_cache(
        self,
        temp_cache_dir: Path,
        sample_table_data: pl.LazyFrame,
    ):
        """Test that Table with data_path creates cache via subprocess."""
        # Save data to parquet file
        data_path = temp_cache_dir / "table_data.parquet"
        sample_table_data.collect().write_parquet(data_path)

        cache_id = "test_table_subprocess"

        # Create component with data_path (triggers subprocess)
        table = Table(
            cache_id=cache_id,
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        # Verify cache was created
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest should exist"
        assert (cache_dir / "preprocessed" / "data.parquet").exists(), (
            "Data parquet should exist"
        )

        # Verify component works
        state = {}
        vue_data = table._prepare_vue_data(state)
        assert "tableData" in vue_data
        assert len(vue_data["tableData"]) == 5

    def test_table_subprocess_called_with_data_path(
        self,
        temp_cache_dir: Path,
        sample_table_data: pl.LazyFrame,
    ):
        """Test that subprocess preprocessing is called when data_path is provided."""
        data_path = temp_cache_dir / "table_data.parquet"
        sample_table_data.collect().write_parquet(data_path)

        with patch(
            "openms_insight.core.subprocess_preprocess.preprocess_component"
        ) as mock_preprocess:
            # Mock successful preprocessing by creating cache manually
            cache_id = "test_table_subprocess_mock"
            cache_dir = temp_cache_dir / cache_id
            (cache_dir / "preprocessed").mkdir(parents=True)

            # Create minimal cache files
            sample_table_data.collect().write_parquet(
                cache_dir / "preprocessed" / "data.parquet"
            )
            import json

            manifest = {
                "cache_version": 3,
                "component_type": "table",
                "filters": {},
                "filter_defaults": {},
                "interactivity": {},
                "config": {"index_field": "id"},
                "data_files": {"data": "data.parquet"},
                "created_at": "2024-01-01T00:00:00",
            }
            (cache_dir / "manifest.json").write_text(json.dumps(manifest))

            Table(
                cache_id=cache_id,
                data_path=str(data_path),
                cache_path=str(temp_cache_dir),
                index_field="id",
            )

            # Verify subprocess function was called
            mock_preprocess.assert_called_once()
            call_kwargs = mock_preprocess.call_args
            assert call_kwargs[1]["data_path"] == str(data_path)


class TestLinePlotSubprocessPreprocessing:
    """Tests for LinePlot subprocess preprocessing."""

    def test_lineplot_with_data_path_creates_cache(
        self,
        temp_cache_dir: Path,
        sample_lineplot_data: pl.LazyFrame,
    ):
        """Test that LinePlot with data_path creates cache via subprocess."""
        data_path = temp_cache_dir / "lineplot_data.parquet"
        sample_lineplot_data.collect().write_parquet(data_path)

        cache_id = "test_lineplot_subprocess"

        plot = LinePlot(
            cache_id=cache_id,
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        # Verify cache was created
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest should exist"
        assert (cache_dir / "preprocessed" / "data.parquet").exists(), (
            "Data parquet should exist"
        )

        # Verify component works
        state = {}
        vue_data = plot._prepare_vue_data(state)
        assert "plotData" in vue_data
        assert len(vue_data["plotData"]) == 5


class TestHeatmapSubprocessPreprocessing:
    """Tests for Heatmap subprocess preprocessing."""

    def test_heatmap_with_data_path_creates_cache(
        self,
        temp_cache_dir: Path,
        sample_heatmap_data: pl.LazyFrame,
    ):
        """Test that Heatmap with data_path creates cache via subprocess."""
        data_path = temp_cache_dir / "heatmap_data.parquet"
        sample_heatmap_data.collect().write_parquet(data_path)

        cache_id = "test_heatmap_subprocess"

        heatmap = Heatmap(
            cache_id=cache_id,
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        # Verify cache was created
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest should exist"
        # Heatmap creates level_*.parquet files in preprocessed/
        preprocessed_dir = cache_dir / "preprocessed"
        level_files = list(preprocessed_dir.glob("level_*.parquet"))
        assert len(level_files) > 0, "Level parquet files should exist"

        # Verify component works
        state = {}
        vue_data = heatmap._prepare_vue_data(state)
        assert "heatmapData" in vue_data


class TestSequenceViewSubprocessPreprocessing:
    """Tests for SequenceView subprocess preprocessing.

    Note: SequenceView uses sequence_data_path and peaks_data_path instead of data_path.
    """

    def test_sequenceview_with_data_path_creates_cache(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that SequenceView with data paths creates cache."""
        sequence_path = temp_cache_dir / "sequence_data.parquet"
        peaks_path = temp_cache_dir / "peaks_data.parquet"
        sample_sequence_data.collect().write_parquet(sequence_path)
        sample_peaks_data.collect().write_parquet(peaks_path)

        cache_id = "test_sequenceview_subprocess"

        sv = SequenceView(
            cache_id=cache_id,
            sequence_data_path=str(sequence_path),
            peaks_data_path=str(peaks_path),
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # Verify cache was created
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / ".cache_config.json").exists(), "Config file should exist"
        assert (cache_dir / "sequences.parquet").exists(), (
            "Sequences parquet should exist"
        )
        assert (cache_dir / "peaks.parquet").exists(), "Peaks parquet should exist"

        # Verify component works
        state = {"spectrum": 1}
        vue_data = sv._prepare_vue_data(state)
        assert "sequenceData" in vue_data


class TestSubprocessVsInProcessEquivalence:
    """Tests that subprocess and in-process preprocessing produce equivalent results."""

    def test_table_subprocess_and_inprocess_equivalent(
        self,
        temp_cache_dir: Path,
        sample_table_data: pl.LazyFrame,
    ):
        """Test that Table produces same results with data_path vs data."""
        # Save data for subprocess version
        data_path = temp_cache_dir / "table_data.parquet"
        sample_table_data.collect().write_parquet(data_path)

        # Create with data_path (subprocess)
        table_subprocess = Table(
            cache_id="table_subprocess",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        # Create with data (in-process)
        table_inprocess = Table(
            cache_id="table_inprocess",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        # Compare Vue data
        state = {}
        vue_subprocess = table_subprocess._prepare_vue_data(state)
        vue_inprocess = table_inprocess._prepare_vue_data(state)

        assert len(vue_subprocess["tableData"]) == len(vue_inprocess["tableData"])

    def test_lineplot_subprocess_and_inprocess_equivalent(
        self,
        temp_cache_dir: Path,
        sample_lineplot_data: pl.LazyFrame,
    ):
        """Test that LinePlot produces same results with data_path vs data."""
        data_path = temp_cache_dir / "lineplot_data.parquet"
        sample_lineplot_data.collect().write_parquet(data_path)

        plot_subprocess = LinePlot(
            cache_id="lineplot_subprocess",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        plot_inprocess = LinePlot(
            cache_id="lineplot_inprocess",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        state = {}
        vue_subprocess = plot_subprocess._prepare_vue_data(state)
        vue_inprocess = plot_inprocess._prepare_vue_data(state)

        assert len(vue_subprocess["plotData"]) == len(vue_inprocess["plotData"])

    def test_heatmap_subprocess_and_inprocess_equivalent(
        self,
        temp_cache_dir: Path,
        sample_heatmap_data: pl.LazyFrame,
    ):
        """Test that Heatmap produces same results with data_path vs data."""
        data_path = temp_cache_dir / "heatmap_data.parquet"
        sample_heatmap_data.collect().write_parquet(data_path)

        heatmap_subprocess = Heatmap(
            cache_id="heatmap_subprocess",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        heatmap_inprocess = Heatmap(
            cache_id="heatmap_inprocess",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        state = {}
        vue_subprocess = heatmap_subprocess._prepare_vue_data(state)
        vue_inprocess = heatmap_inprocess._prepare_vue_data(state)

        # Both should produce heatmap data (sizes may vary due to downsampling randomness)
        assert "heatmapData" in vue_subprocess
        assert "heatmapData" in vue_inprocess
