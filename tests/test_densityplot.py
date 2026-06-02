"""Tests for the DensityPlot component (dual-KDE score distribution plot).

Covers the FLASHApp parity contract checklist items owned by the functionality fan:
 1. KDE over a fixture yields a 200-row {x,y} frame with x=linspace(min,max,200)
    and y=gaussian_kde(x), matching deconv.fdr_density_distribution numerically.
 2. TnT path filters ProteoformLevelQvalue>0, splits target/decoy by DECOY_ prefix;
    empty target/decoy -> empty frame (columns ['x','y'], 0 rows).
 3. Two traces named exactly "Target QScores"/"Decoy QScores" (green/red).
 7. get_state_dependencies()==[] (static, never recomputes on selections).
Plus: precomputed mode, cache reconstruction, vue name/keys.
"""

import numpy as np
import polars as pl
import pytest
from scipy.stats import gaussian_kde

from openms_insight.components.densityplot import KDE_GRID_POINTS, DensityPlot


# --------------------------------------------------------------------------- #
# Reference implementations (copied verbatim from FLASHApp parse code)        #
# --------------------------------------------------------------------------- #
def _ref_deconv(df):
    """Mirror of deconv.py fdr_density_distribution (pandas)."""
    import pandas as pd

    target = df[df["TargetDecoyType"] == 0]["Qscore"].dropna()
    x_t = np.linspace(target.min(), target.max(), 200)
    y_t = gaussian_kde(target)(x_t)
    density_target = pd.DataFrame({"x": x_t, "y": y_t})

    decoy = df[df["TargetDecoyType"] > 0]["Qscore"].dropna()
    if len(decoy) > 0:
        x_d = np.linspace(decoy.min(), decoy.max(), 200)
        y_d = gaussian_kde(decoy)(x_d)
        density_decoy = pd.DataFrame({"x": x_d, "y": y_d})
    else:
        density_decoy = pd.DataFrame(columns=["x", "y"])
    return density_target, density_decoy


def _ref_tnt(df):
    """Mirror of tnt.py fdr_density_distribution (pandas)."""
    import pandas as pd

    df = df[df["ProteoformLevelQvalue"] > 0]
    target = df[~df["accession"].str.startswith("DECOY_")][
        "ProteoformLevelQvalue"
    ].dropna()
    if len(target) > 0:
        x_t = np.linspace(target.min(), target.max(), 200)
        density_target = pd.DataFrame({"x": x_t, "y": gaussian_kde(target)(x_t)})
    else:
        density_target = pd.DataFrame(columns=["x", "y"])

    decoy = df[df["accession"].str.startswith("DECOY_")][
        "ProteoformLevelQvalue"
    ].dropna()
    if len(decoy) > 0:
        x_d = np.linspace(decoy.min(), decoy.max(), 200)
        density_decoy = pd.DataFrame({"x": x_d, "y": gaussian_kde(decoy)(x_d)})
    else:
        density_decoy = pd.DataFrame(columns=["x", "y"])
    return density_target, density_decoy


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def deconv_fdr_data() -> pl.LazyFrame:
    rng = np.random.default_rng(42)
    targets = rng.normal(0.8, 0.1, 300)
    decoys = rng.normal(0.3, 0.15, 120)
    td = [0] * len(targets) + [1] * len(decoys)
    q = np.concatenate([targets, decoys])
    return pl.LazyFrame({"TargetDecoyType": td, "Qscore": q})


@pytest.fixture
def deconv_no_decoy_data() -> pl.LazyFrame:
    rng = np.random.default_rng(7)
    targets = rng.normal(0.8, 0.1, 200)
    return pl.LazyFrame({"TargetDecoyType": [0] * len(targets), "Qscore": targets})


@pytest.fixture
def tnt_protein_data() -> pl.LazyFrame:
    rng = np.random.default_rng(13)
    n_t, n_d = 200, 80
    target_q = rng.uniform(0.001, 0.5, n_t)
    decoy_q = rng.uniform(0.001, 0.5, n_d)
    # Include some rows with Qvalue == 0 that must be pre-filtered out.
    zero_rows = 10
    accessions = (
        [f"PROT_{i}" for i in range(n_t)]
        + [f"DECOY_{i}" for i in range(n_d)]
        + [f"PROT_z{i}" for i in range(zero_rows)]
    )
    qvals = list(target_q) + list(decoy_q) + [0.0] * zero_rows
    return pl.LazyFrame({"accession": accessions, "ProteoformLevelQvalue": qvals})


