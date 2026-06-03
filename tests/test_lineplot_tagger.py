"""Tests for LinePlot(mode="tagger") — sequence-tag overlay + drill-down.

Heavy math (highlight masks, reversed-index gold rule, COG, sequence-arrow
segments) is precomputed in Python; these tests guard the byte-for-byte oracle
parity (1e-5 tolerance, COG = Σ(I/ΣI)·mz, reversedSelectedAA = len-1-selectedAA,
gold rule == i || == i-1).
"""

import pandas as pd
import pytest

from openms_insight import LinePlot
from openms_insight.components.lineplot import (
    compute_charge_cog,
    compute_tagger_charges,
    compute_tagger_level1_spectrum,
    compute_tagger_segments,
)


def _make(temp_cache_dir, data, **overrides):
    """Construct a tagger LinePlot via the grouped ``.tagger(...)`` factory."""
    defaults = {
        "cache_id": "test_tagger",
        "data": data,
        "cache_path": str(temp_cache_dir),
        "filters": {"spectrum": "scan_id", "tag": "tag_id"},
        "filter_defaults": {"tagger_mass": None},
        "interactivity": {"tagger_mass": "peak_id"},
        "x_column": "MonoMass",
        "y_column": "SumIntensity",
        "signal_peaks_column": "SignalPeaks",
        "mz_column": "MonoMass_Anno",
        "mz_intensity_column": "SumIntensity_Anno",
    }
    defaults.update(overrides)
    return LinePlot.tagger(**defaults)


class TestTaggerFrameResolve:
    """Value-based tag resolution: a scalar ``tag`` id (e.g. a Table row click) is
    resolved to a TagData payload via a side frame, equivalent to the opaque dict.
    """

    def _tag_data_path(self, tmp_dir):
        import polars as pl

        path = str(tmp_dir / "tag_data.parquet")
        # mzs as a comma-separated STRING (oracle tag-table column); start=0.
        pl.DataFrame(
            {
                "tag_id": [10, 20],
                "sequence": ["ABC", "XY"],
                "mzs": ["350.0,250.0,150.0", "0,0"],
                "start": [0, 0],
            }
        ).write_parquet(path)
        return path

    def _resolved_tagger(self, temp_cache_dir, data, tmp_path):
        return _make(
            temp_cache_dir,
            data,
            tag_data_path=self._tag_data_path(tmp_path),
            tag_id_column="tag_id",
            tag_sequence_column="sequence",
            tag_masses_column="mzs",
            tag_start_column="start",
            selected_aa_identifier="aa",
        )

    def test_scalar_tag_matches_dict_payload(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD, tmp_path
    ):
        comp = self._resolved_tagger(temp_cache_dir, sample_tagger_data, tmp_path)
        # scalar tag id 10 + residue pos 1 (=> selectedAA = 1 - start(0) = 1, the
        # same as TAG_PAYLOAD["selectedAA"]) must reproduce the dict-payload result.
        result = comp._prepare_vue_data({"spectrum": 1, "tag": 10, "aa": 1})
        df = result["plotData"]
        assert df["highlight"].tolist() == [True, True, True]
        assert df["mass_label"].tolist() == ["150.00", "250.00", "350.00"]
        # selectedAA gold matches the opaque-payload gold (reversedSelectedAA rule).
        assert df["selected_gold"].tolist() == [True, True, False]

    def test_unknown_or_cleared_tag_yields_no_highlight(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, tmp_path
    ):
        comp = self._resolved_tagger(temp_cache_dir, sample_tagger_data, tmp_path)
        # No tag selected -> nothing highlighted.
        r_none = comp._prepare_vue_data({"spectrum": 1, "tag": None})
        assert r_none["plotData"]["highlight"].tolist() == [False, False, False]
        # Stale id with no matching row -> nothing highlighted (no crash).
        r_missing = comp._prepare_vue_data({"spectrum": 1, "tag": 999})
        assert r_missing["plotData"]["highlight"].tolist() == [False, False, False]

    def test_tag_and_residue_are_state_dependencies(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, tmp_path
    ):
        comp = self._resolved_tagger(temp_cache_dir, sample_tagger_data, tmp_path)
        deps = comp.get_state_dependencies()
        assert "tag" in deps  # tag selection drives a re-render
        assert "aa" in deps   # residue selection drives a re-render (gold)


