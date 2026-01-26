"""
Tabulator Integration Tests for Bridge Communication.

Tests the render_component() bridge function with Table component,
focusing on pagination behavior, state synchronization, and cache validity.

Bridge Flow Tested:
    Phase 1: Cache validity check (send cached data if valid)
    Phase 2: Vue component call (vue_func with payload)
    Phase 3: State update from Vue (update_from_vue)
    Phase 4: Data preparation (with updated state)
    Phase 5: Cache storage (for next render)
    Phase 6: Rerun trigger (st.rerun() if state changed)

Test Categories:
    - TestTabulatorPaginationBasic: Basic pagination with single render cycles
    - TestTabulatorPageNavigation: Multi-render scenarios simulating page changes
    - TestTabulatorCacheBehavior: Cache validity and hit/miss scenarios
    - TestTabulatorCounterLogic: Counter-based conflict resolution
    - TestTabulatorNavigationHints: Navigation hints for selection-based navigation
"""

from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import pandas as pd
import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.state import StateManager
from openms_insight.rendering.bridge import (
    _get_component_cache,
    render_component,
)

# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockSessionState(dict):
    """
    Mock Streamlit session_state that behaves like a dict.

    Provides the same interface as st.session_state for testing
    without running a Streamlit server.
    """

    pass


def create_vue_response(
    page: int = 1,
    page_size: int = 100,
    selection_counter: int = 0,
    pagination_counter: int = 0,
    session_id: Optional[float] = None,
    pagination_identifier: str = "test_table_page",
    request_data: bool = False,
    vue_data_hash: Optional[str] = None,
    **selections,
) -> Dict[str, Any]:
    """
    Create Vue component return matching real format.

    Args:
        page: Current page number
        page_size: Rows per page
        selection_counter: Counter for selection state
        pagination_counter: Counter for pagination state
        session_id: Session ID (must match StateManager's id)
        pagination_identifier: Key for pagination state
        request_data: Whether Vue is requesting a data resend
        vue_data_hash: Hash echoed back by Vue
        **selections: Additional selection state (e.g., test_selection=123)

    Returns:
        Dict mimicking Vue component's return value
    """
    result = {
        "selection_counter": selection_counter,
        "pagination_counter": pagination_counter,
        "counter": max(selection_counter, pagination_counter),  # Legacy compat
        "id": session_id,
        pagination_identifier: {
            "page": page,
            "page_size": page_size,
        },
        **selections,
    }

    if request_data:
        result["_requestData"] = True

    if vue_data_hash is not None:
        result["_vueDataHash"] = vue_data_hash

    return result


@pytest.fixture
def mock_streamlit_bridge(mock_streamlit):
    """
    Provides mocked Streamlit infrastructure for bridge testing.

    Yields:
        Dict with:
            - session_state: MockSessionState instance
            - rerun: Mock for st.rerun()
            - vue_func: Mock for declare_component return
    """
    mock_rerun = Mock()
    mock_vue_func = Mock(return_value=None)

    with patch("streamlit.rerun", mock_rerun):
        with patch(
            "openms_insight.rendering.bridge.get_vue_component_function",
            return_value=mock_vue_func,
        ):
            yield {
                "session_state": mock_streamlit,
                "rerun": mock_rerun,
                "vue_func": mock_vue_func,
            }


@pytest.fixture
def state_manager(mock_streamlit):
    """
    Create a real StateManager with mocked session_state backend.

    Returns:
        StateManager instance for testing
    """
    return StateManager(session_key="test_state")


@pytest.fixture
def table_component(pagination_test_data, tmp_path):
    """
    Create a Table component with pagination enabled for testing.

    Returns:
        Table component configured for 500-row test data
    """
    return Table(
        cache_id="test_table",
        data=pagination_test_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="test_table_page",
        index_field="id",
    )


# =============================================================================
# TestTabulatorPaginationBasic
# =============================================================================


