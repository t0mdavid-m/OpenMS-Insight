"""Tests for SequenceView's nucleic-acid (oligonucleotide) mode."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from openms_insight.components import sequenceview as sv

pyopenms = pytest.importorskip("pyopenms")

PROTON = 1.007276


def test_molecule_is_checked():
    with pytest.raises(ValueError):
        sv.ion_types_for("protein")


def test_ion_types_and_sides():
    assert sv.ion_types_for("nucleic_acid") == sv.NUCLEIC_ACID_ION_TYPES
    assert sv.is_prefix_ion("a-B", "nucleic_acid")
    assert sv.is_prefix_ion("d", "nucleic_acid")
    assert not sv.is_prefix_ion("w", "nucleic_acid")
    assert sv.is_prefix_ion("b", "peptide")
    assert not sv.is_prefix_ion("y", "peptide")


def test_ion_label_names_base_loss():
    assert sv.ion_label("a-B", 3) == "a3-B"
    assert sv.ion_label("y", 7) == "y7"


def test_view_settings_per_molecule():
    config = sv.default_annotation_config("nucleic_acid")
    assert config["ion_types"] == ["a-B", "c", "w", "y"]
    assert config["neutral_losses"] is False
    assert "w" in config["colors"]
    # The peptide default is left as it was
    assert sv.default_annotation_config()["ion_types"] == ["b", "y"]
    assert sv.DEFAULT_ANNOTATION_CONFIG["ion_types"] == ["b", "y"]
    assert sv.charge_sign_for("nucleic_acid") == -1
    assert sv.charge_sign_for("peptide") == 1
    assert sv.terminals_for("nucleic_acid") == ["5'", "3'"]
    info = {i["name"]: i for i in sv.ion_type_info("nucleic_acid", ["c"])}
    assert info["c"]["selected"] and not info["w"]["selected"]
    assert info["w"]["slot"] == "x" and not info["w"]["prefix"]
    assert info["a-B"]["slot"] == "a" and info["a-B"]["prefix"]


def test_parse_modified_oligonucleotide():
    residues, mods = sv.parse_sequence("AU[m1A]G", "nucleic_acid")
    assert residues == ["A", "U", "m1A", "G"]
    assert mods[0] is None and mods[3] is None
    assert mods[2] == pytest.approx(14.02, abs=0.01)


def test_fragment_masses_match_pyopenms():
    masses = sv.calculate_fragment_masses("AUGC", "nucleic_acid")
    assert set(masses) == {f"fragment_masses_{i}" for i in sv.NUCLEIC_ACID_ION_TYPES}
    assert len(masses["fragment_masses_c"]) == 4
    # c1 of A: the 5'-OH nucleotide with its 3'-phosphate minus water
    gen = pyopenms.NucleicAcidSpectrumGenerator()
    p = gen.getParameters()
    p.setValue("add_c_ions", "true")
    p.setValue("add_first_prefix_ion", "true")
    for ion in ("b", "y"):
        p.setValue(f"add_{ion}_ions", "false")
    gen.setParameters(p)
    spec = gen.getSpectrum(pyopenms.NASequence.fromString("AUGC"), -1, -1)
    expected = sorted(spec[i].getMZ() + PROTON for i in range(spec.size()))
    got = sorted(m for pos in masses["fragment_masses_c"] for m in pos)
    assert got == pytest.approx(expected, abs=1e-6)


def test_sequence_mass():
    mass = sv.get_sequence_mass("AUGC", "nucleic_acid")
    assert mass == pytest.approx(
        pyopenms.NASequence.fromString("AUGC").getMonoWeight()
    )


def test_match_fragment_ions_negative_mode():
    masses = sv.calculate_fragment_masses("AUGCU", "nucleic_acid")
    neutral = masses["fragment_masses_w"][1][0]
    observed = np.array([(neutral - 2 * PROTON) / 2, 50.0])
    rows = sv.match_fragment_ions(
        "AUGCU", observed, precursor_charge=3, molecule="nucleic_acid"
    )
    assert any(r["ion"] == "w2" and r["charge"] == 2 for r in rows)
    assert all(r["observed_mz"] != 50.0 for r in rows)
    # The same peak read as a positive ion matches nothing named w
    assert all(r["ion_type"] != "w" for r in sv.match_fragment_ions(
        "PEPTIDE", observed, precursor_charge=3
    ))


def test_match_labels_base_loss():
    masses = sv.calculate_fragment_masses("AUGCU", "nucleic_acid")
    neutral = masses["fragment_masses_a-B"][2][0]
    rows = sv.match_fragment_ions(
        "AUGCU", np.array([neutral - PROTON]), molecule="nucleic_acid"
    )
    assert [r["ion"] for r in rows] == ["a3-B"]
    assert rows[0]["ion_type"] == "a-B"


def _view(cache: Path, molecule: str = "nucleic_acid", cache_id: str = "sv_na"):
    return sv.SequenceView(
        cache_id=cache_id,
        sequence_data=pl.LazyFrame(
            {"id": [1], "sequence": ["AU[m1A]GC"], "precursor_charge": [3]}
        ),
        peaks_data=pl.LazyFrame(
            {"id": [1], "peak_id": [1], "mass": [500.0], "intensity": [10.0]}
        ),
        filters={"spectrum": "id"},
        cache_path=str(cache),
        molecule=molecule,
    )


def test_unknown_molecule_rejected(temp_cache_dir: Path):
    with pytest.raises(ValueError):
        _view(temp_cache_dir, molecule="dna")


def test_payload_describes_the_molecule(temp_cache_dir: Path):
    view = _view(temp_cache_dir)
    assert view.molecule == "nucleic_acid"
    data = view._prepare_vue_data({"spectrum": 1})["sequenceData"]
    assert data["molecule"] == "nucleic_acid"
    assert data["sequence"] == ["A", "U", "m1A", "G", "C"]
    assert data["charge_sign"] == -1
    assert data["terminals"] == ["5'", "3'"]
    assert [i["name"] for i in data["ion_types"] if i["selected"]] == [
        "a-B", "c", "w", "y",
    ]
    assert len(data["fragment_masses_w"]) == 5
    assert data["neutral_losses"] is False


def test_peptide_payload_unchanged(temp_cache_dir: Path):
    view = sv.SequenceView(
        cache_id="sv_pep",
        sequence_data=pl.LazyFrame({"id": [1], "sequence": ["PEPTIDER"]}),
        cache_path=str(temp_cache_dir),
    )
    data = view._prepare_vue_data({})["sequenceData"]
    assert data["molecule"] == "peptide"
    assert data["terminals"] == ["N", "C"]
    assert data["charge_sign"] == 1
    assert "fragment_masses_b" in data


def test_molecule_restored_from_cache(temp_cache_dir: Path):
    _view(temp_cache_dir, cache_id="sv_na_cache")
    restored = sv.SequenceView(
        cache_id="sv_na_cache", cache_path=str(temp_cache_dir)
    )
    assert restored.molecule == "nucleic_acid"
