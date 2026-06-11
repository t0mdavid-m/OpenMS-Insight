"""
Tests for the generic "clear dependent selections on click" mechanism.

FLASHApp oracle parity: ``TabulatorProteinTable.updateSelectedProtein`` clears
``selectedAA`` + ``selectedTag`` (+ tagData) on EVERY protein-row click, so
switching proteoform resets the dependent residue/tag selections. In the migrated
value-based model the protein ``Table`` sets {protein, scan} via interactivity,
but the dependent ``aa`` (residue) and ``tag`` selections were NEVER cleared on a
protein switch, leaving the tag table empty / tagger overlay stale.

The generic capability: ``Table(clears_selections=["aa", "tag"])`` makes a row
click ALSO reset each listed identifier to the store's "unset" sentinel (None).
On the Vue side the click writes ``updateSelection(id, null)`` for each; this
arrives in Python as ``None`` and flows through
``StateManager.update_from_vue`` (which treats None as no-selection) so a
dependent component's ``_prepare_vue_data`` (e.g. a tag table whose
``interval_filters={"aa": (...)}`` reads ``aa``) sees no ``aa``/``tag``.

These tests drive the SAME selection-handling path the component uses (the
bridge's ``StateManager.update_from_vue`` with a Vue-shaped payload), then assert:
  - with clears_selections set, a protein-row click ALSO clears aa/tag in state;
  - a dependent tag table's _prepare_vue_data then sees no aa (interval filter
    skipped -> all rows) and no tag;
  - default (clears_selections=None) leaves aa/tag untouched;
  - clearsSelections is surfaced to Vue (camelCase) only when set, with no stray
    snake_case arg, and round-trips through cache reconstruction.
"""

from typing import Any, Dict, Optional

import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.state import StateManager

# =============================================================================
# Vue-payload helper (mirrors App.vue's JSON-cloned selection store -> Python)
# =============================================================================