def _collect(comp: DensityPlot, key: str) -> pl.DataFrame:
    data = comp._preprocessed_data[key]
    return data.collect() if isinstance(data, pl.LazyFrame) else data


# --------------------------------------------------------------------------- #
# Checklist 1 — Deconv KDE numeric parity                                     #
# --------------------------------------------------------------------------- #
class TestDeconvKDE:
    def test_kde_matches_reference(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_deconv",
            data=deconv_fdr_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        target = _collect(comp, "densityTarget")
        decoy = _collect(comp, "densityDecoy")

        ref_t, ref_d = _ref_deconv(deconv_fdr_data.collect().to_pandas())

        assert target.height == KDE_GRID_POINTS == 200
        assert decoy.height == 200
        assert set(target.columns) == {"x", "y"}

        np.testing.assert_allclose(
            target["x"].to_numpy(), ref_t["x"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            target["y"].to_numpy(), ref_t["y"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            decoy["x"].to_numpy(), ref_d["x"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            decoy["y"].to_numpy(), ref_d["y"].to_numpy(), rtol=1e-6
        )

    def test_x_is_linspace_of_min_max(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_deconv_lin",
            data=deconv_fdr_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        df = deconv_fdr_data.collect()
        targets = df.filter(pl.col("TargetDecoyType") == 0)["Qscore"].to_numpy()
        expected_x = np.linspace(targets.min(), targets.max(), 200)
        target = _collect(comp, "densityTarget")
        # Cached frames are downcast Float64->Float32 for transfer efficiency.
        np.testing.assert_allclose(target["x"].to_numpy(), expected_x, rtol=1e-5)

    def test_empty_decoy_yields_empty_frame(
        self, mock_streamlit, temp_cache_dir, deconv_no_decoy_data
    ):
        comp = DensityPlot(
            cache_id="dp_deconv_nodecoy",
            data=deconv_no_decoy_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        target = _collect(comp, "densityTarget")
        decoy = _collect(comp, "densityDecoy")
        assert target.height == 200
        assert decoy.height == 0
        assert set(decoy.columns) == {"x", "y"}


# --------------------------------------------------------------------------- #
# Checklist 2 — TnT path                                                       #
# --------------------------------------------------------------------------- #
class TestTnTKDE:
    def test_kde_matches_reference(
        self, mock_streamlit, temp_cache_dir, tnt_protein_data
    ):
        comp = DensityPlot(
            cache_id="dp_tnt",
            data=tnt_protein_data,
            mode="tnt",
            cache_path=str(temp_cache_dir),
        )
        target = _collect(comp, "densityTarget")
        decoy = _collect(comp, "densityDecoy")

        ref_t, ref_d = _ref_tnt(tnt_protein_data.collect().to_pandas())

        assert target.height == 200
        assert decoy.height == 200
        np.testing.assert_allclose(
            target["x"].to_numpy(), ref_t["x"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            target["y"].to_numpy(), ref_t["y"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            decoy["x"].to_numpy(), ref_d["x"].to_numpy(), rtol=1e-6
        )
        np.testing.assert_allclose(
            decoy["y"].to_numpy(), ref_d["y"].to_numpy(), rtol=1e-6
        )

    def test_prefilter_qvalue_positive(
        self, mock_streamlit, temp_cache_dir, tnt_protein_data
    ):
        """Rows with ProteoformLevelQvalue==0 must be excluded before KDE."""
        comp = DensityPlot(
            cache_id="dp_tnt_prefilter",
            data=tnt_protein_data,
            mode="tnt",
            cache_path=str(temp_cache_dir),
        )
        target = _collect(comp, "densityTarget")
        # The 10 zero-Qvalue rows are excluded; min x must be > 0.
        assert target["x"].min() > 0

    def test_empty_target_and_decoy(self, mock_streamlit, temp_cache_dir):
        # All rows have Qvalue==0 -> both empty after pre-filter.
        empty = pl.LazyFrame(
            {
                "accession": ["PROT_1", "DECOY_1"],
                "ProteoformLevelQvalue": [0.0, 0.0],
            }
        )
        comp = DensityPlot(
            cache_id="dp_tnt_empty",
            data=empty,
            mode="tnt",
            cache_path=str(temp_cache_dir),
        )
        assert _collect(comp, "densityTarget").height == 0
        assert _collect(comp, "densityDecoy").height == 0
        assert set(_collect(comp, "densityTarget").columns) == {"x", "y"}


# --------------------------------------------------------------------------- #
# Precomputed mode                                                             #
# --------------------------------------------------------------------------- #
class TestPrecomputedMode:
    def test_precomputed_xy(self, mock_streamlit, temp_cache_dir):
        target_xy = pl.LazyFrame({"x": [1.0, 2.0, 3.0], "y": [0.1, 0.5, 0.2]})
        decoy_xy = pl.LazyFrame(
            {"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64}
        )
        comp = DensityPlot(
            cache_id="dp_precomp",
            density_target=target_xy,
            density_decoy=decoy_xy,
            cache_path=str(temp_cache_dir),
        )
        t = _collect(comp, "densityTarget")
        d = _collect(comp, "densityDecoy")
        assert t.height == 3
        assert d.height == 0
        # Cached frames are downcast Float64->Float32 for transfer efficiency.
        np.testing.assert_allclose(t["y"].to_numpy(), [0.1, 0.5, 0.2], rtol=1e-5)


# --------------------------------------------------------------------------- #
# Checklist 3 / 7 — args, state deps, vue identity                            #
# --------------------------------------------------------------------------- #
class TestArgsAndState:
    def test_component_args_series_names_and_colors(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_args",
            data=deconv_fdr_data,
            mode="deconv",
            title="FDR Plot",
            cache_path=str(temp_cache_dir),
        )
        args = comp._get_component_args()
        assert args["componentType"] == "PlotlyDensity"
        assert args["targetName"] == "Target QScores"
        assert args["decoyName"] == "Decoy QScores"
        assert args["targetColor"] == "green"
        assert args["decoyColor"] == "red"
        assert args["xLabel"] == "QScore"
        assert args["yLabel"] == "Density"
        assert args["title"] == "FDR Plot"
        assert args["interactivity"] == {}

    def test_state_dependencies_empty(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_state",
            data=deconv_fdr_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        assert comp.get_state_dependencies() == []
        assert comp.get_filters_mapping() == {}
        assert comp.get_interactivity_mapping() == {}

    def test_vue_name_and_data_key(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_vue",
            data=deconv_fdr_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        assert comp._get_vue_component_name() == "PlotlyDensity"
        assert comp._get_data_key() == "densityTarget"

    def test_prepare_vue_data_ignores_state(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp = DensityPlot(
            cache_id="dp_prepare",
            data=deconv_fdr_data,
            mode="deconv",
            cache_path=str(temp_cache_dir),
        )
        out_a = comp._prepare_vue_data({})
        out_b = comp._prepare_vue_data({"scanIndex": 5, "massIndex": 2})
        assert out_a["_hash"] == out_b["_hash"]  # state has no effect
        assert len(out_a["densityTarget"]) == 200
        assert "densityDecoy" in out_a


# --------------------------------------------------------------------------- #
# Cache reconstruction                                                         #
# --------------------------------------------------------------------------- #
class TestCacheReconstruction:
    def test_reconstruct_from_cache(
        self, mock_streamlit, temp_cache_dir, deconv_fdr_data
    ):
        comp1 = DensityPlot(
            cache_id="dp_reconstruct",
            data=deconv_fdr_data,
            mode="deconv",
            title="FDR Plot",
            cache_path=str(temp_cache_dir),
        )
        comp2 = DensityPlot(
            cache_id="dp_reconstruct",
            cache_path=str(temp_cache_dir),
        )
        t1 = _collect(comp1, "densityTarget")
        t2 = _collect(comp2, "densityTarget")
        assert t1.height == t2.height == 200
        np.testing.assert_allclose(t1["y"].to_numpy(), t2["y"].to_numpy(), rtol=1e-4)
        # Config restored
        assert comp2._target_name == "Target QScores"
        assert comp2.get_state_dependencies() == []
