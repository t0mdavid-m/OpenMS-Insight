"""Tests for the SELECTIVE-HIGHLIGHT (FLASHApp parity) default-mode LinePlot path.

Reproduces the oracle PlotlyLineplotUnified.vue selection-driven interaction:
- ANNOTATED spectrum (LINK path): selecting a mass highlights ONLY that mass's
  signal peaks (linked by signal-peak membership), with per-charge ``z=N`` labels
  at each charge group's intensity-weighted center-of-gravity m/z; the ALL-SIGNAL
  set (every signal peak) powers the "Show Deconvolved Peaks" toggle (1:many per
  peak supported).
- DECONVOLVED spectrum (MATCH-COLUMN path): selecting a mass highlights the base
  row(s) whose ``mass_in_scan`` equals the selection; NO z=N labels, NO toggle.

The highlight is computed at RENDER time from the selection state and is NOT
cached as a stray arg; the new params round-trip through the manifest like the
existing config. All new behavior is default-OFF (no ``highlight_selection`` =>
byte-identical to the classic stick spectrum).
"""

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def annotated_base() -> pl.LazyFrame:
    """Annotated-spectrum base frame: one row per m/z peak (peak_id)."""
    return pl.LazyFrame(
        {
            "mz": [75.0, 75.1, 50.0, 125.0, 175.0],
            "intensity": [3.0, 1.0, 2.0, 4.0, 6.0],
            "scan_id": [1, 1, 1, 1, 1],
            "peak_id": [0, 1, 2, 3, 4],
        }
    )


@pytest.fixture
def deconv_base() -> pl.LazyFrame:
    """Deconvolved-spectrum base frame: one row per mass, carrying mass_in_scan."""
    return pl.LazyFrame(
        {
            "mass": [150.0, 250.0, 350.0],
            "intensity": [1000.0, 2000.0, 1500.0],
            "scan_id": [1, 1, 1],
            "mass_index": [0, 1, 2],
            "mass_in_scan": [150.0, 250.0, 350.0],
        }
    )


def _write_link(tmp_path, rows: dict) -> str:
    path = str(tmp_path / "highlight_link.parquet")
    pl.DataFrame(rows).write_parquet(path)
    return path


def _make_annotated(tmp_path, data, link_path, **overrides):
    defaults = {
        "cache_id": "anno_hl",
        "data": data,
        "cache_path": str(tmp_path),
        "x_column": "mz",
        "y_column": "intensity",
        "filters": {"spectrum": "scan_id"},
        "interactivity": {"peak": "peak_id"},
        "highlight_selection": "mass",
        "highlight_link_path": link_path,
        "deconv_peaks_toggle": True,
    }
    defaults.update(overrides)
    return LinePlot(**defaults)


# --------------------------------------------------------------------------- LINK
class TestLinkPathSelectiveHighlight:
    """Annotated spectrum: selective highlight via the signal-peak linkage frame."""

    def _link_rows(self):
        # peaks 0,1,2 -> mass 150 (0,1 are charge 12 isotopes; 2 is charge 13),
        # peak 3 -> mass 250 (charge 5), peak 4 -> mass 350 (charge 7).
        return {
            "peak_id": [0, 1, 2, 3, 4],
            "mass_in_scan": [150.0, 150.0, 150.0, 250.0, 350.0],
            "charge": [12, 12, 13, 5, 7],
        }

    def test_selective_highlight_only_selected_mass_peaks(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(tmp_path, self._link_rows())
        comp = _make_annotated(tmp_path, annotated_base, link)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 150.0})
        df = res["plotData"]
        # Only mass 150's peaks (0,1,2) are highlighted via the dynamic column.
        assert res["_plotConfig"]["highlightColumn"] == "_dynamic_highlight"
        assert list(df["_dynamic_highlight"]) == [True, True, True, False, False]

    def test_selecting_other_mass_moves_highlight(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(tmp_path, self._link_rows())
        comp = _make_annotated(tmp_path, annotated_base, link)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        # Only peak 3 belongs to mass 250.
        assert list(res["plotData"]["_dynamic_highlight"]) == [
            False,
            False,
            False,
            True,
            False,
        ]

    def test_charge_labels_at_cog_for_selected_mass(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(tmp_path, self._link_rows())
        comp = _make_annotated(tmp_path, annotated_base, link)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 150.0})
        pa = res["peakAnnotations"]
        by_text = {d["text"]: d for d in pa}
        # z=12 (peaks 0,1: mz 75.0 int 3, mz 75.1 int 1) => COG 75.025.
        # z=13 (peak 2: mz 50, single) => COG 50.0.
        assert set(by_text) == {"z=12", "z=13"}
        assert by_text["z=12"]["x"] == pytest.approx(75.025, abs=1e-2)
        assert by_text["z=13"]["x"] == pytest.approx(50.0, abs=1e-3)
        assert by_text["z=12"]["color"] == "#E4572E"
        assert by_text["z=12"]["group"] == "charge"

    def test_all_signal_set_is_every_linkage_peak(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(tmp_path, self._link_rows())
        comp = _make_annotated(tmp_path, annotated_base, link)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 150.0})
        sh = res["selectiveHighlight"]
        assert sh["idColumn"] == "peak_id"
        # ALL-SIGNAL set powers the "Show Deconvolved Peaks" toggle (every peak).
        assert sh["allSignalKeys"] == [0, 1, 2, 3, 4]
        # Oracle toggle DEFAULTS: annotations ON, deconv-peaks OFF, button enabled.
        assert sh["annotationsVisible"] is True
        assert sh["deconvolvedPeaksHighlightMode"] is False
        assert sh["deconvPeaksToggle"] is True

    def test_one_to_many_peak_membership(self, mock_streamlit, tmp_path, annotated_base):
        """A single peak may belong to MULTIPLE masses (1:many linkage)."""
        # peak 0 belongs to BOTH mass 150 and mass 999 (shared signal peak).
        rows = {
            "peak_id": [0, 0, 1, 2],
            "mass_in_scan": [150.0, 999.0, 150.0, 999.0],
            "charge": [12, 4, 12, 4],
        }
        link = _write_link(tmp_path, rows)
        comp = _make_annotated(tmp_path, annotated_base, link)
        # Selecting 999 highlights peaks 0 and 2 (both linked to 999).
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 999.0})
        assert list(res["plotData"]["_dynamic_highlight"]) == [
            True,
            False,
            True,
            False,
            False,
        ]
        # all-signal de-duplicates the peak ids (0 appears once).
        assert res["selectiveHighlight"]["allSignalKeys"] == [0, 1, 2]

    def test_no_selection_no_highlight(self, mock_streamlit, tmp_path, annotated_base):
        link = _write_link(tmp_path, self._link_rows())
        comp = _make_annotated(tmp_path, annotated_base, link)
        res = comp._prepare_vue_data({"spectrum": 1})  # no mass selected
        df = res["plotData"]
        # No selective highlight => the dynamic column (if present) is all-False.
        if "_dynamic_highlight" in df.columns:
            assert not any(df["_dynamic_highlight"])
        # No z=N labels without a selected mass.
        assert "peakAnnotations" not in res
        # The all-signal set is still sent (the toggle works pre-selection).
        assert res["selectiveHighlight"]["allSignalKeys"] == [0, 1, 2, 3, 4]


