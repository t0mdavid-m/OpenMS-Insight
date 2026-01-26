"""Tests for verifying components can be constructed and rendered in Streamlit.

These tests verify that all components:
1. Can be constructed with valid data
2. Can prepare Vue data correctly
3. Can work with StateManager for filtering and interactivity
4. Return proper component args for Vue

Note: Fixtures (temp_cache_dir, sample_*_data, mock_streamlit) are defined in conftest.py
"""

from pathlib import Path

import polars as pl

from openms_insight.components.heatmap import Heatmap
from openms_insight.components.lineplot import LinePlot
from openms_insight.components.sequenceview import SequenceView
from openms_insight.components.table import Table
from openms_insight.core.state import StateManager, reset_default_state_manager


class TestTableStreamlitConstruction:
    """Tests for Table component Streamlit construction."""

    def test_table_prepares_vue_data(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table prepares Vue data correctly."""
        table = Table(
            cache_id="test_table",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        state = {}
        vue_data = table._prepare_vue_data(state)

        # Table uses 'tableData' key
        assert "tableData" in vue_data
        data = vue_data["tableData"]
        assert len(data) == 5  # 5 rows in sample data

    def test_table_prepares_vue_data_with_filter(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table filters data based on state."""
        table = Table(
            cache_id="test_table_filter",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            index_field="id",
        )

        # Filter to scan_id=100 (2 rows)
        state = {"spectrum": 100}
        vue_data = table._prepare_vue_data(state)

        data = vue_data["tableData"]
        assert len(data) == 2  # Only rows with scan_id=100

    def test_table_get_vue_component_name(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table returns correct Vue component name."""
        table = Table(
            cache_id="test_table_name",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        assert table._get_vue_component_name() == "TabulatorTable"

    def test_table_get_component_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table returns correct component args."""
        table = Table(
            cache_id="test_table_args",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="Test Table",
            index_field="id",
        )

        args = table._get_component_args()

        assert args["componentType"] == "TabulatorTable"
        assert args["title"] == "Test Table"
        assert args["tableIndexField"] == "id"
        assert "columnDefinitions" in args

    def test_table_get_data_key(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table returns correct data key."""
        table = Table(
            cache_id="test_table_key",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        assert table._get_data_key() == "tableData"


class TestLinePlotStreamlitConstruction:
    """Tests for LinePlot component Streamlit construction."""

    def test_lineplot_prepares_vue_data(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot prepares Vue data correctly."""
        plot = LinePlot(
            cache_id="test_lineplot",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        state = {}
        vue_data = plot._prepare_vue_data(state)

        # LinePlot uses 'plotData' key
        assert "plotData" in vue_data
        data = vue_data["plotData"]
        assert len(data) == 5

    def test_lineplot_prepares_vue_data_with_filter(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot filters data based on state."""
        plot = LinePlot(
            cache_id="test_lineplot_filter",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            filters={"spectrum": "scan_id"},
        )

        # Filter to scan_id=1 (3 rows)
        state = {"spectrum": 1}
        vue_data = plot._prepare_vue_data(state)

        data = vue_data["plotData"]
        assert len(data) == 3

    def test_lineplot_get_vue_component_name(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot returns correct Vue component name."""
        plot = LinePlot(
            cache_id="test_lineplot_name",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        # Actual Vue component name is PlotlyLineplotUnified
        assert plot._get_vue_component_name() == "PlotlyLineplotUnified"

    def test_lineplot_get_component_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot returns correct component args."""
        plot = LinePlot(
            cache_id="test_lineplot_args",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            title="Test Plot",
            x_label="Mass (Da)",
            y_label="Intensity",
        )

        args = plot._get_component_args()

        assert args["componentType"] == "PlotlyLineplotUnified"
        assert args["title"] == "Test Plot"
        assert args["xLabel"] == "Mass (Da)"
        assert args["yLabel"] == "Intensity"

    def test_lineplot_highlight_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot with highlight column prepares data correctly."""
        plot = LinePlot(
            cache_id="test_lineplot_highlight",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            highlight_column="annotation",
        )

        state = {}
        plot._prepare_vue_data(state)
        args = plot._get_component_args()

        assert args.get("highlightColumn") == "annotation"

    def test_lineplot_get_data_key(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot returns correct data key."""
        plot = LinePlot(
            cache_id="test_lineplot_key",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        assert plot._get_data_key() == "plotData"


class TestHeatmapStreamlitConstruction:
    """Tests for Heatmap component Streamlit construction."""

    def test_heatmap_prepares_vue_data(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap prepares Vue data correctly."""
        heatmap = Heatmap(
            cache_id="test_heatmap",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        state = {}
        vue_data = heatmap._prepare_vue_data(state)

        # Heatmap returns multi-resolution data with 'heatmapData' key
        assert "heatmapData" in vue_data

    def test_heatmap_get_vue_component_name(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap returns correct Vue component name."""
        heatmap = Heatmap(
            cache_id="test_heatmap_name",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        assert heatmap._get_vue_component_name() == "PlotlyHeatmap"

    def test_heatmap_get_component_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap returns correct component args."""
        heatmap = Heatmap(
            cache_id="test_heatmap_args",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
            title="Test Heatmap",
            colorscale="Viridis",
        )

        args = heatmap._get_component_args()

        assert args["componentType"] == "PlotlyHeatmap"
        assert args["title"] == "Test Heatmap"
        assert args["colorscale"] == "Viridis"

    def test_heatmap_zoom_state(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap responds to zoom state."""
        heatmap = Heatmap(
            cache_id="test_heatmap_zoom",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        # Get state dependencies - should include zoom
        deps = heatmap.get_state_dependencies()
        assert "heatmap_zoom" in deps

    def test_heatmap_get_data_key(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap returns correct data key."""
        heatmap = Heatmap(
            cache_id="test_heatmap_key",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        assert heatmap._get_data_key() == "heatmapData"


class TestSequenceViewStreamlitConstruction:
    """Tests for SequenceView component Streamlit construction."""

    def test_sequenceview_prepares_vue_data(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Test that SequenceView prepares Vue data correctly."""
        sv = SequenceView(
            cache_id="test_sequenceview",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # With filter set
        state = {"spectrum": 1}
        vue_data = sv._prepare_vue_data(state)

        # Should have sequence data
        assert "sequenceData" in vue_data
        seq_data = vue_data["sequenceData"]
        assert "sequence" in seq_data
        # Sequence is returned as array of characters for Vue
        assert "".join(seq_data["sequence"]) == "PEPTIDER"

    def test_sequenceview_static_sequence(self, mock_streamlit, temp_cache_dir: Path):
        """Test that SequenceView with static sequence works."""
        sv = SequenceView(
            cache_id="test_sequenceview_static",
            sequence_data=("PEPTIDER", 2),
            cache_path=str(temp_cache_dir),
        )

        state = {}
        vue_data = sv._prepare_vue_data(state)

        assert "sequenceData" in vue_data
        seq_data = vue_data["sequenceData"]
        # Sequence is returned as array of characters for Vue
        assert "".join(seq_data["sequence"]) == "PEPTIDER"
        # precursorCharge is at top level, not inside sequenceData
        assert vue_data["precursorCharge"] == 2

    def test_sequenceview_get_vue_component_name(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
    ):
        """Test that SequenceView returns correct Vue component name."""
        sv = SequenceView(
            cache_id="test_sequenceview_name",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
        )

        assert sv._get_vue_component_name() == "SequenceView"

    def test_sequenceview_get_component_args(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
    ):
        """Test that SequenceView returns correct component args."""
        sv = SequenceView(
            cache_id="test_sequenceview_args",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
            title="Test Sequence",
            height=500,
        )

        args = sv._get_component_args()

        assert args["componentType"] == "SequenceView"
        assert args["title"] == "Test Sequence"
        assert args["height"] == 500

    def test_sequenceview_get_data_key(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
    ):
        """Test that SequenceView returns correct data key."""
        sv = SequenceView(
            cache_id="test_sequenceview_key",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
        )

        assert sv._get_data_key() == "sequenceData"


class TestStateManagerIntegration:
    """Tests for StateManager integration with components."""

    def test_state_manager_initialization(self, mock_streamlit):
        """Test that StateManager initializes correctly."""
        reset_default_state_manager()
        sm = StateManager()

        assert sm.counter == 0
        assert sm.get_all_selections() == {}

    def test_state_manager_set_selection(self, mock_streamlit):
        """Test setting a selection."""
        reset_default_state_manager()
        sm = StateManager()

        changed = sm.set_selection("spectrum", 100)
        assert changed is True
        assert sm.get_selection("spectrum") == 100

        # Setting same value should return False
        changed = sm.set_selection("spectrum", 100)
        assert changed is False

    def test_state_manager_get_state_for_vue(self, mock_streamlit):
        """Test getting state formatted for Vue."""
        reset_default_state_manager()
        sm = StateManager()

        sm.set_selection("spectrum", 100)
        sm.set_selection("peak", 42)

        state = sm.get_state_for_vue()

        assert "counter" in state
        assert "id" in state
        assert state["spectrum"] == 100
        assert state["peak"] == 42

    def test_component_uses_state_for_filtering(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that component uses StateManager for filtering."""
        reset_default_state_manager()
        sm = StateManager()

        table = Table(
            cache_id="test_table_state",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            index_field="id",
        )

        # Set selection
        sm.set_selection("spectrum", 100)
        state = sm.get_state_for_vue()

        # Prepare data - should filter by scan_id=100
        vue_data = table._prepare_vue_data(state)
        data = vue_data["tableData"]

        assert len(data) == 2  # Only rows with scan_id=100


class TestFilterDefaults:
    """Tests for filter defaults functionality."""

    def test_table_filter_defaults_applied(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that filter defaults are applied when state is None."""
        table = Table(
            cache_id="test_table_defaults",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            filter_defaults={"spectrum": 100},
            index_field="id",
        )

        # No selection set - should use default
        state = {}
        vue_data = table._prepare_vue_data(state)

        data = vue_data["tableData"]

        # Should filter by default value scan_id=100
        assert len(data) == 2


class TestInteractivityMapping:
    """Tests for interactivity mapping."""

    def test_table_interactivity_mapping(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table exposes interactivity mapping correctly."""
        table = Table(
            cache_id="test_table_interact",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            interactivity={"selected_peak": "mass"},
            index_field="id",
        )

        mapping = table.get_interactivity_mapping()
        assert mapping == {"selected_peak": "mass"}

    def test_lineplot_interactivity_mapping(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot exposes interactivity mapping correctly."""
        plot = LinePlot(
            cache_id="test_lineplot_interact",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
            interactivity={"peak": "peak_id"},
        )

        mapping = plot.get_interactivity_mapping()
        assert mapping == {"peak": "peak_id"}

    def test_table_interactivity_columns_in_vue_data(
        self, mock_streamlit, temp_cache_dir: Path
    ):
        """Test that interactivity columns are included in Vue data even if not in column_definitions.

        This is a regression test for a bug where interactivity columns were filtered out
        of the data sent to Vue, causing row clicks to not update selections properly.
        """
        # Create data with columns for interactivity that are NOT in column_definitions
        data = pl.LazyFrame(
            {
                "id": [1, 2, 3],
                "name": ["a", "b", "c"],
                "file_index": [10, 20, 30],  # interactivity column, not displayed
                "scan_id": [100, 200, 300],  # interactivity column, not displayed
            }
        )

        table = Table(
            cache_id="test_table_interact_cols",
            data=data,
            cache_path=str(temp_cache_dir),
            # Only 'name' is in column_definitions
            column_definitions=[
                {"field": "name", "title": "Name"},
            ],
            # But interactivity references columns NOT in column_definitions
            interactivity={"file": "file_index", "spectrum": "scan_id"},
            index_field="id",
        )

        state = {}
        vue_data = table._prepare_vue_data(state)

        # The Vue data should include interactivity columns even though
        # they're not in column_definitions
        df = vue_data["tableData"]
        columns = list(df.columns)

        # Verify interactivity columns are present
        assert "file_index" in columns, (
            "Interactivity column 'file_index' missing from Vue data"
        )
        assert "scan_id" in columns, (
            "Interactivity column 'scan_id' missing from Vue data"
        )

        # Verify we can access the values
        assert df["file_index"].tolist() == [10, 20, 30]
        assert df["scan_id"].tolist() == [100, 200, 300]


class TestTableAutoSelection:
    """Tests for auto-selecting first row when filter data changes."""

    def test_auto_selection_returns_first_row_value(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Verify _auto_selection contains first row's interactivity column value."""
        table = Table(
            cache_id="test_autoselect",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
        )

        # Filter to scan_id=100 -> 2 rows (id=1, id=2), first row has id=1
        result = table._prepare_vue_data({"spectrum": 100})

        assert "_auto_selection" in result
        assert result["_auto_selection"] == {"selected_id": 1}

    def test_auto_selection_empty_when_no_data(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Verify _auto_selection is empty when filtered data has no rows."""
        table = Table(
            cache_id="test_autoselect_empty",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
        )

        # Filter to scan_id=999 -> no matching rows
        result = table._prepare_vue_data({"spectrum": 999})

        assert "_auto_selection" in result
        assert result["_auto_selection"] == {}

    def test_auto_selection_empty_when_no_interactivity(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Verify _auto_selection is empty when no interactivity defined."""
        table = Table(
            cache_id="test_autoselect_no_interact",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            # No interactivity
        )

        result = table._prepare_vue_data({})

        assert "_auto_selection" in result
        assert result["_auto_selection"] == {}

    def test_auto_selection_multiple_interactivity_columns(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Verify _auto_selection works with multiple interactivity mappings."""
        table = Table(
            cache_id="test_autoselect_multi",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            interactivity={"selected_id": "id", "selected_scan": "scan_id"},
        )

        result = table._prepare_vue_data({})

        assert "_auto_selection" in result
        # First row: id=1, scan_id=100
        assert result["_auto_selection"] == {"selected_id": 1, "selected_scan": 100}

    def test_auto_selection_with_state_manager(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test auto-selection integration with StateManager."""
        reset_default_state_manager()
        sm = StateManager()

        table = Table(
            cache_id="test_autoselect_sm",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
        )

        # Set filter
        sm.set_selection("spectrum", 100)
        state = sm.get_state_for_vue()

        vue_data = table._prepare_vue_data(state)

        # Auto-selection should be first row of filtered data
        assert vue_data["_auto_selection"] == {"selected_id": 1}

    def test_auto_selection_respects_sort(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Verify _auto_selection respects sort order (uses first row after sort)."""
        table = Table(
            cache_id="test_autoselect_sort",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            interactivity={"selected_id": "id"},
            pagination_identifier="test_page",
        )

        # Sort by mass descending - row with id=5 (mass=900.9) should be first
        result = table._prepare_vue_data(
            {"test_page": {"sort_column": "mass", "sort_dir": "desc"}}
        )

        assert "_auto_selection" in result
        assert result["_auto_selection"] == {"selected_id": 5}


class TestComponentVueArgsKeys:
    """Tests verifying Vue component args have required keys."""

    def test_table_required_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data: pl.LazyFrame
    ):
        """Test that Table includes all required Vue args."""
        table = Table(
            cache_id="test_table_required",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )

        args = table._get_component_args()

        required_keys = ["componentType", "tableIndexField", "columnDefinitions"]
        for key in required_keys:
            assert key in args, f"Missing required key: {key}"

    def test_lineplot_required_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_lineplot_data: pl.LazyFrame
    ):
        """Test that LinePlot includes all required Vue args."""
        plot = LinePlot(
            cache_id="test_lineplot_required",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )

        args = plot._get_component_args()

        required_keys = ["componentType", "xColumn", "yColumn"]
        for key in required_keys:
            assert key in args, f"Missing required key: {key}"

    def test_heatmap_required_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_heatmap_data: pl.LazyFrame
    ):
        """Test that Heatmap includes all required Vue args."""
        heatmap = Heatmap(
            cache_id="test_heatmap_required",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )

        args = heatmap._get_component_args()

        required_keys = ["componentType", "xColumn", "yColumn", "intensityColumn"]
        for key in required_keys:
            assert key in args, f"Missing required key: {key}"

    def test_sequenceview_required_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_sequence_data: pl.LazyFrame
    ):
        """Test that SequenceView includes all required Vue args."""
        sv = SequenceView(
            cache_id="test_sequenceview_required",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
        )

        args = sv._get_component_args()

        required_keys = ["componentType"]
        for key in required_keys:
            assert key in args, f"Missing required key: {key}"
