"""Table show_position: the selected row's place, a display option that never touches the cache."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def scans() -> pl.LazyFrame:
    return pl.LazyFrame(
        {"id": [1, 2, 3], "scan": [10, 20, 30], "mz": [100.5, 200.25, 300.125]}
    )


def _table(cache_path: Path, data: pl.LazyFrame, **kwargs) -> Table:
    return Table(
        cache_id="place",
        data=data,
        cache_path=str(cache_path),
        interactivity={"spectrum": "scan"},
        index_field="id",
        page_size=20,
        **kwargs,
    )


def test_on_by_default(mock_streamlit, temp_cache_dir: Path, scans):
    # Vue treats a missing value as on, so the default sends nothing
    assert "showPosition" not in _table(temp_cache_dir, scans)._get_component_args()


def test_turned_off(mock_streamlit, temp_cache_dir: Path, scans):
    args = _table(temp_cache_dir, scans, show_position=False)._get_component_args()
    assert args["showPosition"] is False


@pytest.mark.parametrize("value", [True, False])
def test_cache_unchanged(mock_streamlit, temp_cache_dir: Path, scans, value):
    plain = _table(temp_cache_dir / "plain", scans)
    table = _table(temp_cache_dir / "set", scans, show_position=value)
    assert "show_position" not in table._get_cache_config()
    assert table._compute_config_hash() == plain._compute_config_hash()
