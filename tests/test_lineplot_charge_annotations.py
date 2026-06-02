"""Tests for the generic per-peak charge annotations (Item B).

`set_peak_annotations` adds render-time, NOT-cached label descriptors in data
coordinates (mirrors the existing _dynamic_annotations pattern). The COG /
charge-group math is done in Python (`compute_charge_annotations`).
"""

import pandas as pd
import pytest

from openms_insight import LinePlot
from openms_insight.components.lineplot import (
    compute_charge_annotations,
    compute_charge_cog,
)


def _make(temp_cache_dir, data, **overrides):
    defaults = {
        "cache_id": "test_charge_ann",
        "data": data,
        "cache_path": str(temp_cache_dir),
        "x_column": "mass",
        "y_column": "intensity",
        "filters": {"spectrum": "scan_id"},
        "interactivity": {"peak": "peak_id"},
    }
    defaults.update(overrides)
    return LinePlot(**defaults)


class TestSetPeakAnnotations:
    def test_attaches_peak_annotations_and_changes_hash(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = _make(temp_cache_dir, sample_lineplot_data)
        base = comp._prepare_vue_data({"spectrum": 1})
        base_hash = base["_hash"]
        assert "peakAnnotations" not in base

        labels = [
            {"x": 1000.5, "text": "z=12", "color": "#E4572E"},
            {"x": 1000.7, "text": "z=11"},
        ]
        comp.set_peak_annotations(labels)
        result = comp._prepare_vue_data({"spectrum": 1})
        assert result["peakAnnotations"] == labels
        # Hash incorporates the labels => differs from no-annotation hash.
        assert result["_hash"] != base_hash
        # Still a dict with a string _hash (contract invariant).
        assert isinstance(result, dict)
        assert isinstance(result["_hash"], str)

    def test_clear_peak_annotations(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = _make(temp_cache_dir, sample_lineplot_data)
        base_hash = comp._prepare_vue_data({"spectrum": 1})["_hash"]
        comp.set_peak_annotations([{"x": 1.0, "text": "z=1"}])
        with_ann = comp._prepare_vue_data({"spectrum": 1})
        assert "peakAnnotations" in with_ann

        comp.clear_peak_annotations()
        cleared = comp._prepare_vue_data({"spectrum": 1})
        assert "peakAnnotations" not in cleared
        # Hash reverts to the no-annotation hash.
        assert cleared["_hash"] == base_hash

    def test_setters_return_self(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = _make(temp_cache_dir, sample_lineplot_data)
        assert comp.set_peak_annotations([]) is comp
        assert comp.clear_peak_annotations() is comp

    def test_strip_dynamic_columns_removes_peak_annotations(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = _make(temp_cache_dir, sample_lineplot_data)
        comp.set_peak_annotations([{"x": 1.0, "text": "z=1"}])
        vue_data = comp._prepare_vue_data({"spectrum": 1})
        assert "peakAnnotations" in vue_data

        stripped = comp._strip_dynamic_columns(vue_data)
        # Cache cleanliness: render-time labels removed.
        assert "peakAnnotations" not in stripped

    def test_apply_fresh_annotations_reattaches_peak_annotations(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = _make(temp_cache_dir, sample_lineplot_data)
        base = comp._prepare_vue_data({"spectrum": 1})
        base_clean = comp._strip_dynamic_columns(base)

        comp.set_peak_annotations([{"x": 2.0, "text": "z=2"}])
        refreshed = comp._apply_fresh_annotations(base_clean)
        # Cache-hit path re-attaches the current labels.
        assert refreshed["peakAnnotations"] == [{"x": 2.0, "text": "z=2"}]

    def test_cache_reconstruction_clears_peak_annotations(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Render-time state is not persisted; reloaded instance has None."""
        _make(
            temp_cache_dir,
            sample_lineplot_data,
            cache_id="charge_ann_reload",
        )
        restored = LinePlot(
            cache_id="charge_ann_reload", cache_path=str(temp_cache_dir)
        )
        assert restored._peak_annotations is None
        # Does not error on prepare.
        restored._prepare_vue_data({"spectrum": 1})


class TestChargeAnnotationCOG:
    def test_cog_two_peaks(self):
        """Two isotope peaks (mz=1000,i=3),(mz=1001,i=1) => COG 1000.25."""
        assert compute_charge_cog([(1000.0, 3.0), (1001.0, 1.0)]) == pytest.approx(
            1000.25
        )

    def test_compute_charge_annotations_descriptors(self):
        """compute_charge_annotations groups by charge and places labels at COG."""
        sp = [
            [0, 1000.0, 3.0, 12.0],
            [1, 1001.0, 1.0, 12.0],
            [2, 500.0, 2.0, 24.0],
        ]
        labels = compute_charge_annotations(sp, color="#E4572E")
        assert len(labels) == 2
        by_text = {label["text"]: label for label in labels}
        assert "z=12" in by_text
        assert "z=24" in by_text
        # z=12 label at intensity-weighted COG 1000.25
        assert by_text["z=12"]["x"] == pytest.approx(1000.25)
        # z=24 single peak COG == mz
        assert by_text["z=24"]["x"] == pytest.approx(500.0)
        # Color + group propagated (group enables all-or-nothing overlap scoping)
        assert by_text["z=12"]["color"] == "#E4572E"
        assert by_text["z=12"]["group"] == "charge"

    def test_compute_charge_annotations_default_color(self):
        sp = [[0, 100.0, 1.0, 3.0]]
        labels = compute_charge_annotations(sp)
        assert labels[0]["color"] == "#E4572E"
        assert labels[0]["text"] == "z=3"

    def test_charge_annotations_emit_no_hover(self):
        """Charge labels carry NO hover key (oracle m/z charge branch emits no
        hover point; PlotlyLineplotUnified.vue 889-899). The badge geometry is
        the fixed xpos_scaling width on the Vue side — descriptors only supply
        {x, text, color, group}, never a measured-text hover.
        """
        sp = [
            [0, 1000.0, 3.0, 12.0],
            [1, 1001.0, 1.0, 12.0],
            [2, 500.0, 2.0, 24.0],
        ]
        labels = compute_charge_annotations(sp)
        assert len(labels) == 2
        for label in labels:
            assert "hover" not in label
            # Fields the Vue fixed-geometry (xpos_scaling) badge path consumes.
            assert set(label.keys()) == {"x", "text", "color", "group"}
            assert label["group"] == "charge"


class TestChargeAnnotationsIntegration:
    def test_charge_labels_from_signal_peaks(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """End-to-end: COG-derived descriptors flow into the vue payload."""
        comp = _make(temp_cache_dir, sample_lineplot_data)
        sp = [
            [0, 1000.0, 3.0, 12.0],
            [1, 1001.0, 1.0, 12.0],
        ]
        comp.set_peak_annotations(compute_charge_annotations(sp))
        result = comp._prepare_vue_data({"spectrum": 1})
        pa = result["peakAnnotations"]
        assert pa[0]["text"] == "z=12"
        assert pa[0]["x"] == pytest.approx(1000.25)
