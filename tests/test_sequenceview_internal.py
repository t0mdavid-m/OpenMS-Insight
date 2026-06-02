"""Pinned-math tests for the ported internal-fragment enumeration.

These tests pin the pure functions ported from FLASHApp/src/render/sequence.py
into openms_insight.components.sequenceview. They encode every parity trap:
min-length-5 start, end reaching the C-terminus, start barred from first/last,
asymmetric (start 0-based, end 1-based) indices, the three family shifts
(by/cz -> +0, bz -> -NH3, cy -> +NH3), ambiguous-modification forking, and the
per-candidate terminal-collision filter.
"""

import math
from collections import Counter

from openms_insight.components.sequenceview import (
    calculate_fragment_masses_pyopenms,
    compute_internal_fragment_data,
    compute_internal_fragment_masses,
    parse_openms_sequence,
    _terminal_collision_masses,
)

NH3 = 17.0265491015


def _collision_masses_from_families(fragment_masses, ions):
    """Build a sorted terminal-collision list from explicit ion families.

    Helper mirroring :func:`_terminal_collision_masses` but with a configurable
    family tuple, so a test can contrast the oracle's ``b, y, c, z`` set against
    the (incorrect) ``b, c, x, y`` set.
    """
    masses = []
    for ion in ions:
        for per_pos in fragment_masses.get(f"fragment_masses_{ion}", []):
            masses.extend(per_pos)
    masses.sort()
    return masses


def test_internal_fragment_golden_PEPTIDEK_no_mods_no_collision():
    """NUMERIC GOLDEN: PEPTIDEK, no mods, collisions off."""
    residues = list("PEPTIDEK")
    data = compute_internal_fragment_data(
        residues,
        ion_types=("by", "bz", "cy"),
        min_length=5,
        modifications=None,
        remove_terminal_collisions=False,
    )

    # start/end indices identical across families
    for fam in ("by", "bz", "cy"):
        assert data[f"start_indices_{fam}"] == [1, 1, 1, 2, 2, 3]
        assert data[f"end_indices_{fam}"] == [6, 7, 8, 7, 8, 8]

    expected_by = [
        555.254043,  # (1,6) EPTID
        684.296636,  # (1,7) EPTIDE
        812.391599,  # (1,8) EPTIDEK  (end reaches C-terminus, includes K)
        555.254043,  # (2,7) PTIDE
        683.349006,  # (2,8) PTIDEK
        586.296242,  # (3,8) TIDEK
    ]
    assert len(data["fragment_masses_by"]) == len(expected_by)
    for got, exp in zip(data["fragment_masses_by"], expected_by):
        assert math.isclose(got, exp, abs_tol=1e-4)

    # bz = by - NH3 ; cy = by + NH3 (family-shift invariant)
    for by, bz, cy in zip(
        data["fragment_masses_by"],
        data["fragment_masses_bz"],
        data["fragment_masses_cy"],
    ):
        assert math.isclose(bz, by - NH3, abs_tol=1e-6)
        assert math.isclose(cy, by + NH3, abs_tol=1e-6)


def test_internal_fragment_golden_bz_cy_absolute():
    """Pin the exact bz and cy mass lists too (not just the invariant)."""
    residues = list("PEPTIDEK")
    data = compute_internal_fragment_data(
        residues, remove_terminal_collisions=False
    )
    expected_bz = [
        538.227494,
        667.270087,
        795.365050,
        538.227494,
        666.322457,
        569.269693,
    ]
    expected_cy = [
        572.280592,
        701.323185,
        829.418148,
        572.280592,
        700.375555,
        603.322791,
    ]
    for got, exp in zip(data["fragment_masses_bz"], expected_bz):
        assert math.isclose(got, exp, abs_tol=1e-4)
    for got, exp in zip(data["fragment_masses_cy"], expected_cy):
        assert math.isclose(got, exp, abs_tol=1e-4)


def test_internal_min_length_enforced():
    """Smallest fragment spans exactly 5 residues; none shorter appears."""
    residues = list("PEPTIDEK")
    _m, s, e = compute_internal_fragment_masses(
        residues, "by", min_length=5, terminal_masses=None
    )
    # end is 1-based, start 0-based -> residue span length == end - start
    assert all((end - start) >= 5 for start, end in zip(s, e))
    # first/last start positions barred -> start in [1, L-2]
    assert min(s) >= 1
    assert max(s) <= len(residues) - 2


def test_internal_min_length_custom():
    """A larger min_length removes the short windows."""
    residues = list("PEPTIDEK")
    _m5, s5, _e5 = compute_internal_fragment_masses(
        residues, "by", min_length=5, terminal_masses=None
    )
    _m6, s6, _e6 = compute_internal_fragment_masses(
        residues, "by", min_length=6, terminal_masses=None
    )
    assert len(s6) < len(s5)


