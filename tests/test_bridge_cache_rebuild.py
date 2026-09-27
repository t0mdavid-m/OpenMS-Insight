"""Tests that the bridge's session payload cache notices a rebuilt cache.

The payload cache is keyed by component id, which comes from cache_id. Rerunning a
workflow rebuilds the cache on disk under the same cache_id, and before the cache
generation was part of the key the session kept serving the previous run's data.
"""

from unittest.mock import patch

import polars as pl

from openms_insight import Table
from openms_insight.rendering.bridge import (
    _payload_cache_key,
    _prepare_vue_data_cached,
)

COMPONENT_ID = "Table:svc_rerun"


def _render(table, session_state):
    """Prepare the payload the way render_component does, returning its rows."""
    state_keys = set(table.get_state_dependencies())
    key = _payload_cache_key(table, {}, state_keys)
    with patch("openms_insight.rendering.bridge.st.session_state", session_state):
        vue_data, _ = _prepare_vue_data_cached(table, COMPONENT_ID, key, {})
    return vue_data["_pagination"]["total_rows"]


def _data(n_rows):
    return pl.LazyFrame({"id": list(range(n_rows)), "score": [1.0] * n_rows})


def test_regenerated_cache_is_not_served_stale(mock_streamlit, temp_cache_dir):
    first = Table(
        cache_id="rerun",
        data=_data(2),
        cache_path=str(temp_cache_dir),
        index_field="id",
    )
    assert _render(first, mock_streamlit) == 2

    rerun = Table(
        cache_id="rerun",
        data=_data(3),
        cache_path=str(temp_cache_dir),
        index_field="id",
        regenerate_cache=True,
    )
    assert _render(rerun, mock_streamlit) == 3


def test_cache_rebuilt_elsewhere_is_picked_up_on_reconstruction(
    mock_streamlit, temp_cache_dir
):
    # The page reconstructs from cache; a workflow process rebuilds it in between.
    Table(
        cache_id="rerun",
        data=_data(2),
        cache_path=str(temp_cache_dir),
        index_field="id",
    )
    page = Table(cache_id="rerun", cache_path=str(temp_cache_dir))
    assert _render(page, mock_streamlit) == 2

    Table(
        cache_id="rerun",
        data=_data(3),
        cache_path=str(temp_cache_dir),
        index_field="id",
        regenerate_cache=True,
    )
    page = Table(cache_id="rerun", cache_path=str(temp_cache_dir))
    assert _render(page, mock_streamlit) == 3


def test_unchanged_cache_still_hits(mock_streamlit, temp_cache_dir):
    Table(
        cache_id="rerun",
        data=_data(2),
        cache_path=str(temp_cache_dir),
        index_field="id",
    )
    first = Table(cache_id="rerun", cache_path=str(temp_cache_dir))
    second = Table(cache_id="rerun", cache_path=str(temp_cache_dir))

    state_keys = set(first.get_state_dependencies())
    assert _payload_cache_key(first, {}, state_keys) == _payload_cache_key(
        second, {}, state_keys
    )


def test_manifest_without_generation_falls_back_to_created_at(temp_cache_dir):
    import json

    table = Table(
        cache_id="legacy",
        data=_data(1),
        cache_path=str(temp_cache_dir),
        index_field="id",
    )
    manifest_path = table._get_manifest_path()
    manifest = json.loads(manifest_path.read_text())
    del manifest["cache_generation"]
    manifest_path.write_text(json.dumps(manifest))

    legacy = Table(cache_id="legacy", cache_path=str(temp_cache_dir))
    assert legacy._cache_generation == manifest["created_at"]
