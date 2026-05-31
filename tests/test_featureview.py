"""Tests for the FeatureView (FLASHQuant) component.

Covers the FeatureView.md verification checklist (functionality slice):
- 10 feature-group table columns (titles + fields).
- trace3DgraphData parity: one trace per unique charge, name "Charge: {z}",
  color #3366CC, -1e3 sentinels bracketing each mass trace.
- comma-string MZs/RTs/Intensities parsed to floats; maximumIntensity = max
  real intensity.
- no feature group selected -> empty trace list (blank 3D plot).
- empty / zero-trace feature group renders without crash; no -inf max.
- internal selector + cache config + reconstruction.
"""

from pathlib import Path

import polars as pl
import pytest

from openms_insight.components.featureview import (
    DEFAULT_LINE_COLOR,
    FEATURE_GROUP_COLUMN_DEFINITIONS,
    SENTINEL_INTENSITY,
    FeatureView,
    compute_trace_3d_data,
)


@pytest.fixture
def sample_featureview_data() -> pl.LazyFrame:
    """Two feature groups with comma-string trace encoding.

    FG 0: charges [1, 1, 2] -> two traces of charge 1 (grouped), one of charge 2.
    FG 1: charges [3]       -> single trace, single charge.
    """
    return pl.LazyFrame(
        {
            "FeatureGroupIndex": [0, 1],
            "MonoisotopicMass": [1000.0, 2000.0],
            "AverageMass": [1000.5, 2000.5],
            "StartRetentionTime(FWHM)": [10.0, 20.0],
            "EndRetentionTime(FWHM)": [12.0, 22.0],
            "HighestApexRetentionTime": [11.0, 21.0],
            "FeatureGroupQuantity": [5000.0, 9000.0],
            "AllAreaUnderTheCurve": [1.0, 2.0],
            "MinCharge": [1, 3],
            "MaxCharge": [2, 3],
            "MostAbundantFeatureCharge": [1, 3],
            "IsotopeCosineScore": [0.99, 0.95],
            "Charges": [[1, 1, 2], [3]],
            "IsotopeIndices": [[0, 1, 0], [0]],
            "CentroidMzs": [[500.0, 501.0, 250.0], [667.0]],
            "RTs": [["10.0,10.5", "10.0,10.5", "11.0,11.5"], ["20.0,20.5"]],
            "MZs": [["500.0,500.1", "501.0,501.1", "250.0,250.1"], ["667.0,667.1"]],
            "Intensities": [["100,200", "150,250", "300,400"], ["500,600"]],
        }
    )


# --------------------------------------------------------------------------- #
# compute_trace_3d_data (algorithm parity)
# --------------------------------------------------------------------------- #
class TestComputeTrace3DData:
    def _fg0(self):
        return {
            "Charges": [1, 1, 2],
            "MZs": ["500.0,500.1", "501.0,501.1", "250.0,250.1"],
            "RTs": ["10.0,10.5", "10.0,10.5", "11.0,11.5"],
            "Intensities": ["100,200", "150,250", "300,400"],
        }

    def test_one_trace_per_unique_charge(self):
        result = compute_trace_3d_data(self._fg0())
        traces = result["traces"]
        # Unique charges {1, 2} -> 2 traces.
        assert len(traces) == 2
        names = {t["name"] for t in traces}
        assert names == {"Charge: 1", "Charge: 2"}

    def test_trace_color_and_type(self):
        traces = compute_trace_3d_data(self._fg0())["traces"]
        for t in traces:
            assert t["line"]["color"] == DEFAULT_LINE_COLOR  # #3366CC
            assert t["type"] == "scatter3d"
            assert t["mode"] == "lines"

    def test_sentinels_bracket_each_trace(self):
        traces = compute_trace_3d_data(self._fg0())["traces"]
        charge1 = next(t for t in traces if t["name"] == "Charge: 1")
        # Charge 1 has TWO mass traces; each contributes:
        #   leading sentinel + 2 real points + trailing sentinel = 4 z-values.
        # So 2 traces -> 8 z-values, with sentinel at positions 0,3,4,7.
        z = charge1["z"]
        assert len(z) == 8
        assert z[0] == SENTINEL_INTENSITY
        assert z[3] == SENTINEL_INTENSITY
        assert z[4] == SENTINEL_INTENSITY
        assert z[7] == SENTINEL_INTENSITY
        # Real intensities present in between.
        assert z[1] == 100.0 and z[2] == 200.0
        assert z[5] == 150.0 and z[6] == 250.0

    def test_comma_strings_parsed_to_floats(self):
        traces = compute_trace_3d_data(self._fg0())["traces"]
        charge2 = next(t for t in traces if t["name"] == "Charge: 2")
        # x = [sentinel-x(=250.0), 250.0, 250.1, trailing-x(NaN)]
        assert charge2["x"][1] == 250.0
        assert charge2["x"][2] == pytest.approx(250.1)
        assert charge2["z"][1] == 300.0
        assert charge2["z"][2] == 400.0

    def test_maximum_intensity_is_max_real_intensity(self):
        result = compute_trace_3d_data(self._fg0())
        # Real intensities: 100,200,150,250,300,400 -> max 400.
        assert result["maximumIntensity"] == 400.0

    def test_empty_feature_group_returns_empty(self):
        assert compute_trace_3d_data({})["traces"] == []
        assert compute_trace_3d_data({})["maximumIntensity"] == 0.0

    def test_empty_charges_returns_empty_no_inf(self):
        fg = {"Charges": [], "MZs": [], "RTs": [], "Intensities": []}
        result = compute_trace_3d_data(fg)
        assert result["traces"] == []
        # Must not be -inf.
        assert result["maximumIntensity"] == 0.0

    def test_single_point_trace_no_crash(self):
        fg = {
            "Charges": [5],
            "MZs": ["700.0"],
            "RTs": ["30.0"],
            "Intensities": ["999"],
        }
        result = compute_trace_3d_data(fg)
        assert len(result["traces"]) == 1
        assert result["traces"][0]["name"] == "Charge: 5"
        assert result["maximumIntensity"] == 999.0


