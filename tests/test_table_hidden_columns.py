"""Table `hidden_columns`: columns hidden until the viewer turns them on stay
hidden when the table is loaded from its cache."""

from __future__ import annotations

import polars as pl

from openms_insight import Table


def _table(cache_dir, cache_id, **kwargs):
    return Table(
        cache_id=cache_id,
        data=pl.LazyFrame({"id": [1, 2], "name": ["a", "b"], "extra": [1.0, 2.0]}),
        cache_path=str(cache_dir),
        index_field="id",
        **kwargs,
    )


def test_none_by_default(mock_streamlit, temp_cache_dir):
    table = _table(temp_cache_dir, "plain")
    args = table._get_component_args()

    assert "hiddenColumns" not in args
    assert "hidden_columns" not in table._get_cache_config()


def test_survives_reload(mock_streamlit, temp_cache_dir):
    _table(temp_cache_dir, "hidden", hidden_columns=["extra"])

    reloaded = Table(cache_id="hidden", cache_path=str(temp_cache_dir))
    args = reloaded._get_component_args()

    assert args["hiddenColumns"] == ["extra"]
    assert "hidden_columns" not in args
