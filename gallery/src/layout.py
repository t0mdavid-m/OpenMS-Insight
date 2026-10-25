"""Shared furniture for example pages.

Every example page is a plain Streamlit script. It defines one ``example(sm)``
function containing nothing but the openms-insight code being demonstrated, and hands
it to :func:`render`. The source shown on the page is extracted from that function
with :func:`inspect.getsource`, so the code a reader copies is by construction the code
that produced the component above it -- the two cannot drift apart.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable, Sequence
from typing import Any

import polars as pl
import streamlit as st

from openms_insight import StateManager

from . import dataset

REPO_URL = "https://github.com/t0mdavid-m/OpenMS-Insight"

# Every example table fits under this except the MS1 map (608,134 rows), so in
# practice one table is truncated and the rest are shown in full.
PREVIEW_ROW_LIMIT = 10_000


def source_of(fn: Callable[..., Any]) -> str:
    """The body of ``fn``, dedented, with its ``def`` line removed.

    Showing only the body is what keeps examples looking as short as they are: the
    wrapper exists so the page can call the code twice (once to run, once to display),
    and is noise to a reader.
    """
    source = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(source)
    body = tree.body[0].body  # type: ignore[attr-defined]
    first = body[0].lineno - 1
    lines = source.splitlines()[first:]
    return textwrap.dedent("\n".join(lines)).strip()


def state_manager(page: str) -> StateManager:
    """A StateManager scoped to one page, so pages cannot disturb each other."""
    return StateManager(session_key=f"svc_state_{page}")


def _options(component: type, shown: Sequence[str]) -> None:
    """Parameter reference generated from the component's own signature."""
    signature = inspect.signature(component.__init__)
    rows = []
    for name, parameter in signature.parameters.items():
        if name in ("self", "kwargs") or name.startswith("_"):
            continue
        default = parameter.default
        rows.append(
            {
                "parameter": name,
                "default": "required"
                if default is inspect.Parameter.empty
                else repr(default),
                "used here": "yes" if name in shown else "",
            }
        )
    st.caption(
        f"Generated from `{component.__name__}.__init__`, so it cannot fall out of "
        "date with the code."
    )
    st.dataframe(pl.DataFrame(rows), width="stretch", hide_index=True)


def _data_preview(tables: Sequence[str]) -> None:
    """The source tables behind a page, whole and scrollable.

    Every table is shown in full, because a five-row sample invites the reader to
    assume that is all there is -- the component above is drawing hundreds or
    thousands of these rows. The one exception is the 608k-point MS1 map, which is
    truncated because sending it row-wise to the browser costs more than the page it
    documents; the caption always says which case applies.

    This is still the source table, not a mirror of what is drawn: a component that
    filters (a plot showing one scan) draws a subset of these rows.
    """
    for name in tables:
        info = dataset.table_info(name)
        st.markdown(f"**`{name}`** — {info.get('description', '')}")
        frame = pl.read_parquet(dataset.data(name))
        st.dataframe(
            frame.head(PREVIEW_ROW_LIMIT), width="stretch", hide_index=True, height=320
        )
        truncated = frame.height > PREVIEW_ROW_LIMIT
        counted = (
            f"First {PREVIEW_ROW_LIMIT:,} of {frame.height:,} rows"
            if truncated
            else f"All {frame.height:,} rows"
        )
        st.caption(
            f"{counted} · derived from `{info.get('derived_from', '?')}` · "
            f"{info.get('transformation', '')}"
        )


def render(
    *,
    title: str,
    summary: str,
    example: Callable[[StateManager], Any],
    component: type | None = None,
    used: Sequence[str] = (),
    tables: Sequence[str] = (),
    notes: str | None = None,
) -> None:
    """Render one example page: the live component, then its source and context."""
    st.title(title)
    st.markdown(summary)

    sm = state_manager(title)
    example(sm)

    if notes:
        st.info(notes)

    st.subheader("Code")
    st.caption(
        "This is the exact code that produced the component above, extracted from the "
        "running page. `scan(...)` is just `pl.scan_parquet(...)` — substitute your "
        "own polars LazyFrame or DataFrame."
    )
    st.code(source_of(example), language="python")

    if tables:
        with st.expander("Data"):
            _data_preview(tables)
    if component is not None:
        with st.expander("Options"):
            _options(component, used)
    with st.expander("Live selection state"):
        st.caption(
            "Identifiers shared between components. Click something above and watch "
            "this change -- this dictionary is how components stay linked."
        )
        st.json(sm.get_all_selections())