def make_vue_click_payload(
    *,
    session_id: float,
    selection_counter: int,
    selections: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the dict a row click sends Python, matching App.vue's setComponentValue.

    A row click calls ``selectionStore.updateSelection(id, value)`` for each
    interactivity selection AND ``updateSelection(id, null)`` for each cleared
    dependent identifier; App.vue JSON-clones the whole store (null -> Python None)
    and sends it. ``selections`` maps identifier -> value (use None for a cleared
    identifier, exactly as Vue sends ``null``).
    """
    payload: Dict[str, Any] = {
        "selection_counter": selection_counter,
        "pagination_counter": 0,
        "counter": selection_counter,
        "id": session_id,
    }
    payload.update(selections)
    return payload


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def protein_df() -> pl.LazyFrame:
    """Tiny protein table: clicking a row sets {protein: id, scan: Scan}."""
    return pl.LazyFrame(
        {
            "id": [0, 1, 2],
            "Scan": [10, 20, 30],
            "accession": ["P0", "P1", "P2"],
        }
    )


@pytest.fixture
def tag_df() -> pl.LazyFrame:
    """
    Dependent tag table. ``interval_filters={"aa": ("startPos", "endPos")}`` keeps
    rows spanning the selected residue ``aa``; when ``aa`` is unset (None) the
    filter is skipped and ALL rows show.
    """
    return pl.LazyFrame(
        {
            "id": [0, 1, 2],
            "tag_id": [100, 101, 102],
            "startPos": [0, 5, 10],
            "endPos": [4, 9, 14],
        }
    )


@pytest.fixture
def state_manager(mock_streamlit) -> StateManager:
    """Fresh StateManager backed by mocked st.session_state."""
    return StateManager(session_key="clears_sel_state")


def _make_protein_table(
    data: pl.LazyFrame,
    cache_path: str,
    clears_selections: Optional[list] = None,
) -> Table:
    return Table(
        cache_id="protein_table",
        data=data,
        cache_path=cache_path,
        interactivity={"protein": "id", "scan": "Scan"},
        index_field="id",
        clears_selections=clears_selections,
    )


def _make_tag_table(data: pl.LazyFrame, cache_path: str) -> Table:
    # Dependent tag table: no equality filter here; the residue selection ``aa`` is
    # read via interval_filters (keep rows spanning the selected residue).
    return Table(
        cache_id="tag_table",
        data=data,
        cache_path=cache_path,
        interval_filters={"aa": ("startPos", "endPos")},
        interactivity={"tag": "tag_id"},
        index_field="id",
        pagination=False,
    )


# =============================================================================
# Core behavior: click clears dependent selections through the state path
# =============================================================================


class TestClearsSelectionsStateFlow:
    """Driving the bridge's update_from_vue with a row-click payload."""

    def test_row_click_clears_aa_and_tag_in_state(
        self, protein_df, tag_df, tmp_path, state_manager
    ):
        """
        With clears_selections=["aa","tag"], processing a protein-row click also
        clears aa/tag in the resulting state.

        Scenario: a previous proteoform left aa=7 and an opaque tag payload set.
        The user clicks protein row id=2 (Scan=30). The Vue click writes
        {protein:2, scan:30} AND {aa:null, tag:null}; update_from_vue applies it.
        """
        _make_protein_table(protein_df, str(tmp_path), clears_selections=["aa", "tag"])

        # Stale dependent selections from a previous proteoform.
        state_manager.set_selection("aa", 7)
        state_manager.set_selection("tag", {"sequence": "ABC", "selectedAA": 1})
        assert state_manager.get_selection("aa") == 7
        assert state_manager.get_selection("tag") is not None

        # Simulate the row click round-trip: own selections written + dependents
        # nulled (exactly what TabulatorTable.onRowClick + clearDependentSelections
        # push into the store, then App.vue forwards).
        payload = make_vue_click_payload(
            session_id=state_manager.session_id,
            selection_counter=state_manager.selection_counter + 1,
            selections={"protein": 2, "scan": 30, "aa": None, "tag": None},
        )
        modified = state_manager.update_from_vue(payload)

        assert modified is True
        # Own interactivity selections recorded.
        assert state_manager.get_selection("protein") == 2
        assert state_manager.get_selection("scan") == 30
        # Dependent selections cleared to the "unset" sentinel (None).
        assert state_manager.get_selection("aa") is None
        assert state_manager.get_selection("tag") is None

    def test_dependent_table_prepare_vue_data_sees_no_aa_after_clear(
        self, protein_df, tag_df, tmp_path, state_manager
    ):
        """
        After the click clears aa, the dependent tag table's _prepare_vue_data
        applies NO interval filter on aa (so all rows show), i.e. it sees no aa.

        This is the downstream half: the tag table reads `aa` via interval_filters;
        a stale aa would empty/narrow it, the cleared aa restores the full set.
        """
        _make_protein_table(protein_df, str(tmp_path), clears_selections=["aa", "tag"])
        tag_table = _make_tag_table(tag_df, str(tmp_path))

        # First establish a stale aa that DOES narrow the tag table, to prove the
        # filter is active before clearing.
        state_manager.set_selection("aa", 7)  # only row [5,9] spans residue 7
        state_stale = state_manager.get_state_for_vue()
        narrowed = tag_table._prepare_vue_data(state_stale)
        assert len(narrowed["tableData"]) == 1  # only the [5,9] tag spans aa=7

        # Now process the protein-row click that clears aa/tag.
        payload = make_vue_click_payload(
            session_id=state_manager.session_id,
            selection_counter=state_manager.selection_counter + 1,
            selections={"protein": 1, "scan": 20, "aa": None, "tag": None},
        )
        state_manager.update_from_vue(payload)

        # Dependent component re-renders with the cleared state.
        state_after = state_manager.get_state_for_vue()
        assert state_after.get("aa") is None
        assert state_after.get("tag") is None

        result = tag_table._prepare_vue_data(state_after)
        # aa unset => interval filter skipped => ALL rows visible (no stale narrowing).
        assert len(result["tableData"]) == len(tag_df.collect())

    def test_default_none_leaves_dependents_untouched(
        self, protein_df, tag_df, tmp_path, state_manager
    ):
        """
        Default (clears_selections=None): a protein-row click does NOT clear aa/tag.

        The Vue click for a table without clearsSelections writes ONLY its own
        interactivity selections; nothing nulls aa/tag, so they survive.
        """
        _make_protein_table(protein_df, str(tmp_path), clears_selections=None)

        state_manager.set_selection("aa", 7)
        state_manager.set_selection("tag", {"sequence": "ABC"})

        # A default table's click payload carries only protein/scan (no aa/tag keys).
        payload = make_vue_click_payload(
            session_id=state_manager.session_id,
            selection_counter=state_manager.selection_counter + 1,
            selections={"protein": 0, "scan": 10},
        )
        state_manager.update_from_vue(payload)

        assert state_manager.get_selection("protein") == 0
        # Dependents untouched.
        assert state_manager.get_selection("aa") == 7
        assert state_manager.get_selection("tag") == {"sequence": "ABC"}


# =============================================================================
# Args / config surface
# =============================================================================


class TestClearsSelectionsArgs:
    """clearsSelections surfaces to Vue cleanly and round-trips through cache."""

    def test_default_off_adds_no_arg(self, protein_df, tmp_path, mock_streamlit):
        table = _make_protein_table(protein_df, str(tmp_path), clears_selections=None)
        args = table._get_component_args()
        assert "clearsSelections" not in args
        # No stray snake_case managed arg either.
        assert "clears_selections" not in args
        assert table._clears_selections == []

    def test_on_surfaces_camelcase_no_snake_leak(
        self, protein_df, tmp_path, mock_streamlit
    ):
        table = _make_protein_table(
            protein_df, str(tmp_path), clears_selections=["aa", "tag"]
        )
        args = table._get_component_args()
        assert args["clearsSelections"] == ["aa", "tag"]
        assert "clears_selections" not in args  # managed key filtered from _config

    def test_cache_reconstruction_round_trip(
        self, protein_df, tmp_path, mock_streamlit
    ):
        # Create (writes cache), then reconstruct from cache only.
        _make_protein_table(protein_df, str(tmp_path), clears_selections=["aa", "tag"])
        reconstructed = Table(cache_id="protein_table", cache_path=str(tmp_path))
        assert reconstructed._clears_selections == ["aa", "tag"]
        args = reconstructed._get_component_args()
        assert args["clearsSelections"] == ["aa", "tag"]
        assert "clears_selections" not in args
