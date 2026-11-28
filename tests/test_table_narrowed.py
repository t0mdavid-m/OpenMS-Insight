"""Table narrowed_labels: chips naming what the linked filters narrow a table to."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def psms() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "id": [1, 2, 3, 4],
            "peptide_id": [10, 10, 20, 20],
            "sequence": ["PEPTIDE", "PEPTIDE", "ELVISK", "ELVISK"],
            "file": ["a", "b", "a", "b"],
        }
    )


def _table(cache_path: Path, data: pl.LazyFrame, **kwargs) -> Table:
    return Table(
        cache_id="narrowed",
        data=data,
        cache_path=str(cache_path),
        filters={"peptide": "peptide_id"},
        interactivity={"psm": "id"},
        index_field="id",
        page_size=20,
        **kwargs,
    )


def _narrowed(table: Table, state: dict) -> list:
    return table._prepare_vue_data(state)["_pagination"].get("narrowed", [])


def test_named_after_the_column_by_default(mock_streamlit, temp_cache_dir, psms):
    table = _table(temp_cache_dir, psms)
    assert _narrowed(table, {"peptide": 20}) == [
        {"identifier": "peptide", "label": "peptide_id", "value": "20"}
    ]


def test_a_label_and_a_column_shown_instead_of_the_id(
    mock_streamlit, temp_cache_dir, psms
):
    table = _table(
        temp_cache_dir,
        psms,
        narrowed_labels={"peptide": {"label": "Peptide", "column": "sequence"}},
    )
    assert _narrowed(table, {"peptide": 20}) == [
        {"identifier": "peptide", "label": "Peptide", "value": "ELVISK"}
    ]
    assert _narrowed(table, {"peptide": 10})[0]["value"] == "PEPTIDE"


def test_a_plain_label(mock_streamlit, temp_cache_dir, psms):
    table = _table(temp_cache_dir, psms, narrowed_labels={"peptide": "Peptide"})
    assert _narrowed(table, {"peptide": 10})[0]["label"] == "Peptide"


def test_none_without_a_selection_or_when_left_out(
    mock_streamlit, temp_cache_dir, psms
):
    assert _narrowed(_table(temp_cache_dir / "a", psms), {}) == []
    off = _table(temp_cache_dir / "b", psms, narrowed_labels={"peptide": False})
    assert _narrowed(off, {"peptide": 10}) == []


def test_no_match_shows_the_selected_value(mock_streamlit, temp_cache_dir, psms):
    table = _table(
        temp_cache_dir,
        psms,
        narrowed_labels={"peptide": {"label": "Peptide", "column": "sequence"}},
    )
    assert _narrowed(table, {"peptide": 99})[0]["value"] == "99"


def test_cache_unchanged(mock_streamlit, temp_cache_dir, psms):
    plain = _table(temp_cache_dir / "plain", psms)
    table = _table(temp_cache_dir / "set", psms, narrowed_labels={"peptide": "Peptide"})
    assert "narrowed_labels" not in table._get_cache_config()
    assert table._compute_config_hash() == plain._compute_config_hash()
