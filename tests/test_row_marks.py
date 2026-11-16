"""`row_marks` / `row_notes`: marking table rows and noting on them.

The marks live in the state under one identifier, keyed by the row's index
value, and the table shows them as the columns ``mark`` and ``note``, which
filter, sort and export like the table's own columns.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import StateManager, Table
from openms_insight.core.row_marks import (
    apply_row_mark,
    normalize_row_marks,
    row_marks_args,
    with_row_marks,
)
from openms_insight.core.state import _render_state_manager

LABELS = ["Accept", "Reject"]


def _render_with(state_manager, fn):
    token = _render_state_manager.set(state_manager)
    try:
        return fn()
    finally:
        _render_state_manager.reset(token)


# -- helpers -----------------------------------------------------------------


def test_normalize_labels_and_colors():
    marks = normalize_row_marks(["Accept", {"label": "Reject", "color": "#123456"}])
    assert marks[0]["label"] == "Accept" and marks[0]["color"].startswith("#")
    assert marks[1] == {"label": "Reject", "color": "#123456"}
    assert normalize_row_marks(None) == []


@pytest.mark.parametrize(
    "bad",
    ["Accept", ["Accept", "Accept"], [{"color": "#fff"}], [{"label": "A", "x": 1}]],
)
def test_normalize_rejects(bad):
    with pytest.raises(ValueError):
        normalize_row_marks(bad)


def test_apply_mark_toggle_and_note():
    marks = apply_row_mark(None, 3, LABELS, mark="Accept")
    assert marks == {"3": {"mark": "Accept"}}
    marks = apply_row_mark(marks, "3", LABELS, note="  co-eluting ")
    assert marks == {"3": {"mark": "Accept", "note": "co-eluting"}}
    marks = apply_row_mark(marks, 3, LABELS, mark=None)
    assert marks == {"3": {"note": "co-eluting"}}
    # A row left with nothing is removed
    assert apply_row_mark(marks, 3, LABELS, note="") == {}


def test_apply_mark_ignores_unknown_and_unchanged():
    assert apply_row_mark(None, 1, LABELS, mark="Maybe") is None
    assert apply_row_mark({"1": {"mark": "Accept"}}, 1, LABELS, mark="Accept") is None
    assert apply_row_mark(None, None, LABELS, mark="Accept") is None


def test_with_row_marks_joins_by_index_value():
    data = pl.LazyFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    out = with_row_marks(
        data, "id", {"2": {"mark": "Reject", "note": "n"}}, notes=True
    ).collect()
    assert out["id"].to_list() == [1, 2, 3]
    assert out["mark"].to_list() == [None, "Reject", None]
    assert out["note"].to_list() == [None, "n", None]
    empty = with_row_marks(data, "id", None, notes=False).collect()
    assert empty.columns == ["id", "x", "mark"]
    assert empty["mark"].null_count() == 3


def test_with_row_marks_checks_columns():
    with pytest.raises(ValueError, match="index field"):
        with_row_marks(pl.LazyFrame({"x": [1]}), "id", None, notes=False)
    with pytest.raises(ValueError, match="already has"):
        with_row_marks(pl.LazyFrame({"id": [1], "mark": ["a"]}), "id", None, False)


def test_args():
    args = row_marks_args(normalize_row_marks(LABELS), True, "t_marks")["rowMarks"]
    assert args["identifier"] == "t_marks"
    assert args["field"] == "mark" and args["noteField"] == "note"
    assert [o["label"] for o in args["options"]] == LABELS


# -- Table ---------------------------------------------------------------------


@pytest.fixture
def psms() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "id": list(range(6)),
            "peptide": ["PEPA", "PEPB", "PEPC", "PEPD", "PEPE", "PEPF"],
            "score": [float(i) for i in range(6)],
        }
    )


def _table(temp_cache_dir, data=None, **kwargs):
    return Table(
        cache_id="tbl_marks",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
        column_definitions=[
            {"field": "peptide", "title": "Peptide"},
            {"field": "score", "title": "Score"},
        ],
        **kwargs,
    )


def test_table_without_marks_is_unchanged(mock_streamlit, temp_cache_dir, psms):
    table = _table(temp_cache_dir, psms)
    args = table._get_component_args()
    assert "rowMarks" not in args
    assert [c["field"] for c in args["columnDefinitions"]] == ["peptide", "score"]
    assert "tbl_marks_marks" not in table.get_state_dependencies()
    assert "mark" not in table.export_data().columns


def test_table_marks_columns_and_metadata(mock_streamlit, temp_cache_dir, psms):
    table = _table(temp_cache_dir, psms, row_marks=LABELS, row_notes=True)
    args = table._get_component_args()
    assert args["rowMarks"]["identifier"] == "tbl_marks_marks"
    fields = [c["field"] for c in args["columnDefinitions"]]
    assert fields == ["peptide", "score", "mark", "note"]
    assert args["columnMetadata"]["mark"] == {
        "type": "categorical",
        "unique_values": LABELS,
    }
    assert args["columnMetadata"]["note"] == {"type": "text"}
    assert "tbl_marks_marks" in table.get_state_dependencies()
    # Render-time only: the cache config does not change
    plain = _table(temp_cache_dir)
    assert plain._get_cache_config() == table._get_cache_config()


def test_table_mark_event_updates_state_and_rows(mock_streamlit, temp_cache_dir, psms):
    table = _table(temp_cache_dir, psms, row_marks=LABELS, row_notes=True)
    state_manager = StateManager()

    def send(event):
        return _render_with(
            state_manager, lambda: table._handle_event({"type": "row_mark", **event})
        )

    assert send({"key": 2, "mark": "Reject"})
    assert send({"key": 4, "mark": "Accept"})
    assert send({"key": 4, "note": "check charge"})
    assert not send({"key": 4, "mark": "Unknown"})
    assert state_manager.get_selection("tbl_marks_marks") == {
        "2": {"mark": "Reject"},
        "4": {"mark": "Accept", "note": "check charge"},
    }

    state = state_manager.get_all_selections()
    rows = table._prepare_vue_data(state)["tableData"]
    assert rows.loc[rows["id"] == 2, "mark"].item() == "Reject"
    assert rows.loc[rows["id"] == 4, "note"].item() == "check charge"

    # Filter by mark, as the filter dialog does
    state["tbl_marks_page"] = {
        "column_filters": [{"field": "mark", "type": "in", "value": ["Accept"]}]
    }
    out = table.export_data(state)
    assert out["id"].to_list() == [4]
    assert out["note"].to_list() == ["check charge"]

    # Clicking the mark again takes it off
    assert send({"key": 2, "mark": None})
    assert "2" not in state_manager.get_selection("tbl_marks_marks")


def test_table_marks_shared_identifier_and_notes_only(
    mock_streamlit, temp_cache_dir, psms
):
    table = _table(
        temp_cache_dir, psms, row_notes=True, row_marks_identifier="reviewed"
    )
    args = table._get_component_args()
    assert [c["field"] for c in args["columnDefinitions"]][-1] == "note"
    assert "mark" not in args["columnMetadata"]
    state_manager = StateManager()
    # Marks cannot be set on a table without them
    assert not _render_with(
        state_manager,
        lambda: table._handle_event({"type": "row_mark", "key": 1, "mark": "Accept"}),
    )
    assert _render_with(
        state_manager,
        lambda: table._handle_event({"type": "row_mark", "key": 1, "note": "x"}),
    )
    out = table.export_data(state_manager.get_all_selections())
    assert "mark" not in out.columns
    assert out.filter(pl.col("id") == 1)["note"].item() == "x"
