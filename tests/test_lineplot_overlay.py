"""Tests for LinePlot overlay (second-series) support — tagger-overlay primitive."""

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def primary_df() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1, 2, 2],
            "mass": [100.0, 200.0, 300.0, 400.0, 500.0],
            "intensity": [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )


@pytest.fixture
def overlay_df() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 2],
            "mass": [101.0, 201.0, 401.0],
            "intensity": [5.0, 15.0, 45.0],
        }
    )


class TestLinePlotOverlay:
    def test_overlay_emitted_and_filtered(
        self, mock_streamlit, temp_cache_dir, primary_df, overlay_df
    ):
        lp = LinePlot(
            cache_id="lp_overlay",
            data=primary_df,
            overlay_data=overlay_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            overlay_color="#abcdef",
            overlay_name="Raw",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({"scanIndex": 1})
        assert "plotData" in out
        assert "plotDataOverlay" in out
        assert len(out["plotData"]) == 3  # scan 1 primary peaks
        assert len(out["plotDataOverlay"]) == 2  # scan 1 overlay peaks

    def test_overlay_args(self, mock_streamlit, temp_cache_dir, primary_df, overlay_df):
        lp = LinePlot(
            cache_id="lp_overlay_args",
            data=primary_df,
            overlay_data=overlay_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            overlay_color="#abcdef",
            overlay_name="Raw",
            cache_path=str(temp_cache_dir),
        )
        args = lp._get_component_args()
        assert args["hasOverlay"] is True
        assert args["overlayColor"] == "#abcdef"
        assert args["overlayName"] == "Raw"
        assert args["overlayXColumn"] == "mass"
        assert args["overlayYColumn"] == "intensity"

    def test_no_overlay_unaffected(self, mock_streamlit, temp_cache_dir, primary_df):
        """LinePlot without overlay behaves exactly as before."""
        lp = LinePlot(
            cache_id="lp_no_overlay",
            data=primary_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({"scanIndex": 1})
        assert "plotData" in out
        assert "plotDataOverlay" not in out
        assert lp._get_component_args().get("hasOverlay") is None

    def test_overlay_distinct_columns(self, mock_streamlit, temp_cache_dir):
        """Overlay may use different x/y column names than the primary series."""
        primary = pl.LazyFrame(
            {"scan_id": [1, 1], "mz": [100.0, 200.0], "inten": [10.0, 20.0]}
        )
        overlay = pl.LazyFrame(
            {"scan_id": [1, 1], "raw_mz": [101.0, 201.0], "raw_inten": [5.0, 15.0]}
        )
        lp = LinePlot(
            cache_id="lp_overlay_cols",
            data=primary,
            overlay_data=overlay,
            filters={"scanIndex": "scan_id"},
            x_column="mz",
            y_column="inten",
            overlay_x_column="raw_mz",
            overlay_y_column="raw_inten",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({"scanIndex": 1})
        ov = out["plotDataOverlay"]
        assert "raw_mz" in ov.columns
        assert "raw_inten" in ov.columns
        assert len(ov) == 2

    def test_overlay_survives_cache_reconstruction(
        self, mock_streamlit, temp_cache_dir, primary_df, overlay_df
    ):
        LinePlot(
            cache_id="lp_overlay_recon",
            data=primary_df,
            overlay_data=overlay_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            overlay_name="Raw",
            cache_path=str(temp_cache_dir),
        )
        lp2 = LinePlot(cache_id="lp_overlay_recon", cache_path=str(temp_cache_dir))
        assert lp2._has_overlay is True
        assert lp2._overlay_name == "Raw"
        out = lp2._prepare_vue_data({"scanIndex": 2})
        assert len(out["plotDataOverlay"]) == 1

    def test_overlay_empty_without_selection(
        self, mock_streamlit, temp_cache_dir, primary_df, overlay_df
    ):
        lp = LinePlot(
            cache_id="lp_overlay_empty",
            data=primary_df,
            overlay_data=overlay_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({})
        assert len(out["plotData"]) == 0
        assert len(out["plotDataOverlay"]) == 0