def test_internal_end_can_reach_cterminus():
    """The end index may equal L (fragment includes the last residue)."""
    residues = list("PEPTIDEK")
    _m, _s, e = compute_internal_fragment_masses(
        residues, "by", terminal_masses=None
    )
    assert max(e) == len(residues)  # includes the last residue (K)


def test_internal_short_sequence_empty():
    """A sequence shorter than min_length yields no internal fragments."""
    residues = list("PEPT")  # length 4 < 5
    data = compute_internal_fragment_data(
        residues, remove_terminal_collisions=False
    )
    for fam in ("by", "bz", "cy"):
        assert data[f"fragment_masses_{fam}"] == []
        assert data[f"start_indices_{fam}"] == []
        assert data[f"end_indices_{fam}"] == []


def test_internal_ambiguous_modification_forks():
    """Partially overlapping mods fork; fully-contained mods add once."""
    residues = list("PEPTIDEK")
    mods = [(2, 4, 79.966331)]  # 1-based start/end inclusive (phospho), ambiguous
    m, s, e = compute_internal_fragment_masses(
        residues, "by", min_length=5, modifications=mods, terminal_masses=None
    )

    pairs = Counter(zip(s, e))
    # Some (start,end) windows fork into two masses (unmodified + +79.966331).
    assert any(c == 2 for c in pairs.values()), (
        "ambiguous mod must fork into two masses"
    )

    # Freeze the exact output (derived by running the ported implementation).
    expected_starts = [1, 1, 1, 2, 2, 2, 2, 3, 3]
    expected_ends = [6, 7, 8, 7, 7, 8, 8, 8, 8]
    assert s == expected_starts
    assert e == expected_ends
    expected_masses = [
        635.220374,  # (1,6) mod fully contained [2,4] -> single shifted entry
        764.262967,  # (1,7) fully contained
        892.357930,  # (1,8) fully contained
        555.254043,  # (2,7) partial -> unmodified variant
        635.220374,  # (2,7) partial -> +phospho variant
        683.349006,  # (2,8) partial -> unmodified variant
        763.315337,  # (2,8) partial -> +phospho variant
        586.296242,  # (3,8) partial -> unmodified variant
        666.262573,  # (3,8) partial -> +phospho variant
    ]
    assert len(m) == len(expected_masses)
    for got, exp in zip(m, expected_masses):
        assert math.isclose(got, exp, abs_tol=1e-4)

    # (1,6) is fully contained -> appears exactly once (single, shifted).
    assert pairs[(1, 6)] == 1
    # (2,7) partially overlaps -> appears twice.
    assert pairs[(2, 7)] == 2


def test_internal_terminal_collision_drops_entries():
    """A terminal mass equal to a candidate's pre-shift sum drops that entry."""
    residues = list("PEPTIDEK")
    base = compute_internal_fragment_data(
        residues, remove_terminal_collisions=False
    )
    # The collision filter compares the PRE-(+H2O+shift) candidate `mm`.
    # For 'by' the emitted mass is mm + H2O + shift with shift == -H2O, so the
    # net add is 0 and mm == by_mass exactly.
    first_by = base["fragment_masses_by"][0]
    preshift = first_by
    filtered_m, _s, _e = compute_internal_fragment_masses(
        residues, "by", terminal_masses=[preshift], terminal_collision_ppm=10.0
    )
    # The colliding entry (and any duplicate-mass window) is removed.
    assert len(filtered_m) < len(base["fragment_masses_by"])
    # The exact masses surviving (PEPTIDEK has two windows at 555.254043).
    expected_remaining = [684.296636, 812.391599, 683.349006, 586.296242]
    assert len(filtered_m) == len(expected_remaining)
    for got, exp in zip(filtered_m, expected_remaining):
        assert math.isclose(got, exp, abs_tol=1e-4)


def test_internal_terminal_collision_default_on_in_data():
    """compute_internal_fragment_data honours remove_terminal_collisions."""
    residues = list("PEPTIDEK")
    on = compute_internal_fragment_data(residues, remove_terminal_collisions=True)
    off = compute_internal_fragment_data(
        residues, remove_terminal_collisions=False
    )
    # With no terminal_masses provided, "on" degrades to no filtering (term=None
    # only when remove flag is False; when True but terminal_masses=None the
    # per-family call still gets terminal_masses=None -> no drops).
    # So both are equal here; the meaningful collision behaviour is covered by
    # test_internal_terminal_collision_drops_entries with explicit terminals.
    assert on["fragment_masses_by"] == off["fragment_masses_by"]