# ------------------------------------------------------------------- MATCH-COLUMN
class TestMatchColumnSelectiveHighlight:
    """Deconvolved spectrum: selective highlight via base[mass_in_scan] == sel."""

    def _make(self, tmp_path, data, **overrides):
        defaults = {
            "cache_id": "deconv_hl",
            "data": data,
            "cache_path": str(tmp_path),
            "x_column": "mass",
            "y_column": "intensity",
            "filters": {"spectrum": "scan_id"},
            "interactivity": {"massidx": "mass_index"},
            "highlight_selection": "mass",
            "highlight_match_column": "mass_in_scan",
        }
        defaults.update(overrides)
        return LinePlot(**defaults)

    def test_highlights_matching_base_row(self, mock_streamlit, tmp_path, deconv_base):
        comp = self._make(tmp_path, deconv_base)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        assert res["_plotConfig"]["highlightColumn"] == "_dynamic_highlight"
        assert list(res["plotData"]["_dynamic_highlight"]) == [False, True, False]

    def test_no_charge_labels_and_no_toggle(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        comp = self._make(tmp_path, deconv_base)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        # Deconv spectrum: NO z=N charge labels (oracle).
        assert "peakAnnotations" not in res
        sh = res["selectiveHighlight"]
        # No link frame => no all-signal toggle set; the deconv button stays OFF.
        assert sh["allSignalKeys"] is None
        assert sh["deconvPeaksToggle"] is False

    def test_unmatched_selection_highlights_nothing(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        comp = self._make(tmp_path, deconv_base)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 9999.0})
        df = res["plotData"]
        if "_dynamic_highlight" in df.columns:
            assert not any(df["_dynamic_highlight"])

    def test_value_label_on_matched_stick(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        # round-9 finding 3-deconv-001: the selected mass's MonoMass VALUE LABEL
        # (oracle mass.toFixed(2)) rides the peakAnnotations channel via
        # highlight_value_column + highlight_value_template.
        comp = self._make(
            tmp_path,
            deconv_base,
            highlight_value_column="mass",
            highlight_value_template="{:.2f}",
        )
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        # still highlights ONLY the matched stick
        assert list(res["plotData"]["_dynamic_highlight"]) == [False, True, False]
        anns = res["peakAnnotations"]
        assert len(anns) == 1  # exactly one label, for the selected mass
        assert anns[0]["x"] == 250.0  # at the stick's x (MonoMass)
        assert anns[0]["text"] == "250.00"  # 2-decimal MonoMass value

    def test_no_value_label_without_value_column(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        # Without highlight_value_column the match path emits no value label
        # (back-compat; the highlight still works).
        comp = self._make(tmp_path, deconv_base)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        assert "peakAnnotations" not in res


# --------------------------------------------------------------------- DEFAULT OFF
class TestSelectiveHighlightDefaultOff:
    """No ``highlight_selection`` => classic stick spectrum, byte-identical."""

    def _make_plain(self, tmp_path, data, **overrides):
        defaults = {
            "cache_id": "plain",
            "data": data,
            "cache_path": str(tmp_path),
            "x_column": "mass",
            "y_column": "intensity",
            "filters": {"spectrum": "scan_id"},
            "interactivity": {"massidx": "mass_index"},
        }
        defaults.update(overrides)
        return LinePlot(**defaults)

    def test_no_selective_payload(self, mock_streamlit, tmp_path, deconv_base):
        comp = self._make_plain(tmp_path, deconv_base)
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 250.0})
        assert "selectiveHighlight" not in res
        assert "peakAnnotations" not in res
        # highlightColumn stays the static one (None here).
        assert res["_plotConfig"]["highlightColumn"] is None

    def test_static_highlight_column_still_works(
        self, mock_streamlit, tmp_path
    ):
        """The legacy static highlight_column path is unchanged when set."""
        data = pl.LazyFrame(
            {
                "mass": [150.0, 250.0, 350.0],
                "intensity": [1000.0, 2000.0, 1500.0],
                "scan_id": [1, 1, 1],
                "mass_index": [0, 1, 2],
                "is_signal": [True, False, True],
            }
        )
        comp = self._make_plain(
            tmp_path, data, cache_id="plain_static", highlight_column="is_signal"
        )
        res = comp._prepare_vue_data({"spectrum": 1})
        assert res["_plotConfig"]["highlightColumn"] == "is_signal"
        assert list(res["plotData"]["is_signal"]) == [True, False, True]

    def test_state_dependencies_unchanged_when_off(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        comp = self._make_plain(tmp_path, deconv_base)
        # Off => only the filter identifiers (no highlight selection dependency).
        assert comp.get_state_dependencies() == ["spectrum"]

    def test_state_dependencies_include_highlight_selection_when_on(
        self, mock_streamlit, tmp_path, deconv_base
    ):
        comp = LinePlot(
            cache_id="deps_on",
            data=deconv_base,
            cache_path=str(tmp_path),
            x_column="mass",
            y_column="intensity",
            filters={"spectrum": "scan_id"},
            interactivity={"massidx": "mass_index"},
            highlight_selection="mass",
            highlight_match_column="mass_in_scan",
        )
        deps = comp.get_state_dependencies()
        assert "spectrum" in deps
        assert "mass" in deps  # selection-driven highlight => cache-invalidating


# ----------------------------------------------------------------- CONFIG ROUNDTRIP
class TestSelectiveHighlightConfigRoundtrip:
    """The new params round-trip through cache reconstruction (no stray args)."""

    def test_params_roundtrip_and_not_stray_args(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(
            tmp_path,
            {"peak_id": [0], "mass_in_scan": [150.0], "charge": [12]},
        )
        comp = _make_annotated(
            tmp_path,
            annotated_base,
            link,
            cache_id="rt_hl",
            highlight_annotation_template="charge {}",
        )
        # Stored in cache config (data-shaping), NOT render config.
        cache_cfg = comp._get_cache_config()
        assert cache_cfg["highlight_selection"] == "mass"
        assert cache_cfg["highlight_link_path"] == link
        assert cache_cfg["highlight_annotation_template"] == "charge {}"
        assert cache_cfg["deconv_peaks_toggle"] is True

        # The managed keys must NOT leak as stray top-level component args.
        args = comp._get_component_args()
        for stray in (
            "highlight_selection",
            "highlight_match_column",
            "highlight_link_path",
            "highlight_link_key_column",
            "highlight_link_match_column",
            "highlight_charge_column",
            "highlight_annotation_template",
            "deconv_peaks_toggle",
        ):
            assert stray not in args, f"{stray} leaked into component args"
        # The DEDICATED camelCase flags ARE surfaced (button enable).
        assert args["selectiveHighlightEnabled"] is True
        assert args["deconvPeaksToggle"] is True

        # Reconstruct from ONLY cache_id + cache_path.
        restored = LinePlot(cache_id="rt_hl", cache_path=str(tmp_path))
        assert restored._highlight_selection == "mass"
        assert restored._highlight_link_path == link
        assert restored._highlight_annotation_template == "charge {}"
        assert restored._deconv_peaks_toggle is True
        # The reconstructed instance re-scans the linkage frame lazily.
        assert restored._highlight_link is not None

    def test_custom_template_applied_to_labels(
        self, mock_streamlit, tmp_path, annotated_base
    ):
        link = _write_link(
            tmp_path,
            {"peak_id": [0, 1], "mass_in_scan": [150.0, 150.0], "charge": [12, 12]},
        )
        comp = _make_annotated(
            tmp_path,
            annotated_base,
            link,
            cache_id="tmpl_hl",
            highlight_annotation_template="z={}+",
        )
        res = comp._prepare_vue_data({"spectrum": 1, "mass": 150.0})
        assert res["peakAnnotations"][0]["text"] == "z=12+"
