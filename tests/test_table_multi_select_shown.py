"""Table `multi_select_shown`: the check box column shown from the start."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def files() -> pl.LazyFrame:
    return pl.LazyFrame({"row": [0, 1, 2], "name": ["a.raw", "b.raw", "db.fasta"]})


def _table(cache_path: Path, data: pl.LazyFrame | None, **kwargs) -> Table:
    return Table(
        cache_id="picker",
        data=data,
        cache_path=str(cache_path),
        index_field="row",
        **kwargs,
    )


def test_hidden_by_default(mock_streamlit, temp_cache_dir: Path, files):
    table = _table(temp_cache_dir, files, multi_select={"picked": "row"})
    assert "multiSelectShown" not in table._get_component_args()


def test_shown(mock_streamlit, temp_cache_dir: Path, files):
    table = _table(
        temp_cache_dir, files, multi_select={"picked": "row"}, multi_select_shown=True
    )
    assert table._get_component_args()["multiSelectShown"] is True
    assert "multi_select_shown" not in table._config


def test_needs_multi_select(mock_streamlit, temp_cache_dir: Path, files):
    table = _table(temp_cache_dir, files, multi_select_shown=True)
    assert "multiSelectShown" not in table._get_component_args()


def test_cache_unchanged(mock_streamlit, temp_cache_dir: Path, files):
    plain = _table(temp_cache_dir / "plain", files, multi_select={"picked": "row"})
    shown = _table(
        temp_cache_dir / "shown", files, multi_select={"picked": "row"},
        multi_select_shown=True,
    )
    assert shown._compute_config_hash() == plain._compute_config_hash()
    restored = _table(
        temp_cache_dir / "shown", None, multi_select={"picked": "row"},
        multi_select_shown=True,
    )
    assert restored._get_component_args()["multiSelectShown"] is True