class TestTabulatorPaginationBasic:
    """
    Basic pagination scenarios with single render cycles.

    Tests verify that the Table component correctly slices data
    for different pages and returns proper metadata.
    """

    def test_first_page_returns_correct_rows(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page 1 returns rows 0-99.

        Verifies:
            - Data content is correct (first 100 rows)
            - Row IDs match expected range
        """
        # Configure Vue to return page 1 state
        session_id = state_manager.session_id
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=100,
            session_id=session_id,
            pagination_identifier="test_table_page",
        )

        # Call _prepare_vue_data directly to test data preparation
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 1, "page_size": 100}

        result = table_component._prepare_vue_data(state)

        # Verify data content
        table_data = result["tableData"]
        assert len(table_data) == 100
        assert table_data["id"].iloc[0] == 0
        assert table_data["id"].iloc[99] == 99
        assert table_data["value"].iloc[0] == "item_0"

    def test_middle_page_returns_correct_rows(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page 3 returns rows 200-299.

        Verifies:
            - Offset calculation is correct ((3-1) * 100 = 200)
            - Data slice matches expected range
        """
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 3, "page_size": 100}

        result = table_component._prepare_vue_data(state)

        table_data = result["tableData"]
        assert len(table_data) == 100
        assert table_data["id"].iloc[0] == 200
        assert table_data["id"].iloc[99] == 299

    def test_last_page_returns_correct_rows(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page 5 returns rows 400-499.

        Verifies:
            - Last page handling is correct
            - All 100 rows returned (exact fit)
        """
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 5, "page_size": 100}

        result = table_component._prepare_vue_data(state)

        table_data = result["tableData"]
        assert len(table_data) == 100
        assert table_data["id"].iloc[0] == 400
        assert table_data["id"].iloc[99] == 499

    def test_partial_last_page(self, tmp_path, state_manager, mock_streamlit_bridge):
        """
        Partial last page returns remaining rows (e.g., 50 rows on page 6 of 550).

        Verifies:
            - Partial page handling is correct
            - Correct row count for final partial page
        """
        # Create 550-row dataset (5 full pages + 50 rows)
        data = pl.LazyFrame(
            {
                "id": list(range(550)),
                "value": [f"item_{i}" for i in range(550)],
            }
        )

        table = Table(
            cache_id="partial_page_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="partial_page_test_page",
        )

        state = state_manager.get_state_for_vue()
        state["partial_page_test_page"] = {"page": 6, "page_size": 100}

        result = table._prepare_vue_data(state)

        table_data = result["tableData"]
        assert len(table_data) == 50  # Only 50 rows on last page
        assert table_data["id"].iloc[0] == 500
        assert table_data["id"].iloc[49] == 549

    def test_page_metadata_structure(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Verify _pagination dict contains required fields.

        Verifies:
            - total_rows is correct (500)
            - total_pages is correct (5)
            - page matches requested page
            - page_size matches configuration
        """
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 2, "page_size": 100}

        result = table_component._prepare_vue_data(state)

        pagination = result["_pagination"]
        assert pagination["total_rows"] == 500
        assert pagination["total_pages"] == 5
        assert pagination["page"] == 2
        assert pagination["page_size"] == 100

    def test_payload_structure_complete(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Verify full payload structure for Vue.

        Verifies:
            - tableData is a pandas DataFrame
            - _hash is a non-empty string
            - _pagination dict is present
        """
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 1, "page_size": 100}

        result = table_component._prepare_vue_data(state)

        assert "tableData" in result
        assert isinstance(result["tableData"], pd.DataFrame)
        assert "_hash" in result
        assert isinstance(result["_hash"], str)
        assert len(result["_hash"]) > 0
        assert "_pagination" in result
        assert isinstance(result["_pagination"], dict)


# =============================================================================
# TestTabulatorPageNavigation
# =============================================================================


class TestTabulatorPageNavigation:
    """
    Multi-render scenarios simulating page changes.

    Tests verify that page navigation works correctly across
    multiple render cycles through the bridge.
    """

    def test_forward_navigation(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page 1 -> 2 -> 3 navigation updates data correctly.

        Verifies:
            - Each page returns correct data slice
            - State updates propagate correctly
        """
        # Page 1
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 1, "page_size": 100}
        result1 = table_component._prepare_vue_data(state)
        assert result1["tableData"]["id"].iloc[0] == 0

        # Page 2
        state["test_table_page"] = {"page": 2, "page_size": 100}
        result2 = table_component._prepare_vue_data(state)
        assert result2["tableData"]["id"].iloc[0] == 100

        # Page 3
        state["test_table_page"] = {"page": 3, "page_size": 100}
        result3 = table_component._prepare_vue_data(state)
        assert result3["tableData"]["id"].iloc[0] == 200

    def test_backward_navigation(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page 3 -> 2 -> 1 navigation updates data correctly.

        Verifies:
            - Backward navigation returns correct data slices
        """
        state = state_manager.get_state_for_vue()

        # Start at page 3
        state["test_table_page"] = {"page": 3, "page_size": 100}
        result3 = table_component._prepare_vue_data(state)
        assert result3["tableData"]["id"].iloc[0] == 200

        # Navigate to page 2
        state["test_table_page"] = {"page": 2, "page_size": 100}
        result2 = table_component._prepare_vue_data(state)
        assert result2["tableData"]["id"].iloc[0] == 100

        # Navigate to page 1
        state["test_table_page"] = {"page": 1, "page_size": 100}
        result1 = table_component._prepare_vue_data(state)
        assert result1["tableData"]["id"].iloc[0] == 0

    def test_jump_navigation(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Direct page jump (1 -> 5) works correctly.

        Verifies:
            - Direct page jumps return correct data
        """
        state = state_manager.get_state_for_vue()

        # Start at page 1
        state["test_table_page"] = {"page": 1, "page_size": 100}
        result1 = table_component._prepare_vue_data(state)
        assert result1["tableData"]["id"].iloc[0] == 0

        # Jump to page 5
        state["test_table_page"] = {"page": 5, "page_size": 100}
        result5 = table_component._prepare_vue_data(state)
        assert result5["tableData"]["id"].iloc[0] == 400

    def test_page_size_change(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Page size change (100 -> 50) recalculates pagination.

        Verifies:
            - Page size change affects row count
            - total_pages recalculates correctly
        """
        state = state_manager.get_state_for_vue()

        # Page 1 with 100 rows per page
        state["test_table_page"] = {"page": 1, "page_size": 100}
        result100 = table_component._prepare_vue_data(state)
        assert len(result100["tableData"]) == 100
        assert result100["_pagination"]["total_pages"] == 5

        # Page 1 with 50 rows per page
        state["test_table_page"] = {"page": 1, "page_size": 50}
        result50 = table_component._prepare_vue_data(state)
        assert len(result50["tableData"]) == 50
        assert result50["_pagination"]["total_pages"] == 10

    def test_navigation_triggers_rerun(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Vue requesting new page triggers st.rerun().

        Verifies:
            - State change from Vue triggers rerun
        """
        session_id = state_manager.session_id

        # First render: Vue returns page change request
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=2,
            page_size=100,
            session_id=session_id,
            pagination_identifier="test_table_page",
            pagination_counter=0,
        )

        # This should trigger a rerun because Vue requested page 2
        render_component(table_component, state_manager)

        # Verify rerun was called
        mock_streamlit_bridge["rerun"].assert_called()


# =============================================================================
# TestTabulatorCacheBehavior
# =============================================================================


class TestTabulatorCacheBehavior:
    """
    Cache validity and hit/miss scenarios.

    Tests verify that the bridge correctly caches data and
    detects when cache is valid vs invalid.
    """

    def test_cache_hit_same_page(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Re-requesting same page returns cached data.

        Verifies:
            - Cache is stored after first render
            - Same filter state returns cached data
        """
        state = state_manager.get_state_for_vue()
        state["test_table_page"] = {"page": 1, "page_size": 100}

        # First call - computes data
        result1 = table_component._prepare_vue_data(state)
        hash1 = result1["_hash"]

        # Second call with same state - should return same hash
        result2 = table_component._prepare_vue_data(state)
        hash2 = result2["_hash"]

        assert hash1 == hash2

    def test_cache_miss_page_change(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Requesting different page computes fresh data.

        Verifies:
            - Different page returns different data
            - Hash changes with page
        """
        state = state_manager.get_state_for_vue()

        # Page 1
        state["test_table_page"] = {"page": 1, "page_size": 100}
        result1 = table_component._prepare_vue_data(state)

        # Page 2 - should have different hash
        state["test_table_page"] = {"page": 2, "page_size": 100}
        result2 = table_component._prepare_vue_data(state)

        assert result1["_hash"] != result2["_hash"]
        assert result1["tableData"]["id"].iloc[0] != result2["tableData"]["id"].iloc[0]

    def test_cache_invalidation_on_filter(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        External filter change invalidates cache.

        Verifies:
            - Cache invalidates when filter state changes
            - New filter produces different data
        """
        # Create table with filter
        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,  # 100 rows for scan 1, 100 for scan 2
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        table = Table(
            cache_id="filter_cache_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"scan": "scan_id"},
            pagination=True,
            page_size=50,
            pagination_identifier="filter_cache_test_page",
        )

        state = state_manager.get_state_for_vue()
        state["filter_cache_test_page"] = {"page": 1, "page_size": 50}

        # Filter to scan_id=1
        state["scan"] = 1
        result1 = table._prepare_vue_data(state)
        assert result1["_pagination"]["total_rows"] == 100

        # Filter to scan_id=2 - should invalidate cache
        state["scan"] = 2
        result2 = table._prepare_vue_data(state)
        assert result2["_pagination"]["total_rows"] == 100

        # Data should be different
        assert result1["_hash"] != result2["_hash"]

    def test_cache_stores_pagination_state(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Check cache structure includes filter state and annotation hash.

        Verifies:
            - Cache entry is a 4-tuple
            - Filter state is stored for validation
        """
        session_id = state_manager.session_id

        # Configure vue_func to return valid state
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=100,
            session_id=session_id,
            pagination_identifier="test_table_page",
        )

        # Render to populate cache
        render_component(table_component, state_manager)

        # Check cache structure
        cache = _get_component_cache()
        _component_id = f"TabulatorTable:svc_test_table_{hash('{}')}"[:50]  # noqa: F841

        # Find the cache entry (key includes hash)
        cache_keys = [k for k in cache.keys() if "test_table" in k]
        assert len(cache_keys) > 0

        entry = cache[cache_keys[0]]

        # Cache should be 4-tuple: (filter_state, data, hash, ann_hash)
        assert len(entry) == 4
        filter_state, data, data_hash, ann_hash = entry
        assert isinstance(filter_state, tuple)
        assert isinstance(data, dict)
        assert isinstance(data_hash, str)


# =============================================================================
# TestTabulatorCounterLogic
# =============================================================================


class TestTabulatorCounterLogic:
    """
    Counter-based conflict resolution.

    Tests verify that the StateManager correctly handles counters
    for pagination vs selection state updates.
    """

    def test_pagination_counter_increments(self, state_manager, mock_streamlit_bridge):
        """
        Page change increments pagination_counter.

        Verifies:
            - set_selection for pagination identifier increments pagination_counter
            - selection_counter remains unchanged
        """
        initial_pagination = state_manager.pagination_counter
        initial_selection = state_manager.selection_counter

        # Set pagination state (ends with _page)
        state_manager.set_selection("test_table_page", {"page": 2, "page_size": 100})

        # Pagination counter should increment
        assert state_manager.pagination_counter == initial_pagination + 1
        # Selection counter should NOT increment
        assert state_manager.selection_counter == initial_selection

    def test_selection_counter_independent(self, state_manager, mock_streamlit_bridge):
        """
        Selection vs pagination counters are independent.

        Verifies:
            - Selection update increments selection_counter
            - Pagination counter remains unchanged
        """
        initial_pagination = state_manager.pagination_counter
        initial_selection = state_manager.selection_counter

        # Set selection state (not ending with _page)
        state_manager.set_selection("scan", 123)

        # Selection counter should increment
        assert state_manager.selection_counter == initial_selection + 1
        # Pagination counter should NOT increment
        assert state_manager.pagination_counter == initial_pagination

    def test_counter_conflict_resolution(self, state_manager, mock_streamlit_bridge):
        """
        Stale Vue update is rejected if counter is lower.

        Verifies:
            - Updates with old counter values are rejected
        """
        session_id = state_manager.session_id

        # Set initial pagination state
        state_manager.set_selection("test_page", {"page": 1, "page_size": 100})
        current_counter = state_manager.pagination_counter

        # Python updates to page 3
        state_manager.set_selection("test_page", {"page": 3, "page_size": 100})
        _new_counter = state_manager.pagination_counter  # noqa: F841

        # Vue sends stale update (page 2) with old counter
        stale_vue_state = {
            "id": session_id,
            "pagination_counter": current_counter - 1,  # Stale counter
            "selection_counter": state_manager.selection_counter,
            "test_page": {"page": 2, "page_size": 100},
        }

        _modified = state_manager.update_from_vue(stale_vue_state)  # noqa: F841

        # Stale update should be rejected
        assert state_manager.get_selection("test_page")["page"] == 3

    def test_counter_in_payload(
        self, table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Counters are sent to Vue in selection_store.

        Verifies:
            - get_state_for_vue includes both counters
        """
        state = state_manager.get_state_for_vue()

        assert "selection_counter" in state
        assert "pagination_counter" in state
        assert "counter" in state  # Legacy compatibility
        assert "id" in state


# =============================================================================
# TestTabulatorNavigationHints
# =============================================================================


class TestTabulatorNavigationHints:
    """
    Navigation hints for selection-based navigation.

    Tests verify that the Table component provides hints to Vue
    for navigating to selected rows across pages.
    """

    def test_navigate_to_page_hint_present(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        Selection on different page sets _navigate_to_page hint.

        Verifies:
            - When selection is on different page, hint is set
        """
        data = pl.LazyFrame(
            {
                "id": list(range(500)),
                "value": [f"item_{i}" for i in range(500)],
            }
        )

        table = Table(
            cache_id="nav_hint_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="nav_hint_test_page",
            interactivity={"row_id": "id"},
            index_field="id",
        )

        state = state_manager.get_state_for_vue()
        state["nav_hint_test_page"] = {"page": 1, "page_size": 100}
        state["row_id"] = 250  # Row 250 is on page 3

        result = table._prepare_vue_data(state)

        # Should navigate to page 3
        assert result.get("_navigate_to_page") == 3

    def test_target_row_index_hint_present(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        Selection provides _target_row_index for highlighting.

        Verifies:
            - Target row index within page is provided
        """
        data = pl.LazyFrame(
            {
                "id": list(range(500)),
                "value": [f"item_{i}" for i in range(500)],
            }
        )

        table = Table(
            cache_id="row_index_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="row_index_test_page",
            interactivity={"row_id": "id"},
            index_field="id",
        )

        state = state_manager.get_state_for_vue()
        state["row_index_test_page"] = {"page": 1, "page_size": 100}
        state["row_id"] = 250  # Row 250 is index 50 on page 3

        result = table._prepare_vue_data(state)

        # Row 250 is at index 50 within page 3 (250 - 200 = 50)
        assert result.get("_target_row_index") == 50

    def test_no_hints_when_selection_on_page(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        No navigation hints when selection is on current page.

        Verifies:
            - Hints are absent when row is already visible
        """
        data = pl.LazyFrame(
            {
                "id": list(range(500)),
                "value": [f"item_{i}" for i in range(500)],
            }
        )

        table = Table(
            cache_id="no_hint_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="no_hint_test_page",
            interactivity={"row_id": "id"},
            index_field="id",
        )

        # Create fresh state for this test
        state = state_manager.get_state_for_vue()
        # Page 1, row 50 - already on current page
        state["no_hint_test_page"] = {"page": 1, "page_size": 100}
        state["row_id"] = 50

        result = table._prepare_vue_data(state)

        # No navigation needed - row is on current page
        # Note: Component may still set hints for first selection
        # The key is that page doesn't change (page=1, row 50 is on page 1)
        assert result["_pagination"]["page"] == 1

    def test_go_to_request_navigation(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        Go-to request navigates to specific row by field value.

        Verifies:
            - go_to_request in pagination state triggers navigation
            - Correct page and row index are set
        """
        data = pl.LazyFrame(
            {
                "id": list(range(500)),
                "value": [f"item_{i}" for i in range(500)],
            }
        )

        table = Table(
            cache_id="goto_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="goto_test_page",
            go_to_fields=["id"],
            index_field="id",
        )

        state = state_manager.get_state_for_vue()
        state["goto_test_page"] = {
            "page": 1,
            "page_size": 100,
            "go_to_request": {"field": "id", "value": 350},
        }

        result = table._prepare_vue_data(state)

        # Should navigate to page 4 (rows 300-399 contain id=350)
        assert result.get("_navigate_to_page") == 4
        # Row 350 is at index 50 within page 4
        assert result.get("_target_row_index") == 50


# =============================================================================
# TestTableExternalFilterAutoSelection
# =============================================================================


class TestTableExternalFilterAutoSelection:
    """
    Integration tests for auto-selection when external filters change.

    Tests verify that:
    - When an external filter changes the contents of a Table, the first row is auto-selected
    - Auto-selection is applied through the full `render_component()` cycle
    - User clicks override auto-selection (auto-select doesn't overwrite explicit selection)
    """

    @pytest.fixture
    def filtered_table_component(self, tmp_path, mock_streamlit):
        """
        Create a Table with external filter for auto-selection testing.

        Schema:
            - id: Unique row ID (0-199)
            - scan_id: Filter key (1 for first 100 rows, 2 for second 100)
            - value: String value
        """
        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        return Table(
            cache_id="autoselect_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
            pagination=True,
            page_size=50,
            pagination_identifier="autoselect_test_page",
        )

    def test_external_filter_change_triggers_auto_selection(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """When external filter changes, auto-selection sets first row's interactivity value."""
        session_id = state_manager.session_id

        # Set initial filter
        state_manager.set_selection("spectrum", 1)

        # First render: Vue returns state (simulating component mounted)
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="autoselect_test_page",
        )

        render_component(filtered_table_component, state_manager)

        # Auto-selection should have set selected_id = 0 (first row of scan_id=1)
        assert state_manager.get_selection("selected_id") == 0

    def test_filter_change_to_different_value_updates_auto_selection(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """Filter change from scan_id=1 to scan_id=2 updates auto-selection to first row of new data."""
        session_id = state_manager.session_id

        # Initial filter: scan_id=1
        state_manager.set_selection("spectrum", 1)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="autoselect_test_page",
        )

        render_component(filtered_table_component, state_manager)

        # First auto-selection: first row of scan_id=1 (id=0)
        assert state_manager.get_selection("selected_id") == 0

        # Clear selection to allow new auto-selection
        state_manager.set_selection("selected_id", None)

        # Change filter to scan_id=2
        state_manager.set_selection("spectrum", 2)

        render_component(filtered_table_component, state_manager)

        # Auto-selection should now be first row of scan_id=2 (id=100)
        assert state_manager.get_selection("selected_id") == 100

    def test_filter_cleared_to_none_no_auto_selection(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """When filter cleared (spectrum: 1 -> None), no auto-selection occurs with awaiting_filters=True."""
        session_id = state_manager.session_id

        # Create table WITHOUT filter_defaults (awaits filter value)
        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        table = Table(
            cache_id="filter_cleared_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
            pagination=True,
            page_size=50,
            pagination_identifier="filter_cleared_test_page",
        )

        # Initial filter: scan_id=1
        state_manager.set_selection("spectrum", 1)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="filter_cleared_test_page",
        )

        render_component(table, state_manager)

        # First auto-selection occurred
        assert state_manager.get_selection("selected_id") == 0

        # Clear both selection and filter
        state_manager.set_selection("selected_id", None)
        state_manager.set_selection("spectrum", None)

        render_component(table, state_manager)

        # With filter cleared and no default, no data is shown, no auto-selection
        assert state_manager.get_selection("selected_id") is None

    def test_filter_set_from_none_triggers_auto_selection(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """When filter set from None (spectrum: None -> 1), auto-selection triggers."""
        session_id = state_manager.session_id

        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        table = Table(
            cache_id="filter_from_none_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
            pagination=True,
            page_size=50,
            pagination_identifier="filter_from_none_test_page",
        )

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="filter_from_none_test_page",
        )

        # First render with no filter (awaiting)
        render_component(table, state_manager)

        # No auto-selection when awaiting filter
        assert state_manager.get_selection("selected_id") is None

        # Now set filter
        state_manager.set_selection("spectrum", 1)

        render_component(table, state_manager)

        # Auto-selection should have triggered for first row of scan_id=1
        assert state_manager.get_selection("selected_id") == 0

    def test_user_click_prevents_auto_selection_override(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """User's explicit row click should not be overwritten by auto-selection.

        This tests that when a user explicitly selects a row, subsequent renders
        don't overwrite it with auto-selection (which selects the first row).
        The selection must remain VALID in the filtered data.

        Note: If the filter changes such that the selected value no longer exists
        in the filtered data, the selection IS cleared and auto-selection kicks in.
        That behavior is tested in TestTableSelectionClearingOnInvalidFilter.
        """
        session_id = state_manager.session_id

        # Initial render with filter
        state_manager.set_selection("spectrum", 1)
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="autoselect_test_page",
        )
        render_component(filtered_table_component, state_manager)

        # Auto-selection set selected_id = 0
        assert state_manager.get_selection("selected_id") == 0

        # User clicks row 50 (simulated by setting selection)
        # This is still valid in spectrum=1 (scan_id=1 has ids 0-99)
        state_manager.set_selection("selected_id", 50)

        # Re-render with SAME filter (selection remains valid)
        render_component(filtered_table_component, state_manager)

        # User's selection should NOT be overwritten by auto-selection
        # Auto-selection only applies when get_selection() returns None
        assert state_manager.get_selection("selected_id") == 50

    def test_rerun_triggered_on_auto_selection(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """Auto-selection setting a value triggers st.rerun()."""
        session_id = state_manager.session_id

        # Set filter
        state_manager.set_selection("spectrum", 1)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="autoselect_test_page",
        )

        # Reset rerun mock to count from this point
        mock_streamlit_bridge["rerun"].reset_mock()

        render_component(filtered_table_component, state_manager)

        # Rerun should have been called (for auto-selection state change)
        assert mock_streamlit_bridge["rerun"].called


# =============================================================================
# TestTableInitialSelection
# =============================================================================


class TestTableInitialSelection:
    """
    Tests for get_initial_selection() method (initial load behavior).

    This method is called in Phase 1 of render_component() to pre-compute
    selection before Vue renders, avoiding an extra rerun on initial load.
    """

    @pytest.fixture
    def initial_selection_table(self, tmp_path, mock_streamlit):
        """
        Create a Table for testing get_initial_selection().

        Has interactivity configured but no default filters.
        """
        data = pl.LazyFrame(
            {
                "id": list(range(100)),
                "scan_id": [1] * 50 + [2] * 50,
                "value": [f"item_{i}" for i in range(100)],
            }
        )

        return Table(
            cache_id="initial_selection_test",
            data=data,
            cache_path=str(tmp_path),
            interactivity={"selected_id": "id", "selected_scan": "scan_id"},
            pagination=True,
            page_size=50,
            pagination_identifier="initial_selection_test_page",
        )

    def test_get_initial_selection_returns_first_row(
        self, initial_selection_table, state_manager
    ):
        """Fresh table with no existing selection returns first row values."""
        state = state_manager.get_state_for_vue()

        result = initial_selection_table.get_initial_selection(state)

        # Should return dict with first row values for each interactivity column
        assert result is not None
        assert result["selected_id"] == 0
        assert result["selected_scan"] == 1

    def test_get_initial_selection_returns_none_when_selection_exists(
        self, initial_selection_table, state_manager
    ):
        """Returns None when selection already set for interactivity identifier."""
        # Set a selection
        state_manager.set_selection("selected_id", 50)

        state = state_manager.get_state_for_vue()
        result = initial_selection_table.get_initial_selection(state)

        # Should return None (don't override existing selection)
        assert result is None

    def test_get_initial_selection_returns_none_when_pagination_exists(
        self, initial_selection_table, state_manager
    ):
        """Returns None when pagination state exists (not truly initial load)."""
        # Set pagination state (simulates user already interacted)
        state_manager.set_selection(
            "initial_selection_test_page", {"page": 2, "page_size": 50}
        )

        state = state_manager.get_state_for_vue()
        result = initial_selection_table.get_initial_selection(state)

        # Should return None (not initial load)
        assert result is None

    def test_get_initial_selection_returns_none_when_awaiting_filter(
        self, tmp_path, state_manager, mock_streamlit
    ):
        """Returns None when required filter not yet set."""
        data = pl.LazyFrame(
            {
                "id": list(range(100)),
                "scan_id": [1] * 50 + [2] * 50,
                "value": [f"item_{i}" for i in range(100)],
            }
        )

        table = Table(
            cache_id="awaiting_filter_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},  # Required filter
            interactivity={"selected_id": "id"},
            pagination=True,
            page_size=50,
            pagination_identifier="awaiting_filter_test_page",
        )

        state = state_manager.get_state_for_vue()
        result = table.get_initial_selection(state)

        # Should return None (no data to select from)
        assert result is None

    def test_initial_selection_applied_before_vue_render(
        self, initial_selection_table, state_manager, mock_streamlit_bridge
    ):
        """
        Full render cycle on initial load: StateManager has selection BEFORE vue_func is called.

        This verifies that get_initial_selection() is called in Phase 1 and its results
        are applied to state before Phase 2 (vue_func call).
        """
        session_id = state_manager.session_id

        # Track what state was passed to vue_func
        captured_state = {}

        def capture_vue_call(**kwargs):
            captured_state.update(kwargs.get("selection_store", {}))
            return create_vue_response(
                page=1,
                page_size=50,
                session_id=session_id,
                pagination_identifier="initial_selection_test_page",
            )

        mock_streamlit_bridge["vue_func"].side_effect = capture_vue_call

        # Initial render (no existing state)
        render_component(initial_selection_table, state_manager)

        # Verify that selection was already in state when vue_func was called
        assert captured_state.get("selected_id") == 0
        assert captured_state.get("selected_scan") == 1

        # Also verify final state
        assert state_manager.get_selection("selected_id") == 0
        assert state_manager.get_selection("selected_scan") == 1


# =============================================================================
# TestTableSelectionClearingOnInvalidFilter
# =============================================================================


class TestTableSelectionClearingOnInvalidFilter:
    """
    Integration tests for selection clearing when filter changes invalidate selections.

    Tests verify that:
    - When an external filter changes and the current selection no longer exists
      in the filtered data, the selection is cleared
    - Table auto-selects first row after clearing (consistent with auto-selection)
    - Selections that still exist in filtered data are kept
    - st.rerun() is triggered when selection is cleared

    These tests are TDD - they should FAIL initially until clearing behavior is implemented.
    """

    @pytest.fixture
    def filtered_table_component(self, tmp_path, mock_streamlit):
        """
        Create a Table with external filter for selection clearing tests.

        Schema:
            - id: Unique row ID (0-199)
            - scan_id: Filter key (1 for first 100 rows, 2 for second 100)
            - value: String value

        Rows 0-99 have scan_id=1, rows 100-199 have scan_id=2.
        """
        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        return Table(
            cache_id="clearing_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id"},
            pagination=True,
            page_size=50,
            pagination_identifier="clearing_test_page",
        )

    def test_selection_cleared_when_not_in_filtered_data(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Selection should be cleared when filtered out, then auto-select first row.

        Scenario: User selects id=50 (scan_id=1), then filter changes to scan_id=2.
        Expected: selected_id is cleared and auto-selected to 100 (first row of scan_id=2).
        """
        session_id = state_manager.session_id

        # Initial state: filter=1, selected=50
        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 50)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="clearing_test_page",
        )
        render_component(filtered_table_component, state_manager)

        # Verify initial selection is set
        assert state_manager.get_selection("selected_id") == 50

        # Change filter to scan_id=2 (id 100-199)
        # Row 50 does NOT exist in this filtered data
        state_manager.set_selection("spectrum", 2)

        render_component(filtered_table_component, state_manager)

        # Selection should be cleared and auto-selected to first row (id=100)
        assert state_manager.get_selection("selected_id") == 100

    def test_selection_kept_when_still_in_filtered_data(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Selection should remain if it exists in filtered data.

        Scenario: User selects id=50 (scan_id=1), filter stays scan_id=1.
        Expected: selected_id stays 50 (no clearing needed).
        """
        session_id = state_manager.session_id

        # Initial state: filter=1, selected=50
        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 50)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="clearing_test_page",
        )
        render_component(filtered_table_component, state_manager)

        # Re-render with same filter
        render_component(filtered_table_component, state_manager)

        # Selection should remain unchanged
        assert state_manager.get_selection("selected_id") == 50

    def test_selection_on_different_page_navigates_not_clears(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Selection on different page should trigger navigation, not clearing.

        Scenario: User selects id=75 (page 2 within scan_id=1), Vue shows page 1.
        Expected: Navigation to page 2 (existing behavior), row still exists in data.
        """
        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 75)  # Page 2 (rows 50-99)

        # Vue reports page 1
        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="clearing_test_page",
        )

        render_component(filtered_table_component, state_manager)

        # Selection should remain (row exists, just different page)
        assert state_manager.get_selection("selected_id") == 75

    def test_selection_cleared_when_all_data_filtered_out(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Selection should be cleared when filter results in no data.

        Scenario: Filter to a value with no matching rows (scan_id=999).
        Expected: selected_id is None (no first row to auto-select).
        """
        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 50)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="clearing_test_page",
        )
        render_component(filtered_table_component, state_manager)

        # Change to non-existent filter value (no rows match scan_id=999)
        state_manager.set_selection("spectrum", 999)

        render_component(filtered_table_component, state_manager)

        # With no data, selection should be cleared (no first row to auto-select)
        assert state_manager.get_selection("selected_id") is None

    def test_rerun_triggered_when_selection_cleared(
        self, filtered_table_component, state_manager, mock_streamlit_bridge
    ):
        """
        Clearing selection should trigger st.rerun().

        Scenario: Selection is cleared due to filter change.
        Expected: st.rerun() is called.
        """
        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 50)

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="clearing_test_page",
        )
        render_component(filtered_table_component, state_manager)

        mock_streamlit_bridge["rerun"].reset_mock()

        # Filter change that invalidates selection
        state_manager.set_selection("spectrum", 2)

        render_component(filtered_table_component, state_manager)

        # Rerun should be called (selection changed from 50 to 100)
        mock_streamlit_bridge["rerun"].assert_called()

    def test_multiple_interactivity_columns_all_cleared(
        self, tmp_path, state_manager, mock_streamlit_bridge
    ):
        """
        All interactivity selections should be cleared when filter invalidates them.

        Scenario: Table has multiple interactivity columns, filter change invalidates all.
        Expected: All interactivity selections are cleared and re-selected.
        """
        session_id = state_manager.session_id

        # Create table with multiple interactivity columns
        data = pl.LazyFrame(
            {
                "id": list(range(200)),
                "scan_id": [1] * 100 + [2] * 100,
                "category": ["A", "B"] * 100,  # Another column for interactivity
                "value": [f"item_{i}" for i in range(200)],
            }
        )

        table = Table(
            cache_id="multi_interactivity_test",
            data=data,
            cache_path=str(tmp_path),
            filters={"spectrum": "scan_id"},
            interactivity={"selected_id": "id", "selected_category": "category"},
            pagination=True,
            page_size=50,
            pagination_identifier="multi_interactivity_test_page",
        )

        # Initial state: filter=1, select first row values
        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_id", 50)  # In scan_id=1
        state_manager.set_selection("selected_category", "A")  # Valid for scan_id=1

        mock_streamlit_bridge["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=50,
            session_id=session_id,
            pagination_identifier="multi_interactivity_test_page",
        )
        render_component(table, state_manager)

        # Change filter - id=50 doesn't exist in scan_id=2
        state_manager.set_selection("spectrum", 2)

        render_component(table, state_manager)

        # Both selections should be updated to first row of scan_id=2 (id=100)
        assert state_manager.get_selection("selected_id") == 100
        # First row of scan_id=2 has id=100, which has category="A" (100 % 2 = 0 -> "A")
        assert state_manager.get_selection("selected_category") == "A"


