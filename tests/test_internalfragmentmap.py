"""Tests for the InternalFragmentMap component.

Verifies parity of the internal-fragment compute ported from FLASHApp
``src/render/sequence.py:204-274`` plus the OpenMS-Insight component behavior
(Deconv vs TnT source, empty handling, cache config, state deps).

pyOpenMS is not required to run these tests: the component's terminal-mass path
falls back to a pure-python implementation, which is what we assert against using an
independent reference implementation of the same algorithm.
"""

from pathlib import Path

import polars as pl
import pytest

from openms_insight.components.internalfragmentmap import (
    AA_MASSES,
    H2O,
    NH3,
    InternalFragmentMap,
    _terminal_fragment_masses_simple,
    get_internal_fragment_data_from_seq,
    get_internal_fragment_masses_with_seq,
)


# --------------------------------------------------------------------------- #
# Independent reference implementation (mirrors sequence.py:204-256 exactly,    #
# using the pure-python terminal masses so it is reproducible without pyOpenMS) #
# --------------------------------------------------------------------------- #
def _ref_is_match(sorted_values, target, ppm):
    tol = target * ppm / 1e6
    lo, hi = 0, len(sorted_values) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(sorted_values[mid] - target) <= tol:
            return True
        elif sorted_values[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False


def _ref_internal(sequence, res_type, modifications=None):
    if res_type in ("by", "cz"):
        shift = -H2O
    elif res_type == "bz":
        shift = -H2O - NH3
    else:
        shift = -H2O + NH3

    terminal = _terminal_fragment_masses_simple(sequence)
    masses, starts, ends = [], [], []
    n = len(sequence)
    for i in range(n):
        if i == 0:
            continue
        if i == n - 1:
            break
        mass = 0.0
        for j in range(n):
            if j >= i:
                mass += AA_MASSES.get(sequence[j], 0.0)
            if j < i + 5 - 1:
                continue
            possible = [mass]
            if modifications is not None:
                for s, e, m in modifications:
                    if (s >= i + 1) and (e <= j + 1):
                        possible[0] += m
                    elif (s >= i + 1) or (e <= j + 1):
                        possible.append(mass + m)
            for mass in possible:
                if _ref_is_match(terminal, mass, 10.0):
                    continue
                masses.append(mass + H2O + shift)
                starts.append(i)
                ends.append(j + 1)
    return masses, starts, ends


SEQ = "PEPTIDESEQUENCE"  # length 15, no ambiguous residues


class TestComputeParity:
    def test_matches_reference_no_mods(self):
        for ion in ("by", "bz", "cy"):
            got = get_internal_fragment_masses_with_seq(SEQ, ion)
            ref = _ref_internal(SEQ, ion)
            assert got[1] == ref[1], f"start indices differ for {ion}"
            assert got[2] == ref[2], f"end indices differ for {ion}"
            assert got[0] == pytest.approx(ref[0]), f"masses differ for {ion}"

    def test_matches_reference_with_mods(self):
        mods = [(3, 5, 79.96633), (8, 8, 15.994915)]  # phospho-ish range + oxidation
        for ion in ("by", "bz", "cy"):
            got = get_internal_fragment_masses_with_seq(SEQ, ion, mods)
            ref = _ref_internal(SEQ, ion, mods)
            assert got[1] == ref[1]
            assert got[2] == ref[2]
            assert got[0] == pytest.approx(ref[0])

    def test_per_type_shift_relationship(self):
        """bz mass = by mass - NH3; cy mass = by mass + NH3 for the same fragment span."""
        by_m, by_s, by_e = get_internal_fragment_masses_with_seq(SEQ, "by")
        bz_m, bz_s, bz_e = get_internal_fragment_masses_with_seq(SEQ, "bz")
        cy_m, cy_s, cy_e = get_internal_fragment_masses_with_seq(SEQ, "cy")
        # Build lookup by (start, end). The set of spans differs because terminal
        # exclusion uses the per-type running mass which is identical across types
        # (the shift is applied AFTER the exclusion check), so spans match.
        by_map = {(s, e): m for m, s, e in zip(by_m, by_s, by_e)}
        bz_map = {(s, e): m for m, s, e in zip(bz_m, bz_s, bz_e)}
        cy_map = {(s, e): m for m, s, e in zip(cy_m, cy_s, cy_e)}
        assert by_map.keys() == bz_map.keys() == cy_map.keys()
        for span in by_map:
            assert bz_map[span] == pytest.approx(by_map[span] - NH3)
            assert cy_map[span] == pytest.approx(by_map[span] + NH3)

    def test_final_plus_h2o_and_shift(self):
        """Spot-check the emitted mass formula: running residue sum + H2O + shift."""
        # by shift is -H2O, so the net offset to the residue running sum is 0 for by
        # fragments that survive terminal exclusion.
        masses, starts, ends = get_internal_fragment_masses_with_seq(SEQ, "by")
        for m, s, e in zip(masses, starts, ends):
            residue_sum = sum(AA_MASSES[SEQ[k]] for k in range(s, e))
            assert m == pytest.approx(residue_sum)  # + H2O + (-H2O) = +0


class TestConstraints:
    def test_first_and_last_excluded(self):
        # The N-terminal index i never starts at 0 (first residue excluded) and never
        # equals len-1 (last residue excluded via the loop `break`). The C-terminal
        # bound is end = j+1, where j max is len-1, so end may equal len.
        for ion in ("by", "bz", "cy"):
            _, starts, ends = get_internal_fragment_masses_with_seq(SEQ, ion)
            assert all(s >= 1 for s in starts), "start index 0 must be excluded"
            assert all(s <= len(SEQ) - 2 for s in starts), (
                "N-terminal index must never reach the last residue"
            )
            assert all(e <= len(SEQ) for e in ends)

    def test_min_length_five(self):
        for ion in ("by", "bz", "cy"):
            _, starts, ends = get_internal_fragment_masses_with_seq(SEQ, ion)
            for s, e in zip(starts, ends):
                # fragment spans residues [s..e-1] inclusive -> length (e-1)-s+1 = e-s
                assert (e - s) >= 5, f"fragment ({s},{e}) shorter than 5"

    def test_short_sequence_yields_empty(self):
        # Length <= 5 can never produce an internal fragment: i in [1, len-2], the
        # smallest C-bound is i+5-1 = i+4, requiring len-1 >= i+4 i.e. len >= 6.
        for seq in ("", "PE", "PEPT", "PEPTI"):
            data = get_internal_fragment_data_from_seq(seq)
            for ion in ("by", "bz", "cy"):
                assert data[f"fragment_masses_{ion}"] == []
                assert data[f"start_indices_{ion}"] == []
                assert data[f"end_indices_{ion}"] == []

    def test_length_six_boundary(self):
        # Length 6: only i=1, j=5 satisfies (j >= i+4) with i in [1, len-2=4].
        # Exactly one fragment per ion type, span (start=1, end=6).
        data = get_internal_fragment_data_from_seq("PEPTID")
        for ion in ("by", "bz", "cy"):
            assert len(data[f"fragment_masses_{ion}"]) == 1
            assert data[f"start_indices_{ion}"] == [1]
            assert data[f"end_indices_{ion}"] == [6]

    def test_data_dict_shape(self):
        data = get_internal_fragment_data_from_seq(SEQ)
        for ion in ("by", "bz", "cy"):
            assert f"fragment_masses_{ion}" in data
            assert f"start_indices_{ion}" in data
            assert f"end_indices_{ion}" in data
            n = len(data[f"fragment_masses_{ion}"])
            assert len(data[f"start_indices_{ion}"]) == n
            assert len(data[f"end_indices_{ion}"]) == n


class TestComponentDeconv:
    def test_static_sequence_prepares_data(self, temp_cache_dir: Path):
        ifm = InternalFragmentMap(
            cache_id="ifm_deconv",
            sequence_data=SEQ,
            cache_path=str(temp_cache_dir),
        )
        vue = ifm._prepare_vue_data({})
        ifd = vue["internalFragmentData"]
        assert ifd["sequence"] == list(SEQ)
        for ion in ("by", "bz", "cy"):
            assert f"fragment_masses_{ion}" in ifd
        assert len(ifd["fragment_masses_by"]) > 0
        assert vue["observedMasses"] == []

    def test_component_args(self, temp_cache_dir: Path):
        ifm = InternalFragmentMap(
            cache_id="ifm_args",
            sequence_data=SEQ,
            cache_path=str(temp_cache_dir),
        )
        args = ifm._get_component_args()
        assert args["componentType"] == "InternalFragmentMap"
        assert args["title"] == "Internal Fragment Map"
        assert args["toleranceUnit"] == "ppm"
        assert args["ionColors"]["by"] == "#f0a441"

    def test_short_sequence_component_empty(self, temp_cache_dir: Path):
        ifm = InternalFragmentMap(
            cache_id="ifm_short",
            sequence_data="PEPTI",
            cache_path=str(temp_cache_dir),
        )
        vue = ifm._prepare_vue_data({})
        ifd = vue["internalFragmentData"]
        assert ifd["sequence"] == list("PEPTI")
        assert ifd["fragment_masses_by"] == []


class TestComponentTnT:
    @pytest.fixture
    def proteoform_lf(self) -> pl.LazyFrame:
        return pl.LazyFrame(
            {
                "proteoform_index": [0, 1, 2],
                "sequence": ["PEPTIDESEQUENCE", "ACDEFGHIKLMNPQR", "MNPQRSTVWYACDEF"],
                "computed_mass": [1.0, 2.0, 3.0],
            }
        )

    def test_filter_selects_right_proteoform(self, temp_cache_dir: Path, proteoform_lf):
        ifm = InternalFragmentMap(
            cache_id="ifm_tnt",
            sequence_data=proteoform_lf,
            filters={"proteinIndex": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        seq0 = ifm._get_sequence_for_state({"proteinIndex": 0})
        seq1 = ifm._get_sequence_for_state({"proteinIndex": 1})
        assert seq0 == "PEPTIDESEQUENCE"
        assert seq1 == "ACDEFGHIKLMNPQR"

    def test_missing_selection_empty(self, temp_cache_dir: Path, proteoform_lf):
        ifm = InternalFragmentMap(
            cache_id="ifm_tnt_empty",
            sequence_data=proteoform_lf,
            filters={"proteinIndex": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        seq = ifm._get_sequence_for_state({"proteinIndex": None})
        assert seq == ""
        vue = ifm._prepare_vue_data({"proteinIndex": None})
        assert vue["internalFragmentData"]["sequence"] == []
        assert vue["internalFragmentData"]["fragment_masses_by"] == []

    def test_proteoform_start_end_slicing(self, temp_cache_dir: Path):
        lf = pl.LazyFrame(
            {
                "proteoform_index": [0],
                "sequence": ["XXXPEPTIDESEQUENCEXXX"],
                "proteoform_start": [3],
                "proteoform_end": [17],
            }
        )
        ifm = InternalFragmentMap(
            cache_id="ifm_slice",
            sequence_data=lf,
            filters={"proteinIndex": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        seq = ifm._get_sequence_for_state({"proteinIndex": 0})
        assert seq == "PEPTIDESEQUENCE"

    def test_state_dependencies(self, temp_cache_dir: Path, proteoform_lf):
        ifm = InternalFragmentMap(
            cache_id="ifm_deps",
            sequence_data=proteoform_lf,
            filters={"proteinIndex": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        assert ifm.get_state_dependencies() == ["proteinIndex"]


class TestObservedMassMatching:
    def test_observed_masses_filter(self, temp_cache_dir: Path):
        peaks = pl.LazyFrame(
            {
                "proteoform_index": [0, 0, 0],
                "mass": [123.0, 456.0, 789.0],
            }
        )
        seqs = pl.LazyFrame(
            {
                "proteoform_index": [0],
                "sequence": [SEQ],
            }
        )
        ifm = InternalFragmentMap(
            cache_id="ifm_obs",
            sequence_data=seqs,
            peaks_data=peaks,
            filters={"proteinIndex": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        obs = ifm._get_observed_masses_for_state({"proteinIndex": 0})
        assert obs == [123.0, 456.0, 789.0]
        obs_none = ifm._get_observed_masses_for_state({"proteinIndex": None})
        assert obs_none == []


class TestCacheReconstruction:
    def test_reconstruct_from_cache(self, temp_cache_dir: Path):
        ifm = InternalFragmentMap(
            cache_id="ifm_recon",
            sequence_data=SEQ,
            tolerance=20.0,
            tolerance_ppm=False,
            cache_path=str(temp_cache_dir),
        )
        first = ifm._prepare_vue_data({})

        # Reconstruct (no data) — config restored from manifest.
        ifm2 = InternalFragmentMap(
            cache_id="ifm_recon",
            cache_path=str(temp_cache_dir),
        )
        assert ifm2._tolerance == 20.0
        assert ifm2._tolerance_ppm is False
        args = ifm2._get_component_args()
        assert args["toleranceUnit"] == "Da"
        second = ifm2._prepare_vue_data({})
        assert (
            second["internalFragmentData"]["sequence"]
            == first["internalFragmentData"]["sequence"]
        )
        assert second["internalFragmentData"]["fragment_masses_by"] == pytest.approx(
            first["internalFragmentData"]["fragment_masses_by"]
        )
