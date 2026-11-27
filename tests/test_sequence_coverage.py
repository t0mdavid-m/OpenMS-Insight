"""Tests for the SequenceCoverage component."""

import polars as pl
import pytest

from openms_insight import SequenceCoverage
from openms_insight.components.sequence_coverage import (
    DEFAULT_COUNT_BINS,
    EMPTY_COUNT_COLOR,
    count_color,
    covered_positions,
    pack_lanes,
)


def _coverage(data, tmp_path, **kwargs):
    defaults = {
        "cache_id": "coverage",
        "data": data,
        "cache_path": str(tmp_path),
        "reference": "AUGGCUACGU",
        "count_column": "psms",
        "track_column": "condition",
        "modifications_column": "mod_positions",
        "modification_labels_column": "mod_names",
        "filters": {"accession": "accession"},
        "interactivity": {"oligo": "oligo_id"},
    }
    defaults.update(kwargs)
    return SequenceCoverage(**defaults)


def test_count_color_bins():
    assert count_color(None) == EMPTY_COUNT_COLOR
    assert count_color(0) == EMPTY_COUNT_COLOR
    assert count_color(float("nan")) == EMPTY_COUNT_COLOR
    assert count_color(1) == DEFAULT_COUNT_BINS[0][2]
    assert count_color(3) == DEFAULT_COUNT_BINS[2][2]
    assert count_color(10_000) == DEFAULT_COUNT_BINS[-1][2]
    # Bins stored with None as the open upper bound
    assert count_color(500, [[1, "1", "#a"], [None, "2+", "#b"]]) == "#b"


def test_pack_lanes_stacks_overlaps():
    hits = [
        {"start": 1, "end": 4},
        {"start": 3, "end": 6},
        {"start": 5, "end": 8},
        {"start": 9, "end": 9},
    ]
    assert pack_lanes(hits) == 2
    assert [h["lane"] for h in hits] == [0, 1, 0, 0]
    assert pack_lanes([]) == 1


def test_covered_positions_clips_to_length():
    hits = [{"start": 0, "end": 3}, {"start": 2, "end": 12}]
    assert covered_positions(hits, 10) == 10
    assert covered_positions([{"start": 4, "end": 5}], 10) == 2


def test_block_size_validated(sample_coverage_data, tmp_path):
    with pytest.raises(ValueError, match="block_size"):
        _coverage(sample_coverage_data, tmp_path, block_size=5)
    with pytest.raises(ValueError, match="block_size"):
        _coverage(sample_coverage_data, tmp_path, block_size=True)


def test_missing_column_rejected(sample_coverage_data, tmp_path):
    with pytest.raises(ValueError, match="Missing required columns"):
        _coverage(sample_coverage_data, tmp_path, count_column="spectra")


def test_model_tracks_lanes_and_coverage(sample_coverage_data, tmp_path):
    coverage = _coverage(sample_coverage_data, tmp_path, track_order=["drug"])
    model = coverage.build_model({"accession": "tRNA1"})
    assert model["length"] == 10
    assert [t["name"] for t in model["tracks"]] == ["drug", "ctrl"]
    drug, ctrl = model["tracks"]
    assert drug["covered"] == 3 and drug["coverage"] == pytest.approx(0.3)
    assert ctrl["covered"] == 8 and ctrl["lanes"] == 2
    assert model["covered"] == 8
    assert model["coverage"] == pytest.approx(0.8)
    # Sorted by start, then longer first; lanes packed in that order
    assert [(h["start"], h["end"], h["lane"]) for h in ctrl["hits"]] == [
        (1, 4, 0),
        (3, 6, 1),
        (5, 8, 0),
    ]
    first = ctrl["hits"][0]
    assert first["label"] == "AUGG"
    assert first["count"] == 1
    assert first["values"] == {"oligo": 0}
    assert first["modifications"] == [{"position": 2, "label": "m1A"}]
    assert ctrl["hits"][2]["color"] == count_color(40)
    # A count of zero is drawn in the empty colour
    assert drug["hits"][0]["color"] == EMPTY_COUNT_COLOR