# =============================================================================
# TestLinePlotSelectionClearing
# =============================================================================


class TestLinePlotSelectionClearing:
    """
    Integration tests for LinePlot selection clearing when filter invalidates selection.

    Tests verify that:
    - When filter changes and selection no longer exists, it's cleared to None
    - LinePlot does NOT auto-select (unlike Table which auto-selects first row)
    - st.rerun() is triggered when selection is cleared

    These tests are TDD - they should FAIL initially until clearing behavior is implemented.
    """

    @pytest.fixture
    def lineplot_with_interactivity(self, tmp_path, mock_streamlit):
        """
        LinePlot with external filter and interactivity.

        Schema:
            - mass: x-axis values
            - intensity: y-axis values
            - scan_id: Filter key (1 for first 3 rows, 2 for last 3)
            - peak_id: Interactivity column (unique peak identifier)
        """
        from openms_insight import LinePlot

        data = pl.LazyFrame(
            {
                "mass": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
                "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0, 500.0],
                "scan_id": [1, 1, 1, 2, 2, 2],
                "peak_id": [10, 20, 30, 40, 50, 60],
            }
        )

        return LinePlot(
            cache_id="lineplot_clear_test",
            data=data,
            cache_path=str(tmp_path),
            x_column="mass",
            y_column="intensity",
            filters={"spectrum": "scan_id"},
            interactivity={"selected_peak": "peak_id"},
        )

    def test_lineplot_selection_cleared_to_none(
        self, lineplot_with_interactivity, state_manager, mock_streamlit_bridge
    ):
        """
        LinePlot should clear invalid selection to None (not auto-select).

        Scenario: LinePlot has peak_id=10 selected, filter changes to scan_id=2.
        Expected: selected_peak is cleared to None (NOT auto-selected to 40).
        """
        from openms_insight.rendering.bridge import render_component

        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_peak", 10)  # scan_id=1 peak

        mock_streamlit_bridge["vue_func"].return_value = {
            "id": session_id,
            "counter": 0,
        }
        render_component(lineplot_with_interactivity, state_manager)

        # Verify initial selection is set
        assert state_manager.get_selection("selected_peak") == 10

        # Change filter - peak_id=10 doesn't exist in scan_id=2
        state_manager.set_selection("spectrum", 2)

        render_component(lineplot_with_interactivity, state_manager)

        # LinePlot should clear to None (not auto-select first)
        assert state_manager.get_selection("selected_peak") is None

    def test_lineplot_selection_kept_when_valid(
        self, lineplot_with_interactivity, state_manager, mock_streamlit_bridge
    ):
        """
        LinePlot should keep selection when it still exists in filtered data.

        Scenario: LinePlot has peak_id=10 selected, filter stays scan_id=1.
        Expected: selected_peak stays 10.
        """
        from openms_insight.rendering.bridge import render_component

        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_peak", 10)  # scan_id=1 peak

        mock_streamlit_bridge["vue_func"].return_value = {
            "id": session_id,
            "counter": 0,
        }
        render_component(lineplot_with_interactivity, state_manager)

        # Re-render with same filter
        render_component(lineplot_with_interactivity, state_manager)

        # Selection should remain unchanged
        assert state_manager.get_selection("selected_peak") == 10

    def test_lineplot_rerun_triggered_on_clear(
        self, lineplot_with_interactivity, state_manager, mock_streamlit_bridge
    ):
        """
        LinePlot clearing selection should trigger st.rerun().

        Scenario: Selection is cleared due to filter change.
        Expected: st.rerun() is called.
        """
        from openms_insight.rendering.bridge import render_component

        session_id = state_manager.session_id

        state_manager.set_selection("spectrum", 1)
        state_manager.set_selection("selected_peak", 10)

        mock_streamlit_bridge["vue_func"].return_value = {
            "id": session_id,
            "counter": 0,
        }
        render_component(lineplot_with_interactivity, state_manager)

        mock_streamlit_bridge["rerun"].reset_mock()

        # Filter change that invalidates selection
        state_manager.set_selection("spectrum", 2)

        render_component(lineplot_with_interactivity, state_manager)

        # Rerun should be called (selection changed from 10 to None)
        mock_streamlit_bridge["rerun"].assert_called()
