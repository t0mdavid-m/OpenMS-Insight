"""Unit tests for the LinePlot tagger extension.

Covers the three extension surfaces added for FLASHApp `PlotlyLineplotTagger`
parity, plus strict backward-compatibility guarantees:

  1. Second overlaid series (deconv sticks + raw/annotated peaks).
  2. Signal-peak membership markers (`SignalPeaks` → boolean column).
  3. Sequence-tag overlay: tag masses matched with abs(Δ) < tag_tolerance (1e-5).

Backward compat: when none of the new params are supplied, the component's
output and hash must be identical to the pre-extension behavior.

These mirror the existing contract-test harness (preprocess→_prepare_vue_data).
"""

import pytest

from openms_insight import LinePlot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(component_cls=LinePlot, **kwargs):
    """Construct a LinePlot, defaulting cache_path via the kwargs caller."""
    return component_cls(**kwargs)


def _vue(component, state=None):
    """Run the render-time data prep with a given selection state."""
    return component._prepare_vue_data(state or {})


# ---------------------------------------------------------------------------
# 1. Long-format peak explosion + scanIndex filter (contract checklist 1)
# ---------------------------------------------------------------------------


def test_scan_filter_returns_only_selected_scan(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _make(
        cache_id="tagger_scanfilter",
        data=sample_combined_spectrum_data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        interactivity={"massIndex": "peak_id"},
        x_column="MonoMass",
        y_column="SumIntensity",
    )
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    # Scan 1 has exactly 4 peaks
    assert len(df) == 4
    assert set(df["MonoMass"].tolist()) == {100.0, 200.0, 300.0, 400.0}


def test_empty_selection_yields_empty_spectrum(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _make(
        cache_id="tagger_empty",
        data=sample_combined_spectrum_data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        x_column="MonoMass",
        y_column="SumIntensity",
        filter_defaults={"scanIndex": -1},
    )
    # No scan matches index == -1
    result = _vue(plot, {})
    assert len(result["plotData"]) == 0


# ---------------------------------------------------------------------------
# 2. Second-series data path (contract checklist 3)
# ---------------------------------------------------------------------------


def test_second_series_columns_present(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _make(
        cache_id="tagger_second",
        data=sample_combined_spectrum_data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        x_column="MonoMass",
        y_column="SumIntensity",
        x2_column="MonoMass_Anno",
        y2_column="SumIntensity_Anno",
    )
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    # Both series columns must be projected through
    assert "MonoMass" in df.columns and "SumIntensity" in df.columns
    assert "MonoMass_Anno" in df.columns and "SumIntensity_Anno" in df.columns
    assert df["MonoMass_Anno"].tolist() == [101.0, 201.0, 301.0, 401.0]

    cfg = result["_plotConfig"]
    assert cfg["hasSecondSeries"] is True
    assert cfg["x2Column"] == "MonoMass_Anno"
    assert cfg["y2Column"] == "SumIntensity_Anno"

    args = plot._get_component_args()
    assert args["hasSecondSeries"] is True
    assert args["x2Column"] == "MonoMass_Anno"


def test_second_series_requires_both_columns(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    with pytest.raises(ValueError, match="Second series requires BOTH"):
        _make(
            cache_id="tagger_second_bad",
            data=sample_combined_spectrum_data,
            cache_path=str(temp_cache_dir),
            filters={"scanIndex": "index"},
            x_column="MonoMass",
            y_column="SumIntensity",
            x2_column="MonoMass_Anno",  # y2 missing
        )


# ---------------------------------------------------------------------------
# 3. SignalPeaks membership (contract checklist 4)
# ---------------------------------------------------------------------------


def test_signal_peak_membership_column(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _make(
        cache_id="tagger_signal",
        data=sample_combined_spectrum_data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        x_column="MonoMass",
        y_column="SumIntensity",
        signal_peak_column="is_signal",
    )
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    assert "is_signal" in df.columns
    # Scan 1 signal flags: peaks 100,300,400 are signal; 200 is not
    assert df["is_signal"].tolist() == [True, False, True, True]
    assert result["_plotConfig"]["signalPeakColumn"] == "is_signal"
    assert plot._get_component_args()["signalPeakColumn"] == "is_signal"


def test_signal_peak_invalid_column_raises(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    with pytest.raises(ValueError, match="signal_peak_column"):
        _make(
            cache_id="tagger_signal_bad",
            data=sample_combined_spectrum_data,
            cache_path=str(temp_cache_dir),
            filters={"scanIndex": "index"},
            x_column="MonoMass",
            y_column="SumIntensity",
            signal_peak_column="does_not_exist",
        )


# ---------------------------------------------------------------------------
# 4. Tag-mass overlay: abs(Δ) < 1e-5 (contract checklist 5)
# ---------------------------------------------------------------------------


def _tag_plot(cache_id, data, temp_cache_dir, **extra):
    return _make(
        cache_id=cache_id,
        data=data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        x_column="MonoMass",
        y_column="SumIntensity",
        tag_filters={"tag": "MonoMass"},
        tag_mass_column="MonoMass",
        **extra,
    )


def test_tag_overlay_highlights_matching_peaks(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot("tagger_tag_match", sample_combined_spectrum_data, temp_cache_dir)
    # Tag masses 200.0 and 400.0 exist exactly in scan 1
    result = _vue(plot, {"scanIndex": 1, "tag": [200.0, 400.0]})
    df = result["plotData"]
    assert "_tag_highlight" in df.columns
    assert "_tag_annotation" in df.columns
    # Peaks at 200 and 400 (indices 1 and 3) highlighted, 100 and 300 not
    assert df["_tag_highlight"].tolist() == [False, True, False, True]
    assert df["_tag_annotation"].tolist() == ["", "200.00", "", "400.00"]
    cfg = result["_plotConfig"]
    assert cfg["tagHighlightColumn"] == "_tag_highlight"
    assert cfg["tagAnnotationColumn"] == "_tag_annotation"


def test_tag_overlay_tolerance_boundary(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot("tagger_tag_tol", sample_combined_spectrum_data, temp_cache_dir)
    # Within tolerance (Δ = 5e-6 < 1e-5) → matches; just outside (Δ = 2e-5) → no match
    result = _vue(plot, {"scanIndex": 1, "tag": [200.0 + 5e-6, 300.0 + 2e-5]})
    flags = result["plotData"]["_tag_highlight"].tolist()
    # 200.x matches index 1; 300.x does NOT match index 2
    assert flags == [False, True, False, False]


def test_tag_overlay_accepts_selectedtag_dict(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    """FLASHApp selectedTag is an object with a `masses` array; accept dict form."""
    plot = _tag_plot("tagger_tag_dict", sample_combined_spectrum_data, temp_cache_dir)
    result = _vue(plot, {"scanIndex": 1, "tag": {"masses": [400.0]}})
    assert result["plotData"]["_tag_highlight"].tolist() == [False, False, False, True]


def test_no_tag_selected_no_highlight(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot("tagger_tag_none", sample_combined_spectrum_data, temp_cache_dir)
    # No tag value → no tag columns produced
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]
    assert "_tag_highlight" not in df.columns


def test_empty_tag_list_no_highlight(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot(
        "tagger_tag_emptylist", sample_combined_spectrum_data, temp_cache_dir
    )
    result = _vue(plot, {"scanIndex": 1, "tag": []})
    assert "_tag_highlight" not in result["plotData"].columns


def test_tag_identifier_in_state_dependencies(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot("tagger_tag_deps", sample_combined_spectrum_data, temp_cache_dir)
    deps = plot.get_state_dependencies()
    assert "scanIndex" in deps
    assert "tag" in deps


def test_tag_selection_changes_hash(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _tag_plot("tagger_tag_hash", sample_combined_spectrum_data, temp_cache_dir)
    h_a = _vue(plot, {"scanIndex": 1, "tag": [200.0]})["_hash"]
    h_b = _vue(plot, {"scanIndex": 1, "tag": [400.0]})["_hash"]
    assert h_a != h_b


# ---------------------------------------------------------------------------
# 5. Backward compatibility (HARD constraint: NO REGRESSION)
# ---------------------------------------------------------------------------


def test_backward_compat_identical_output_when_unused(
    mock_streamlit, temp_cache_dir, sample_lineplot_data
):
    """A plain LinePlot (no new params) must behave exactly as before.

    The new args carry None/False and the tagger columns must be absent.
    """
    common = {
        "data": sample_lineplot_data,
        "cache_path": str(temp_cache_dir),
        "x_column": "mass",
        "y_column": "intensity",
        "filters": {"scanIndex": "scan_id"},
    }
    plot = _make(cache_id="bc_plot", **common)
    result = _vue(plot, {"scanIndex": 1})
    df = result["plotData"]

    # No tagger columns leak into the payload
    for leaked in ("_tag_highlight", "_tag_annotation"):
        assert leaked not in df.columns

    cfg = result["_plotConfig"]
    assert cfg["hasSecondSeries"] is False
    assert cfg["x2Column"] is None
    assert cfg["y2Column"] is None
    assert cfg["signalPeakColumn"] is None
    assert cfg["tagHighlightColumn"] is None
    assert cfg["tagAnnotationColumn"] is None

    # State dependencies unchanged (only the base filter identifier)
    assert plot.get_state_dependencies() == ["scanIndex"]

    # Component args include the new keys but all disabled
    args = plot._get_component_args()
    assert args["hasSecondSeries"] is False
    assert args["x2Column"] is None
    assert args["tagHighlightColumn"] is None


def test_backward_compat_hash_stable_across_versions(
    mock_streamlit, temp_cache_dir, sample_lineplot_data
):
    """Two identical plain plots produce the same hash (deterministic, no tag salt)."""
    common = {
        "data": sample_lineplot_data,
        "cache_path": str(temp_cache_dir),
        "x_column": "mass",
        "y_column": "intensity",
        "filters": {"scanIndex": "scan_id"},
    }
    h1 = _vue(_make(cache_id="bc_h1", **common), {"scanIndex": 1})["_hash"]
    h2 = _vue(_make(cache_id="bc_h2", **common), {"scanIndex": 1})["_hash"]
    assert h1 == h2
    # Plain hash must not carry the tag salt suffix
    assert "_tag" not in h1


def test_strip_dynamic_columns_removes_tag_columns(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    """Cache base must not retain stale tag columns."""
    plot = _tag_plot("tagger_strip", sample_combined_spectrum_data, temp_cache_dir)
    result = _vue(plot, {"scanIndex": 1, "tag": [200.0]})
    assert "_tag_highlight" in result["plotData"].columns
    stripped = plot._strip_dynamic_columns(result)
    assert "_tag_highlight" not in stripped["plotData"].columns
    assert "_tag_annotation" not in stripped["plotData"].columns


# ---------------------------------------------------------------------------
# 6. Combined: all three extensions together (parity smoke test)
# ---------------------------------------------------------------------------


def test_all_extensions_together(
    mock_streamlit, temp_cache_dir, sample_combined_spectrum_data
):
    plot = _make(
        cache_id="tagger_all",
        data=sample_combined_spectrum_data,
        cache_path=str(temp_cache_dir),
        filters={"scanIndex": "index"},
        interactivity={"massIndex": "peak_id"},
        x_column="MonoMass",
        y_column="SumIntensity",
        x2_column="MonoMass_Anno",
        y2_column="SumIntensity_Anno",
        signal_peak_column="is_signal",
        tag_filters={"tag": "MonoMass"},
        tag_mass_column="MonoMass",
        title="Augmented Deconvolved Spectrum",
        x_label="Monoisotopic Mass",
        y_label="Intensity",
    )
    result = _vue(plot, {"scanIndex": 1, "tag": [200.0, 400.0]})
    df = result["plotData"]
    cfg = result["_plotConfig"]

    # Series 1 + series 2 + signal + tag all present
    assert {
        "MonoMass",
        "SumIntensity",
        "MonoMass_Anno",
        "SumIntensity_Anno",
        "is_signal",
        "_tag_highlight",
        "_tag_annotation",
    }.issubset(set(df.columns))
    assert cfg["hasSecondSeries"] is True
    assert cfg["signalPeakColumn"] == "is_signal"
    assert cfg["tagHighlightColumn"] == "_tag_highlight"

    args = plot._get_component_args()
    assert args["title"] == "Augmented Deconvolved Spectrum"
    assert args["xLabel"] == "Monoisotopic Mass"
    assert args["yLabel"] == "Intensity"