def test_filter_selects_reference(sample_coverage_data, tmp_path):
    coverage = _coverage(sample_coverage_data, tmp_path)
    model = coverage.build_model({"accession": "tRNA2"})
    assert [t["name"] for t in model["tracks"]] == ["ctrl"]
    assert model["tracks"][0]["hits"][0]["label"] == "GCGC"


def test_hits_clipped_and_dropped(tmp_path):
    data = pl.LazyFrame(
        {
            "start": [0, 8, 20, 6],
            "end": [3, 14, 25, 4],
            "sequence": ["a", "b", "c", "d"],
        }
    )
    coverage = SequenceCoverage(
        cache_id="clip", data=data, cache_path=str(tmp_path), reference="ACGUACGUAC"
    )
    model = coverage.build_model({})
    hits = model["tracks"][0]["hits"]
    # (0..3) -> 1..3, (8..14) -> 8..10, (20..25) dropped, (6..4) swapped to 4..6
    assert [(h["start"], h["end"]) for h in hits] == [(1, 3), (4, 6), (8, 10)]
    assert model["tracks"][0]["name"] == ""
    assert all(h["count"] == 1 for h in hits)


def test_set_reference_changes_render_key(sample_coverage_data, tmp_path):
    coverage = _coverage(sample_coverage_data, tmp_path)
    assert coverage._get_render_key() is None
    before = coverage._prepare_vue_data({"accession": "tRNA1"})["_hash"]
    coverage.set_reference(list("AUGG"), name="short")
    assert coverage.reference == ["A", "U", "G", "G"]
    assert coverage._get_render_key() is not None
    data = coverage._prepare_vue_data({"accession": "tRNA1"})
    assert data["_hash"] != before
    assert data["coverageData"]["name"] == "short"
    assert data["coverageData"]["length"] == 4
    coverage.set_reference(None)
    assert coverage.reference == list("AUGGCUACGU")


def test_tokens_as_list(tmp_path):
    data = pl.LazyFrame({"start": [2], "end": [3], "sequence": ["[m1A]G"]})
    coverage = SequenceCoverage(
        cache_id="tokens",
        data=data,
        cache_path=str(tmp_path),
        reference=["A", "[m1A]", "G", "U"],
    )
    model = coverage.build_model({})
    assert model["reference"][1] == "[m1A]"
    assert model["covered"] == 2


def test_component_args(sample_coverage_data, tmp_path):
    coverage = _coverage(
        sample_coverage_data,
        tmp_path,
        notes=["Counts are PSMs."],
        count_label="PSMs",
        image_format="png",
    )
    args = coverage._get_component_args()
    assert args["componentType"] == "SequenceCoverage"
    assert args["blockSize"] == 50
    assert args["countLabel"] == "PSMs"
    assert args["countBins"][-1][0] is None
    assert args["notes"] == ["Counts are PSMs."]
    assert args["interactivity"] == {"oligo": "oligo_id"}
    assert args["hasCounts"] is True
    assert coverage._get_vue_component_name() == "SequenceCoverage"
    assert coverage._get_data_key() == "coverageData"


def test_restored_from_cache(sample_coverage_data, tmp_path):
    _coverage(
        sample_coverage_data,
        tmp_path,
        block_size=30,
        track_order=["drug"],
        reference_name="tRNA",
    )
    restored = SequenceCoverage(cache_id="coverage", cache_path=str(tmp_path))
    assert restored.reference == list("AUGGCUACGU")
    assert restored._block_size == 30
    assert restored._track_order == ["drug"]
    model = restored.build_model({"accession": "tRNA1"})
    assert [t["name"] for t in model["tracks"]] == ["drug", "ctrl"]
    data = restored._prepare_vue_data({"accession": "tRNA1"})
    assert data["coverageData"]["name"] == "tRNA"


def test_call_validates_block_size(sample_coverage_data, tmp_path):
    coverage = _coverage(sample_coverage_data, tmp_path)
    with pytest.raises(ValueError, match="block_size"):
        coverage(key="c", block_size=500)
