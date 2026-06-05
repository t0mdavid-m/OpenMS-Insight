"""Tests for LinePlot(mode="density") — target/decoy KDE / FDR plot.

The density path consumes a PRECOMPUTED tidy long {x, y, group} frame and emits
it under `plotData`. An optional `kde_from` builds the curves from raw scores via
a LAZY scipy import (scipy is NOT a hard dependency).
"""

import pandas as pd
import pytest

from openms_insight import LinePlot


def _make(temp_cache_dir, data, **overrides):
    """Construct a density LinePlot via the grouped ``.density(...)`` factory."""
    defaults = {
        "cache_id": "test_density",
        "data": data,
        "cache_path": str(temp_cache_dir),
    }
    defaults.update(overrides)
    return LinePlot.density(**defaults)


class TestDensityPrepareVueData:
    def test_prepare_vue_data_returns_dict_with_hash(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(temp_cache_dir, sample_density_data)
        result = comp._prepare_vue_data({})
        assert isinstance(result, dict)
        assert "_hash" in result
        assert isinstance(result["_hash"], str)

    def test_emits_tidy_long_with_group(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(temp_cache_dir, sample_density_data)
        result = comp._prepare_vue_data({})
        df = result["plotData"]
        assert isinstance(df, pd.DataFrame)
        assert "group" in df.columns
        assert set(df["group"]).issubset({"target", "decoy"})
        # x, y columns present
        assert "x" in df.columns
        assert "y" in df.columns

    def test_empty_decoy_ok(
        self, mock_streamlit, temp_cache_dir, sample_density_data_target_only
    ):
        """Target-only input -> only target rows; no exception (parity)."""
        comp = _make(temp_cache_dir, sample_density_data_target_only)
        result = comp._prepare_vue_data({})
        df = result["plotData"]
        assert set(df["group"]) == {"target"}

    def test_state_dependencies_empty(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(temp_cache_dir, sample_density_data)
        assert comp.get_state_dependencies() == []

    def test_hash_stable_across_states(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        """Density is static — hash does not depend on selection state."""
        comp = _make(temp_cache_dir, sample_density_data)
        h1 = comp._prepare_vue_data({})["_hash"]
        h2 = comp._prepare_vue_data({"spectrum": 5, "anything": "x"})["_hash"]
        assert h1 == h2

    def test_plot_config_carries_mode_and_columns(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(temp_cache_dir, sample_density_data)
        cfg = comp._prepare_vue_data({})["_plotConfig"]
        assert cfg["mode"] == "density"
        assert cfg["xColumn"] == "x"
        assert cfg["yColumn"] == "y"
        assert cfg["categoryColumn"] == "group"
        assert cfg["targetValue"] == "target"
        assert cfg["decoyValue"] == "decoy"


class TestDensityKdeFromRawScores:
    def test_kde_from_raw_scores(
        self, mock_streamlit, temp_cache_dir, sample_density_scores
    ):
        """With kde_from + scipy, output has exactly 2*kde_points rows; y >= 0."""
        pytest.importorskip("scipy")
        comp = _make(
            temp_cache_dir,
            sample_density_scores,
            cache_id="test_density_kde",
            kde_from={"score": "Qscore", "label": "label"},
            kde_points=200,
            target_value="target",
            decoy_value="decoy",
        )
        result = comp._prepare_vue_data({})
        df = result["plotData"]
        # 200 per group for a two-class input = 400 rows total
        assert len(df) == 400
        assert (df["y"] >= 0).all()
        assert set(df["group"]) == {"target", "decoy"}

    def test_kde_from_requires_scipy(self, mock_streamlit, temp_cache_dir):
        """When scipy is missing, kde_from raises a clear ImportError."""
        try:
            import scipy  # noqa: F401

            pytest.skip("scipy is installed; cannot test the missing-scipy error")
        except ImportError:
            pass

        import polars as pl

        data = pl.LazyFrame(
            {
                "Qscore": [0.1, 0.5, 0.9, 0.2, 0.6],
                "label": ["target", "target", "target", "decoy", "decoy"],
            }
        )
        with pytest.raises(ImportError, match="scipy"):
            _make(
                temp_cache_dir,
                data,
                cache_id="test_density_no_scipy",
                kde_from={"score": "Qscore", "label": "label"},
            )


class TestDensityComponentArgs:
    def test_component_args(self, mock_streamlit, temp_cache_dir, sample_density_data):
        comp = _make(temp_cache_dir, sample_density_data)
        args = comp._get_component_args()
        assert args["componentType"] == "PlotlyDensityPlot"
        assert args["mode"] == "density"
        assert args["xLabel"] == "QScore"
        assert args["yLabel"] == "Density"
        assert args["styling"]["targetColor"] == "green"
        assert args["styling"]["decoyColor"] == "red"
        assert args["categoryColumn"] == "group"
        assert args["targetValue"] == "target"
        assert args["decoyValue"] == "decoy"
        assert args["scoreLabel"] == "QScore"

    def test_score_label_configurable(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(
            temp_cache_dir,
            sample_density_data,
            config={"scoreLabel": "ProteoformLevelQvalue"},
        )
        args = comp._get_component_args()
        assert args["scoreLabel"] == "ProteoformLevelQvalue"

    def test_trace_labels_default_none_and_configurable(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        # Default: no explicit trace labels -> Vue falls back to
        # f"{scoreLabel} (Target|Decoy)".
        default_args = _make(temp_cache_dir, sample_density_data)._get_component_args()
        assert default_args["targetLabel"] is None
        assert default_args["decoyLabel"] is None
        # Configurable -> oracle FDR legend names.
        comp = _make(
            temp_cache_dir,
            sample_density_data,
            config={"targetLabel": "Target QScores", "decoyLabel": "Decoy QScores"},
        )
        args = comp._get_component_args()
        assert args["targetLabel"] == "Target QScores"
        assert args["decoyLabel"] == "Decoy QScores"

    def test_vue_component_name(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(temp_cache_dir, sample_density_data)
        assert comp._get_vue_component_name() == "PlotlyDensityPlot"


class TestDensityCacheConfig:
    def test_cache_config_roundtrip(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        comp = _make(
            temp_cache_dir,
            sample_density_data,
            category_column="group",
            target_value="tgt",
            decoy_value="dcy",
            kde_points=123,
        )
        # kde_from is a non-default optional convenience; set it on the instance
        # (constructing with a real kde_from would trigger the scipy KDE path).
        comp._kde_from = {"score": "s", "label": "l"}
        config = comp._get_cache_config()
        assert config["mode"] == "density"
        assert config["category_column"] == "group"
        assert config["target_value"] == "tgt"
        assert config["decoy_value"] == "dcy"
        assert config["kde_from"] == {"score": "s", "label": "l"}
        assert config["kde_points"] == 123

        restored = _make(
            temp_cache_dir,
            sample_density_data,
            cache_id="test_density_restore",
        )
        restored._restore_cache_config(config)
        assert restored._mode == "density"
        assert restored._category_column == "group"
        assert restored._target_value == "tgt"
        assert restored._decoy_value == "dcy"
        assert restored._kde_from == {"score": "s", "label": "l"}
        assert restored._kde_points == 123

    def test_cache_reconstruction_no_error(
        self, mock_streamlit, temp_cache_dir, sample_density_data
    ):
        """A density LinePlot reloaded purely from cache works."""
        _make(temp_cache_dir, sample_density_data, cache_id="density_reload")
        restored = LinePlot(cache_id="density_reload", cache_path=str(temp_cache_dir))
        assert restored._mode == "density"
        result = restored._prepare_vue_data({})
        assert "plotData" in result
