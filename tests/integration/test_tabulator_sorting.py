"""
Tabulator Column Sorting Integration Tests.

Tests the Table component's server-side sorting functionality,
including basic sorting, sort with pagination, and sort with filters.

Sort Parameters:
    - sort_column: Column name to sort by
    - sort_dir: "asc" or "desc"

Test Categories:
    - TestSortBasic: Basic ascending/descending sort tests
    - TestSortNoSort: Default behavior without sort
    - TestSortMetadata: Sort metadata verification
    - TestSortWithPagination: Sort-pagination interactions
    - TestSortWithFilters: Sort-filter combinations
    - TestSortEdgeCases: Edge cases and error handling
    - TestSortColumnTypes: Different column data types
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pandas as pd
import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.state import StateManager


# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockSessionState(dict):
    """Mock Streamlit session_state that behaves like a dict."""

    pass


def create_sort_state(
    page: int = 1,
    page_size: int = 100,
    column_filters: Optional[List[Dict[str, Any]]] = None,
    sort_column: Optional[str] = None,
    sort_dir: str = "asc",
    pagination_identifier: str = "test_sort_table_page",
) -> Dict[str, Any]:
    """
    Create pagination state dict with sort parameters.

    Args:
        page: Current page number
        page_size: Rows per page
        column_filters: List of column filter dicts
        sort_column: Column to sort by
        sort_dir: Sort direction ("asc" or "desc")
        pagination_identifier: Key for pagination state

    Returns:
        Dict with pagination state including sort parameters
    """
    state: Dict[str, Any] = {
        pagination_identifier: {
            "page": page,
            "page_size": page_size,
        }
    }
    if column_filters:
        state[pagination_identifier]["column_filters"] = column_filters
    if sort_column:
        state[pagination_identifier]["sort_column"] = sort_column
        state[pagination_identifier]["sort_dir"] = sort_dir
    return state


@pytest.fixture
def mock_streamlit_sort():
    """Mock Streamlit's session_state for sort testing."""
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def state_manager_sort(mock_streamlit_sort):
    """Create a StateManager with mocked session_state for sort tests."""
    return StateManager(session_key="test_sort_state")


@pytest.fixture
def sort_table_component(pagination_test_data, tmp_path):
    """
    Create a Table component configured for sort testing.

    Returns:
        Table component with 500-row test data
    """
    return Table(
        cache_id="test_sort_table",
        data=pagination_test_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="test_sort_table_page",
        index_field="id",
    )


# =============================================================================
# TestSortBasic
# =============================================================================


