"""Tests for the Plot3D component."""

from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from openms_insight import Plot3D


class TestPlot3DInit:
    """Tests for Plot3D initialization."""

    def test_init_with_lazyframe(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Test initialization with a LazyFrame."""
        plot = Plot3D(
            cache_id="test_plot3d",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            cache_path=str(temp_cache_dir),
        )

        assert plot is not None
        assert plot._x_column == "mass"
        assert plot._y_column == "charge"
        assert plot._z_column == "intensity"
        assert plot._category_column == "series"
        # Default series colors (oracle)
        assert plot._category_colors == {"Signal": "#3366CC", "Noise": "#DC3912"}

    def test_init_missing_column(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Test initialization fails with a missing required column."""
        with pytest.raises(ValueError, match="Missing required columns"):
            Plot3D(
                cache_id="test_plot3d_missing",
                data=sample_plot3d_data,
                x_column="mass",
                y_column="charge",
                z_column="nonexistent_intensity",
                cache_path=str(temp_cache_dir),
            )

    def test_init_missing_filter_column(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Test initialization fails with a bad filter mapping (base validation)."""
        with pytest.raises(ValueError, match="not found in data"):
            Plot3D(
                cache_id="test_plot3d_bad_filter",
                data=sample_plot3d_data,
                x_column="mass",
                y_column="charge",
                z_column="intensity",
                filters={"spectrum": "nonexistent_column"},
                cache_path=str(temp_cache_dir),
            )


class TestPlot3DPreprocessing:
    """Tests for Plot3D preprocessing."""

    def test_drop_nonpositive_z(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Points with intensity <= 0 are dropped during preprocessing."""
        plot = Plot3D(
            cache_id="test_plot3d_drop",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            cache_path=str(temp_cache_dir),
        )

        data = plot._preprocessed_data["plot3dData"]
        df = data.collect() if isinstance(data, pl.LazyFrame) else data

        # No remaining non-positive intensity rows
        assert (df["intensity"] <= 0).sum() == 0

        # Row count equals number of positive-intensity input rows
        original = sample_plot3d_data.collect()
        expected = int((original["intensity"] > 0).sum())
        assert len(df) == expected

    def test_keep_nonpositive_when_disabled(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """When drop_nonpositive_z=False, non-positive rows are retained."""
        plot = Plot3D(
            cache_id="test_plot3d_keep",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            drop_nonpositive_z=False,
            cache_path=str(temp_cache_dir),
        )

        data = plot._preprocessed_data["plot3dData"]
        df = data.collect() if isinstance(data, pl.LazyFrame) else data
        assert len(df) == len(sample_plot3d_data.collect())


class TestPlot3DPrepareVueData:
    """Tests for _prepare_vue_data output shape."""

    def test_prepare_vue_data_shape(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Result is a dict with a pandas DataFrame and a non-empty str hash."""
        plot = Plot3D(
            cache_id="test_plot3d_shape",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            cache_path=str(temp_cache_dir),
        )

        result = plot._prepare_vue_data({})

        assert isinstance(result, dict)
        assert isinstance(result["plot3dData"], pd.DataFrame)

        cols = set(result["plot3dData"].columns)
        assert {"mass", "charge", "intensity"}.issubset(cols)
        assert "series" in cols

        assert isinstance(result["_hash"], str)
        assert len(result["_hash"]) > 0

    def test_filter_empty_when_no_selection(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """With filter_defaults, no scan selection yields an empty frame."""
        plot = Plot3D(
            cache_id="test_plot3d_empty",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            filters={"spectrum": "scan"},
            filter_defaults={"spectrum": -1},
            cache_path=str(temp_cache_dir),
        )

        result = plot._prepare_vue_data({})
        assert len(result["plot3dData"]) == 0

    def test_filter_selects_scan(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Selecting a scan returns only that scan's positive-intensity rows."""
        plot = Plot3D(
            cache_id="test_plot3d_scan",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            filters={"spectrum": "scan"},
            cache_path=str(temp_cache_dir),
        )

        result = plot._prepare_vue_data({"spectrum": 200})
        df = result["plot3dData"]
        assert len(df) > 0
        assert set(df["scan"].tolist()) == {200}

        # Scan 200 has three rows, all positive intensity -> all three kept.
        original = sample_plot3d_data.collect()
        expected = int(
            ((original["scan"] == 200) & (original["intensity"] > 0)).sum()
        )
        assert len(df) == expected

    def test_optional_filter_shows_all_until_selected(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """An optional filter is skipped when unset (show all rows for the required
        filters) and narrows only when its selection is present."""
        plot = Plot3D(
            cache_id="test_plot3d_optional",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            filters={"spectrum": "scan", "mass": "mass_index"},
            filter_defaults={"spectrum": -1},
            optional_filters=["mass"],
            cache_path=str(temp_cache_dir),
        )

        # scan selected, mass UNSET -> all of scan 200's positive-intensity rows
        # (mass filter skipped), not an empty frame.
        all_masses = plot._prepare_vue_data({"spectrum": 200})["plot3dData"]
        assert set(all_masses["scan"].tolist()) == {200}
        assert len(all_masses) == 3

        # scan + mass selected -> narrowed to that mass ordinal.
        one_mass = plot._prepare_vue_data(
            {"spectrum": 200, "mass": 1}
        )["plot3dData"]
        assert set(one_mass["mass_index"].tolist()) == {1}
        assert len(one_mass) == 2

        # required filter (spectrum) still empties when unset.
        assert len(plot._prepare_vue_data({})["plot3dData"]) == 0


class TestPlot3DComponentArgs:
    """Tests for component args generation."""

    def test_component_args_keys(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """_get_component_args contains the documented keys/defaults."""
        plot = Plot3D(
            cache_id="test_plot3d_args",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            cache_path=str(temp_cache_dir),
        )

        args = plot._get_component_args()

        assert args["componentType"] == "Plotly3D"
        assert args["xColumn"] == "mass"
        assert args["yColumn"] == "charge"
        assert args["zColumn"] == "intensity"
        assert args["categoryColors"] == {"Signal": "#3366CC", "Noise": "#DC3912"}
        assert args["cameraEye"] == {"x": 2.5, "y": 0, "z": 0.2}
        assert args["yDtick"] == 1
        assert args["yTick0"] == 0
        assert args["xLabel"] == "Mass"
        assert args["yLabel"] == "Charge"
        assert args["zLabel"] == "Intensity"

    def test_vue_component_name(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Vue component name and data key match the spec."""
        plot = Plot3D(
            cache_id="test_plot3d_vue",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            cache_path=str(temp_cache_dir),
        )

        assert plot._get_vue_component_name() == "Plotly3D"
        assert plot._get_data_key() == "plot3dData"


class TestPlot3DRenderTimeMode:
    """Tests for render-time trace_mode behavior."""

    def test_trace_mode_is_render_time(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """trace_mode is render-time: not in cache config, settable w/o rebuild."""
        plot = Plot3D(
            cache_id="test_plot3d_mode",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            cache_path=str(temp_cache_dir),
        )

        # trace_mode must NOT participate in cache invalidation
        assert "trace_mode" not in plot._get_cache_config()

        # Default trace_mode (oracle) is "lines"
        assert plot._get_component_args()["traceMode"] == "lines"

        # Setting render-time trace_mode reflects in component args
        plot._current_trace_mode = "markers"
        assert plot._get_component_args()["traceMode"] == "markers"


class TestPlot3DCacheReconstruction:
    """Tests for cache reconstruction."""

    def test_cache_reconstruction(
        self,
        mock_streamlit,
        temp_cache_dir: Path,
        sample_plot3d_data: pl.LazyFrame,
    ):
        """Reconstruct from cache restores labels/colors/camera/columns."""
        Plot3D(
            cache_id="test_plot3d_reconstruct",
            data=sample_plot3d_data,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            title="Precursor Signals",
            cache_path=str(temp_cache_dir),
        )

        # Reconstruct with only cache_id + cache_path (no data, no config)
        plot2 = Plot3D(
            cache_id="test_plot3d_reconstruct",
            cache_path=str(temp_cache_dir),
        )

        assert plot2._x_column == "mass"
        assert plot2._y_column == "charge"
        assert plot2._z_column == "intensity"
        assert plot2._category_column == "series"
        assert plot2._title == "Precursor Signals"

        args = plot2._get_component_args()
        assert args["categoryColors"] == {"Signal": "#3366CC", "Noise": "#DC3912"}
        assert args["cameraEye"] == {"x": 2.5, "y": 0, "z": 0.2}
        assert args["xLabel"] == "Mass"
        assert args["yLabel"] == "Charge"
        assert args["zLabel"] == "Intensity"
