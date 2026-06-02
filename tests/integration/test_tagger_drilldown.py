"""Integration: tagger drill-down routed through the generic selection store.

Simulates the store flow (tag click -> mass click -> back -> scan change) by
driving the state dict that the bridge would pass to `_prepare_vue_data`, and
asserts the derived drill-down level + emitted frames respond correctly.
"""

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def tagger_plot(temp_cache_dir, mock_streamlit, sample_tagger_data):
    return LinePlot(
        cache_id="tagger_integration",
        data=sample_tagger_data,
        cache_path=str(temp_cache_dir),
        mode="tagger",
        filters={"spectrum": "scan_id", "tag": "tag_id"},
        filter_defaults={"tagger_mass": None},
        interactivity={"tagger_mass": "peak_id"},
        x_column="MonoMass",
        y_column="SumIntensity",
        signal_peaks_column="SignalPeaks",
        mz_column="MonoMass_Anno",
        mz_intensity_column="SumIntensity_Anno",
    )


def test_tag_then_mass_click_drills_down(tagger_plot, TAG_PAYLOAD):
    """updateSelection('tag', TAG) then a peak click -> level 1 charges."""
    # 1. Tag selected (TagData payload flows through the generic 'tag' key).
    state = {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": None}
    r_l0 = tagger_plot._prepare_vue_data(state)
    assert r_l0["_plotConfig"]["level"] == "deconvolved"
    assert len(r_l0["plotDataTaggerCharges"]) == 0
    # Level-0 sticks highlight the tag masses.
    assert r_l0["plotData"]["highlight"].tolist() == [True, True, True]

    # 2. Click a highlighted mass button (peak_id=0 => MonoMass 150).
    state["tagger_mass"] = 0
    r_l1 = tagger_plot._prepare_vue_data(state)
    assert r_l1["_plotConfig"]["level"] == "annotated"
    charges = r_l1["plotDataTaggerCharges"]
    assert len(charges) > 0
    # The open mass's raw m/z peaks (mass 150 has 3 signal peaks).
    assert len(charges) == 3


def test_back_button_returns_to_level0(tagger_plot, TAG_PAYLOAD):
    """updateSelection('tagger_mass', None) -> empty charges + level 0."""
    state = {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
    r_l1 = tagger_plot._prepare_vue_data(state)
    assert r_l1["_plotConfig"]["level"] == "annotated"

    # Back button clears tagger_mass.
    state["tagger_mass"] = None
    r_back = tagger_plot._prepare_vue_data(state)
    assert r_back["_plotConfig"]["level"] == "deconvolved"
    assert len(r_back["plotDataTaggerCharges"]) == 0


def test_scan_change_resets_drilldown(tagger_plot, TAG_PAYLOAD):
    """Changing scan with a stale tagger_mass not in the new highlight set resets.

    Scan 2 has different masses ([100, 200]) and the TAG_PAYLOAD masses don't
    match them, so nothing is highlighted and a leftover tagger_mass is stale =>
    level 0 (oracle reset parity).
    """
    # Drilled into scan 1.
    state = {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
    r1 = tagger_plot._prepare_vue_data(state)
    assert r1["_plotConfig"]["level"] == "annotated"

    # Switch to scan 2 while tagger_mass is still 0.
    state["spectrum"] = 2
    r2 = tagger_plot._prepare_vue_data(state)
    # tag masses don't match scan 2 masses -> no highlights -> stale mass -> level 0
    assert r2["plotData"]["highlight"].tolist() == [False, False]
    assert r2["_plotConfig"]["level"] == "deconvolved"
    assert len(r2["plotDataTaggerCharges"]) == 0


def test_hash_changes_with_drilldown(tagger_plot, TAG_PAYLOAD):
    """The data hash differs between level 0 and level 1 (cache key changes)."""
    h0 = tagger_plot._prepare_vue_data(
        {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": None}
    )["_hash"]
    h1 = tagger_plot._prepare_vue_data(
        {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
    )["_hash"]
    assert h0 != h1


def test_tagger_mass_as_float_coerced(tagger_plot, TAG_PAYLOAD):
    """A float tagger_mass (JS numbers) is coerced to int and drills down."""
    state = {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0.0}
    r = tagger_plot._prepare_vue_data(state)
    assert r["_plotConfig"]["level"] == "annotated"
    assert len(r["plotDataTaggerCharges"]) == 3


def test_tag_payload_via_json_roundtrip(tagger_plot, TAG_PAYLOAD):
    """The TagData payload survives a JSON clone (App.vue clones before send)."""
    import json

    cloned = json.loads(json.dumps(TAG_PAYLOAD))
    r = tagger_plot._prepare_vue_data({"spectrum": 1, "tag": cloned})
    assert r["plotData"]["highlight"].tolist() == [True, True, True]


# ---------------------------------------------------------------------------
# Full bridge render path (cache hit must preserve the state-derived level).
# ---------------------------------------------------------------------------


def _make_vue_response(state_manager, **selections):
    """Minimal Vue return echoing the StateManager session id + selections."""
    return {
        "selection_counter": 1,
        "pagination_counter": 0,
        "counter": 1,
        "id": state_manager.session_id,
        **selections,
    }


def test_bridge_render_preserves_level_on_cache_hit(
    tagger_plot, TAG_PAYLOAD, mock_streamlit
):
    """Through render_component: the tagger _plotConfig.level survives a cache hit.

    The bridge normally rebuilds _plotConfig from the static highlight/annotation
    columns on a cache hit, which would drop the tagger drill-down `level`. The
    component opts into preserving its cached config (_preserves_plot_config).
    """
    from unittest.mock import Mock, patch

    from openms_insight.core.state import StateManager
    from openms_insight.rendering.bridge import (
        _prepare_vue_data_cached,
        clear_component_cache,
        render_component,
    )

    clear_component_cache()
    sm = StateManager(session_key="tagger_bridge_state")
    sm.set_selection("spectrum", 1)
    sm.set_selection("tag", TAG_PAYLOAD)
    sm.set_selection("tagger_mass", 0)  # drilled into level 1

    mock_vue = Mock(return_value=_make_vue_response(sm))
    with patch("streamlit.rerun", Mock()):
        with patch(
            "openms_insight.rendering.bridge.get_vue_component_function",
            return_value=mock_vue,
        ):
            # First render: cache miss -> computes + caches the level-1 config.
            render_component(tagger_plot, sm, key="tagger_bridge")

    # Now exercise the cache-hit path directly with the same drill-down state.
    state = sm.get_state_for_vue()
    state_keys = set(tagger_plot.get_state_dependencies())
    from openms_insight.rendering.bridge import _make_hashable

    filter_state_hashable = tuple(
        sorted((k, _make_hashable(state.get(k))) for k in state_keys)
    )
    relevant_state = {k: state.get(k) for k in state_keys}
    component_id = f"{tagger_plot._get_vue_component_name()}:tagger_bridge"

    vue_data, _ = _prepare_vue_data_cached(
        tagger_plot, component_id, filter_state_hashable, relevant_state
    )
    # The cached config must still report the annotated drill-down level.
    assert vue_data["_plotConfig"]["level"] == "annotated"
    assert vue_data["_plotConfig"]["selectedColumn"] == "selected_gold"
