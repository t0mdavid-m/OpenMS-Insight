"""Tests for verifying components can be reconstructed from cache.

These tests verify that all components:
1. Can be created with data and generate a valid cache
2. Can be reconstructed from ONLY cache_path + cache_id (all config restored from cache)
3. Reconstructed components are equivalent to the originals

Note: Fixtures (temp_cache_dir, sample_*_data) are defined in conftest.py
"""

from pathlib import Path

import polars as pl
import pytest

from openms_insight.components.table import Table
from openms_insight.components.lineplot import LinePlot
from openms_insight.components.heatmap import Heatmap
from openms_insight.components.sequenceview import SequenceView
from openms_insight.core.cache import CacheMissError


class TestTableCacheReconstruction:
    """Tests for Table component cache reconstruction."""

    def test_table_creates_cache(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table creates cache when initialized with data."""
        cache_id = "test_table"

        table = Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        # Verify cache directory exists
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest file should exist"
        assert (cache_dir / "preprocessed").is_dir(), "Preprocessed dir should exist"

    def test_table_reconstructs_from_cache_only(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table can be reconstructed from ONLY cache_id and cache_path."""
        cache_id = "test_table"

        # Create original table with data and configuration
        original = Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="custom_id",
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "mass"},
            title="Test Table",
            pagination=False,
            page_size=50,
        )

        # Reconstruct from ONLY cache_id and cache_path - no other config!
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Verify all configuration was restored from cache
        assert reconstructed._cache_id == original._cache_id
        assert reconstructed._filters == original._filters
        assert reconstructed._interactivity == original._interactivity
        assert reconstructed._index_field == original._index_field
        assert reconstructed._title == original._title
        assert reconstructed._pagination == original._pagination
        assert reconstructed._page_size == original._page_size

    def test_table_cache_miss_raises_error(self, temp_cache_dir: Path):
        """Test that Table raises CacheMissError when no cache and no data."""
        with pytest.raises(CacheMissError):
            Table(
                cache_id="nonexistent_table",
                cache_path=str(temp_cache_dir),
            )

    def test_table_data_equivalence(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that reconstructed Table has equivalent data."""
        cache_id = "test_table_data"

        # Create original
        original = Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        # Get schema info from original
        original_data = original._preprocessed_data.get("data")
        if isinstance(original_data, pl.LazyFrame):
            original_schema = original_data.collect_schema()
            original_count = original_data.select(pl.len()).collect().item()
        else:
            original_schema = original_data.schema
            original_count = len(original_data)

        # Reconstruct from cache only
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Get reconstructed data info
        reconstructed_data = reconstructed._preprocessed_data.get("data")
        if isinstance(reconstructed_data, pl.LazyFrame):
            reconstructed_schema = reconstructed_data.collect_schema()
            reconstructed_count = reconstructed_data.select(pl.len()).collect().item()
        else:
            reconstructed_schema = reconstructed_data.schema
            reconstructed_count = len(reconstructed_data)

        # Verify equivalence
        assert reconstructed_schema.names() == original_schema.names()
        assert reconstructed_count == original_count


class TestLinePlotCacheReconstruction:
    """Tests for LinePlot component cache reconstruction."""

    def test_lineplot_creates_cache(
        self, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot creates cache when initialized with data."""
        cache_id = "test_lineplot"

        plot = LinePlot(
            cache_id=cache_id,
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        # Verify cache directory exists
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest file should exist"

    def test_lineplot_reconstructs_from_cache_only(
        self, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot can be reconstructed from ONLY cache_id and cache_path."""
        cache_id = "test_lineplot"

        # Create original with configuration
        original = LinePlot(
            cache_id=cache_id,
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            highlight_column="annotation",
            title="Test Plot",
            x_label="Mass (Da)",
            y_label="Intensity",
        )

        # Reconstruct from ONLY cache_id and cache_path
        reconstructed = LinePlot(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Verify all configuration was restored
        assert reconstructed._cache_id == original._cache_id
        assert reconstructed._filters == original._filters
        assert reconstructed._interactivity == original._interactivity
        assert reconstructed._x_column == original._x_column
        assert reconstructed._y_column == original._y_column
        assert reconstructed._title == original._title
        assert reconstructed._x_label == original._x_label
        assert reconstructed._y_label == original._y_label

    def test_lineplot_cache_miss_raises_error(self, temp_cache_dir: Path):
        """Test that LinePlot raises CacheMissError when no cache and no data."""
        with pytest.raises(CacheMissError):
            LinePlot(
                cache_id="nonexistent_lineplot",
                cache_path=str(temp_cache_dir),
            )

    def test_lineplot_data_equivalence(
        self, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that reconstructed LinePlot has equivalent data."""
        cache_id = "test_lineplot_data"

        # Create original
        original = LinePlot(
            cache_id=cache_id,
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        # Get original data info
        original_data = original._preprocessed_data.get("data")
        if isinstance(original_data, pl.LazyFrame):
            original_count = original_data.select(pl.len()).collect().item()
        else:
            original_count = len(original_data)

        # Reconstruct from cache only
        reconstructed = LinePlot(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Get reconstructed data info
        reconstructed_data = reconstructed._preprocessed_data.get("data")
        if isinstance(reconstructed_data, pl.LazyFrame):
            reconstructed_count = reconstructed_data.select(pl.len()).collect().item()
        else:
            reconstructed_count = len(reconstructed_data)

        # Verify equivalence
        assert reconstructed_count == original_count


class TestHeatmapCacheReconstruction:
    """Tests for Heatmap component cache reconstruction."""

    def test_heatmap_creates_cache(
        self, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap creates cache when initialized with data."""
        cache_id = "test_heatmap"

        heatmap = Heatmap(
            cache_id=cache_id,
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        # Verify cache directory exists
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / "manifest.json").exists(), "Manifest file should exist"

    def test_heatmap_reconstructs_from_cache_only(
        self, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap can be reconstructed from ONLY cache_id and cache_path."""
        cache_id = "test_heatmap"

        # Create original with configuration
        original = Heatmap(
            cache_id=cache_id,
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
            filters={"spectrum": "scan_id"},
            title="Test Heatmap",
            colorscale="Viridis",
        )

        # Reconstruct from ONLY cache_id and cache_path
        reconstructed = Heatmap(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Verify all configuration was restored
        assert reconstructed._cache_id == original._cache_id
        assert reconstructed._filters == original._filters
        assert reconstructed._x_column == original._x_column
        assert reconstructed._y_column == original._y_column
        assert reconstructed._min_points == original._min_points
        assert reconstructed._title == original._title
        assert reconstructed._colorscale == original._colorscale

    def test_heatmap_cache_miss_raises_error(self, temp_cache_dir: Path):
        """Test that Heatmap raises CacheMissError when no cache and no data."""
        with pytest.raises(CacheMissError):
            Heatmap(
                cache_id="nonexistent_heatmap",
                cache_path=str(temp_cache_dir),
            )

    def test_heatmap_levels_preserved(
        self, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap multi-resolution levels are preserved through cache."""
        cache_id = "test_heatmap_levels"

        # Create original
        original = Heatmap(
            cache_id=cache_id,
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        original_num_levels = original._preprocessed_data.get("num_levels", 0)

        # Reconstruct from cache only
        reconstructed = Heatmap(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        reconstructed_num_levels = reconstructed._preprocessed_data.get("num_levels", 0)

        # Verify levels count matches
        assert reconstructed_num_levels == original_num_levels
        assert reconstructed_num_levels > 0, "Should have at least one level"


class TestSequenceViewCacheReconstruction:
    """Tests for SequenceView component cache reconstruction."""

    def test_sequenceview_creates_cache(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that SequenceView creates cache when initialized with data."""
        cache_id = "test_sequenceview"

        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # Verify cache directory exists
        cache_dir = temp_cache_dir / cache_id
        assert cache_dir.exists(), "Cache directory should be created"
        assert (cache_dir / ".cache_config.json").exists(), "Config file should exist"
        assert (cache_dir / "sequences.parquet").exists(), "Sequences parquet should exist"
        assert (cache_dir / "peaks.parquet").exists(), "Peaks parquet should exist"

    def test_sequenceview_reconstructs_from_cache_only(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that SequenceView can be reconstructed from ONLY cache_id and cache_path."""
        cache_id = "test_sequenceview"

        # Create original with configuration
        original = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            title="Test Sequence",
            height=500,
            deconvolved=True,
        )

        # Reconstruct from ONLY cache_id and cache_path
        reconstructed = SequenceView(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Verify all configuration was restored
        assert reconstructed._cache_id == original._cache_id
        assert reconstructed._filters == original._filters
        assert reconstructed._interactivity == original._interactivity
        assert reconstructed._title == original._title
        assert reconstructed._height == original._height
        assert reconstructed._deconvolved == original._deconvolved

        # Verify cached LazyFrames exist
        assert reconstructed._cached_sequences is not None
        assert reconstructed._cached_peaks is not None

    def test_sequenceview_static_sequence_reconstructs(self, temp_cache_dir: Path):
        """Test that SequenceView with static sequence can be reconstructed."""
        cache_id = "test_sequenceview_static"

        # Create original with static sequence
        original = SequenceView(
            cache_id=cache_id,
            sequence_data=("PEPTIDER", 2),
            cache_path=str(temp_cache_dir),
            title="Static Sequence",
        )

        # Reconstruct from cache only
        reconstructed = SequenceView(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Verify cached sequences exist and contain the sequence
        assert reconstructed._cached_sequences is not None
        df = reconstructed._cached_sequences.collect()
        assert df.height == 1
        assert df["sequence"][0] == "PEPTIDER"
        assert df["precursor_charge"][0] == 2
        assert reconstructed._title == original._title

    def test_sequenceview_data_equivalence(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that reconstructed SequenceView has equivalent data."""
        cache_id = "test_sequenceview_data"

        # Create original
        original = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # Get original data counts
        original_seq_count = original._cached_sequences.select(pl.len()).collect().item()
        original_peaks_count = original._cached_peaks.select(pl.len()).collect().item()

        # Reconstruct from cache only
        reconstructed = SequenceView(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # Get reconstructed data counts
        reconstructed_seq_count = reconstructed._cached_sequences.select(pl.len()).collect().item()
        reconstructed_peaks_count = reconstructed._cached_peaks.select(pl.len()).collect().item()

        # Verify equivalence
        assert reconstructed_seq_count == original_seq_count
        assert reconstructed_peaks_count == original_peaks_count

    def test_sequenceview_peaks_data_property(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that peaks_data property returns cached data after reconstruction."""
        cache_id = "test_sequenceview_peaks_prop"

        # Create original
        original = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
        )

        assert original.peaks_data is not None

        # Reconstruct from cache only
        reconstructed = SequenceView(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        # peaks_data property should still work
        assert reconstructed.peaks_data is not None

        # Data should be equivalent
        original_count = original.peaks_data.select(pl.len()).collect().item()
        reconstructed_count = reconstructed.peaks_data.select(pl.len()).collect().item()
        assert reconstructed_count == original_count

    def test_sequenceview_cache_miss_raises_error(self, temp_cache_dir: Path):
        """Test that SequenceView raises ValueError when no cache and no data."""
        with pytest.raises(ValueError, match="Cache not found"):
            SequenceView(
                cache_id="nonexistent_sequenceview",
                cache_path=str(temp_cache_dir),
            )


class TestDataRequiredForConfiguration:
    """Tests verifying that configuration arguments require data."""

    def test_table_filters_without_data_fails(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that passing filters without data fails."""
        cache_id = "test_table_filters"

        # Create cache first
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with filters should fail
        with pytest.raises(CacheMissError, match="Configuration arguments"):
            Table(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                filters={"spectrum": "scan_id"},
            )

    def test_table_interactivity_without_data_fails(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that passing interactivity without data fails."""
        cache_id = "test_table_interact"

        # Create cache first
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with interactivity should fail
        with pytest.raises(CacheMissError, match="Configuration arguments"):
            Table(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                interactivity={"peak": "mass"},
            )

    def test_table_filter_defaults_without_data_fails(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that passing filter_defaults without data fails."""
        cache_id = "test_table_defaults"

        # Create cache first
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with filter_defaults should fail
        with pytest.raises(CacheMissError, match="Configuration arguments"):
            Table(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                filter_defaults={"id": -1},
            )

    def test_lineplot_config_without_data_fails(
        self, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that passing config to LinePlot without data fails."""
        cache_id = "test_lineplot_config"

        # Create cache first
        LinePlot(
            cache_id=cache_id,
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        # Attempting to reconstruct with filters should fail
        with pytest.raises(CacheMissError, match="Configuration arguments"):
            LinePlot(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                filters={"spectrum": "scan_id"},
            )

    def test_heatmap_config_without_data_fails(
        self, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that passing config to Heatmap without data fails."""
        cache_id = "test_heatmap_config"

        # Create cache first
        Heatmap(
            cache_id=cache_id,
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        # Attempting to reconstruct with filters should fail
        with pytest.raises(CacheMissError, match="Configuration arguments"):
            Heatmap(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                filters={"spectrum": "scan_id"},
            )

    def test_sequenceview_config_without_data_fails(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that passing config to SequenceView without data fails."""
        cache_id = "test_sequenceview_config"

        # Create cache first
        SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with filters should fail
        with pytest.raises(ValueError, match="Configuration arguments require"):
            SequenceView(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                filters={"spectrum": "scan_id"},
            )

    def test_sequenceview_title_without_data_fails(
        self, temp_cache_dir: Path, sample_sequence_data: pl.LazyFrame
    ):
        """Test that passing title to SequenceView without data fails."""
        cache_id = "test_sequenceview_title"

        # Create cache first
        SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with title should fail
        with pytest.raises(ValueError, match="Configuration arguments require"):
            SequenceView(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                title="New Title",
            )

    def test_sequenceview_height_without_data_fails(
        self, temp_cache_dir: Path, sample_sequence_data: pl.LazyFrame
    ):
        """Test that passing non-default height to SequenceView without data fails."""
        cache_id = "test_sequenceview_height"

        # Create cache first
        SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
        )

        # Attempting to reconstruct with non-default height should fail
        with pytest.raises(ValueError, match="Configuration arguments require"):
            SequenceView(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                height=600,  # Non-default value
            )


class TestRegenerateCache:
    """Tests for regenerate_cache functionality."""

    def test_regenerate_cache_requires_data(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that regenerate_cache=True requires data to be provided."""
        cache_id = "test_regen"

        # Create initial cache
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        # regenerate_cache=True without data should fail
        with pytest.raises(CacheMissError, match="regenerate_cache=True requires data"):
            Table(
                cache_id=cache_id,
                cache_path=str(temp_cache_dir),
                regenerate_cache=True,
            )

    def test_regenerate_cache_overwrites(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that regenerate_cache=True with data creates new cache."""
        cache_id = "test_regen_overwrite"

        # Create initial cache
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="Original Title",
        )

        # Get original manifest time
        import json
        manifest_path = temp_cache_dir / cache_id / "manifest.json"
        with open(manifest_path) as f:
            original_manifest = json.load(f)
        original_time = original_manifest["created_at"]

        # Wait a tiny bit and regenerate with new config
        import time
        time.sleep(0.01)

        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="New Title",
            regenerate_cache=True,
        )

        # Check manifest was updated
        with open(manifest_path) as f:
            new_manifest = json.load(f)
        new_time = new_manifest["created_at"]

        assert new_time != original_time, "Manifest should be regenerated"

        # Verify new config was saved
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )
        assert reconstructed._title == "New Title"


class TestFilterAndInteractivityRestoration:
    """Tests for filter and interactivity restoration from cache."""

    def test_table_filters_restored_from_cache(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that filters are correctly restored from manifest."""
        cache_id = "test_filters_restore"
        filters = {"spectrum": "scan_id", "peak": "id"}

        # Create with filters
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters=filters,
        )

        # Reconstruct with only cache_id and cache_path
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        assert reconstructed.get_filters_mapping() == filters

    def test_lineplot_interactivity_restored_from_cache(
        self, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that interactivity is correctly restored from manifest."""
        cache_id = "test_interact_restore"
        interactivity = {"selected_peak": "peak_id"}

        # Create with interactivity
        LinePlot(
            cache_id=cache_id,
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            interactivity=interactivity,
        )

        # Reconstruct with only cache_id and cache_path
        reconstructed = LinePlot(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        assert reconstructed.get_interactivity_mapping() == interactivity

    def test_filter_defaults_restored_from_cache(
        self, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that filter_defaults are correctly restored from manifest."""
        cache_id = "test_filter_defaults"
        filter_defaults = {"identification": -1}

        # Create with filter_defaults
        Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filter_defaults=filter_defaults,
        )

        # Reconstruct with only cache_id and cache_path
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )

        assert reconstructed.get_filter_defaults() == filter_defaults