class TestTaggerPrepareVueData:
    def test_prepare_vue_data_returns_dict_with_hash(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        comp = _make(temp_cache_dir, sample_tagger_data)
        result = comp._prepare_vue_data({"spectrum": 1, "tag": TAG_PAYLOAD})
        assert isinstance(result, dict)
        assert "_hash" in result
        assert isinstance(result["_hash"], str)
        assert "plotData" in result
        assert "plotDataTaggerSegments" in result
        assert "plotDataTaggerCharges" in result

    def test_level0_highlights_tag_masses(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """plotData[highlight] is True exactly for masses within 1e-5 of tag masses."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        result = comp._prepare_vue_data({"spectrum": 1, "tag": TAG_PAYLOAD})
        df = result["plotData"]
        # All three masses (150, 250, 350) are in TAG_PAYLOAD["masses"]
        assert df["highlight"].tolist() == [True, True, True]
        # Mass labels only on highlighted peaks
        assert df["mass_label"].tolist() == ["150.00", "250.00", "350.00"]

    def test_highlight_all_or_nothing(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        """If not all tag masses match, NONE are highlighted (oracle parity)."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        bad_tag = {
            "sequence": "ABC",
            "nTerminal": True,
            "masses": [350.0, 250.0, 999.0],  # 999 not in MonoMass
            "selectedAA": 1,
            "startPos": 0,
            "endPos": 2,
        }
        result = comp._prepare_vue_data({"spectrum": 1, "tag": bad_tag})
        df = result["plotData"]
        assert df["highlight"].tolist() == [False, False, False]

    def test_gold_selection_reversed_index(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """Gold flags match the oracle reversedSelectedAA == hpos || == hpos-1.

        tag.masses [350,250,150] -> highlighted_pos (in tag-mass order) = [2,1,0]
        (MonoMass indices). hpos = position within highlighted_pos, i.e. the
        oracle highlightedValues index: MonoMass idx 0(150)->hpos2,
        1(250)->hpos1, 2(350)->hpos0. reversedSelectedAA = (3-1) - 1 = 1.
        Gold iff hpos == 1 or hpos == 2 => MonoMass idx 0 (hpos2) and 1 (hpos1).
        """
        comp = _make(temp_cache_dir, sample_tagger_data)
        result = comp._prepare_vue_data({"spectrum": 1, "tag": TAG_PAYLOAD})
        df = result["plotData"]
        # MonoMass natural order [150, 250, 350] => gold [True, True, False].
        assert df["selected_gold"].tolist() == [True, True, False]

    def test_segments_residues_and_delta(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """Segments residues = sequence[len-1-i]; delta = |x_start-x_end|; n-1 rows."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        result = comp._prepare_vue_data({"spectrum": 1, "tag": TAG_PAYLOAD})
        seg = result["plotDataTaggerSegments"]
        # highlighted_pos = [2, 1, 0] -> masses [350, 250, 150]
        # 3 highlighted masses => 2 segments
        assert len(seg) == 2
        # residue i=0 -> sequence[2] = 'C'; i=1 -> sequence[1] = 'B'
        assert seg["residue"].tolist() == ["C", "B"]
        # delta = |350-250| = 100 ; |250-150| = 100
        assert seg["delta"].tolist() == [100.0, 100.0]
        # gold segment when reversedSelectedAA(=1) == i -> i=1
        assert seg["selected"].tolist() == [False, True]

    def test_level1_charges_only_when_mass_selected(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """tagger_mass None => empty charges; valid mass => the mass's raw peaks."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        # No drill-down
        r0 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": None}
        )
        assert len(r0["plotDataTaggerCharges"]) == 0
        assert r0["_plotConfig"]["level"] == "deconvolved"

        # Drill into MonoMass idx 0 (mass 150) which has 3 signal peaks
        r1 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
        )
        charges = r1["plotDataTaggerCharges"]
        assert len(charges) == 3
        assert r1["_plotConfig"]["level"] == "annotated"
        # charge labels "z=<charge>"
        assert set(charges["charge_label"]) == {"z=12", "z=13"}

    def test_level1_renders_full_annotated_spectrum(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """Level-1 draws the FULL annotated spectrum (not just the open mass's
        envelope), highlighting ONLY the open mass's m/z peaks (oracle parity).

        Scan 1 MonoMass_Anno = [75.0, 75.1, 50.0, 125.0, 175.0] (5 peaks). Mass
        150 (MonoMass idx 0) has 3 signal peaks at mz 75.0/75.1/50.0. So the
        level-1 frame must contain ALL 5 annotated peaks (superset of the
        3-peak envelope) with highlight True only on the open mass's 3 peaks.
        """
        comp = _make(temp_cache_dir, sample_tagger_data)
        r0 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": None}
        )
        # No drill-down => empty level-1 spectrum.
        assert "plotDataTaggerLevel1" in r0
        assert len(r0["plotDataTaggerLevel1"]) == 0

        r1 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
        )
        lvl1 = r1["plotDataTaggerLevel1"]
        # FULL annotated spectrum (5 peaks), NOT the 3-peak signal-peak envelope.
        assert lvl1["x"].tolist() == [75.0, 75.1, 50.0, 125.0, 175.0]
        assert lvl1["y"].tolist() == [3.0, 1.0, 2.0, 4.0, 6.0]
        # ONLY the open mass's (mass 150) m/z peaks are highlighted; the peaks
        # belonging to masses 250 (125.0) and 350 (175.0) stay unhighlighted.
        assert lvl1["highlight"].tolist() == [True, True, True, False, False]

    def test_level1_stick_gold_uses_reversed_selected_aa(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """Level-1 STICK gold follows the reversedSelectedAA rule, scoped to the
        open mass's peaks (oracle Tagger.vue:260 -> reversedSelectedAA).

        Drill into MonoMass idx 0 (mass 150): open_hpos = 2, reversedSelectedAA =
        (3-1)-1 = 1 => stick_gold = (1==2)||(1==1) = True for all open-mass peaks;
        unhighlighted peaks are never gold.
        """
        comp = _make(temp_cache_dir, sample_tagger_data)
        r1 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
        )
        lvl1 = r1["plotDataTaggerLevel1"]
        assert lvl1["selected_gold"].tolist() == [True, True, True, False, False]

        # Drill into MonoMass idx 2 (mass 350): open_hpos = 0, reversedSelectedAA
        # = 1 => stick_gold = (1==0)||(1==-1) = False (orange, not gold).
        r2 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 2}
        )
        lvl2 = r2["plotDataTaggerLevel1"]
        # mass 350 has one signal peak at mz 175.0 -> highlighted, not gold.
        hl2 = [
            x
            for x, h in zip(lvl2["x"].tolist(), lvl2["highlight"].tolist())
            if h
        ]
        assert hl2 == [175.0]
        assert lvl2["selected_gold"].tolist() == [False] * len(lvl2)

    def test_cog_intensity_weighted(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """COG = Σ(I/ΣI)*mz for the charge-12 group of mass 150."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        r1 = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 0}
        )
        charges = r1["plotDataTaggerCharges"]
        # charge-12 peaks: (mz=75.0,i=3),(mz=75.1,i=1) => COG = (3*75 + 1*75.1)/4
        expected = (3 * 75.0 + 1 * 75.1) / 4
        c12 = charges[charges["charge"] == 12]
        assert c12["cog"].iloc[0] == pytest.approx(expected, abs=1e-9)
        # charge-13 single peak COG == its mz
        c13 = charges[charges["charge"] == 13]
        assert c13["cog"].iloc[0] == pytest.approx(50.0, abs=1e-9)

    def test_stale_tagger_mass_ignored(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data, TAG_PAYLOAD
    ):
        """A tagger_mass peak_id absent from the highlighted set -> level 0."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        # peak_id 99 doesn't exist -> stale -> level 0
        result = comp._prepare_vue_data(
            {"spectrum": 1, "tag": TAG_PAYLOAD, "tagger_mass": 99}
        )
        assert len(result["plotDataTaggerCharges"]) == 0
        assert result["_plotConfig"]["level"] == "deconvolved"

    def test_no_tag_no_highlights(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        """Without a tag payload, nothing is highlighted and no segments emitted."""
        comp = _make(temp_cache_dir, sample_tagger_data)
        result = comp._prepare_vue_data({"spectrum": 1})
        df = result["plotData"]
        assert df["highlight"].tolist() == [False, False, False]
        assert len(result["plotDataTaggerSegments"]) == 0


class TestTaggerStateDependencies:
    def test_state_dependencies(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        comp = _make(temp_cache_dir, sample_tagger_data)
        deps = set(comp.get_state_dependencies())
        assert deps == {"spectrum", "tag", "tagger_mass"}


class TestTaggerComponentArgs:
    def test_component_args(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        comp = _make(temp_cache_dir, sample_tagger_data)
        args = comp._get_component_args()
        assert args["mode"] == "tagger"
        assert args["componentType"] == "PlotlyLineplot"
        assert args["interactivity"] == {"tagger_mass": "peak_id"}
        assert args["taggerMassButtons"] is True
        assert args["xPosScalingFactor"] == 27.5
        # Titles / x-labels for both levels present
        assert args["title"] == "Augmented Deconvolved Spectrum"
        assert args["titleLevel1"] == "Augmented Annotated Spectrum"
        assert args["xLabel"] == "Monoisotopic Mass"
        assert args["xLabelLevel1"] == "m/z"
        assert args["highlightColumn"] == "highlight"
        assert args["annotationColumn"] == "mass_label"
        assert args["taggerSegmentsKey"] == "plotDataTaggerSegments"
        assert args["taggerChargesKey"] == "plotDataTaggerCharges"
        assert args["taggerLevel1Key"] == "plotDataTaggerLevel1"

    def test_vue_component_name(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        comp = _make(temp_cache_dir, sample_tagger_data)
        assert comp._get_vue_component_name() == "PlotlyLineplot"


class TestTaggerCacheConfig:
    def test_cache_config_roundtrip(
        self, mock_streamlit, temp_cache_dir, sample_tagger_data
    ):
        comp = _make(temp_cache_dir, sample_tagger_data)
        config = comp._get_cache_config()
        assert config["mode"] == "tagger"
        assert config["signal_peaks_column"] == "SignalPeaks"
        assert config["mz_column"] == "MonoMass_Anno"
        assert config["mz_intensity_column"] == "SumIntensity_Anno"
        assert config["tag_identifier"] == "tag"
        assert config["mass_match_tol"] == 1e-5

        restored = _make(
            temp_cache_dir, sample_tagger_data, cache_id="tagger_restore"
        )
        restored._restore_cache_config(config)
        assert restored._mode == "tagger"
        assert restored._signal_peaks_column == "SignalPeaks"
        assert restored._mz_column == "MonoMass_Anno"
        assert restored._mz_intensity_column == "SumIntensity_Anno"
        assert restored._tag_identifier == "tag"
        assert restored._mass_match_tol == 1e-5


class TestDefaultModeRegressionGuard:
    """LinePlot(mode='default') / omitted mode must keep the classic payload."""

    def test_default_mode_unchanged(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = LinePlot(
            cache_id="default_guard",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )
        result = comp._prepare_vue_data({})
        # plotData-only payload, no tagger keys
        assert "plotData" in result
        assert "plotDataTaggerSegments" not in result
        assert "plotDataTaggerCharges" not in result
        # Default mode vue dispatch unchanged (Unified)
        assert comp._get_vue_component_name() == "PlotlyLineplotUnified"
        args = comp._get_component_args()
        assert args["mode"] == "default"
        assert args["componentType"] == "PlotlyLineplotUnified"

    def test_omitted_mode_is_default(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = LinePlot(
            cache_id="omitted_mode_guard",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )
        assert comp._mode == "default"


# ---------------------------------------------------------------------------
# Pure-function (oracle parity) tests for the numeric core.
# ---------------------------------------------------------------------------


class TestTaggerNumericCore:
    def test_compute_charge_cog(self):
        # (mz=1000, i=3), (mz=1001, i=1) => 1000.25 (intensity-weighted)
        assert compute_charge_cog([(1000.0, 3.0), (1001.0, 1.0)]) == pytest.approx(
            1000.25
        )

    def test_compute_charge_cog_zero_intensity(self):
        # Degenerate guard: zero total -> simple mean
        assert compute_charge_cog([(100.0, 0.0), (200.0, 0.0)]) == pytest.approx(150.0)

    def test_compute_tagger_segments_residue_reversed(self):
        # masses positions 0,1,2; sequence 'XYZ'
        segs = compute_tagger_segments(
            [100.0, 200.0, 350.0], [0, 1, 2], "XYZ", reversed_selected_aa=1
        )
        assert len(segs) == 2
        # i=0 -> sequence[2]='Z'; i=1 -> sequence[1]='Y'
        assert [s["residue"] for s in segs] == ["Z", "Y"]
        assert [s["delta"] for s in segs] == [100.0, 150.0]
        assert [s["selected"] for s in segs] == [False, True]

    def test_compute_tagger_charges_layout(self):
        sp = [
            [0, 75.0, 3.0, 12.0],
            [1, 75.1, 1.0, 12.0],
            [2, 50.0, 2.0, 13.0],
        ]
        rows = compute_tagger_charges(sp, selected_aa=0, selected_mass_index=0)
        assert len(rows) == 3
        assert {r["charge"] for r in rows} == {12, 13}
        # COG shared within a charge group
        c12 = [r for r in rows if r["charge"] == 12]
        assert all(r["cog"] == pytest.approx((3 * 75.0 + 75.1) / 4) for r in c12)
        # gold rule: selectedAA(0) == selected_mass_index(0) -> True
        assert all(r["selected"] for r in rows)

    def test_compute_tagger_level1_full_spectrum_with_highlight(self):
        """Level-1 sticks = the FULL annotated spectrum; only the open mass's m/z
        peaks (within tol of its signal-peak mzs) are highlighted.

        anno = 4 peaks; open mass signal peaks at mz 75.0/50.0 => peaks 0 and 2
        highlighted, peaks 1 and 3 (other masses) unhighlighted.
        """
        anno_mz = [75.0, 125.0, 50.0, 175.0]
        anno_int = [3.0, 4.0, 2.0, 6.0]
        open_signal_peaks = [
            [0.0, 75.0, 3.0, 12.0],
            [1.0, 50.0, 2.0, 13.0],
        ]
        rows = compute_tagger_level1_spectrum(
            anno_mz, anno_int, open_signal_peaks, stick_gold=False, tol=1e-5
        )
        # Full spectrum (4 rows), not the 2-peak envelope.
        assert [r["x"] for r in rows] == anno_mz
        assert [r["y"] for r in rows] == anno_int
        assert [r["highlight"] for r in rows] == [True, False, True, False]

    def test_compute_tagger_level1_stick_gold_distinct_from_badge(self):
        """STICK gold is driven by the caller-supplied `stick_gold` bool (derived
        from reversedSelectedAA) and applies ONLY to highlighted peaks — distinct
        from the per-charge BADGE gold (raw selectedAA) in compute_tagger_charges.
        """
        anno_mz = [75.0, 125.0]
        anno_int = [3.0, 4.0]
        open_signal_peaks = [[0.0, 75.0, 3.0, 12.0]]

        gold_rows = compute_tagger_level1_spectrum(
            anno_mz, anno_int, open_signal_peaks, stick_gold=True, tol=1e-5
        )
        # Highlighted open-mass peak is gold; the unhighlighted peak never is.
        assert [r["selected_gold"] for r in gold_rows] == [True, False]

        plain_rows = compute_tagger_level1_spectrum(
            anno_mz, anno_int, open_signal_peaks, stick_gold=False, tol=1e-5
        )
        assert [r["selected_gold"] for r in plain_rows] == [False, False]

        # The BADGE path uses the RAW selectedAA rule, independent of stick_gold:
        # selectedAA=0 == selected_mass_index=0 -> badge gold True even though a
        # caller could pass stick_gold=False for the same drill-down.
        badge = compute_tagger_charges(
            open_signal_peaks, selected_aa=0, selected_mass_index=0
        )
        assert all(r["selected"] for r in badge)
