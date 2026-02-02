"""
Cross-Component Selection Synchronization Tests.

Tests the interaction between components sharing selection state via StateManager.
Verifies that when one component (e.g., Heatmap) sets a selection, another
component (e.g., Table) correctly responds with navigation hints.

This addresses the bug report: "Table component does not highlight/scroll to row
when Heatmap selection changes"

Test Categories:
    - TestCrossComponentSelectionBasic: Basic cross-component selection via shared StateManager
    - TestCrossComponentSelectionPagination: Selection navigation across paginated Table data
    - TestCrossComponentSelectionWithFilters: Cross-component selection with active filters
    - TestCrossComponentSelectionTypeMismatch: Type coercion between selection and column types
    - TestCrossComponentSelectionMultipleComponents: Multiple components sharing identifiers
    - TestCrossComponentSelectionWithSort: Cross-component selection with active sorting
"""

from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.state import StateManager
from openms_insight.rendering.bridge import render_component

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


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_streamlit_cross():
    """
    Mock Streamlit's session_state for cross-component testing.

    This fixture patches st.session_state to allow testing components
    without running a full Streamlit server.
    """
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def mock_streamlit_bridge_cross(mock_streamlit_cross):
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
                "session_state": mock_streamlit_cross,
                "rerun": mock_rerun,
                "vue_func": mock_vue_func,
            }


@pytest.fixture
def state_manager_cross(mock_streamlit_cross):
    """
    StateManager with fresh state for cross-component tests.

    Returns:
        StateManager instance for testing
    """
    return StateManager(session_key="cross_component_state")


@pytest.fixture
def cross_component_data() -> pl.LazyFrame:
    """
    500-row dataset for cross-component selection testing.

    Columns:
        - id: Unique row identifier (0-499)
        - id_idx: Alternative identifier (1000-1499) for type mismatch testing
        - string_id: String identifier ("000"-"499") with leading zeros
        - scan_id: Filter key for testing filtered selection
            - Rows 0-249 have scan_id=1
            - Rows 250-499 have scan_id=2
            - When filter=1, only first 250 rows shown
            - When filter=2, only last 250 rows shown
        - score: Float for sorting (0.0, 1.0, ..., 499.0)
        - category: Categorical A/B/C/D/E cycling (for additional filtering)

    Data relationships:
        - id=100 has scan_id=1, score=100.0, string_id="100"
        - id=300 has scan_id=2, score=300.0, string_id="300"
    """
    return pl.LazyFrame(
        {
            "id": list(range(500)),
            "id_idx": list(range(1000, 1500)),
            "string_id": [f"{i:03d}" for i in range(500)],
            "scan_id": [1] * 250 + [2] * 250,
            "score": [float(i) for i in range(500)],
            "category": ["A", "B", "C", "D", "E"] * 100,
        }
    )


@pytest.fixture
def paginated_table_with_interactivity(
    cross_component_data, tmp_path, mock_streamlit_cross
):
    """Table with pagination and interactivity for external selection testing."""
    return Table(
        cache_id="cross_table",
        data=cross_component_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="cross_table_page",
        interactivity={"identification": "id"},
        index_field="id",
    )


@pytest.fixture
def filtered_table_with_interactivity(
    cross_component_data, tmp_path, mock_streamlit_cross
):
    """Table with filter and interactivity."""
    return Table(
        cache_id="cross_filtered_table",
        data=cross_component_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="cross_filtered_page",
        filters={"spectrum": "scan_id"},
        interactivity={"identification": "id"},
        index_field="id",
    )


# =============================================================================
# TestCrossComponentSelectionBasic
# =============================================================================


