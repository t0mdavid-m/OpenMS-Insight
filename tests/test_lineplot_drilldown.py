"""Unit tests for the LinePlot charge drill-down + parity-fix Python API.

Covers the new OPTIONAL/backward-compatible params added for FLASHApp
PlotlyLineplot/Tagger parity:

  * signal_mz_column / signal_charge_column / signal_intensity_column
    (per-row signal-peak arrays for the charge-state drill-down sub-view);
  * show_signal_markers (gate for the non-legacy signal-peak markers, default OFF);
  * tag-walk nTerminal / selectedAA anchoring forwarded into the ``tagWalk`` payload.

All assertions are against the Python render-time contract
(``_prepare_vue_data`` / ``_get_component_args`` / ``_build_plot_config``); the
Vue layer reads these. Backward-compat: absent params must not change output.
"""

import polars as pl
import pytest

from openms_insight import LinePlot


def _drilldown_data() -> pl.LazyFrame:
    """Long-format deconv spectrum with per-row signal-peak arrays.

    Scan 1 has 3 deconv peaks. Each row's signal arrays are aligned 1:1:
      - signal_mzs[i]:        list[float] of signal-peak m/z
      - signal_charges[i]:    list[int]   of signal-peak charges
      - signal_intensities[i]: list[float] of signal-peak intensities
    """
    return pl.LazyFrame(
        {
            "index": [1, 1, 1, 2, 2],
            "peak_id": [10, 11, 12, 20, 21],
            "MonoMass": [1000.0, 2000.0, 3000.0, 1500.0, 2500.0],
            "SumIntensity": [500.0, 900.0, 700.0, 400.0, 600.0],
            "signal_mzs": [
                [500.1, 500.2, 334.0],
                [667.0, 1000.5],
                [],
                [750.0],
                [625.0, 626.0],
            ],
            "signal_charges": [
                [2, 2, 3],
                [3, 2],
                [],
                [2],
                [4, 4],
            ],
            "signal_intensities": [
                [100.0, 200.0, 150.0],
                [300.0, 100.0],
                [],
                [50.0],
                [10.0, 20.0],
            ],
        }
    )


def _vue(component, state=None):
    return component._prepare_vue_data(state or {})


def _make(cache_id, temp_cache_dir, **extra):
    return LinePlot(
        cache_id=cache_id,
        data=_drilldown_data(),
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        interactivity={"massIndex": "peak_id"},
        x_column="MonoMass",
        y_column="SumIntensity",
        **extra,
    )


# ---------------------------------------------------------------------------
# Charge drill-down columns + config
# ---------------------------------------------------------------------------


def test_signal_arrays_projected_through(mock_streamlit, temp_cache_dir):
    plot = _make(
        "dd_cols",
        temp_cache_dir,
        signal_mz_column="signal_mzs",
        signal_charge_column="signal_charges",
        signal_intensity_column="signal_intensities",
    )
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    assert {"signal_mzs", "signal_charges", "signal_intensities"}.issubset(df.columns)
    # First deconv row's signal arrays survive intact (pandas cells are np arrays).
    assert list(df["signal_mzs"].iloc[0]) == [500.1, 500.2, 334.0]
    assert list(df["signal_charges"].iloc[0]) == [2, 2, 3]

    cfg = result["_plotConfig"]
    assert cfg["signalMzColumn"] == "signal_mzs"
    assert cfg["signalChargeColumn"] == "signal_charges"
    assert cfg["signalIntensityColumn"] == "signal_intensities"
    assert cfg["hasSignalDrilldown"] is True


def test_component_args_advertise_drilldown(mock_streamlit, temp_cache_dir):
    plot = _make(
        "dd_args",
        temp_cache_dir,
        signal_mz_column="signal_mzs",
        signal_charge_column="signal_charges",
        signal_intensity_column="signal_intensities",
    )
    args = plot._get_component_args()
    assert args["signalMzColumn"] == "signal_mzs"
    assert args["signalChargeColumn"] == "signal_charges"
    assert args["signalIntensityColumn"] == "signal_intensities"
    assert args["hasSignalDrilldown"] is True
    # Markers OFF by default (legacy parity)
    assert args["showSignalMarkers"] is False


def test_drilldown_requires_mz_and_charge(mock_streamlit, temp_cache_dir):
    """hasSignalDrilldown is True only when BOTH mz + charge columns are wired."""
    plot = _make("dd_mzonly", temp_cache_dir, signal_mz_column="signal_mzs")
    args = plot._get_component_args()
    assert args["hasSignalDrilldown"] is False