# --------------------------------------------------------------------------- #
# FeatureView component
# --------------------------------------------------------------------------- #
class TestFeatureViewInit:
    def test_init_with_lazyframe(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv = FeatureView(
            cache_id="test_fv",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        assert fv is not None
        assert fv._get_vue_component_name() == "PlotlyFeatureView"
        assert fv._get_data_key() == "quant_data"

    def test_init_with_pandas(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        pdf = sample_featureview_data.collect().to_pandas()
        fv = FeatureView(
            cache_id="test_fv_pd",
            data=pdf,
            cache_path=str(temp_cache_dir),
        )
        assert fv is not None

    def test_init_rejects_non_featuregroup_frame(
        self, mock_streamlit, temp_cache_dir: Path
    ):
        bad = pl.LazyFrame({"foo": [1, 2], "bar": [3, 4]})
        with pytest.raises(ValueError, match="none of the configured table columns"):
            FeatureView(
                cache_id="test_fv_bad",
                data=bad,
                cache_path=str(temp_cache_dir),
            )


class TestFeatureViewColumns:
    def test_ten_distinct_columns(self):
        assert len(FEATURE_GROUP_COLUMN_DEFINITIONS) == 10
        fields = [c["field"] for c in FEATURE_GROUP_COLUMN_DEFINITIONS]
        # No duplicate field (the source listed FeatureGroupQuantity twice; we
        # reproduce ONE).
        assert len(set(fields)) == 10
        assert fields.count("FeatureGroupQuantity") == 1

    def test_column_titles_and_fields(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv = FeatureView(
            cache_id="test_fv_cols",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        args = fv._get_component_args()
        cols = args["columnDefinitions"]
        expected = [
            ("Index", "FeatureGroupIndex"),
            ("Monoisotopic Mass", "MonoisotopicMass"),
            ("Average Mass", "AverageMass"),
            ("Start Retention Time (FWHM)", "StartRetentionTime(FWHM)"),
            ("End Retention Time (FWHM)", "EndRetentionTime(FWHM)"),
            ("Feature Group Quantity", "FeatureGroupQuantity"),
            ("Min Charge", "MinCharge"),
            ("Max Charge", "MaxCharge"),
            ("Most Abundant Charge", "MostAbundantFeatureCharge"),
            ("Isotope Cosine Score", "IsotopeCosineScore"),
        ]
        assert [(c["title"], c["field"]) for c in cols] == expected
        assert args["tableIndexField"] == "FeatureGroupIndex"
        assert args["defaultRow"] == 0


class TestFeatureViewComponentArgs:
    def test_plot_args(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv = FeatureView(
            cache_id="test_fv_args",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        args = fv._get_component_args()
        assert args["plotTitle"] == "Feature group signals"
        assert args["lineColor"] == "#3366CC"
        assert args["plotHeight"] == 800
        assert args["xAxisTitle"] == "m/z"
        assert args["yAxisTitle"] == "retention time"
        assert args["zAxisTitle"] == "intensity"
        assert args["sentinelIntensity"] == SENTINEL_INTENSITY
        assert args["selectionIdentifier"] == "selectedFeatureGroupIndex"

    def test_no_external_state_dependencies(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv = FeatureView(
            cache_id="test_fv_deps",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        # Standalone: consumes/emits no external state.
        assert fv.get_state_dependencies() == []
        assert fv.get_filter_identifiers() == []
        assert fv.get_interactivity_identifiers() == []


class TestFeatureViewPrepareVueData:
    def test_full_table_sent(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv = FeatureView(
            cache_id="test_fv_data",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        vue_data = fv._prepare_vue_data({})
        assert "quant_data" in vue_data
        assert "_hash" in vue_data
        df = vue_data["quant_data"]
        assert len(df) == 2  # two feature groups
        # List columns preserved for the 3D redraw.
        for col in ("Charges", "MZs", "RTs", "Intensities"):
            assert col in df.columns
        # The comma-string encoding survives.
        assert list(df["Charges"].iloc[0]) == [1, 1, 2]

    def test_prepare_then_compute_roundtrip(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        """End-to-end: data payload -> compute_trace_3d_data parity."""
        fv = FeatureView(
            cache_id="test_fv_roundtrip",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        df = fv._prepare_vue_data({})["quant_data"]
        fg = df.iloc[0].to_dict()
        result = compute_trace_3d_data(fg)
        names = {t["name"] for t in result["traces"]}
        assert names == {"Charge: 1", "Charge: 2"}
        assert result["maximumIntensity"] == 400.0


class TestFeatureViewCacheReconstruction:
    def test_reconstruct_from_cache(
        self, mock_streamlit, temp_cache_dir: Path, sample_featureview_data
    ):
        fv1 = FeatureView(
            cache_id="test_fv_reconstruct",
            data=sample_featureview_data,
            cache_path=str(temp_cache_dir),
        )
        fv2 = FeatureView(
            cache_id="test_fv_reconstruct",
            cache_path=str(temp_cache_dir),
        )
        # Config restored.
        args1 = fv1._get_component_args()
        args2 = fv2._get_component_args()
        assert args1["columnDefinitions"] == args2["columnDefinitions"]
        assert args2["plotTitle"] == "Feature group signals"
        assert args2["lineColor"] == "#3366CC"
        # Data restored.
        df2 = fv2._prepare_vue_data({})["quant_data"]
        assert len(df2) == 2