class TestCrossComponentSelectionBasic:
    """
    Basic cross-component selection via shared StateManager.

    Tests verify that external selection (simulating Heatmap click)
    correctly sets navigation hints in Table's _prepare_vue_data().
    """

    def test_external_selection_sets_navigation_hints(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        When selection is set externally (simulating Heatmap click),
        Table's _prepare_vue_data() returns navigation hints.

        App Setup: User has a Heatmap and Table side-by-side, both configured
        with interactivity={"identification": "id"}. Table shows 500 rows
        paginated at 100 rows/page.

        Scenario: User clicks a point in the Heatmap representing row id=250.

        Expected Behavior:
        - Heatmap's click handler calls state_manager.set_selection("identification", 250)
        - Table's _prepare_vue_data() returns _navigate_to_page=3 and _target_row_index=50
        """
        # Simulate external component (Heatmap) setting selection
        state_manager_cross.set_selection("identification", 250)  # Row on page 3

        # Get state and call _prepare_vue_data (as render_component would)
        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}  # Currently on page 1

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        # Should have navigation hints to page 3
        assert result.get("_navigate_to_page") == 3
        assert result.get("_target_row_index") == 50  # 250 % 100 = 50

    def test_external_selection_on_current_page(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection on current page may or may not trigger navigation hints,
        but should highlight row at correct index.

        App Setup: Same Heatmap + Table setup. Table is currently showing
        page 1 (rows 0-99).

        Scenario: User clicks a Heatmap point representing row id=50.

        Expected Behavior:
        - Selection is set for id=50
        - Row 50 is on page 1 (current page)
        - Pagination metadata shows correct page
        """
        # Simulate external selection on current page
        state_manager_cross.set_selection("identification", 50)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        # Row is on current page - pagination should show page 1
        assert result["_pagination"]["page"] == 1
        # If target_row_index is set, it should be 50
        if "_target_row_index" in result:
            assert result["_target_row_index"] == 50

    def test_external_selection_on_different_page(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection on different page triggers navigation.

        App Setup: Same Heatmap + Table setup. Table is currently showing page 1.

        Scenario: User clicks a Heatmap point representing row id=450 (on page 5).

        Expected Behavior:
        - Selection is set for id=450
        - Table returns _navigate_to_page=5, _target_row_index=50
        """
        # Simulate selection to row on page 5
        state_manager_cross.set_selection("identification", 450)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        # Should navigate to page 5
        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 50  # 450 % 100 = 50

    def test_external_selection_clears_pending(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Rapid selection changes should result in only the final selection.

        App Setup: Same setup, but with a timing scenario where multiple
        selections happen in sequence.

        Scenario: User rapidly clicks two different points: first id=250, then id=350.

        Expected Behavior:
        - Only the final selection (id=350) is used
        - Navigation goes to page 4
        """
        # First selection
        state_manager_cross.set_selection("identification", 250)

        # Second selection overwrites
        state_manager_cross.set_selection("identification", 350)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        # Only the final selection (350) should be navigated to
        assert result.get("_navigate_to_page") == 4  # 350 is on page 4
        assert result.get("_target_row_index") == 50  # 350 % 100 = 50


# =============================================================================
# TestCrossComponentSelectionPagination
# =============================================================================


class TestCrossComponentSelectionPagination:
    """
    Selection navigation across paginated Table data.

    Tests verify correct page calculation and row index within page.
    """

    def test_selection_from_page_1_to_page_5(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection navigates from page 1 to page 5.

        App Setup: Heatmap showing all 500 data points. Table showing
        page 1 (rows 0-99) with 100 rows/page.

        Scenario: User is browsing page 1 of the Table. Clicks a Heatmap
        point for row id=450.

        Expected Behavior:
        - Table navigates from page 1 to page 5
        - _navigate_to_page=5, _target_row_index=50 (450 % 100 = 50)
        """
        state_manager_cross.set_selection("identification", 450)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 50

    def test_selection_from_page_5_to_page_1(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection navigates backward from page 5 to page 1.

        App Setup: Same setup. User has manually navigated Table to page 5.

        Scenario: User clicks a Heatmap point for row id=25.

        Expected Behavior:
        - Table navigates from page 5 back to page 1
        - _navigate_to_page=1, _target_row_index=25
        """
        state_manager_cross.set_selection("identification", 25)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 5, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 1
        assert result.get("_target_row_index") == 25

    def test_selection_on_boundary_row_page_end(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection on last row of a page.

        App Setup: Table with 100 rows/page. Page 1 shows rows 0-99.

        Scenario: User clicks Heatmap point for id=99 (last row of page 1).

        Expected Behavior:
        - _navigate_to_page=1, _target_row_index=99
        """
        state_manager_cross.set_selection("identification", 99)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 3, "page_size": 100}  # Currently on page 3

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 1
        assert result.get("_target_row_index") == 99

    def test_selection_on_boundary_row_page_start(
        self, paginated_table_with_interactivity, state_manager_cross
    ):
        """
        Selection on first row of a page (boundary).

        App Setup: Table with 100 rows/page. Page 2 shows rows 100-199.

        Scenario: User clicks Heatmap point for id=100 (first row of page 2).

        Expected Behavior:
        - _navigate_to_page=2, _target_row_index=0
        """
        state_manager_cross.set_selection("identification", 100)

        state = state_manager_cross.get_state_for_vue()
        state["cross_table_page"] = {"page": 1, "page_size": 100}

        result = paginated_table_with_interactivity._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 2
        assert result.get("_target_row_index") == 0

    def test_selection_with_page_size_change(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection with different page sizes calculates correctly.

        App Setup: User changes Table page size from 100 to 50 rows/page.

        Scenario: Selection is set for id=250 with page_size=50.

        Expected Behavior:
        - With page_size=50: _navigate_to_page=6 (rows 250-299)
        """
        table = Table(
            cache_id="page_size_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=50,  # Smaller page size
            pagination_identifier="page_size_test_page",
            interactivity={"identification": "id"},
            index_field="id",
        )

        state_manager_cross.set_selection("identification", 250)

        state = state_manager_cross.get_state_for_vue()
        state["page_size_test_page"] = {"page": 1, "page_size": 50}

        result = table._prepare_vue_data(state)

        # With page_size=50: 250 / 50 = 5, so page 6 (1-indexed)
        assert result.get("_navigate_to_page") == 6
        assert result.get("_target_row_index") == 0  # 250 % 50 = 0


# =============================================================================
# TestCrossComponentSelectionWithFilters
# =============================================================================


class TestCrossComponentSelectionWithFilters:
    """
    Cross-component selection when Table has active filters.

    Tests verify that external selection respects active filters
    and handles cases where the selected row is not in filtered data.
    """

    def test_external_selection_respects_filter(
        self, filtered_table_with_interactivity, state_manager_cross
    ):
        """
        External selection finds row within filtered data.

        App Setup:
        - Test data structure: 500 rows with scan_id column:
          - Rows id=0-249 have scan_id=1
          - Rows id=250-499 have scan_id=2
        - Table configured with filters={"spectrum": "scan_id"}
        - Filter set: spectrum=1 (showing only rows 0-249)

        Scenario: User clicks Heatmap point for row id=100. This row has
        scan_id=1, so it passes the Table's active filter.

        Expected Behavior:
        - Table checks: does id=100 exist in filtered data? YES
        - Within the filtered 250-row dataset, id=100 is at position 100
        - With page_size=100: _navigate_to_page=2, _target_row_index=0
        """
        # Set filter to show only scan_id=1 (rows 0-249)
        state_manager_cross.set_selection("spectrum", 1)
        # External selection within filtered data
        state_manager_cross.set_selection("identification", 100)

        state = state_manager_cross.get_state_for_vue()
        state["cross_filtered_page"] = {"page": 1, "page_size": 100}

        result = filtered_table_with_interactivity._prepare_vue_data(state)

        # id=100 is in filtered data (scan_id=1), at position 100 in filtered set
        # Page 2 (rows 100-199 of filtered data), index 0
        assert result.get("_navigate_to_page") == 2
        assert result.get("_target_row_index") == 0
        assert result["_pagination"]["total_rows"] == 250  # Only scan_id=1 rows

    def test_external_selection_not_found_after_filter(
        self, filtered_table_with_interactivity, state_manager_cross
    ):
        """
        External selection for row not in filtered data returns no navigation hints.

        App Setup:
        - Same data structure: rows 0-249 have scan_id=1, rows 250-499 have scan_id=2
        - Table filtered to spectrum=1 (showing only rows with scan_id=1)
        - Heatmap shows ALL 500 points (unfiltered view)

        Scenario: User clicks Heatmap point for row id=300. This row has
        scan_id=2, which is EXCLUDED by the Table's active filter.

        Expected Behavior:
        - Table checks: does id=300 exist in filtered data? NO
        - _prepare_vue_data() returns no navigation hints
        - No ComputeError or crash - graceful handling
        """
        # Set filter to show only scan_id=1 (rows 0-249)
        state_manager_cross.set_selection("spectrum", 1)
        # External selection NOT in filtered data (id=300 has scan_id=2)
        state_manager_cross.set_selection("identification", 300)

        state = state_manager_cross.get_state_for_vue()
        state["cross_filtered_page"] = {"page": 1, "page_size": 100}

        # Should NOT raise ComputeError
        result = filtered_table_with_interactivity._prepare_vue_data(state)

        # Row 300 not found in filtered data - no navigation
        # The component should gracefully handle this
        assert result["_pagination"]["total_rows"] == 250

    def test_selection_with_filter_and_sort(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection with both filter and sort applied.

        App Setup: Table with filter (scan_id=1) AND sort (score descending).

        Scenario: User clicks Heatmap point for id=50. Row 50 has scan_id=1
        (passes filter) and score=50.0.

        Expected Behavior:
        - Row found in filtered AND sorted data
        - Navigation hint reflects sorted position
        """
        table = Table(
            cache_id="filter_sort_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="filter_sort_test_page",
            filters={"spectrum": "scan_id"},
            interactivity={"identification": "id"},
            index_field="id",
            initial_sort=[{"column": "score", "dir": "desc"}],
        )

        # Filter to scan_id=1 (rows 0-249, scores 0.0-249.0)
        state_manager_cross.set_selection("spectrum", 1)
        # Select row with id=50, score=50.0
        state_manager_cross.set_selection("identification", 50)

        state = state_manager_cross.get_state_for_vue()
        state["filter_sort_test_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # With descending sort, id=50 (score=50.0) should be near the end
        # In filtered data (250 rows), score 50.0 is position 199 (0-indexed from end)
        # That's 249 - 50 = 199, so page 2 (rows 100-199), index 99
        assert result["_pagination"]["total_rows"] == 250

    def test_filter_change_invalidates_external_selection(
        self,
        filtered_table_with_interactivity,
        state_manager_cross,
        mock_streamlit_bridge_cross,
    ):
        """
        Filter change that invalidates selection triggers auto-selection.

        App Setup:
        - Table showing scan_id=1 filter (rows 0-249)
        - Selection set to id=100

        Scenario: Another component changes filter to scan_id=2.

        Expected Behavior:
        - New filter shows rows 250-499
        - Previous selection id=100 is no longer valid
        - Auto-selection or selection clearing occurs
        """
        session_id = state_manager_cross.session_id

        # Initial setup: filter=1, selection=100
        state_manager_cross.set_selection("spectrum", 1)
        state_manager_cross.set_selection("identification", 100)

        mock_streamlit_bridge_cross["vue_func"].return_value = create_vue_response(
            page=1,
            page_size=100,
            session_id=session_id,
            pagination_identifier="cross_filtered_page",
        )

        render_component(filtered_table_with_interactivity, state_manager_cross)

        # Verify initial selection
        assert state_manager_cross.get_selection("identification") == 100

        # Change filter - id=100 doesn't exist in scan_id=2
        state_manager_cross.set_selection("spectrum", 2)

        render_component(filtered_table_with_interactivity, state_manager_cross)

        # Selection should change (either cleared or auto-selected to first row of new filter)
        # First row of scan_id=2 is id=250
        new_selection = state_manager_cross.get_selection("identification")
        assert new_selection != 100 or new_selection is None


# =============================================================================
# TestCrossComponentSelectionTypeMismatch
# =============================================================================


class TestCrossComponentSelectionTypeMismatch:
    """
    Type coercion when selection value type differs from column type.

    Tests verify graceful handling of type mismatches between
    selection values and column data types.
    """

    def test_string_column_numeric_selection_value(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Numeric selection value with string column.

        App Setup:
        - Table's interactivity column (string_id) is string type: "000", "001", ..., "499"

        Scenario: User clicks Heatmap point. Heatmap sets selection as integer 42.

        Expected Behavior:
        - Table needs to find row where string_id == "042" (string)
        - Should NOT raise ComputeError: cannot compare string with numeric type
        """
        table = Table(
            cache_id="type_mismatch_string",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="type_mismatch_string_page",
            interactivity={"identification": "string_id"},  # String column
            index_field="id",
        )

        # Numeric value (as might come from Heatmap)
        state_manager_cross.set_selection("identification", 42)

        state = state_manager_cross.get_state_for_vue()
        state["type_mismatch_string_page"] = {"page": 1, "page_size": 100}

        # Should NOT raise ComputeError
        result = table._prepare_vue_data(state)

        # Result should be valid (may or may not find match depending on conversion)
        assert "tableData" in result
        assert "_pagination" in result

    def test_numeric_column_string_selection_value(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        String selection value with numeric column.

        App Setup:
        - Table's interactivity column (id) is integer type

        Scenario: Selection set as string "42".

        Expected Behavior:
        - Table needs to find row where id == 42 (integer)
        - Should convert string "42" to int 42 for comparison
        """
        table = Table(
            cache_id="type_mismatch_numeric",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="type_mismatch_numeric_page",
            interactivity={"identification": "id"},  # Integer column
            index_field="id",
        )

        # String value for numeric column
        state_manager_cross.set_selection("identification", "42")

        state = state_manager_cross.get_state_for_vue()
        state["type_mismatch_numeric_page"] = {"page": 1, "page_size": 100}

        # Should NOT raise ComputeError
        result = table._prepare_vue_data(state)

        # Result should be valid
        assert "tableData" in result
        assert "_pagination" in result

    def test_selection_value_with_leading_zeros(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        String selection with leading zeros.

        App Setup:
        - Table's interactivity column is string: "000", "001", ..., "099", ...

        Scenario: User selects value "007" (string with leading zeros).

        Expected Behavior:
        - Selection value "007" should match row with string_id="007"
        - Should NOT convert "007" to integer 7
        """
        table = Table(
            cache_id="leading_zeros_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="leading_zeros_test_page",
            interactivity={"identification": "string_id"},
            index_field="id",
        )

        # String with leading zeros
        state_manager_cross.set_selection("identification", "007")

        state = state_manager_cross.get_state_for_vue()
        state["leading_zeros_test_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # Should find the row with string_id="007"
        # Row 7 in original data has string_id="007"
        assert "tableData" in result

    def test_float_column_string_selection_value(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        String selection value with float column.

        App Setup:
        - Table's interactivity column (score) is float type: 0.0, 1.0, ..., 499.0

        Scenario: Selection set as string "21.0".

        Expected Behavior:
        - Convert string "21.0" to float 21.0
        - Find row where score == 21.0
        """
        table = Table(
            cache_id="float_type_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="float_type_test_page",
            interactivity={"identification": "score"},  # Float column
            index_field="id",
        )

        # String representation of float
        state_manager_cross.set_selection("identification", "21.0")

        state = state_manager_cross.get_state_for_vue()
        state["float_type_test_page"] = {"page": 1, "page_size": 100}

        # Should NOT raise ComputeError
        result = table._prepare_vue_data(state)

        assert "tableData" in result
        assert "_pagination" in result


# =============================================================================
# TestCrossComponentSelectionMultipleComponents
# =============================================================================


class TestCrossComponentSelectionMultipleComponents:
    """
    Multiple components sharing the same interactivity identifier.

    Tests verify that selections propagate correctly across
    multiple components reacting to the same identifier.
    """

    def test_two_tables_same_identifier(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Two tables with same interactivity identifier both react to selection.

        App Setup:
        - Table A: interactivity={"protein": "id"}
        - Table B: interactivity={"protein": "id"}
        - Both linked by same "protein" identifier

        Scenario: Selection protein=250 is set externally.

        Expected Behavior:
        - Both Table A and Table B receive the selection
        - Both components should have navigation hints
        """
        table_a = Table(
            cache_id="multi_table_a",
            data=cross_component_data,
            cache_path=str(tmp_path / "a"),
            pagination=True,
            page_size=100,
            pagination_identifier="multi_table_a_page",
            interactivity={"protein": "id"},
            index_field="id",
        )

        table_b = Table(
            cache_id="multi_table_b",
            data=cross_component_data,
            cache_path=str(tmp_path / "b"),
            pagination=True,
            page_size=100,
            pagination_identifier="multi_table_b_page",
            interactivity={"protein": "id"},
            index_field="id",
        )

        # External selection
        state_manager_cross.set_selection("protein", 250)

        state = state_manager_cross.get_state_for_vue()
        state["multi_table_a_page"] = {"page": 1, "page_size": 100}
        state["multi_table_b_page"] = {"page": 1, "page_size": 100}

        result_a = table_a._prepare_vue_data(state)
        result_b = table_b._prepare_vue_data(state)

        # Both should navigate to page 3
        assert result_a.get("_navigate_to_page") == 3
        assert result_b.get("_navigate_to_page") == 3

    def test_table_and_heatmap_shared_identifier(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Table receives selection from Heatmap via shared identifier.

        App Setup:
        - Heatmap: shows 2D mass spec data, interactivity={"identification": "id_idx"}
        - Table: shows identification details, interactivity={"identification": "id_idx"}
        - This is the exact bug report scenario

        Scenario: User clicks a point in Heatmap for id_idx=1250.

        Expected Behavior:
        - Heatmap sets state_manager.set_selection("identification", 1250)
        - Table's _prepare_vue_data() returns navigation hints
        """
        table = Table(
            cache_id="heatmap_table_sync",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="heatmap_table_sync_page",
            interactivity={"identification": "id_idx"},  # id_idx column: 1000-1499
            index_field="id",
        )

        # Simulate Heatmap click setting selection
        state_manager_cross.set_selection("identification", 1250)  # id_idx value

        state = state_manager_cross.get_state_for_vue()
        state["heatmap_table_sync_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # id_idx=1250 corresponds to id=250, which is on page 3
        assert result.get("_navigate_to_page") == 3
        assert result.get("_target_row_index") == 50

    def test_cascading_selection(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection cascades through multiple components.

        App Setup:
        - Component A: Sets "identification" on click
        - Component B (Table): Filters by "identification", sets "category" on click

        Scenario: Selection "identification"=100 is set, Table should filter/highlight.
        """
        # Table that filters by identification and sets category
        table = Table(
            cache_id="cascade_table",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="cascade_table_page",
            interactivity={"category_selection": "category"},
            index_field="id",
        )

        # Simulate first selection in chain
        state_manager_cross.set_selection("category_selection", "A")

        state = state_manager_cross.get_state_for_vue()
        state["cascade_table_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # Table should function correctly with cascading selection
        assert "tableData" in result

    def test_selection_order_independence(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Component render order doesn't affect selection propagation.

        App Setup:
        - Component A and Component B both react to identifier "foo"

        Scenario: Selection foo=123 is set externally.

        Expected Behavior:
        - Whether A renders first or B renders first, both get the selection
        """
        table_a = Table(
            cache_id="order_test_a",
            data=cross_component_data,
            cache_path=str(tmp_path / "a"),
            pagination=True,
            page_size=100,
            pagination_identifier="order_test_a_page",
            interactivity={"foo": "id"},
            index_field="id",
        )

        table_b = Table(
            cache_id="order_test_b",
            data=cross_component_data,
            cache_path=str(tmp_path / "b"),
            pagination=True,
            page_size=100,
            pagination_identifier="order_test_b_page",
            interactivity={"foo": "id"},
            index_field="id",
        )

        state_manager_cross.set_selection("foo", 123)

        state = state_manager_cross.get_state_for_vue()
        state["order_test_a_page"] = {"page": 1, "page_size": 100}
        state["order_test_b_page"] = {"page": 1, "page_size": 100}

        # Render B first, then A (opposite of definition order)
        result_b = table_b._prepare_vue_data(state)
        result_a = table_a._prepare_vue_data(state)

        # Both should get the same selection
        assert state.get("foo") == 123
        # Both should navigate to same page
        assert result_a.get("_navigate_to_page") == result_b.get("_navigate_to_page")


# =============================================================================
# TestCrossComponentSelectionWithSort
# =============================================================================


class TestCrossComponentSelectionWithSort:
    """
    Cross-component selection when Table has active sorting.

    Tests verify that navigation hints reflect sorted position.
    """

    def test_external_selection_with_ascending_sort(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection navigation with ascending sort.

        App Setup:
        - Table with 500 rows, sorted by score ascending
        - Row id=0 has score=0.0 (first in sort), id=499 has score=499.0 (last)

        Scenario: User clicks Heatmap for row id=250 (score=250.0, middle).

        Expected Behavior:
        - In ascending sort, id=250 is at position 250
        - _navigate_to_page=3, _target_row_index=50
        """
        table = Table(
            cache_id="sort_asc_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="sort_asc_test_page",
            interactivity={"identification": "id"},
            index_field="id",
            initial_sort=[{"column": "score", "dir": "asc"}],
        )

        state_manager_cross.set_selection("identification", 250)

        state = state_manager_cross.get_state_for_vue()
        state["sort_asc_test_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # With ascending sort, id=250 (score=250.0) is at position 250
        assert result.get("_navigate_to_page") == 3
        assert result.get("_target_row_index") == 50

    def test_external_selection_with_descending_sort(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection navigation with descending sort.

        App Setup:
        - Same Table, but sorted by score descending
        - Row id=499 (score=499.0) is now first, id=0 (score=0.0) is last

        Scenario: User clicks Heatmap for row id=0.

        Expected Behavior:
        - In descending sort, id=0 (score=0.0) is at position 499 (last)
        - _navigate_to_page=5, _target_row_index=99
        """
        table = Table(
            cache_id="sort_desc_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="sort_desc_test_page",
            interactivity={"identification": "id"},
            index_field="id",
            initial_sort=[{"column": "score", "dir": "desc"}],
        )

        state_manager_cross.set_selection("identification", 0)

        state = state_manager_cross.get_state_for_vue()
        state["sort_desc_test_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # With descending sort, id=0 (score=0.0) is at position 499 (last)
        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 99

    def test_external_selection_with_initial_sort(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection with initial_sort configuration.

        App Setup:
        - Table configured with initial_sort=[{"column": "score", "dir": "desc"}]
        - No user-applied sort yet (using initial configuration)

        Scenario: Page loads, Heatmap click selects id=0.

        Expected Behavior:
        - Initial sort is applied: id=0 is at end (score=0.0 is lowest)
        - Navigation hints reflect initial_sort order
        """
        table = Table(
            cache_id="initial_sort_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="initial_sort_test_page",
            interactivity={"identification": "id"},
            index_field="id",
            initial_sort=[{"column": "score", "dir": "desc"}],
        )

        state_manager_cross.set_selection("identification", 0)

        state = state_manager_cross.get_state_for_vue()
        # No sort_column in pagination state - initial_sort should apply
        state["initial_sort_test_page"] = {"page": 1, "page_size": 100}

        result = table._prepare_vue_data(state)

        # With initial descending sort, id=0 is last
        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 99

    def test_sort_change_updates_selection_position(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Sort change recalculates selection position.

        App Setup:
        - Table sorted ascending, selection set to id=250

        Scenario: Same selection, but sort order changes from asc to desc.

        Expected Behavior:
        - Before: id=250 at position 250 -> page 3
        - After desc sort: id=250 at position 249 (from end)
        """
        table = Table(
            cache_id="sort_change_test",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="sort_change_test_page",
            interactivity={"identification": "id"},
            index_field="id",
        )

        state_manager_cross.set_selection("identification", 250)

        # Ascending sort (default or explicit)
        state = state_manager_cross.get_state_for_vue()
        state["sort_change_test_page"] = {
            "page": 1,
            "page_size": 100,
            "sort_column": "score",
            "sort_dir": "asc",
        }

        result_asc = table._prepare_vue_data(state)
        # id=250 with score=250.0 is at position 250 in ascending
        assert result_asc.get("_navigate_to_page") == 3

        # Change to descending sort
        state["sort_change_test_page"] = {
            "page": 1,
            "page_size": 100,
            "sort_column": "score",
            "sort_dir": "desc",
        }

        result_desc = table._prepare_vue_data(state)
        # id=250 with score=250.0 is at position 249 in descending (500-250-1=249)
        assert (
            result_desc.get("_navigate_to_page") == 3
        )  # Still page 3 but different index
        assert result_desc.get("_target_row_index") == 49  # 249 % 100 = 49


# =============================================================================
# TestPaginationPreservationOnSelection
# =============================================================================


class TestPaginationPreservationOnSelection:
    """
    Test that page number is preserved when user clicks a row on that page.

    This tests the bug: user on page 10, clicks row on page 10, page should stay 10.
    """

    def test_selection_on_page_5_keeps_page_5(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        User on page 5, clicks row 450 (on page 5), page should stay 5.

        Scenario:
        1. User navigates to page 5 (rows 400-499)
        2. User clicks row with id=450
        3. Table should stay on page 5, not reset to page 1

        This is the exact bug reported.
        """
        table = Table(
            cache_id="page_preserve_5",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="page_preserve_5_page",
            interactivity={"selected_id": "id"},
            index_field="id",
        )

        # User clicks row 450 (on page 5: rows 400-499)
        state_manager_cross.set_selection("selected_id", 450)

        state = state_manager_cross.get_state_for_vue()
        state["page_preserve_5_page"] = {
            "page": 5,
            "page_size": 100,
        }  # User is on page 5

        result = table._prepare_vue_data(state)

        # CRITICAL: Page should stay 5, not reset to 1
        assert result["_pagination"]["page"] == 5, (
            f"Page jumped to {result['_pagination']['page']} instead of staying on 5"
        )

    def test_selection_on_page_3_keeps_page_3(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """Same test with page 3."""
        table = Table(
            cache_id="page_preserve_3",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="page_preserve_3_page",
            interactivity={"selected_id": "id"},
            index_field="id",
        )

        # User clicks row 250 (on page 3: rows 200-299)
        state_manager_cross.set_selection("selected_id", 250)

        state = state_manager_cross.get_state_for_vue()
        state["page_preserve_3_page"] = {"page": 3, "page_size": 100}

        result = table._prepare_vue_data(state)

        assert result["_pagination"]["page"] == 3

    def test_selection_change_on_same_page_no_navigation_hint(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Selection change within same page should not produce navigation hints.

        User on page 3, clicks row 250 (also on page 3).
        No _navigate_to_page should be returned since already on correct page.
        """
        table = Table(
            cache_id="no_nav_hint",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="no_nav_hint_page",
            interactivity={"selected_id": "id"},
            index_field="id",
        )

        state_manager_cross.set_selection("selected_id", 250)

        state = state_manager_cross.get_state_for_vue()
        state["no_nav_hint_page"] = {"page": 3, "page_size": 100}

        result = table._prepare_vue_data(state)

        # Should NOT have navigation hint since already on correct page
        assert "_navigate_to_page" not in result or result.get("_navigate_to_page") == 3
        assert result["_pagination"]["page"] == 3

    def test_selection_on_page_with_initial_sort_preserves_page(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Test pagination preservation with initial_sort configured (MHCquant scenario).

        This mirrors the exact setup from MHCquant's Workflow.py:
        - Table with initial_sort=[{'column': 'score', 'dir': 'asc'}]
        - Multiple interactivity identifiers
        - User navigates to a page, clicks a row on that page

        Bug: Page jumps to 1 instead of staying on current page.
        """
        table = Table(
            cache_id="mhcquant_like_table",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="mhcquant_like_table_page",
            interactivity={"identification": "id"},
            index_field="id",
            initial_sort=[{"column": "score", "dir": "asc"}],
        )

        # With ascending sort by score (which equals id in test data),
        # id=250 is at position 250, which is page 3 (rows 200-299)
        state_manager_cross.set_selection("identification", 250)

        state = state_manager_cross.get_state_for_vue()
        # User is already on page 3
        state["mhcquant_like_table_page"] = {"page": 3, "page_size": 100}

        result = table._prepare_vue_data(state)

        # CRITICAL: Page should stay 3, not reset to 1
        assert result["_pagination"]["page"] == 3, (
            f"Page jumped to {result['_pagination']['page']} instead of staying on 3"
        )

    def test_selection_on_page_with_initial_sort_and_multiple_identifiers(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Test with multiple interactivity identifiers (exact MHCquant setup).

        MHCquant uses: interactivity={"file": "file_index", "spectrum": "scan_id", "identification": "id_idx"}
        This test simulates that with our test data structure.
        """
        table = Table(
            cache_id="multi_id_sort_table",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="multi_id_sort_table_page",
            # Multiple identifiers like MHCquant
            interactivity={
                "category_sel": "category",
                "scan_sel": "scan_id",
                "identification": "id",
            },
            index_field="id",
            initial_sort=[{"column": "score", "dir": "asc"}],
        )

        # Set multiple selections (simulating linked components)
        state_manager_cross.set_selection("category_sel", "A")
        state_manager_cross.set_selection("scan_sel", 1)
        state_manager_cross.set_selection("identification", 300)

        state = state_manager_cross.get_state_for_vue()
        # User is on page 4 (row 300 with asc sort is at position 300 = page 4)
        state["multi_id_sort_table_page"] = {"page": 4, "page_size": 100}

        result = table._prepare_vue_data(state)

        # Page should stay 4
        assert result["_pagination"]["page"] == 4, (
            f"Page jumped to {result['_pagination']['page']} instead of staying on 4"
        )

    def test_row_click_on_current_page_with_sort_state_in_pagination(
        self, cross_component_data, tmp_path, state_manager_cross, mock_streamlit_cross
    ):
        """
        Test when pagination state includes sort info (user-applied sort via Vue).

        This tests the scenario where:
        1. User applies sort via Vue (sort info in pagination state)
        2. User navigates to page N
        3. User clicks a row on page N
        4. Page should stay N
        """
        table = Table(
            cache_id="sort_in_pagination_table",
            data=cross_component_data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=100,
            pagination_identifier="sort_in_pagination_table_page",
            interactivity={"identification": "id"},
            index_field="id",
        )

        # User clicked row with id=450
        state_manager_cross.set_selection("identification", 450)

        state = state_manager_cross.get_state_for_vue()
        # Pagination state includes user-applied sort AND current page
        # With desc sort, id=450 (score=450) is at position 49 (500-450-1=49), page 1
        # With asc sort, id=450 is at position 450, page 5
        state["sort_in_pagination_table_page"] = {
            "page": 5,
            "page_size": 100,
            "sort_column": "score",
            "sort_dir": "asc",
        }

        result = table._prepare_vue_data(state)

        # With asc sort, id=450 is on page 5 - should stay there
        assert result["_pagination"]["page"] == 5, (
            f"Page jumped to {result['_pagination']['page']} instead of staying on 5"
        )
