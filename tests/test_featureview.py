"""Tests for FeatureView component."""

import polars as pl
import pytest

from openms_insight import FeatureView


@pytest.fixture
def sample_feature_traces() -> pl.LazyFrame:
    """Long-format trace points for two feature groups.

    fg 0: charge 2 (2 pts), charge 3 (2 pts)
    fg 1: charge 4 (3 pts)
    """
    return pl.LazyFrame(
        {
            "feature_group": [0, 0, 0, 0, 1, 1, 1],
            "charge": [2, 2, 3, 3, 4, 4, 4],
            "mz": [500.0, 500.1, 333.3, 333.4, 250.0, 250.1, 250.2],
            "rt": [10.0, 11.0, 10.0, 11.0, 20.0, 21.0, 22.0],
            "intensity": [1000.0, 1200.0, 800.0, 900.0, 1500.0, 1700.0, 1600.0],
            "isotope": [0, 1, 0, 1, 0, 1, 2],
        }
    )


class TestFeatureViewInit:
    def test_init(self, mock_streamlit, temp_cache_dir, sample_feature_traces):
        fv = FeatureView(
            cache_id="fv_init",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        assert fv._get_vue_component_name() == "PlotlyFeatureView"
        assert fv._get_data_key() == "featureData"

    def test_missing_column(
        self, mock_streamlit, temp_cache_dir, sample_feature_traces
    ):
        with pytest.raises(ValueError, match="not found in data"):
            FeatureView(
                cache_id="fv_missing",
                data=sample_feature_traces,
                intensity_column="nope",
                cache_path=str(temp_cache_dir),
            )


class TestFeatureViewFiltering:
    def test_filter_by_group(
        self, mock_streamlit, temp_cache_dir, sample_feature_traces
    ):
        fv = FeatureView(
            cache_id="fv_filter",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        vue_data = fv._prepare_vue_data({"featureGroup": 0})
        df = vue_data["featureData"]
        assert len(df) == 4
        assert set(df["feature_group"]) == {0}
        assert set(df["charge"]) == {2, 3}

    def test_empty_without_selection(
        self, mock_streamlit, temp_cache_dir, sample_feature_traces
    ):
        fv = FeatureView(
            cache_id="fv_empty",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            cache_path=str(temp_cache_dir),
        )
        assert len(fv._prepare_vue_data({})["featureData"]) == 0

    def test_vue_data_contract(
        self, mock_streamlit, temp_cache_dir, sample_feature_traces
    ):
        fv = FeatureView(
            cache_id="fv_contract",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        vue_data = fv._prepare_vue_data({"featureGroup": 1})
        assert "featureData" in vue_data
        assert "_hash" in vue_data
        for col in ("charge", "mz", "rt", "intensity"):
            assert col in vue_data["featureData"].columns


class TestFeatureViewComponentArgs:
    def test_args(self, mock_streamlit, temp_cache_dir, sample_feature_traces):
        fv = FeatureView(
            cache_id="fv_args",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            title="Feature group signals",
            cache_path=str(temp_cache_dir),
        )
        args = fv._get_component_args()
        assert args["componentType"] == "PlotlyFeatureView"
        assert args["title"] == "Feature group signals"
        assert args["xLabel"] == "m/z"
        assert args["yLabel"] == "retention time"
        assert args["zLabel"] == "intensity"

    def test_default_title(self, mock_streamlit, temp_cache_dir, sample_feature_traces):
        fv = FeatureView(
            cache_id="fv_deftitle",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            cache_path=str(temp_cache_dir),
        )
        assert fv._get_component_args()["title"] == "Feature group signals"


class TestFeatureViewExplodeTraces:
    """Tests for the FLASHQuant array -> long-format helper."""

    def test_explode_comma_joined_strings(self):
        # Shape mirrors connectTraceWithResult: per-group arrays of trace
        # arrays; MZs/RTs/Intensities are comma-joined strings per trace.
        quant_df = pl.DataFrame(
            {
                "FeatureGroupIndex": [0, 1],
                "Charges": [[2, 3], [4]],
                "IsotopeIndices": [[0, 1], [0]],
                "MZs": [["500.0,500.1", "333.3,333.4"], ["250.0,250.1,250.2"]],
                "RTs": [["10.0,11.0", "10.0,11.0"], ["20.0,21.0,22.0"]],
                "Intensities": [["1000,1200", "800,900"], ["1500,1700,1600"]],
            }
        )
        long_df = FeatureView.explode_traces(quant_df)
        # fg0: 2 traces x 2 pts = 4; fg1: 1 trace x 3 pts = 3
        assert long_df.height == 7
        assert set(long_df.columns) >= {
            "feature_group",
            "charge",
            "mz",
            "rt",
            "intensity",
            "isotope",
        }
        fg0 = long_df.filter(pl.col("feature_group") == 0)
        assert fg0.height == 4
        assert set(fg0["charge"].to_list()) == {2, 3}
        # First point of fg0/charge2 trace
        c2 = fg0.filter(pl.col("charge") == 2).sort("rt")
        assert c2["mz"].to_list() == [500.0, 500.1]
        assert c2["intensity"].to_list() == [1000.0, 1200.0]

    def test_explode_then_filter_roundtrip(self, mock_streamlit, temp_cache_dir):
        quant_df = pl.DataFrame(
            {
                "FeatureGroupIndex": [7],
                "Charges": [[2]],
                "IsotopeIndices": [[0]],
                "MZs": [["500.0,500.1"]],
                "RTs": [["10.0,11.0"]],
                "Intensities": [["1000,1200"]],
            }
        )
        long_df = FeatureView.explode_traces(quant_df)
        fv = FeatureView(
            cache_id="fv_roundtrip",
            data=long_df.lazy(),
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        df = fv._prepare_vue_data({"featureGroup": 7})["featureData"]
        assert len(df) == 2
        # Cache downcasts Float64 -> Float32 for transfer, so compare approximately.
        mzs = sorted(df["mz"])
        assert mzs[0] == pytest.approx(500.0, abs=1e-3)
        assert mzs[1] == pytest.approx(500.1, abs=1e-3)


class TestFeatureViewCacheReconstruction:
    def test_reconstruct(self, mock_streamlit, temp_cache_dir, sample_feature_traces):
        FeatureView(
            cache_id="fv_recon",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            title="Feature group signals",
            cache_path=str(temp_cache_dir),
        )
        fv2 = FeatureView(cache_id="fv_recon", cache_path=str(temp_cache_dir))
        assert fv2._title == "Feature group signals"
        assert fv2._filters == {"featureGroup": "feature_group"}
        assert fv2._isotope_column == "isotope"
        df = fv2._prepare_vue_data({"featureGroup": 0})["featureData"]
        assert len(df) == 4
