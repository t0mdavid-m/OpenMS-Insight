"""Table `copy_row`: Ctrl+C copies the selected row, a display option only."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def scans() -> pl.LazyFrame:
    return pl.LazyFrame({"id": [1, 2], "scan": [10, 20], "mz": [100.5, 200.25]})


def _table(cache_path: Path, data: pl.LazyFrame | None, **kwargs) -> Table:
    return Table(
        cache_id="copy",
        data=data,
        cache_path=str(cache_path),
        index_field="id",
        **kwargs,
    )


def test_on_by_default(mock_streamlit, temp_cache_dir: Path, scans):
    # Vue treats a missing value as on, so the default sends nothing
    assert "copyRow" not in _table(temp_cache_dir, scans)._get_component_args()


def test_turned_off(mock_streamlit, temp_cache_dir: Path, scans):
    table = _table(temp_cache_dir, scans, copy_row=False)
    assert table._get_component_args()["copyRow"] is False
    assert "copy_row" not in table._config


def test_cache_unchanged(mock_streamlit, temp_cache_dir: Path, scans):
    plain = _table(temp_cache_dir / "plain", scans)
    off = _table(temp_cache_dir / "off", scans, copy_row=False)
    assert off._get_cache_config() == plain._get_cache_config()
    assert off._compute_config_hash() == plain._compute_config_hash()
    # Restored from the cache, the option still applies
    restored = _table(temp_cache_dir / "off", None, copy_row=False)
    assert restored._get_component_args()["copyRow"] is False