class TestSortBasic:
    """
    Basic sorting tests for ascending and descending order.

    Verifies that data is correctly sorted by different column types
    in both ascending and descending directions.
    """

    def test_sort_numeric_ascending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort numeric column (score) in ascending order.

        Verifies:
            - Scores are in ascending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted ascending
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_numeric_descending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort numeric column (score) in descending order.

        Verifies:
            - Scores are in descending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="desc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted descending
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_text_ascending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort text column (value) in ascending order.

        Verifies:
            - Values are in alphabetical ascending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="value", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted ascending
        values = result["tableData"]["value"].tolist()
        assert values == sorted(values)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "value"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_text_descending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort text column (value) in descending order.

        Verifies:
            - Values are in alphabetical descending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="value", sort_dir="desc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted descending
        values = result["tableData"]["value"].tolist()
        assert values == sorted(values, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "value"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_categorical_ascending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort categorical column (category) in ascending order.

        Verifies:
            - Categories are in alphabetical ascending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="category", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted ascending (A, A, A, ..., B, B, B, ...)
        categories = result["tableData"]["category"].tolist()
        assert categories == sorted(categories)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "category"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_categorical_descending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort categorical column (category) in descending order.

        Verifies:
            - Categories are in alphabetical descending order
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="category", sort_dir="desc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is sorted descending (E, E, E, ..., D, D, D, ...)
        categories = result["tableData"]["category"].tolist()
        assert categories == sorted(categories, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "category"
        assert result["_pagination"]["sort_dir"] == "desc"


# =============================================================================
# TestSortNoSort
# =============================================================================


class TestSortNoSort:
    """
    Tests for default behavior when no sort is applied.

    Verifies that data preserves original order and metadata
    reflects the absence of sorting.
    """

    def test_no_sort_preserves_original_order(
        self, sort_table_component, state_manager_sort
    ):
        """
        Without sort parameters, data preserves original order.

        Verifies:
            - IDs are in original order (0, 1, 2, ...)
            - sort_column is None in metadata
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(create_sort_state(page=1))  # No sort_column

        result = sort_table_component._prepare_vue_data(state)

        # Verify data is in original order (id 0, 1, 2, ...)
        ids = result["tableData"]["id"].tolist()
        assert ids == list(range(100))  # First page: 0-99

        # Verify no sort metadata
        assert result["_pagination"]["sort_column"] is None
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_empty_sort_column_no_effect(
        self, sort_table_component, state_manager_sort
    ):
        """
        Empty string sort_column has no effect on order.

        Verifies:
            - Data preserves original order with empty string sort_column
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            {
                "test_sort_table_page": {
                    "page": 1,
                    "page_size": 100,
                    "sort_column": "",
                    "sort_dir": "asc",
                }
            }
        )

        result = sort_table_component._prepare_vue_data(state)

        # Empty string is falsy, so no sort applied - original order
        ids = result["tableData"]["id"].tolist()
        assert ids == list(range(100))

    def test_none_sort_column_no_effect(
        self, sort_table_component, state_manager_sort
    ):
        """
        None sort_column explicitly has no effect on order.

        Verifies:
            - Data preserves original order with None sort_column
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            {
                "test_sort_table_page": {
                    "page": 1,
                    "page_size": 100,
                    "sort_column": None,
                    "sort_dir": "asc",
                }
            }
        )

        result = sort_table_component._prepare_vue_data(state)

        # None is falsy, so no sort applied - original order
        ids = result["tableData"]["id"].tolist()
        assert ids == list(range(100))


# =============================================================================
# TestSortMetadata
# =============================================================================


class TestSortMetadata:
    """
    Tests for sort metadata in pagination response.

    Verifies that sort_column and sort_dir are correctly
    reported in _pagination metadata for all scenarios.
    """

    def test_sort_metadata_returned_ascending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort metadata correctly returned for ascending sort.

        Verifies:
            - sort_column matches requested column
            - sort_dir is "asc"
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="id", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["sort_column"] == "id"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_metadata_returned_descending(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort metadata correctly returned for descending sort.

        Verifies:
            - sort_column matches requested column
            - sort_dir is "desc"
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="priority", sort_dir="desc")
        )

        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["sort_column"] == "priority"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_metadata_no_sort(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort metadata shows None/default when no sort applied.

        Verifies:
            - sort_column is None when not sorting
            - sort_dir has default value
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(create_sort_state(page=1))  # No sort_column

        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["sort_column"] is None
        assert result["_pagination"]["sort_dir"] == "asc"


# =============================================================================
# TestSortWithPagination
# =============================================================================


class TestSortWithPagination:
    """
    Sort-pagination interaction tests.

    Verifies that sorting works correctly across pages, sort persists
    when navigating, and pagination metadata remains accurate.
    """

    def test_sort_persists_across_pages(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort order persists when navigating between pages.

        Verifies:
            - Page 1 and Page 2 both sorted by same column
            - Last value on Page 1 relates correctly to first value on Page 2
        """
        state = state_manager_sort.get_state_for_vue()

        # Page 1 sorted descending by score
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="desc")
        )
        result1 = sort_table_component._prepare_vue_data(state)

        # Page 2 with same sort
        state.update(
            create_sort_state(page=2, sort_column="score", sort_dir="desc")
        )
        result2 = sort_table_component._prepare_vue_data(state)

        # Last score on page 1 should be >= first score on page 2 (descending)
        last_score_p1 = result1["tableData"]["score"].iloc[-1]
        first_score_p2 = result2["tableData"]["score"].iloc[0]
        assert last_score_p1 >= first_score_p2

        # Both pages have correct metadata
        assert result1["_pagination"]["sort_column"] == "score"
        assert result2["_pagination"]["sort_column"] == "score"

    def test_sort_different_pages_have_correct_order(
        self, sort_table_component, state_manager_sort
    ):
        """
        Each page maintains sorted order within its data.

        Verifies:
            - Page 3 data is sorted within itself
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=3, sort_column="score", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Page 3 should have scores in ascending order
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores)

        # Verify it's page 3 data (scores 300-399.5 range for ids 200-299)
        # With 500 rows, page 3 (page_size=100) has ids 200-299
        # scores: 200*1.5=300 to 299*1.5=448.5
        assert result["_pagination"]["page"] == 3

    def test_sort_change_resets_to_page_one(
        self, sort_table_component, state_manager_sort
    ):
        """
        Changing sort column/direction should work from page 1.

        Note: The actual page reset is handled by Vue; this test verifies
        that the sort works correctly when starting from page 1.

        Verifies:
            - New sort direction is applied
            - sort_column and sort_dir metadata reflect new state
        """
        state = state_manager_sort.get_state_for_vue()

        # Start with ascending sort on page 1
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="asc")
        )
        result1 = sort_table_component._prepare_vue_data(state)
        assert result1["tableData"]["score"].iloc[0] == 0.0  # Min score

        # Change to descending sort (simulating user changing sort)
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="desc")
        )
        result2 = sort_table_component._prepare_vue_data(state)

        # First row should now have max score
        assert result2["tableData"]["score"].iloc[0] == 748.5  # Max score (499 * 1.5)
        assert result2["_pagination"]["sort_dir"] == "desc"

    def test_sort_change_with_selection_jumps_to_selected_page(
        self, sort_table_component, state_manager_sort, mock_streamlit_sort
    ):
        """
        When sort changes and a row is selected, table can navigate to selected row's page.

        Note: This behavior requires interactivity to be configured.
        Without interactivity, there's no selection to track.

        Verifies:
            - Sorting works correctly on specified page
        """
        state = state_manager_sort.get_state_for_vue()

        # Sort by score ascending, request page 3
        state.update(
            create_sort_state(page=3, sort_column="score", sort_dir="asc")
        )
        result = sort_table_component._prepare_vue_data(state)

        # Verify we're on page 3 with correct sort
        assert result["_pagination"]["page"] == 3
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores)

    def test_sort_total_pages_unchanged(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sorting does not change total page count.

        Verifies:
            - total_pages remains same with and without sort
        """
        state = state_manager_sort.get_state_for_vue()

        # Without sort
        state.update(create_sort_state(page=1))
        result_unsorted = sort_table_component._prepare_vue_data(state)

        # With sort
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="desc")
        )
        result_sorted = sort_table_component._prepare_vue_data(state)

        # Total pages should be the same (500 rows / 100 page_size = 5 pages)
        assert result_unsorted["_pagination"]["total_pages"] == 5
        assert result_sorted["_pagination"]["total_pages"] == 5

    def test_sort_page_size_unchanged(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sorting does not affect page size.

        Verifies:
            - page_size remains same with and without sort
            - Returned data has correct number of rows
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1, page_size=50, sort_column="score", sort_dir="desc"
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["page_size"] == 50
        assert len(result["tableData"]) == 50

    def test_sort_last_page_has_correct_data(
        self, sort_table_component, state_manager_sort
    ):
        """
        Last page has correct sorted data (potentially partial page).

        Verifies:
            - Last page data is sorted
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=5, sort_column="score", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        # Page 5 is the last page (400-499 = 100 rows)
        assert result["_pagination"]["page"] == 5
        assert len(result["tableData"]) == 100

        # Data should be sorted
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "asc"


# =============================================================================
# TestSortWithFilters
# =============================================================================


class TestSortWithFilters:
    """
    Sort-filter combination tests.

    Verifies that sorting and filtering work correctly together,
    with filters applied first, then sort applied to filtered data.
    """

    def test_sort_after_categorical_filter(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort applies correctly after categorical filter.

        Verifies:
            - Only filtered rows are returned
            - Filtered data is sorted
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                sort_column="score",
                sort_dir="desc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify filter applied (only category A)
        assert all(result["tableData"]["category"] == "A")

        # Verify sorted descending within filtered data
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "desc"
        assert result["_pagination"]["total_rows"] == 100  # 100 category A rows

    def test_sort_after_numeric_filter(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort applies correctly after numeric range filter.

        Verifies:
            - Only rows within range are returned
            - Filtered data is sorted
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 300.0},
                    {"field": "score", "type": "<=", "value": 450.0},
                ],
                sort_column="id",
                sort_dir="desc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify range filter applied
        scores = result["tableData"]["score"].tolist()
        assert all(300.0 <= s <= 450.0 for s in scores)

        # Verify sorted by id descending
        ids = result["tableData"]["id"].tolist()
        assert ids == sorted(ids, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "id"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_after_text_filter(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort applies correctly after text/regex filter.

        Verifies:
            - Only matching rows are returned
            - Filtered data is sorted
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "even"}
                ],
                sort_column="score",
                sort_dir="asc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify text filter applied (even ids only)
        ids = result["tableData"]["id"].tolist()
        assert all(i % 2 == 0 for i in ids)

        # Verify sorted ascending by score
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "asc"
        assert result["_pagination"]["total_rows"] == 250  # 250 even rows

    def test_sort_after_multiple_filters(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort applies correctly after multiple filters combined.

        Verifies:
            - All filters applied (AND logic)
            - Filtered data is sorted
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A", "B"]},
                    {"field": "score", "type": "<=", "value": 300.0},
                ],
                sort_column="category",
                sort_dir="desc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify both filters applied
        categories = result["tableData"]["category"].tolist()
        scores = result["tableData"]["score"].tolist()
        assert all(c in ["A", "B"] for c in categories)
        assert all(s <= 300.0 for s in scores)

        # Verify sorted by category descending (B before A)
        assert categories == sorted(categories, reverse=True)

        # Verify metadata
        assert result["_pagination"]["sort_column"] == "category"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_filter_then_sort_then_paginate(
        self, sort_table_component, state_manager_sort
    ):
        """
        Filter, sort, and pagination all work together correctly.

        Verifies:
            - Filter reduces total rows
            - Sort orders filtered data
            - Pagination shows correct page of filtered+sorted data
            - sort_column and sort_dir metadata are correct
        """
        state = state_manager_sort.get_state_for_vue()

        # Filter to category A (100 rows), sort by score desc, get page 2
        state.update(
            create_sort_state(
                page=2,
                page_size=25,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                sort_column="score",
                sort_dir="desc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # Verify pagination metadata
        assert result["_pagination"]["total_rows"] == 100
        assert result["_pagination"]["total_pages"] == 4  # 100 rows / 25 page_size
        assert result["_pagination"]["page"] == 2

        # Verify filter applied
        assert all(result["tableData"]["category"] == "A")

        # Verify page 2 data is sorted descending
        scores = result["tableData"]["score"].tolist()
        assert scores == sorted(scores, reverse=True)
        assert len(scores) == 25  # Page size

        # Verify sort metadata
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "desc"


# =============================================================================
# TestSortEdgeCases
# =============================================================================


class TestSortEdgeCases:
    """
    Edge case tests for sorting behavior.

    Verifies graceful handling of empty results, single-row data,
    duplicate values, and invalid sort columns.
    """

    def test_sort_empty_result_no_error(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort on empty filtered result doesn't raise error.

        Verifies:
            - No exception raised
            - Empty DataFrame returned
            - sort_column and sort_dir metadata still present
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["Z"]}],
                sort_column="score",
                sort_dir="asc",
            )
        )

        # Should not raise
        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0
        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_single_row_result(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort on single-row result works correctly.

        Verifies:
            - Single row returned
            - sort_column and sort_dir metadata present
        """
        state = state_manager_sort.get_state_for_vue()
        # Filter to exactly one row (id=100 has score=150.0)
        state.update(
            create_sort_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 150.0},
                    {"field": "score", "type": "<=", "value": 150.0},
                ],
                sort_column="id",
                sort_dir="desc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 1
        assert len(result["tableData"]) == 1
        assert result["tableData"]["id"].iloc[0] == 100
        assert result["_pagination"]["sort_column"] == "id"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_all_same_values(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort on column where all filtered values are the same.

        Verifies:
            - Sort completes without error
            - All values are equal
            - sort_column and sort_dir metadata present
        """
        state = state_manager_sort.get_state_for_vue()
        # Filter to category A, then sort by category (all same value)
        state.update(
            create_sort_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                sort_column="category",
                sort_dir="asc",
            )
        )

        result = sort_table_component._prepare_vue_data(state)

        # All categories should be "A"
        categories = result["tableData"]["category"].tolist()
        assert all(c == "A" for c in categories)
        assert result["_pagination"]["sort_column"] == "category"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_with_invalid_column_graceful(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort on non-existent column raises appropriate error.

        Note: Polars raises ColumnNotFoundError for invalid columns.
        The component should propagate this error.
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(
                page=1,
                sort_column="nonexistent_column",
                sort_dir="asc",
            )
        )

        # Should raise an error for invalid column
        with pytest.raises(Exception):  # Polars ColumnNotFoundError
            sort_table_component._prepare_vue_data(state)


# =============================================================================
# TestSortColumnTypes
# =============================================================================


class TestSortColumnTypes:
    """
    Tests for sorting different column data types.

    Verifies correct sort behavior for float, integer, and
    integer-based categorical columns.
    """

    def test_sort_float_column_score(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort float column (score) correctly.

        Verifies:
            - Float values sorted numerically
            - sort_column and sort_dir metadata correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="score", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        scores = result["tableData"]["score"].tolist()
        # Verify numeric sort (0.0, 1.5, 3.0, ...)
        assert scores == sorted(scores)
        assert scores[0] == 0.0
        assert scores[1] == 1.5

        assert result["_pagination"]["sort_column"] == "score"
        assert result["_pagination"]["sort_dir"] == "asc"

    def test_sort_integer_column_id(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort integer column (id) correctly.

        Verifies:
            - Integer values sorted numerically
            - sort_column and sort_dir metadata correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="id", sort_dir="desc")
        )

        result = sort_table_component._prepare_vue_data(state)

        ids = result["tableData"]["id"].tolist()
        # Verify numeric sort descending (499, 498, 497, ...)
        assert ids == sorted(ids, reverse=True)
        assert ids[0] == 499

        assert result["_pagination"]["sort_column"] == "id"
        assert result["_pagination"]["sort_dir"] == "desc"

    def test_sort_integer_categorical_priority(
        self, sort_table_component, state_manager_sort
    ):
        """
        Sort integer column with few unique values (priority) correctly.

        Priority has values 1-5 cycling, treated as categorical but still
        sortable numerically.

        Verifies:
            - Integer values sorted numerically
            - sort_column and sort_dir metadata correct
        """
        state = state_manager_sort.get_state_for_vue()
        state.update(
            create_sort_state(page=1, sort_column="priority", sort_dir="asc")
        )

        result = sort_table_component._prepare_vue_data(state)

        priorities = result["tableData"]["priority"].tolist()
        # Verify numeric sort (1, 1, 1, ..., 2, 2, 2, ...)
        assert priorities == sorted(priorities)
        assert priorities[0] == 1

        assert result["_pagination"]["sort_column"] == "priority"
        assert result["_pagination"]["sort_dir"] == "asc"
