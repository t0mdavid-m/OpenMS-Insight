"""Tests for the per-scan fragment ion export (SequenceView.export_fragment_ions)."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

pytest.importorskip("pyopenms")

from openms_insight.components.sequenceview import (  # noqa: E402
    PROTON_MASS,
    SequenceView,
    calculate_fragment_masses_pyopenms,
    match_fragment_ions,
)


def _mz(neutral: float, charge: int) -> float:
    return (neutral + charge * PROTON_MASS) / charge


def _ion_mass(sequence: str, ion_type: str, number: int) -> float:
    masses = calculate_fragment_masses_pyopenms(sequence)[f"fragment_masses_{ion_type}"]
    return masses[number - 1][0]


def test_match_reports_charge_states_and_losses():
    seq = "PEPTIDEK"
    y3 = _ion_mass(seq, "y", 3)
    b2 = _ion_mass(seq, "b", 2)
    observed = np.array(
        [
            _mz(y3, 1) + 0.001,  # y3 1+ within 20 ppm
            _mz(y3, 2),  # y3 2+
            _mz(b2 - 18.0105646863, 1),  # b2-H2O 1+
            500.0,  # noise
        ]
    )

    rows = match_fragment_ions(
        seq,
        observed,
        precursor_charge=2,
        annotation_config={"tolerance": 20.0, "tolerance_ppm": True},
        intensities=np.array([10.0, 20.0, 30.0, 40.0]),
        peak_ids=np.array([100, 101, 102, 103]),
    )

    found = {(r["ion"], r["charge"]): r for r in rows}
    assert found[("y3", 1)]["peak_id"] == 100
    assert found[("y3", 1)]["intensity"] == 10.0
    assert found[("y3", 1)]["mass_error_da"] == pytest.approx(0.001, abs=1e-9)
    assert found[("y3", 2)]["peak_id"] == 101
    assert found[("b2-H2O", 1)]["ion_type"] == "b-H2O"
    assert all(r["peak_id"] != 103 for r in rows)


def test_charge_limited_by_precursor_and_da_tolerance():
    seq = "PEPTIDEK"
    y3 = _ion_mass(seq, "y", 3)
    observed = np.array([_mz(y3, 2) + 0.03])

    # 2+ is beyond a 1+ precursor
    assert match_fragment_ions(seq, observed, precursor_charge=1) == []
    # 0.05 Da tolerance catches it at 2+
    rows = match_fragment_ions(
        seq,
        observed,
        precursor_charge=2,
        annotation_config={"tolerance": 0.05, "tolerance_ppm": False},
    )
    assert [(r["ion"], r["charge"]) for r in rows] == [("y3", 2)]


def test_include_unmatched_lists_every_theoretical_ion():
    seq = "PEPTIDEK"
    rows = match_fragment_ions(
        seq,
        np.array([]),
        precursor_charge=1,
        annotation_config={"neutral_losses": False, "ion_types": ["b", "y"]},
        include_unmatched=True,
    )
    # b1..b7 and y1..y7 at charge 1 (no full-length fragment)
    assert len(rows) == 14
    assert all(r["observed_mz"] is None for r in rows)


def test_export_matches_each_psm_against_its_own_scan(temp_cache_dir: Path):
    seq_a, seq_b = "PEPTIDEK", "ELVISK"
    y2_a = _ion_mass(seq_a, "y", 2)
    y2_b = _ion_mass(seq_b, "y", 2)
    sequences = pl.LazyFrame(
        {
            "sequence_id": [0, 1],
            "file_index": [0, 0],
            "scan_id": [10, 20],
            "sequence": [seq_a, seq_b],
            "precursor_charge": [2, 2],
        }
    )
    peaks = pl.LazyFrame(
        {
            "peak_id": [0, 1, 2],
            "file_index": [0, 0, 0],
            "scan_id": [10, 20, 20],
            # scan 20 also holds seq_a's y2, which must not be credited to seq_a
            "mass": [_mz(y2_a, 1), _mz(y2_b, 1), _mz(y2_a, 1)],
            "intensity": [1.0, 2.0, 3.0],
        }
    )
    sv = SequenceView(
        cache_id="fragment_export",
        sequence_data=sequences,
        peaks_data=peaks,
        filters={
            "identification": "sequence_id",
            "file": "file_index",
            "spectrum": "scan_id",
        },
        cache_path=str(temp_cache_dir),
        annotation_config={"tolerance": 10.0, "tolerance_ppm": True},
    )

    export = sv.export_fragment_ions()

    assert export.columns[:5] == [
        "sequence_id",
        "file_index",
        "scan_id",
        "sequence",
        "precursor_charge",
    ]
    by_seq = {
        s: set(zip(g["ion"], g["peak_id"], strict=True))
        for (s,), g in export.partition_by("sequence", as_dict=True).items()
    }
    assert by_seq[seq_a] == {("y2", 0)}
    assert ("y2", 1) in by_seq[seq_b]
    assert all(pid != 2 for _, pid in by_seq[seq_b] if _ == "y2")

    # A view reloaded from its cache exports the same table
    reloaded = SequenceView(cache_id="fragment_export", cache_path=str(temp_cache_dir))
    assert reloaded.export_fragment_ions().equals(export)


def test_export_empty_is_typed(temp_cache_dir: Path):
    sv = SequenceView(
        cache_id="fragment_export_empty",
        sequence_data=pl.LazyFrame(
            {"scan_id": [1], "sequence": ["PEPTIDEK"], "precursor_charge": [2]}
        ),
        peaks_data=pl.LazyFrame(
            {"peak_id": [0], "scan_id": [2], "mass": [100.0], "intensity": [1.0]}
        ),
        filters={"spectrum": "scan_id"},
        cache_path=str(temp_cache_dir),
    )
    export = sv.export_fragment_ions()
    assert export.height == 0
    assert export.schema["theoretical_mz"] == pl.Float64
