"""Tests for the SequenceView coverage / fixed-mod / settings extension.

Covers the FLASHApp -> OpenMS-Insight parity additions:
  - per-residue `coverage` / `maxCoverage` round-trip,
  - C/M fixed-modification computation and round-trip,
  - `settings.tolerance` / `settings.ion_types` plumbing,
  - `filters={'proteinIndex': 'proteoform_index'}` value pushdown,
  - backward-compatibility (existing 2-column inputs and static inputs),
  - empty / no-selection handling.

These tests are additive; the existing tests in `test_sequenceview.py` must
continue to pass unchanged.
"""

from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def proteoform_sequence_data() -> pl.LazyFrame:
    """Per-proteoform sequence data with coverage, maxCoverage and fixed mods."""
    return pl.LazyFrame(
        {
            "proteoform_index": [0, 1],
            "sequence": ["PEPTCMIDEK", "ACDEFGHK"],
            "precursor_charge": [2, 3],
            "coverage": [
                [0.0, 0.5, 1.0, 0.5, 0.0, 0.25, 0.75, 1.0, 0.5, 0.0],
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            ],
            "maxCoverage": [4.0, 3.0],
            "fixed_modifications": [["C", "M"], ["C"]],
        }
    )


class TestCoverageRoundTrip:
    def test_coverage_entry_round_trip(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="cov_entry",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        entry = sv._get_sequence_entry_for_state({"proteinIndex": 0})
        assert entry["sequence"] == "PEPTCMIDEK"
        assert "coverage" in entry
        assert len(list(entry["coverage"])) == 10
        assert entry["maxCoverage"] == pytest.approx(4.0)
        assert list(entry["fixed_modifications"]) == ["C", "M"]

    def test_coverage_in_vue_data(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="cov_vue",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        sd = sv._prepare_vue_data({"proteinIndex": 0})["sequenceData"]
        assert "coverage" in sd
        assert len(sd["coverage"]) == len(sd["sequence"])
        assert sd["maxCoverage"] == pytest.approx(4.0)
        # Coverage values are already-normalized in [0, 1].
        assert all(0.0 <= c <= 1.0 for c in sd["coverage"])

    def test_proteoform_pushdown_selects_correct_entry(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="cov_pushdown",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        e0 = sv._get_sequence_entry_for_state({"proteinIndex": 0})
        e1 = sv._get_sequence_entry_for_state({"proteinIndex": 1})
        assert e0["sequence"] == "PEPTCMIDEK"
        assert e1["sequence"] == "ACDEFGHK"
        assert e1["maxCoverage"] == pytest.approx(3.0)

    def test_missing_proteoform_is_empty(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="cov_missing",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        # No selection -> empty (None default).
        sd_none = sv._prepare_vue_data({"proteinIndex": None})["sequenceData"]
        assert sd_none["sequence"] == []
        assert "coverage" not in sd_none

        # Selecting an absent proteoform -> empty.
        e = sv._get_sequence_entry_for_state({"proteinIndex": 99})
        assert e["sequence"] == ""


class TestFixedModifications:
    def test_fixed_modifications_round_trip(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="fixed_rt",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        sd0 = sv._prepare_vue_data({"proteinIndex": 0})["sequenceData"]
        sd1 = sv._prepare_vue_data({"proteinIndex": 1})["sequenceData"]
        assert sd0["fixed_modifications"] == ["C", "M"]
        assert sd1["fixed_modifications"] == ["C"]

    def test_compute_fixed_modifications_helper(self):
        from openms_insight.components.sequenceview import compute_fixed_modifications

        assert compute_fixed_modifications(list("ACDEFM")) == ["C", "M"]
        assert compute_fixed_modifications(list("PEPTCIDEK")) == ["C"]
        assert compute_fixed_modifications(list("PEPTMIDEK")) == ["M"]
        assert compute_fixed_modifications(list("AGGGK")) == []

    def test_compute_fixed_mods_flag_deconv(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="fixed_compute",
            sequence_data="PEPTCMIDEK",
            cache_path=str(temp_cache_dir),
            compute_fixed_mods=True,
        )
        sd = sv._prepare_vue_data({})["sequenceData"]
        assert sd["fixed_modifications"] == ["C", "M"]

    def test_no_fixed_mods_without_flag_or_data(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="fixed_none",
            sequence_data="PEPTCMIDEK",
            cache_path=str(temp_cache_dir),
        )
        sd = sv._prepare_vue_data({})["sequenceData"]
        assert sd["fixed_modifications"] == []


class TestSettings:
    def test_settings_tolerance_and_ion_types(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="settings_basic",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
            settings={"tolerance": 12.0, "ion_types": ["c", "z"]},
        )

        vd = sv._prepare_vue_data({"proteinIndex": 0})
        assert vd["settings"] == {"tolerance": 12.0, "ion_types": ["c", "z"]}
        sd = vd["sequenceData"]
        # Tolerance flows into the annotation tolerance (ppm) defaults.
        assert sd["fragment_tolerance"] == pytest.approx(12.0)
        assert sd["fragment_tolerance_ppm"] is True
        assert vd["annotationConfig"]["ion_types"] == ["c", "z"]

    def test_settings_default_ion_types(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="settings_default",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
            settings={"tolerance": 10.0, "ion_types": ["b", "y"]},
        )
        assert sv._annotation_config["ion_types"] == ["b", "y"]

    def test_no_settings_omits_key(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="settings_absent",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )
        vd = sv._prepare_vue_data({"proteinIndex": 0})
        assert "settings" not in vd


class TestBackwardCompat:
    def test_two_column_input_no_coverage(
        self, temp_cache_dir: Path, sample_sequence_data: pl.LazyFrame
    ):
        """Existing 2-column (sequence, precursor_charge) data still works and
        produces no coverage / empty fixed mods."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="bc_two_col",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
        )

        df = sample_sequence_data.collect()
        sd = sv._prepare_vue_data({"identification": df["scan_id"][0]})["sequenceData"]
        assert sd["sequence"]  # non-empty
        assert "coverage" not in sd
        assert "maxCoverage" not in sd
        assert sd["fixed_modifications"] == []

    def test_legacy_get_sequence_tuple(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        """`_get_sequence_for_state` still returns a (sequence, charge) tuple."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="bc_legacy_tuple",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )
        result = sv._get_sequence_for_state({"proteinIndex": 1})
        assert isinstance(result, tuple)
        assert result[0] == "ACDEFGHK"
        assert result[1] == 3

    def test_static_string_input_backward_compat(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="bc_static",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
        )
        sd = sv._prepare_vue_data({})["sequenceData"]
        assert sd["sequence"] == list("PEPTIDEK")
        assert "coverage" not in sd
        assert sd["fixed_modifications"] == []

    def test_cache_reload_round_trip(
        self, temp_cache_dir: Path, proteoform_sequence_data: pl.LazyFrame
    ):
        """A reconstructed-from-cache instance preserves coverage/settings."""
        from openms_insight.components.sequenceview import SequenceView

        SequenceView(
            cache_id="bc_reload",
            sequence_data=proteoform_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
            settings={"tolerance": 15.0, "ion_types": ["c", "z"]},
        )

        # Reconstruct from cache (no data args).
        sv2 = SequenceView(cache_id="bc_reload", cache_path=str(temp_cache_dir))
        vd = sv2._prepare_vue_data({"proteinIndex": 0})
        sd = vd["sequenceData"]
        assert "coverage" in sd
        assert sd["maxCoverage"] == pytest.approx(4.0)
        assert vd["settings"] == {"tolerance": 15.0, "ion_types": ["c", "z"]}


class TestFragmentMassesShape:
    def test_fragment_masses_list_of_lists(self, temp_cache_dir: Path):
        """Fragment masses are list-of-lists per position (ambiguous-mod
        multiplicity shape parity with getFragmentDataFromSeq)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="frag_shape",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
        )
        sd = sv._prepare_vue_data({})["sequenceData"]
        for ion in ["a", "b", "c", "x", "y", "z"]:
            key = f"fragment_masses_{ion}"
            assert key in sd
            assert isinstance(sd[key], list)
            # Each position entry is itself a list (supports >1 mass).
            for per_pos in sd[key]:
                assert isinstance(per_pos, list)
