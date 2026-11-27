"""Table levels: Enter and Backspace between tables that narrow each other."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def proteins() -> pl.LazyFrame:
    return pl.LazyFrame({"id": [1, 2, 3], "protein": ["P1", "P2", "P3"]})


def _table(cache_path: Path, data: pl.LazyFrame, **kwargs) -> Table:
    return Table(
        cache_id="levels",
        data=data,
        cache_path=str(cache_path),
        interactivity={"protein": "protein"},
        index_field="id",
        **kwargs,
    )


class TestArgs:
    def test_off_by_default(self, mock_streamlit, temp_cache_dir: Path, proteins):
        args = _table(temp_cache_dir, proteins)._get_component_args()
        assert "level" not in args
        assert "levelIdentifier" not in args

    def test_level_and_shared_identifier(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        args = _table(temp_cache_dir, proteins, level=0)._get_component_args()
        assert args["level"] == 0
        assert args["levelIdentifier"] == "table_level"

    def test_own_identifier(self, mock_streamlit, temp_cache_dir: Path, proteins):
        args = _table(
            temp_cache_dir, proteins, level=2, level_identifier="psm_chain"
        )._get_component_args()
        assert args["level"] == 2
        assert args["levelIdentifier"] == "psm_chain"

    @pytest.mark.parametrize("level", [-1, 1.5, "1", True])
    def test_level_must_be_a_whole_number(
        self, mock_streamlit, temp_cache_dir: Path, proteins, level
    ):
        with pytest.raises(ValueError, match="level"):
            _table(temp_cache_dir, proteins, level=level)


class TestCache:
    def test_display_only(self, mock_streamlit, temp_cache_dir: Path, proteins):
        plain = _table(temp_cache_dir / "plain", proteins)
        table = _table(temp_cache_dir / "set", proteins, level=1)
        assert "level" not in table._get_cache_config()
        assert "level" not in table._config
        assert table._compute_config_hash() == plain._compute_config_hash()

    def test_reconstruction_from_cache(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        _table(temp_cache_dir, proteins)
        restored = Table(cache_id="levels", cache_path=str(temp_cache_dir), level=1)
        assert restored._get_component_args()["level"] == 1
