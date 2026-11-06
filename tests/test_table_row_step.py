"""`row_step`: Previous / Next row buttons of the Table.

Without pagination the browser steps through the rows Tabulator shows. With
server-side pagination the neighbouring row may be on another page, so the
button sends an event and Python selects the row from the full data in the
order shown (filters, search and sort applied).
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import StateManager, Table
from openms_insight.core.state import _render_state_manager


@pytest.fixture
def scans():
    return pl.LazyFrame(
        {
            "id": list(range(6)),
            "scan": [10, 11, 12, 13, 14, 15],
            "level": [1, 2, 2, 1, 2, 2],
            "score": [0.5, 0.9, 0.1, 0.7, 0.3, 0.8],
        }
    )


def _table(cache_dir, data, **kwargs):
    return Table(
        cache_id=kwargs.pop("cache_id", "tbl_step"),
        data=data,
        cache_path=str(cache_dir),
        index_field="id",
        interactivity={"scan": "scan"},
        page_size=2,
        **{"row_step": True, **kwargs},
    )


def _step(table, state_manager, direction):
    token = _render_state_manager.set(state_manager)
    try:
        return table._handle_event({"type": "step_row", "direction": direction})
    finally:
        _render_state_manager.reset(token)


def test_row_step_arg_and_cache_config(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans)
    assert table._get_component_args()["rowStep"] is True
    again = Table(cache_id="tbl_step", cache_path=str(temp_cache_dir))
    args = again._get_component_args()
    assert args["rowStep"] is True
    assert "row_step" not in args

    plain = _table(temp_cache_dir, scans, cache_id="tbl_plain", row_step=False)
    assert "rowStep" not in plain._get_component_args()


def test_row_step_needs_interactivity(mock_streamlit, temp_cache_dir, scans):
    table = Table(
        cache_id="tbl_noint",
        data=scans,
        cache_path=str(temp_cache_dir),
        row_step=True,
    )
    assert "rowStep" not in table._get_component_args()
    assert not _step(table, StateManager(), 1)


def test_step_across_pages(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans)
    state_manager = StateManager()
    state_manager.set_selection("scan", 11)

    # Row 2 is on the second page (page size 2)
    assert _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 12
    assert _step(table, state_manager, -1)
    assert state_manager.get_selection("scan") == 11


def test_step_stops_at_the_ends(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans)
    state_manager = StateManager()
    state_manager.set_selection("scan", 15)
    assert not _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 15
    state_manager.set_selection("scan", 10)
    assert not _step(table, state_manager, -1)


def test_step_without_selection_picks_first_or_last(
    mock_streamlit, temp_cache_dir, scans
):
    table = _table(temp_cache_dir, scans)
    state_manager = StateManager()
    assert _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 10

    state_manager.clear_selection("scan")
    assert _step(table, state_manager, -1)
    assert state_manager.get_selection("scan") == 15


def test_step_follows_sort_and_filters(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans, filters={"level": "level"})
    state_manager = StateManager()
    state_manager.set_selection("level", 2)
    state_manager.set_selection(
        "tbl_step_page", {"page": 1, "sort_column": "score", "sort_dir": "desc"}
    )
    # Level 2 by score, descending: 11 (0.9), 15 (0.8), 14 (0.3), 12 (0.1)
    state_manager.set_selection("scan", 15)
    assert _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 14
    assert _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 12
    assert _step(table, state_manager, -1)
    assert state_manager.get_selection("scan") == 14


def test_step_applies_on_select(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans, on_select={"mass": None})
    state_manager = StateManager()
    state_manager.set_selection("scan", 10)
    state_manager.set_selection("mass", 3)
    assert _step(table, state_manager, 1)
    assert state_manager.get_selection("scan") == 11
    assert state_manager.get_selection("mass") is None


def test_unknown_direction_is_ignored(mock_streamlit, temp_cache_dir, scans):
    table = _table(temp_cache_dir, scans)
    state_manager = StateManager()
    assert not table._handle_event({"type": "step_row", "direction": 2})
    assert state_manager.get_selection("scan") is None
