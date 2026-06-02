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


def _count_break_sentinels(df, *, charge_column, trace_key_column):
    """Reference implementation of the Vue's per-charge sentinel-break count.

    Mirrors ``PlotlyFeatureView``'s ``data()``: within each charge the polyline
    is bracketed by a leading + trailing ``z=-1000`` sentinel, and (when a
    trace-key column is set) a 2-sentinel break is inserted between consecutive
    points whose trace-key differs. Each consecutive trace-key run therefore
    ends up bracketed like a standalone charge, giving exactly ``2`` sentinels
    per run. With no trace-key column every charge is a single run -> 2.

    Returns the total number of ``-1000`` z-values across all charge traces.

    ``df`` is the pandas payload returned by ``_prepare_vue_data`` (the exact
    rows, in order, handed to the Vue).
    """
    total = 0
    # Preserve row order within each charge (Plotly consumes rows as ordered).
    by_charge: dict = {}
    charges = list(df[charge_column])
    keys_col = (
        list(df[trace_key_column])
        if trace_key_column is not None
        else [None] * len(charges)
    )
    for charge, key in zip(charges, keys_col):
        by_charge.setdefault(charge, []).append(key)
    for keys in by_charge.values():
        if not keys:
            continue
        runs = 1
        for i in range(1, len(keys)):
            if trace_key_column is not None and keys[i] != keys[i - 1]:
                runs += 1
        total += 2 * runs
    return total


class TestFeatureViewTraceKeyColumn:
    """Per-trace polyline breaks within a charge via ``trace_key_column``.

    fg 0 has two charges; charge 2 carries TWO isotope traces (iso 0 then iso 1)
    and charge 3 carries TWO isotope traces, so with a trace-key column the
    breaks are inserted between the differing isotope runs within each charge.
    """

    @pytest.fixture
    def traces_with_isotope_runs(self) -> pl.LazyFrame:
        # Within fg 0 / charge 2: iso 0 (2 pts) then iso 1 (2 pts) -> 2 runs.
        # Within fg 0 / charge 3: iso 0 (1 pt) then iso 1 (1 pt) -> 2 runs.
        return pl.LazyFrame(
            {
                "feature_group": [0, 0, 0, 0, 0, 0],
                "charge": [2, 2, 2, 2, 3, 3],
                "isotope": [0, 0, 1, 1, 0, 1],
                "mz": [500.0, 500.1, 500.5, 500.6, 333.3, 333.8],
                "rt": [10.0, 11.0, 10.0, 11.0, 10.0, 10.0],
                "intensity": [1000.0, 1200.0, 800.0, 900.0, 700.0, 600.0],
            }
        )

    def test_trace_key_column_in_args(self, temp_cache_dir, traces_with_isotope_runs):
        fv = FeatureView(
            cache_id="fv_tk_args",
            data=traces_with_isotope_runs,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            trace_key_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        args = fv._get_component_args()
        assert args["traceKeyColumn"] == "isotope"
        assert fv._trace_key_column == "isotope"

    def test_trace_key_column_default_none(self, temp_cache_dir, sample_feature_traces):
        fv = FeatureView(
            cache_id="fv_tk_none",
            data=sample_feature_traces,
            filters={"featureGroup": "feature_group"},
            cache_path=str(temp_cache_dir),
        )
        # Default no-op: arg is None and the trace-key column is absent.
        assert fv._get_component_args()["traceKeyColumn"] is None
        assert fv._trace_key_column is None

    def test_missing_trace_key_column_raises(
        self, temp_cache_dir, sample_feature_traces
    ):
        with pytest.raises(ValueError, match="not found in data"):
            FeatureView(
                cache_id="fv_tk_missing",
                data=sample_feature_traces,
                trace_key_column="nope",
                cache_path=str(temp_cache_dir),
            )

    def test_trace_key_column_present_in_payload(
        self, temp_cache_dir, traces_with_isotope_runs
    ):
        fv = FeatureView(
            cache_id="fv_tk_payload",
            data=traces_with_isotope_runs,
            filters={"featureGroup": "feature_group"},
            trace_key_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        df = fv._prepare_vue_data({"featureGroup": 0})["featureData"]
        # The trace-key column must reach the Vue so it can break per trace.
        assert "isotope" in df.columns

    def test_break_sentinel_count_with_trace_key(
        self, temp_cache_dir, traces_with_isotope_runs
    ):
        fv = FeatureView(
            cache_id="fv_tk_count_on",
            data=traces_with_isotope_runs,
            filters={"featureGroup": "feature_group"},
            trace_key_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        df = fv._prepare_vue_data({"featureGroup": 0})["featureData"]
        # charge 2 -> 2 isotope runs -> 4 sentinels; charge 3 -> 2 runs -> 4.
        n = _count_break_sentinels(
            df, charge_column="charge", trace_key_column="isotope"
        )
        assert n == 8

    def test_break_sentinel_count_without_trace_key_unchanged(
        self, temp_cache_dir, traces_with_isotope_runs
    ):
        fv = FeatureView(
            cache_id="fv_tk_count_off",
            data=traces_with_isotope_runs,
            filters={"featureGroup": "feature_group"},
            cache_path=str(temp_cache_dir),
        )
        df = fv._prepare_vue_data({"featureGroup": 0})["featureData"]
        # No trace-key column: one polyline per charge -> exactly 2 sentinels
        # per charge (2 charges -> 4), regardless of isotope changes.
        n = _count_break_sentinels(df, charge_column="charge", trace_key_column=None)
        assert n == 4

    def test_trace_key_column_survives_cache_reconstruction(
        self, temp_cache_dir, traces_with_isotope_runs
    ):
        FeatureView(
            cache_id="fv_tk_recon",
            data=traces_with_isotope_runs,
            filters={"featureGroup": "feature_group"},
            isotope_column="isotope",
            trace_key_column="isotope",
            cache_path=str(temp_cache_dir),
        )
        fv2 = FeatureView(cache_id="fv_tk_recon", cache_path=str(temp_cache_dir))
        assert fv2._trace_key_column == "isotope"
        assert fv2._get_component_args()["traceKeyColumn"] == "isotope"


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
