"""Tests for the SequenceView FLASHApp parity fixes.

Covers the optional, backward-compatible additions:
  - proteoform_start / proteoform_end (truncation + determined-terminus) round-trip
    incl. the UNDETERMINED_TERMINUS (-2) sentinel,
  - computed_mass (proteoform mass header / TnT path) round-trip,
  - mod_ranges (ambiguous modification ranges) round-trip + `_normalize_mod_ranges`,
  - precursor_mass (precursor mass header) round-trip,
  - disable_variable_modifications flag plumbing + cache round-trip,
  - hash sensitivity to the new fields,
  - backward-compatibility (existing 2-column / static inputs unaffected).

These tests are additive; the existing tests must continue to pass unchanged.
"""

from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def proteoform_parity_data() -> pl.LazyFrame:
    """Per-proteoform data carrying the new optional parity columns."""
    return pl.LazyFrame(
        {
            "proteoform_index": [0, 1, 2],
            "sequence": ["PEPTCMIDEK", "ACDEFGHK", "MKLVNVALVF"],
            "precursor_charge": [2, 3, 2],
            # proteoform 0: N-truncated (determined 2..9); proteoform 1: full;
            # proteoform 2: C-terminus undetermined (sentinel -2).
            "proteoform_start": [2, 0, 0],
            "proteoform_end": [9, 7, -2],
            "computed_mass": [1234.5, 0.0, 980.1],
            "precursor_mass": [1240.0, 0.0, 0.0],
            "mod_ranges": [
                [{"start": 3, "end": 5, "mass_diff": 79.97, "labels": "Phospho"}],
                [],
                [{"start": 1, "end": 1, "mass_diff": 15.99, "labels": "Oxidation"}],
            ],
        }
    )


class TestProteoformBounds:
    def test_proteoform_bounds_round_trip(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="pf_bounds",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        sd0 = sv._prepare_vue_data({"proteinIndex": 0})["sequenceData"]
        assert sd0["proteoform_start"] == 2
        assert sd0["proteoform_end"] == 9

        # Sentinel -2 (UNDETERMINED_TERMINUS) round-trips for the open C-terminus.
        sd2 = sv._prepare_vue_data({"proteinIndex": 2})["sequenceData"]
        assert sd2["proteoform_end"] == -2

    def test_undetermined_sentinel_constant(self):
        from openms_insight.components.sequenceview import UNDETERMINED_TERMINUS

        assert UNDETERMINED_TERMINUS == -2

    def test_bounds_absent_omitted(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="pf_bounds_absent",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
        )
        sd = sv._prepare_vue_data({})["sequenceData"]
        assert "proteoform_start" not in sd
        assert "proteoform_end" not in sd


class TestMassHeader:
    def test_computed_and_precursor_mass_round_trip(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="mass_header",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        vd0 = sv._prepare_vue_data({"proteinIndex": 0})
        sd0 = vd0["sequenceData"]
        assert sd0["computed_mass"] == pytest.approx(1234.5)
        # theoretical_mass is computed from the sequence (non-zero, real protein).
        assert sd0["theoretical_mass"] > 0
        # Observed precursor mass flows into the top-level precursorMass slot.
        assert vd0["precursorMass"] == pytest.approx(1240.0)

    def test_computed_mass_zero_round_trips(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        """A 0.0 computed_mass is still emitted (marks the Proteoform/TnT path,
        even though the observed mass is unknown)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="mass_zero",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )
        sd1 = sv._prepare_vue_data({"proteinIndex": 1})["sequenceData"]
        assert sd1["computed_mass"] == pytest.approx(0.0)

    def test_precursor_mass_absent_defaults_zero(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="prec_absent",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
        )
        vd = sv._prepare_vue_data({})
        assert vd["precursorMass"] == 0.0
        assert "computed_mass" not in vd["sequenceData"]


class TestModRanges:
    def test_mod_ranges_round_trip(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="mod_ranges_rt",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )

        sd0 = sv._prepare_vue_data({"proteinIndex": 0})["sequenceData"]
        assert "mod_ranges" in sd0
        assert len(sd0["mod_ranges"]) == 1
        rng = sd0["mod_ranges"][0]
        assert rng["start"] == 3
        assert rng["end"] == 5
        assert rng["mass_diff"] == pytest.approx(79.97)
        assert rng["labels"] == "Phospho"

    def test_empty_mod_ranges_omitted(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        """An empty mod_ranges list is omitted from the payload (Vue defaults [])."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="mod_ranges_empty",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )
        sd1 = sv._prepare_vue_data({"proteinIndex": 1})["sequenceData"]
        assert "mod_ranges" not in sd1

    def test_normalize_mod_ranges_helper(self):
        from openms_insight.components.sequenceview import _normalize_mod_ranges

        # Well-formed entries pass through with coerced types.
        out = _normalize_mod_ranges(
            [{"start": 1, "end": 3, "mass_diff": 42.01, "labels": "Acetyl"}]
        )
        assert out == [{"start": 1, "end": 3, "mass_diff": 42.01, "labels": "Acetyl"}]

        # Missing optional fields default; missing required fields are dropped.
        out2 = _normalize_mod_ranges(
            [
                {"start": 0, "end": 2},  # mass_diff/labels default
                {"end": 5},  # no start -> dropped
                None,  # dropped
                "garbage",  # dropped
            ]
        )
        assert out2 == [{"start": 0, "end": 2, "mass_diff": 0.0, "labels": ""}]

        # None / non-iterable -> empty.
        assert _normalize_mod_ranges(None) == []


class TestDisableVariableModifications:
    def test_default_disable_true_in_args(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="dvm_default",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
        )
        args = sv._get_component_args()
        assert args["disableVariableModifications"] is True

    def test_enable_variable_modifications_flag(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="dvm_enabled",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
            disable_variable_modifications=False,
        )
        args = sv._get_component_args()
        assert args["disableVariableModifications"] is False

    def test_flag_cache_round_trip(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        SequenceView(
            cache_id="dvm_reload",
            sequence_data="PEPTIDEK",
            cache_path=str(temp_cache_dir),
            disable_variable_modifications=False,
        )
        sv2 = SequenceView(cache_id="dvm_reload", cache_path=str(temp_cache_dir))
        assert sv2._get_component_args()["disableVariableModifications"] is False


class TestParityHashSensitivity:
    def test_hash_changes_with_computed_mass(
        self, temp_cache_dir: Path, proteoform_parity_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="hash_parity",
            sequence_data=proteoform_parity_data,
            cache_path=str(temp_cache_dir),
            filters={"proteinIndex": "proteoform_index"},
        )
        h0 = sv._prepare_vue_data({"proteinIndex": 0})["_hash"]
        h2 = sv._prepare_vue_data({"proteinIndex": 2})["_hash"]
        assert h0 != h2


class TestParityBackwardCompat:
    def test_two_column_unaffected(
        self, temp_cache_dir: Path, sample_sequence_data: pl.LazyFrame
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="parity_bc",
            sequence_data=sample_sequence_data,
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
        )
        df = sample_sequence_data.collect()
        sd = sv._prepare_vue_data({"identification": df["scan_id"][0]})["sequenceData"]
        for key in (
            "proteoform_start",
            "proteoform_end",
            "computed_mass",
            "mod_ranges",
        ):
            assert key not in sd
