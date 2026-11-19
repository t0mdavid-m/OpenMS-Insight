"""SequenceLogo: letter heights from aligned sequences, filters, clicks."""

import math

import polars as pl
import pytest

from openms_insight import SequenceLogo
from openms_insight.core.sequence_logo import (
    DNA,
    PROTEIN,
    default_colors,
    logo_frame,
    max_height,
    normalize_alphabet,
    normalize_background,
)


def _heights(frame: pl.DataFrame) -> dict[tuple[int, str], float]:
    return {
        (p, r): h
        for p, r, h in frame.select("position", "residue", "height").iter_rows()
    }


def test_uniform_background_is_the_usual_logo():
    data = pl.DataFrame({"s": ["AKRG", "AKRG", "AKDG", "AEDG"]})
    frame = logo_frame(data, "s", PROTEIN, normalize_background(None, PROTEIN))
    h = _heights(frame)
    full = math.log2(20)
    assert h[(0, "A")] == pytest.approx(full)
    # Position 1: K 3/4, E 1/4 -> IC = log2(20) - H(0.75, 0.25)
    entropy = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
    assert h[(1, "K")] == pytest.approx(0.75 * (full - entropy))
    assert h[(1, "E")] == pytest.approx(0.25 * (full - entropy))
    # Within a position, from the lowest letter to the highest
    pos1 = frame.filter(pl.col("position") == 1)["residue"].to_list()
    assert pos1 == ["E", "K"]


def test_weights_gaps_and_probability():
    data = pl.DataFrame({"s": ["AC", "-C", "AX"], "w": [3.0, 1.0, 1.0]})
    frame = logo_frame(
        data, "s", DNA, normalize_background(None, DNA), "probability", "w"
    )
    rows = {
        (p, r): (c, f)
        for p, r, c, f in frame.select(
            "position", "residue", "count", "frequency"
        ).iter_rows()
    }
    # '-' and 'X' are not counted
    assert rows == {(0, "A"): (4.0, 1.0), (1, "C"): (4.0, 1.0)}
    assert frame["height"].to_list() == [1.0, 1.0]


def test_background_changes_the_bits():
    data = pl.DataFrame({"s": ["A", "A", "C", "C"]})
    uniform = _heights(logo_frame(data, "s", "AC", normalize_background(None, "AC")))
    assert uniform[(0, "A")] == pytest.approx(0.0)
    skewed = normalize_background({"A": 0.9, "C": 0.1}, "AC")
    h = _heights(logo_frame(data, "s", "AC", skewed))
    expected = 0.5 * math.log2(0.5 / 0.9) + 0.5 * math.log2(0.5 / 0.1)
    assert h[(0, "C")] == pytest.approx(0.5 * expected)


def test_empty_data():
    frame = logo_frame(
        pl.DataFrame({"s": []}, schema={"s": pl.Utf8}),
        "s",
        PROTEIN,
        normalize_background(None, PROTEIN),
    )
    assert frame.height == 0
    assert frame.columns == ["position", "residue", "count", "frequency", "height"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: normalize_alphabet("A"),
        lambda: normalize_background({"Z": 1.0}, PROTEIN),
        lambda: normalize_background({"A": 1.0}, "AC"),
        lambda: normalize_background("other", "AC"),
        lambda: logo_frame(
            pl.DataFrame({"s": ["A"]}), "s", "AC", {"A": 0.5, "C": 0.5}, "nats"
        ),
    ],
)
def test_rejects(call):
    with pytest.raises(ValueError):
        call()


def test_alphabets_colors_and_axis():
    assert normalize_alphabet("dna") == "ACGT"
    assert normalize_alphabet("ABBA") == "AB"
    assert set(default_colors(DNA)) == set(DNA)
    assert max_height("bits", PROTEIN) == pytest.approx(math.log2(20))
    assert max_height("probability", PROTEIN) == 1.0


@pytest.fixture
def sites() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "window": ["AAKR", "GAKP", "LLFA", "VLYA"],
            "protease": ["trypsin", "trypsin", "chymo", "chymo"],
        }
    )


def test_component_filters_labels_and_args(mock_streamlit, temp_cache_dir, sites):
    logo = SequenceLogo(
        cache_id="logo",
        data=sites,
        cache_path=str(temp_cache_dir),
        sequence_column="window",
        position_labels=["P2", "P1", "P1'", "P2'"],
        filters={"protease": "protease"},
        interactivity={"site": "label", "aa": "residue"},
        title="Sites",
    )
    frame = logo.logo_data({"protease": "trypsin"})
    assert set(frame["residue"]) == {"A", "G", "K", "R", "P"}
    assert frame.filter(pl.col("residue") == "K")["label"].to_list() == ["P1'"]
    # Nothing selected: no letters
    assert logo.logo_data({}).height == 0
    args = logo._get_component_args()
    assert args["componentType"] == "SequenceLogo"
    assert args["positionLabels"] == ["P2", "P1", "P1'", "P2'"]
    assert args["yMax"] == pytest.approx(math.log2(20))
    assert args["interactivity"] == {"site": "label", "aa": "residue"}
    payload = logo._prepare_vue_data({"protease": "chymo"})
    assert list(payload["logoData"].columns) == [
        "position",
        "label",
        "residue",
        "count",
        "frequency",
        "height",
    ]
    # Restored from the cache
    again = SequenceLogo(cache_id="logo", cache_path=str(temp_cache_dir))
    assert again.logo_data({"protease": "chymo"}).equals(frame.head(0)) is False
    assert again._get_component_args()["positionLabels"] == ["P2", "P1", "P1'", "P2'"]


def test_component_validates(mock_streamlit, temp_cache_dir, sites):
    with pytest.raises(ValueError, match="interactivity"):
        SequenceLogo(
            cache_id="bad1",
            data=sites,
            cache_path=str(temp_cache_dir),
            sequence_column="window",
            interactivity={"x": "window"},
        )
    with pytest.raises(ValueError, match="not found"):
        SequenceLogo(cache_id="bad2", data=sites, cache_path=str(temp_cache_dir))
    with pytest.raises(ValueError, match="units"):
        SequenceLogo(
            cache_id="bad3",
            data=sites,
            cache_path=str(temp_cache_dir),
            sequence_column="window",
            units="nats",
        )
