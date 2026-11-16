"""Mark rows of a table and note on them: ``row_marks`` and ``row_notes``.

A table given ``row_marks=["Accept", "Reject"]`` gets a **Mark** column with
one button per mark; clicking one marks the row with it, clicking it again
takes the mark off. ``row_notes=True`` adds a **Note** column whose cells are
edited in place. Both are kept in the shared state under one identifier
(default ``"<cache_id>_marks"``), keyed by the row's ``index_field`` value:

    {"17": {"mark": "Accept"}, "42": {"mark": "Reject", "note": "co-eluting"}}

so they survive paging, sorting and reruns, can be read and written by the app
like any other selection, and are stored with a view like the rest of the
state. The table adds them as the columns ``mark`` and ``note``: they can be
sorted and filtered like any other column, and the CSV and Excel downloads and
``Table.export_data()`` include them. Render-time only, never part of the
cache configuration.
"""

from typing import Any

import polars as pl

#: The columns the marks and notes are shown in.
MARK_FIELD = "mark"
NOTE_FIELD = "note"

#: Colours of marks given without one, in order.
_DEFAULT_COLORS = ["#2e7d32", "#c62828", "#ef6c00", "#1565c0", "#6a1b9a", "#00838f"]


def normalize_row_marks(row_marks: Any) -> list[dict[str, str]]:
    """``row_marks`` as ``[{"label", "color"}]``; labels must be unique."""
    if row_marks is None:
        return []
    if isinstance(row_marks, (str, dict)) or not hasattr(row_marks, "__iter__"):
        raise ValueError("row_marks must be a list of labels or {'label', 'color'}")
    marks: list[dict[str, str]] = []
    for i, entry in enumerate(row_marks):
        if isinstance(entry, str):
            entry = {"label": entry}
        if not isinstance(entry, dict) or not str(entry.get("label", "")).strip():
            raise ValueError(f"row_marks[{i}] needs a label")
        unknown = set(entry) - {"label", "color"}
        if unknown:
            raise ValueError(f"row_marks[{i}] has unknown keys {sorted(unknown)}")
        label = str(entry["label"]).strip()
        if any(m["label"] == label for m in marks):
            raise ValueError(f"row_marks has the label {label!r} twice")
        color = entry.get("color") or _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)]
        marks.append({"label": label, "color": str(color)})
    return marks


def apply_row_mark(
    current: Any,
    key: Any,
    labels: list[str],
    mark: Any = ...,
    note: Any = ...,
) -> dict[str, dict[str, str]] | None:
    """The marks after a row's mark or note changed, or None if nothing changed.

    ``mark`` is a label or None (take the mark off); ``note`` a text, empty to
    remove it. Left out (``...``), the row keeps what it has. A row left with
    neither mark nor note is removed. An unknown label is ignored.
    """
    if key is None:
        return None
    key = str(key)
    marks = {str(k): dict(v) for k, v in (current or {}).items() if isinstance(v, dict)}
    entry = dict(marks.get(key, {}))
    if mark is not ...:
        if mark is None or mark == "":
            entry.pop("mark", None)
        elif str(mark) in labels:
            entry["mark"] = str(mark)
        else:
            return None
    if note is not ...:
        text = "" if note is None else str(note).strip()
        if text:
            entry["note"] = text
        else:
            entry.pop("note", None)
    if entry:
        marks[key] = entry
    else:
        marks.pop(key, None)
    before = {
        str(k): dict(v) for k, v in (current or {}).items() if isinstance(v, dict)
    }
    return None if marks == before else marks


def with_row_marks(
    data: pl.LazyFrame,
    index_field: str,
    value: Any,
    notes: bool,
) -> pl.LazyFrame:
    """``data`` with the ``mark`` (and ``note``) column from the stored marks."""
    names = data.collect_schema().names()
    if index_field not in names:
        raise ValueError(
            f"row_marks need the index field {index_field!r} in the table's data"
        )
    added = [MARK_FIELD, NOTE_FIELD] if notes else [MARK_FIELD]
    clash = [c for c in added if c in names]
    if clash:
        raise ValueError(
            f"row_marks add the column(s) {clash}, which the table's data already has"
        )
    entries = {str(k): v for k, v in (value or {}).items() if isinstance(v, dict) and v}
    key = "__row_mark_key"
    marks = pl.DataFrame(
        {
            key: list(entries),
            MARK_FIELD: [v.get("mark") for v in entries.values()],
            NOTE_FIELD: [v.get("note") for v in entries.values()],
        },
        schema={key: pl.Utf8, MARK_FIELD: pl.Utf8, NOTE_FIELD: pl.Utf8},
    ).lazy()
    if not notes:
        marks = marks.drop(NOTE_FIELD)
    if not entries:
        return data.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c) for c in added)
    keyed = data.with_columns(pl.col(index_field).cast(pl.Utf8).alias(key))
    try:
        joined = keyed.join(marks, on=key, how="left", maintain_order="left")
    except TypeError:  # polars before 1.18 keeps the left order anyway
        joined = keyed.join(marks, on=key, how="left")
    return joined.drop(key)


def row_marks_args(
    marks: list[dict[str, str]], notes: bool, identifier: str
) -> dict[str, Any]:
    """What the table's front end needs to draw the marks."""
    return {
        "rowMarks": {
            "identifier": identifier,
            "field": MARK_FIELD,
            "options": marks,
            "noteField": NOTE_FIELD if notes else None,
        }
    }
