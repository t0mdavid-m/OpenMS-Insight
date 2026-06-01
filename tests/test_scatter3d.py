"""Tests for Scatter3D component."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Scatter3D


@pytest.fixture
def sample_scatter3d_data() -> pl.LazyFrame:
    """Long-format signal/noise peaks across two scans and masses.

    scan 1: mass 0 (2 signal, 1 noise), mass 1 (1 signal)
    scan 2: mass 0 (1 signal, 1 noise)
    """
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1, 1, 2, 2],
            "mass_id": [0, 0, 0, 1, 0, 0],
            "mz": [500.0, 600.0, 550.0, 700.0, 800.0, 820.0],
            "charge": [2, 3, 2, 4, 5, 5],
            "intensity": [1000.0, 2000.0, 50.0, 1500.0, 3000.0, 40.0],
            "kind": ["signal", "signal", "noise", "signal", "signal", "noise"],
        }
    )


class TestScatter3DInit:
    def test_init(self, mock_streamlit, temp_cache_dir, sample_scatter3d_data):
        plot = Scatter3D(
            cache_id="s3d_init",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id", "massIndex": "mass_id"},
            cache_path=str(temp_cache_dir),
        )
        assert plot._mz_column == "mz"
        assert plot._get_vue_component_name() == "Plotly3DScatter"
        assert plot._get_data_key() == "scatter3dData"

    def test_init_missing_column(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        with pytest.raises(ValueError, match="not found in data"):
            Scatter3D(
                cache_id="s3d_missing",
                data=sample_scatter3d_data,
                intensity_column="nope",
                cache_path=str(temp_cache_dir),
            )

    def test_state_dependencies(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        plot = Scatter3D(
            cache_id="s3d_deps",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id", "massIndex": "mass_id"},
            cache_path=str(temp_cache_dir),
        )
        assert set(plot.get_state_dependencies()) == {"scanIndex", "massIndex"}


class TestScatter3DFiltering:
    def test_filter_by_scan(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        plot = Scatter3D(
            cache_id="s3d_scan",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        vue_data = plot._prepare_vue_data({"scanIndex": 1})
        df = vue_data["scatter3dData"]
        assert len(df) == 4  # all scan-1 peaks
        assert set(df["scan_id"]) == {1}

    def test_filter_by_scan_and_mass(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        plot = Scatter3D(
            cache_id="s3d_scan_mass",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id", "massIndex": "mass_id"},
            cache_path=str(temp_cache_dir),
        )
        # scan 1, mass 0 -> 2 signal + 1 noise = 3 peaks
        vue_data = plot._prepare_vue_data({"scanIndex": 1, "massIndex": 0})
        df = vue_data["scatter3dData"]
        assert len(df) == 3
        assert set(df["mass_id"]) == {0}
        # signal/noise split preserved
        assert sorted(df["kind"]) == ["noise", "signal", "signal"]

    def test_empty_when_no_scan(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        """No scanIndex selection (and no default) -> empty frame."""
        plot = Scatter3D(
            cache_id="s3d_empty",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        vue_data = plot._prepare_vue_data({})
        assert len(vue_data["scatter3dData"]) == 0

    def test_vue_data_contract(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        plot = Scatter3D(
            cache_id="s3d_contract",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        vue_data = plot._prepare_vue_data({"scanIndex": 1})
        assert isinstance(vue_data, dict)
        assert "scatter3dData" in vue_data
        assert "_hash" in vue_data
        for col in ("mz", "charge", "intensity", "kind", "scan_id"):
            assert col in vue_data["scatter3dData"].columns


class TestScatter3DComponentArgs:
    def test_component_args(
        self, mock_streamlit, temp_cache_dir, sample_scatter3d_data
    ):
        plot = Scatter3D(
            cache_id="s3d_args",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id"},
            title="Precursor Signals",
            cache_path=str(temp_cache_dir),
        )
        args = plot._get_component_args()
        assert args["componentType"] == "Plotly3DScatter"
        assert args["title"] == "Precursor Signals"
        assert args["signalColor"] == "#3366CC"
        assert args["noiseColor"] == "#DC3912"
        assert args["xLabel"] == "Mass"
        assert args["yLabel"] == "Charge"
        assert args["zLabel"] == "Intensity"


class TestScatter3DCacheReconstruction:
    def test_reconstruct(self, mock_streamlit, temp_cache_dir, sample_scatter3d_data):
        Scatter3D(
            cache_id="s3d_recon",
            data=sample_scatter3d_data,
            filters={"scanIndex": "scan_id", "massIndex": "mass_id"},
            title="Precursor Signals",
            cache_path=str(temp_cache_dir),
        )
        plot2 = Scatter3D(cache_id="s3d_recon", cache_path=str(temp_cache_dir))
        assert plot2._title == "Precursor Signals"
        assert plot2._filters == {"scanIndex": "scan_id", "massIndex": "mass_id"}
        df = plot2._prepare_vue_data({"scanIndex": 2, "massIndex": 0})["scatter3dData"]
        assert len(df) == 2