def test_internal_unknown_residue_uses_zero_mass():
    """X/Z map to 0 in the verbatim aa_masses table (no pyOpenMS fallback)."""
    residues = list("PEPXIDEK")  # X at index 3 contributes 0
    with_x = compute_internal_fragment_masses(
        residues, "by", terminal_masses=None
    )
    residues_ref = list("PEPTIDEK")
    ref = compute_internal_fragment_masses(
        residues_ref, "by", terminal_masses=None
    )
    # Same number of windows; masses differ where X replaces T (101.047679).
    assert len(with_x[0]) == len(ref[0])
    # Window (1,6) = EPTID vs EPXID differs by exactly the T residue mass.
    assert math.isclose(ref[0][0] - with_x[0][0], 101.047679, abs_tol=1e-4)


def test_internal_by_cz_same_family():
    """by and cz share the same shift (collapse into one family)."""
    residues = list("PEPTIDEK")
    by_m, _s, _e = compute_internal_fragment_masses(
        residues, "by", terminal_masses=None
    )
    cz_m, _s2, _e2 = compute_internal_fragment_masses(
        residues, "cz", terminal_masses=None
    )
    assert by_m == cz_m


def test_terminal_collision_masses_uses_b_y_c_z_not_b_c_x_y():
    """The collision set is the oracle's b, y, c, z (byp+bys+czp+czs), not b,c,x,y.

    Oracle FLASHApp/src/render/sequence.py:213-215 builds the terminal-collision
    masses from ``byp + bys + czp + czs`` = the b/y prefix-suffix and c/z
    prefix-suffix neutral masses (families b, y, c, z). Substituting ``x`` for
    ``z`` (the prior Insight bug) shifts ~42 Da and changes drop decisions.

    PEPTIDEK exercise: the production helper's list must contain every z neutral
    mass and must NOT equal the x-substituted list.
    """
    fm = calculate_fragment_masses_pyopenms("PEPTIDEK")
    produced = _terminal_collision_masses(fm)
    expected = _collision_masses_from_families(fm, ("b", "y", "c", "z"))
    wrong = _collision_masses_from_families(fm, ("b", "c", "x", "y"))

    assert produced == expected
    # The two family sets must actually differ (z vs x are ~42 Da apart).
    assert produced != wrong
    # Every z terminal neutral mass is present in the collision set.
    z_masses = [m for sub in fm["fragment_masses_z"] for m in sub]
    for zm in z_masses:
        assert any(math.isclose(zm, pm, abs_tol=1e-6) for pm in produced)


def test_internal_terminal_collision_z_vs_x_changes_drop():
    """A by-internal that collides with a z terminal (not x) is dropped via b,y,c,z.

    For RDDMTSELVLE the internal 'by' fragment at (start=3, end=10) has neutral
    mass 773.3993, which is within 10 ppm of a terminal **z** mass (773.3933) but
    of NO terminal **x** mass. So:
      * the oracle's b, y, c, z set (now used by ``_terminal_collision_masses``)
        DROPS (3, 10);
      * the incorrect b, c, x, y set would KEEP it.
    This pins that the family substitution is correct.
    """
    seq = "RDDMTSELVLE"
    residues, _ = parse_openms_sequence(seq)
    fm = calculate_fragment_masses_pyopenms(seq)

    term_correct = _terminal_collision_masses(fm)  # b, y, c, z (production)
    term_wrong = _collision_masses_from_families(fm, ("b", "c", "x", "y"))

    correct = compute_internal_fragment_data(
        residues,
        terminal_masses=term_correct,
        remove_terminal_collisions=True,
        terminal_collision_ppm=10.0,
    )
    wrong = compute_internal_fragment_data(
        residues,
        terminal_masses=term_wrong,
        remove_terminal_collisions=True,
        terminal_collision_ppm=10.0,
    )

    correct_pairs = set(
        zip(correct["start_indices_by"], correct["end_indices_by"])
    )
    wrong_pairs = set(zip(wrong["start_indices_by"], wrong["end_indices_by"]))

    # (3, 10) is dropped by the correct set, kept by the wrong set.
    assert (3, 10) not in correct_pairs
    assert (3, 10) in wrong_pairs
    # And the correct set yields exactly one fewer 'by' internal fragment.
    assert len(correct["fragment_masses_by"]) == len(
        wrong["fragment_masses_by"]
    ) - 1

    # Confirm the divergence is specifically z (within 10 ppm) and not x.
    dropped_mass = 773.399327  # by-internal (3,10) neutral mass, pre-shift net 0
    z_masses = [m for sub in fm["fragment_masses_z"] for m in sub]
    x_masses = [m for sub in fm["fragment_masses_x"] for m in sub]
    tol = dropped_mass * 10.0 / 1e6
    assert any(abs(m - dropped_mass) <= tol for m in z_masses)
    assert not any(abs(m - dropped_mass) <= tol for m in x_masses)