def test_invalid_signal_column_raises(mock_streamlit, temp_cache_dir):
    with pytest.raises(ValueError, match="signal_mz_column"):
        _make("dd_bad", temp_cache_dir, signal_mz_column="nope")


# ---------------------------------------------------------------------------
# show_signal_markers gate (P2)
# ---------------------------------------------------------------------------


def test_show_signal_markers_flag(mock_streamlit, temp_cache_dir):
    plot = _make("dd_markers", temp_cache_dir, show_signal_markers=True)
    assert plot._get_component_args()["showSignalMarkers"] is True
    assert _vue(plot, {"scanIndex": 1})["_plotConfig"]["showSignalMarkers"] is True


def test_show_signal_markers_default_off(mock_streamlit, temp_cache_dir):
    plot = _make("dd_markers_off", temp_cache_dir)
    assert plot._get_component_args()["showSignalMarkers"] is False


# ---------------------------------------------------------------------------
# Tag-walk anchoring: nTerminal / selectedAA forwarded into tagWalk (P1)
# ---------------------------------------------------------------------------


def _tag_plot(cache_id, temp_cache_dir):
    return LinePlot(
        cache_id=cache_id,
        data=_drilldown_data(),
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        x_column="MonoMass",
        y_column="SumIntensity",
        tag_filters={"tag": "MonoMass"},
        tag_mass_column="MonoMass",
    )


def test_tag_walk_forwards_anchoring(mock_streamlit, temp_cache_dir):
    plot = _tag_plot("dd_walk_anchor", temp_cache_dir)
    result = _vue(
        plot,
        {
            "scanIndex": 1,
            "tag": {
                "masses": [1000.0, 2000.0, 3000.0],
                "residues": ["H", "L"],
                "nTerminal": False,
                "selectedAA": 1,
            },
        },
    )
    walk = result["tagWalk"]
    assert walk["masses"] == [1000.0, 2000.0, 3000.0]
    assert walk["residues"] == ["H", "L"]
    assert walk["nTerminal"] is False
    assert walk["selectedAA"] == 1


def test_tag_walk_anchoring_optional(mock_streamlit, temp_cache_dir):
    """Absent nTerminal/selectedAA → keys omitted (backward compatible)."""
    plot = _tag_plot("dd_walk_noanchor", temp_cache_dir)
    result = _vue(
        plot,
        {"scanIndex": 1, "tag": {"masses": [1000.0, 2000.0], "residues": ["H"]}},
    )
    walk = result["tagWalk"]
    assert "nTerminal" not in walk
    assert "selectedAA" not in walk


def test_tag_walk_anchoring_changes_hash(mock_streamlit, temp_cache_dir):
    """Different selectedAA over identical masses/residues → different hash."""
    plot = _tag_plot("dd_walk_anchor_hash", temp_cache_dir)
    base = {"masses": [1000.0, 2000.0, 3000.0], "residues": ["H", "L"]}
    h_a = _vue(plot, {"scanIndex": 1, "tag": {**base, "selectedAA": 0}})["_hash"]
    h_b = _vue(plot, {"scanIndex": 1, "tag": {**base, "selectedAA": 1}})["_hash"]
    assert h_a != h_b


def test_tag_walk_invalid_selectedaa_ignored(mock_streamlit, temp_cache_dir):
    """Non-integer selectedAA is dropped rather than raising."""
    plot = _tag_plot("dd_walk_badaa", temp_cache_dir)
    result = _vue(
        plot,
        {
            "scanIndex": 1,
            "tag": {"masses": [1000.0, 2000.0], "residues": ["H"], "selectedAA": "x"},
        },
    )
    assert "selectedAA" not in result["tagWalk"]


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_backward_compat_no_drilldown_columns(mock_streamlit, temp_cache_dir):
    """Plain plot (no signal params) must not leak drill-down columns/flags."""
    plot = _make("dd_bc", temp_cache_dir)
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    for leaked in ("signal_mzs", "signal_charges", "signal_intensities"):
        assert leaked not in df.columns
    cfg = result["_plotConfig"]
    assert cfg["signalMzColumn"] is None
    assert cfg["signalChargeColumn"] is None
    assert cfg["hasSignalDrilldown"] is False
    assert cfg["showSignalMarkers"] is False
