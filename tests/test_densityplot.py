"""Tests for DensityPlot component."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from openms_insight import DensityPlot


@pytest.fixture
def sample_density_data() -> pl.LazyFrame:
    """Target/decoy score data for DensityPlot (FDR-plot shape)."""
    rng = np.random.default_rng(42)
    targets = rng.normal(0.8, 0.1, 300)
    decoys = rng.normal(0.3, 0.15, 120)
    return pl.LazyFrame(
        {
            "score": np.concatenate([targets, decoys]).tolist(),
            "series": ["Target"] * len(targets) + ["Decoy"] * len(decoys),
        }
    )


@pytest.fixture
def single_series_data() -> pl.LazyFrame:
    """Single-series value data (no series column)."""
    rng = np.random.default_rng(7)
    return pl.LazyFrame({"score": rng.normal(0.5, 0.2, 200).tolist()})


class TestDensityPlotInit:
    def test_init_with_series(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_init",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            cache_path=str(temp_cache_dir),
        )
        assert dp._value_column == "score"
        assert dp._series_column == "series"

    def test_init_missing_value_column(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        with pytest.raises(ValueError, match="not found in data"):
            DensityPlot(
                cache_id="dp_missing",
                data=sample_density_data,
                value_column="nonexistent",
                cache_path=str(temp_cache_dir),
            )


class TestDensityPlotPreprocessing:
    def test_kde_curve_shape(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_shape",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            grid_points=200,
            cache_path=str(temp_cache_dir),
        )
        data = dp._preprocessed_data["densityData"]
        df = data.collect() if isinstance(data, pl.LazyFrame) else data
        # Two non-empty series, 200 grid points each
        assert set(df["series"].unique().to_list()) == {"Target", "Decoy"}
        for series in ("Target", "Decoy"):
            assert df.filter(pl.col("series") == series).height == 200
        # Densities are non-negative
        assert df["y"].min() >= 0

    def test_grid_points_respected(
        self, mock_streamlit, temp_cache_dir: Path, single_series_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_grid",
            data=single_series_data,
            value_column="score",
            grid_points=50,
            cache_path=str(temp_cache_dir),
        )
        data = dp._preprocessed_data["densityData"]
        df = data.collect() if isinstance(data, pl.LazyFrame) else data
        assert df.height == 50
        # Single default series name
        assert df["series"].unique().to_list() == ["Density"]

    def test_empty_decoy_series(self, mock_streamlit, temp_cache_dir: Path):
        """A series with <2 values yields no rows (mirrors empty-decoy case)."""
        data = pl.LazyFrame(
            {
                "score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.9],
                "series": ["Target"] * 5 + ["Decoy"],  # single decoy
            }
        )
        dp = DensityPlot(
            cache_id="dp_empty_decoy",
            data=data,
            value_column="score",
            series_column="series",
            cache_path=str(temp_cache_dir),
        )
        df = dp._preprocessed_data["densityData"]
        df = df.collect() if isinstance(df, pl.LazyFrame) else df
        # Target present; the single-value Decoy produces no curve
        assert "Target" in df["series"].to_list()
        assert "Decoy" not in df["series"].to_list()
        assert dp._preprocessed_data["series_order"] == ["Target"]

    def test_zero_variance_series(self, mock_streamlit, temp_cache_dir: Path):
        """All-equal values have singular covariance -> empty curve, no crash."""
        data = pl.LazyFrame({"score": [0.5] * 20})
        dp = DensityPlot(
            cache_id="dp_zero_var",
            data=data,
            value_column="score",
            cache_path=str(temp_cache_dir),
        )
        df = dp._preprocessed_data["densityData"]
        df = df.collect() if isinstance(df, pl.LazyFrame) else df
        assert df.height == 0


class TestDensityPlotPrepareVueData:
    def test_prepare_vue_data_contract(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_vue",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            cache_path=str(temp_cache_dir),
        )
        vue_data = dp._prepare_vue_data({})
        assert isinstance(vue_data, dict)
        assert "densityData" in vue_data
        assert "_hash" in vue_data
        df = vue_data["densityData"]
        assert list(df.columns) == ["series", "x", "y"]
        assert len(df) == 400  # 2 series x 200 points

    def test_state_ignored(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        """Static plot: different state produces identical data + hash."""
        dp = DensityPlot(
            cache_id="dp_static",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            cache_path=str(temp_cache_dir),
        )
        a = dp._prepare_vue_data({})
        b = dp._prepare_vue_data({"anything": 123})
        assert a["_hash"] == b["_hash"]
        assert dp.get_state_dependencies() == []


class TestDensityPlotComponentArgs:
    def test_component_args_structure(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_args",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            series_config={
                "Target": {"label": "Target QScores", "color": "green"},
                "Decoy": {"label": "Decoy QScores", "color": "red"},
            },
            title="FDR Plot",
            x_label="QScore",
            cache_path=str(temp_cache_dir),
        )
        args = dp._get_component_args()
        assert args["componentType"] == "PlotlyDensity"
        assert args["title"] == "FDR Plot"
        assert args["xLabel"] == "QScore"
        assert args["yLabel"] == "Density"
        # Series presentation: Target first (config order), green/red colors
        series = args["series"]
        assert series[0]["name"] == "Target"
        assert series[0]["label"] == "Target QScores"
        assert series[0]["color"] == "green"
        assert series[1]["name"] == "Decoy"
        assert series[1]["color"] == "red"

    def test_vue_component_name(
        self, mock_streamlit, temp_cache_dir: Path, single_series_data: pl.LazyFrame
    ):
        dp = DensityPlot(
            cache_id="dp_name",
            data=single_series_data,
            value_column="score",
            cache_path=str(temp_cache_dir),
        )
        assert dp._get_vue_component_name() == "PlotlyDensity"
        assert dp._get_data_key() == "densityData"


class TestDensityPlotCacheReconstruction:
    def test_reconstruct_from_cache(
        self, mock_streamlit, temp_cache_dir: Path, sample_density_data: pl.LazyFrame
    ):
        dp1 = DensityPlot(
            cache_id="dp_reconstruct",
            data=sample_density_data,
            value_column="score",
            series_column="series",
            series_config={"Target": {"color": "green"}},
            cache_path=str(temp_cache_dir),
        )
        # Reconstruct from cache (no data)
        dp2 = DensityPlot(
            cache_id="dp_reconstruct",
            cache_path=str(temp_cache_dir),
        )
        assert dp2._value_column == "score"
        assert dp2._series_column == "series"
        assert dp2._series_config == {"Target": {"color": "green"}}

        d1 = dp1._prepare_vue_data({})["densityData"]
        d2 = dp2._prepare_vue_data({})["densityData"]
        assert len(d1) == len(d2)
