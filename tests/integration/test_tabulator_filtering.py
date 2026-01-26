"""
Tabulator Column Filter Integration Tests.

Tests the Table component's server-side column filtering functionality,
including categorical, numeric, and text filters with pagination interactions.

Filter Types Tested:
    - Categorical ("in"): Multi-select from unique values
    - Numeric (">=" / "<="): Range filters with min/max bounds
    - Text ("regex"): Regular expression pattern matching

Column Filter Structure:
    {"field": str, "type": str, "value": Any}

Test Categories:
    - TestColumnFilterCategorical: Categorical "in" filter tests
    - TestColumnFilterNumeric: Numeric range filter tests
    - TestColumnFilterText: Text/regex filter tests
    - TestColumnFilterMultiple: Combined filter scenarios
    - TestColumnFilterWithPagination: Filter-pagination interactions
    - TestColumnFilterMetadata: Column metadata verification
    - TestColumnFilterClear: Clear filter behavior
"""

from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from openms_insight import Table
from openms_insight.core.state import StateManager

# =============================================================================
# Mock Infrastructure (reused from test_tabulator.py)
# =============================================================================


class MockSessionState(dict):
    """Mock Streamlit session_state that behaves like a dict."""

    pass


def create_filter_state(
    page: int = 1,
    page_size: int = 100,
    column_filters: Optional[List[Dict[str, Any]]] = None,
    sort_column: Optional[str] = None,
    sort_dir: str = "asc",
    pagination_identifier: str = "test_filter_table_page",
) -> Dict[str, Any]:
    """
    Create pagination state dict with column filters.

    Args:
        page: Current page number
        page_size: Rows per page
        column_filters: List of column filter dicts
        sort_column: Column to sort by
        sort_dir: Sort direction ("asc" or "desc")
        pagination_identifier: Key for pagination state

    Returns:
        Dict with pagination state including column filters
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
def mock_streamlit_filter():
    """Mock Streamlit's session_state for filter testing."""
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def state_manager_filter(mock_streamlit_filter):
    """Create a StateManager with mocked session_state for filter tests."""
    return StateManager(session_key="test_filter_state")


@pytest.fixture
def filter_table_component(pagination_test_data, tmp_path):
    """
    Create a Table component configured for filter testing.

    Returns:
        Table component with 500-row test data
    """
    return Table(
        cache_id="test_filter_table",
        data=pagination_test_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="test_filter_table_page",
        index_field="id",
    )


# =============================================================================
# TestColumnFilterCategorical
# =============================================================================


class TestColumnFilterCategorical:
    """
    Categorical filter tests using the "in" filter type.

    Verifies multi-select categorical filtering with correct row filtering,
    OR logic within a single filter, and pagination metadata updates.
    """

    def test_categorical_single_value(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filter by single category value returns only matching rows.

        Verifies:
            - Only rows with category="A" are returned
            - 100 total rows (500 / 5 categories)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 100
        # All returned rows should have category="A"
        table_data = result["tableData"]
        assert all(table_data["category"] == "A")

    def test_categorical_multiple_values(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filter by multiple category values uses OR logic.

        Verifies:
            - Rows with category="A" OR category="B" are returned
            - 200 total rows (100 per category)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A", "B"]}
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 200
        table_data = result["tableData"]
        assert all(table_data["category"].isin(["A", "B"]))

    def test_categorical_all_values(self, filter_table_component, state_manager_filter):
        """
        Filter including all categories returns all data.

        Verifies:
            - All 500 rows returned when all categories selected
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {
                        "field": "category",
                        "type": "in",
                        "value": ["A", "B", "C", "D", "E"],
                    }
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 500

    def test_categorical_no_match(self, filter_table_component, state_manager_filter):
        """
        Filter by non-existent value returns empty result.

        Verifies:
            - Empty DataFrame returned
            - total_rows is 0
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["Z"]}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0

    def test_categorical_updates_pagination_metadata(
        self, filter_table_component, state_manager_filter
    ):
        """
        Categorical filter correctly updates pagination metadata.

        Verifies:
            - total_rows reflects filtered count
            - total_pages recalculates based on filtered rows
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                page_size=50,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # 100 rows matching "A", page_size=50 -> 2 pages
        assert result["_pagination"]["total_rows"] == 100
        assert result["_pagination"]["total_pages"] == 2
        assert result["_pagination"]["page_size"] == 50


# =============================================================================
# TestColumnFilterNumeric
# =============================================================================


class TestColumnFilterNumeric:
    """
    Numeric range filter tests using ">=" and "<=" filter types.

    Verifies range filtering with min/max bounds, inclusive boundaries,
    and correct row filtering for numeric columns.
    """

    def test_numeric_min_bound_only(self, filter_table_component, state_manager_filter):
        """
        Filter with >= only applies lower bound.

        Verifies:
            - Only rows with score >= 600.0 are returned
            - score ranges 0.0 to 748.5 (0*1.5 to 499*1.5)
            - score >= 600 means id >= 400 (600/1.5 = 400)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "score", "type": ">=", "value": 600.0}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Rows with score >= 600.0 (id >= 400): 400, 401, ..., 499 = 100 rows
        assert result["_pagination"]["total_rows"] == 100
        table_data = result["tableData"]
        assert all(table_data["score"] >= 600.0)

    def test_numeric_max_bound_only(self, filter_table_component, state_manager_filter):
        """
        Filter with <= only applies upper bound.

        Verifies:
            - Only rows with score <= 150.0 are returned
            - score <= 150 means id <= 100 (150/1.5 = 100)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "score", "type": "<=", "value": 150.0}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Rows with score <= 150.0 (id <= 100): 0, 1, ..., 100 = 101 rows
        assert result["_pagination"]["total_rows"] == 101
        table_data = result["tableData"]
        assert all(table_data["score"] <= 150.0)

    def test_numeric_range_both_bounds(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filter with >= and <= creates a range.

        Verifies:
            - Only rows within range are returned
            - Both bounds are combined with AND logic
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 150.0},
                    {"field": "score", "type": "<=", "value": 300.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Rows with 150.0 <= score <= 300.0
        # id 100 (score=150) to id 200 (score=300) = 101 rows
        assert result["_pagination"]["total_rows"] == 101
        table_data = result["tableData"]
        assert all((table_data["score"] >= 150.0) & (table_data["score"] <= 300.0))

    def test_numeric_range_no_match(self, filter_table_component, state_manager_filter):
        """
        Range that excludes all rows returns empty result.

        Verifies:
            - Empty DataFrame when min > max
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 1000.0},
                    {"field": "score", "type": "<=", "value": 2000.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0

    def test_numeric_at_boundary(self, filter_table_component, state_manager_filter):
        """
        Values exactly at boundaries are included (inclusive).

        Verifies:
            - Boundary values are included in the result
            - >= and <= are both inclusive
        """
        state = state_manager_filter.get_state_for_vue()
        # Filter for exactly score=150.0 (id=100)
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 150.0},
                    {"field": "score", "type": "<=", "value": 150.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 1
        table_data = result["tableData"]
        assert table_data["score"].iloc[0] == 150.0
        assert table_data["id"].iloc[0] == 100

    def test_numeric_updates_pagination_metadata(
        self, filter_table_component, state_manager_filter
    ):
        """
        Numeric filter correctly updates pagination metadata.

        Verifies:
            - total_rows reflects filtered count
            - total_pages recalculates
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                page_size=25,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 600.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # 100 rows matching >= 600, page_size=25 -> 4 pages
        assert result["_pagination"]["total_rows"] == 100
        assert result["_pagination"]["total_pages"] == 4


# =============================================================================
# TestColumnFilterText
# =============================================================================


class TestColumnFilterText:
    """
    Text/regex filter tests using the "regex" filter type.

    Verifies pattern matching, case sensitivity, and edge cases
    for text column filtering.
    """

    def test_text_simple_pattern(self, filter_table_component, state_manager_filter):
        """
        Simple substring pattern matches correctly.

        Verifies:
            - Pattern "even" matches rows with "even" in description
            - Rows with even ids have "even" in description
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "even"}
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # 250 rows have even ids (0, 2, 4, ..., 498)
        assert result["_pagination"]["total_rows"] == 250
        table_data = result["tableData"]
        assert all(table_data["id"] % 2 == 0)

    def test_text_regex_pattern(self, filter_table_component, state_manager_filter):
        """
        Regex with special characters works correctly.

        Verifies:
            - Pattern "row \\d{1}$" matches single-digit row numbers (0-9)
        """
        state = state_manager_filter.get_state_for_vue()
        # Match "row X" where X is a single digit at end of text
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "row [0-9] with"}
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Rows 0-9 match "row X with" where X is single digit
        assert result["_pagination"]["total_rows"] == 10
        table_data = result["tableData"]
        assert all(table_data["id"] < 10)

    def test_text_case_sensitive(self, filter_table_component, state_manager_filter):
        """
        Text search is case-sensitive by default.

        Verifies:
            - "EVEN" (uppercase) doesn't match "even" (lowercase)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "EVEN"}
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # No matches - "EVEN" not in description (only "even")
        assert result["_pagination"]["total_rows"] == 0

    def test_text_no_match(self, filter_table_component, state_manager_filter):
        """
        Pattern that matches nothing returns empty result.

        Verifies:
            - Empty DataFrame returned
            - total_rows is 0
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {
                        "field": "description",
                        "type": "regex",
                        "value": "nonexistent_pattern_xyz",
                    }
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0

    def test_text_updates_pagination_metadata(
        self, filter_table_component, state_manager_filter
    ):
        """
        Text filter correctly updates pagination metadata.

        Verifies:
            - total_rows reflects filtered count
            - total_pages recalculates
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                page_size=50,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "odd"}
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # 250 rows have odd ids (1, 3, 5, ..., 499), page_size=50 -> 5 pages
        assert result["_pagination"]["total_rows"] == 250
        assert result["_pagination"]["total_pages"] == 5

    def test_text_invalid_regex_returns_empty(
        self, filter_table_component, state_manager_filter
    ):
        """
        Invalid regex pattern returns empty result instead of raising error.

        Verifies:
            - Malformed regex (unclosed bracket) doesn't raise exception
            - Returns empty DataFrame with total_rows=0
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "description", "type": "regex", "value": "[invalid"}
                ],
            )
        )

        # Should not raise - returns empty result instead
        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0


# =============================================================================
# TestColumnFilterMultiple
# =============================================================================


class TestColumnFilterMultiple:
    """
    Combined filter scenarios testing AND logic across multiple filters.

    Verifies that multiple filters are applied together with AND logic,
    both on the same column and across different columns.
    """

    def test_multiple_filters_same_column(
        self, filter_table_component, state_manager_filter
    ):
        """
        Two filters on same column (score range) use AND logic.

        Verifies:
            - Range filter works (>= AND <=)
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "score", "type": ">=", "value": 100.0},
                    {"field": "score", "type": "<=", "value": 200.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # id 67 (100.5) to id 133 (199.5) - need to check exact boundary
        # score=100 -> id=66.67, score=200 -> id=133.33
        # So ids 67-133 inclusive, but need to verify actual count
        table_data = result["tableData"]
        assert all((table_data["score"] >= 100.0) & (table_data["score"] <= 200.0))
        # Count should be rows where 100 <= score <= 200
        # That's ids where 100/1.5 <= id <= 200/1.5 -> 66.67 <= id <= 133.33
        # So ids 67 to 133 = 67 rows
        assert result["_pagination"]["total_rows"] == 67

    def test_multiple_filters_different_columns(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filters on different columns use AND logic.

        Verifies:
            - Category="A" AND score >= 300
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A"]},
                    {"field": "score", "type": ">=", "value": 300.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Category A: ids 0, 5, 10, 15, ... (every 5th)
        # Score >= 300: id >= 200 (300/1.5 = 200)
        # Both: 200, 205, 210, ..., 495 = 60 rows
        table_data = result["tableData"]
        assert all(table_data["category"] == "A")
        assert all(table_data["score"] >= 300.0)
        assert result["_pagination"]["total_rows"] == 60

    def test_three_filter_combination(
        self, filter_table_component, state_manager_filter
    ):
        """
        Three filters combined (category + score + text).

        Verifies:
            - All three filter types applied together
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A", "B"]},
                    {"field": "score", "type": ">=", "value": 0.0},
                    {"field": "score", "type": "<=", "value": 150.0},
                    {"field": "description", "type": "regex", "value": "even"},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Category A or B: ids 0,1, 5,6, 10,11, ... (A=0,5,10..., B=1,6,11...)
        # Score <= 150: id <= 100
        # Even id: id % 2 == 0
        # Combined: even ids, category A or B, id <= 100
        # That's: 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 (category A, even)
        #     plus: 6, 16, 26, 36, 46, 56, 66, 76, 86, 96 (category B, even)
        # Wait, B is at 1,6,11,16... so even Bs are 6, 16, 26, ...
        table_data = result["tableData"]
        assert all(table_data["category"].isin(["A", "B"]))
        assert all(table_data["score"] <= 150.0)
        assert all(table_data["id"] % 2 == 0)

    def test_progressive_filtering(self, filter_table_component, state_manager_filter):
        """
        Adding filters progressively reduces rows.

        Verifies:
            - Each additional filter reduces or maintains row count
        """
        # No filters
        state = state_manager_filter.get_state_for_vue()
        state.update(create_filter_state(page=1, column_filters=[]))

        result0 = filter_table_component._prepare_vue_data(state)
        count0 = result0["_pagination"]["total_rows"]
        assert count0 == 500

        # Add category filter
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A", "B"]}
                ],
            )
        )
        result1 = filter_table_component._prepare_vue_data(state)
        count1 = result1["_pagination"]["total_rows"]
        assert count1 == 200  # 2 of 5 categories
        assert count1 < count0

        # Add score filter
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A", "B"]},
                    {"field": "score", "type": "<=", "value": 300.0},
                ],
            )
        )
        result2 = filter_table_component._prepare_vue_data(state)
        count2 = result2["_pagination"]["total_rows"]
        assert count2 < count1

    def test_multiple_filters_no_match(
        self, filter_table_component, state_manager_filter
    ):
        """
        Combined filters that exclude all rows return empty.

        Verifies:
            - Empty DataFrame when filters have no intersection
        """
        state = state_manager_filter.get_state_for_vue()
        # Category A AND score > 750 (max score is 748.5)
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A"]},
                    {"field": "score", "type": ">=", "value": 750.0},
                ],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 0
        assert len(result["tableData"]) == 0


# =============================================================================
# TestColumnFilterWithPagination
# =============================================================================


class TestColumnFilterWithPagination:
    """
    Filter-pagination interaction tests.

    Verifies that column filters interact correctly with pagination,
    including page resets, filter persistence, and sort combinations.
    """

    def test_filter_returns_page_one_data(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filtered results correctly return first page data.

        Verifies:
            - First page of filtered data is returned
            - Data is from the filtered set
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                page_size=50,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        assert len(result["tableData"]) == 50
        assert result["_pagination"]["page"] == 1
        # First 50 rows with category A (ids 0, 5, 10, ..., 245)
        table_data = result["tableData"]
        assert all(table_data["category"] == "A")

    def test_filter_persistence_across_pages(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filter stays applied when navigating pages.

        Verifies:
            - Page 2 still has filter applied
            - Data on page 2 matches filter
        """
        state = state_manager_filter.get_state_for_vue()

        # Page 1 with filter
        state.update(
            create_filter_state(
                page=1,
                page_size=50,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result1 = filter_table_component._prepare_vue_data(state)
        assert all(result1["tableData"]["category"] == "A")

        # Navigate to page 2
        state.update(
            create_filter_state(
                page=2,
                page_size=50,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result2 = filter_table_component._prepare_vue_data(state)

        # Still filtered to category A
        assert all(result2["tableData"]["category"] == "A")
        assert result2["_pagination"]["page"] == 2
        # Different data than page 1
        assert result1["tableData"]["id"].iloc[0] != result2["tableData"]["id"].iloc[0]

    def test_filter_with_sort(self, filter_table_component, state_manager_filter):
        """
        Filter and sort work together.

        Verifies:
            - Filter applied first, then sorted
        """
        state = state_manager_filter.get_state_for_vue()
        state.update(
            create_filter_state(
                page=1,
                page_size=100,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                sort_column="score",
                sort_dir="desc",
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        table_data = result["tableData"]
        # All rows are category A
        assert all(table_data["category"] == "A")
        # Sorted descending by score
        scores = table_data["score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_total_pages_recalculated(
        self, filter_table_component, state_manager_filter
    ):
        """
        Filter changes total_pages based on filtered row count.

        Verifies:
            - total_pages reflects filtered data size
        """
        state = state_manager_filter.get_state_for_vue()

        # Without filter: 500 rows, page_size=100 -> 5 pages
        state.update(create_filter_state(page=1, page_size=100, column_filters=[]))
        result_unfiltered = filter_table_component._prepare_vue_data(state)
        assert result_unfiltered["_pagination"]["total_pages"] == 5

        # With filter: 100 rows, page_size=100 -> 1 page
        state.update(
            create_filter_state(
                page=1,
                page_size=100,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result_filtered = filter_table_component._prepare_vue_data(state)
        assert result_filtered["_pagination"]["total_pages"] == 1

    def test_page_clamp_after_filter(
        self, filter_table_component, state_manager_filter
    ):
        """
        Page number clamped to valid range after filter reduces pages.

        Verifies:
            - Requesting page 5 when only 1 page exists returns page 1
        """
        state = state_manager_filter.get_state_for_vue()
        # Request page 5, but filter reduces to 1 page (100 rows, page_size=100)
        state.update(
            create_filter_state(
                page=5,
                page_size=100,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )

        result = filter_table_component._prepare_vue_data(state)

        # Page should be clamped to 1 (max valid page)
        assert result["_pagination"]["page"] == 1
        assert result["_pagination"]["total_pages"] == 1


# =============================================================================
# TestColumnFilterMetadata
# =============================================================================


class TestColumnFilterMetadata:
    """
    Column metadata verification tests.

    Verifies that column metadata is correctly computed during preprocessing
    and passed to Vue for filter dialogs.
    """

    def test_numeric_column_has_min_max(
        self, filter_table_component, state_manager_filter
    ):
        """
        Numeric columns have min/max in metadata.

        Verifies:
            - Score column has min and max values
        """
        # Access preprocessed metadata
        column_metadata = filter_table_component._preprocessed_data.get(
            "column_metadata", {}
        )

        assert "score" in column_metadata
        score_meta = column_metadata["score"]
        assert score_meta["type"] == "numeric"
        assert "min" in score_meta
        assert "max" in score_meta
        assert score_meta["min"] == 0.0
        assert score_meta["max"] == 748.5  # 499 * 1.5

    def test_categorical_column_has_unique_values(
        self, filter_table_component, state_manager_filter
    ):
        """
        Categorical columns have unique_values list.

        Verifies:
            - Category column has unique_values
        """
        column_metadata = filter_table_component._preprocessed_data.get(
            "column_metadata", {}
        )

        assert "category" in column_metadata
        category_meta = column_metadata["category"]
        assert category_meta["type"] == "categorical"
        assert "unique_values" in category_meta
        assert set(category_meta["unique_values"]) == {"A", "B", "C", "D", "E"}

    def test_numeric_few_unique_becomes_categorical(
        self, filter_table_component, state_manager_filter
    ):
        """
        Numeric column with few unique values is treated as categorical.

        Verifies:
            - Priority column (5 unique values) is categorical
        """
        column_metadata = filter_table_component._preprocessed_data.get(
            "column_metadata", {}
        )

        assert "priority" in column_metadata
        priority_meta = column_metadata["priority"]
        # With only 5 unique values (1-5), should be categorical
        assert priority_meta["type"] == "categorical"
        assert "unique_values" in priority_meta
        assert set(priority_meta["unique_values"]) == {1, 2, 3, 4, 5}

    def test_text_column_has_type_text(
        self, filter_table_component, state_manager_filter
    ):
        """
        Text column with many unique values has type "text".

        Verifies:
            - Description column (500 unique) is type "text"
        """
        column_metadata = filter_table_component._preprocessed_data.get(
            "column_metadata", {}
        )

        assert "description" in column_metadata
        description_meta = column_metadata["description"]
        # 500 unique values -> treated as text, not categorical
        assert description_meta["type"] == "text"

    def test_metadata_in_component_args(
        self, filter_table_component, state_manager_filter
    ):
        """
        Column metadata is passed to Vue in component args.

        Verifies:
            - columnMetadata key exists in args
        """
        args = filter_table_component._get_component_args()

        assert "columnMetadata" in args
        assert isinstance(args["columnMetadata"], dict)
        assert "score" in args["columnMetadata"]
        assert "category" in args["columnMetadata"]


# =============================================================================
# TestColumnFilterClear
# =============================================================================


class TestColumnFilterClear:
    """
    Clear filter behavior tests.

    Verifies that removing filters correctly restores full data
    and pagination metadata.
    """

    def test_clear_all_filters(self, filter_table_component, state_manager_filter):
        """
        Removing all column_filters returns all rows.

        Verifies:
            - Empty column_filters list returns full dataset
        """
        state = state_manager_filter.get_state_for_vue()

        # First apply filter
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result_filtered = filter_table_component._prepare_vue_data(state)
        assert result_filtered["_pagination"]["total_rows"] == 100

        # Clear filters
        state.update(create_filter_state(page=1, column_filters=[]))
        result_cleared = filter_table_component._prepare_vue_data(state)

        assert result_cleared["_pagination"]["total_rows"] == 500

    def test_clear_single_filter(self, filter_table_component, state_manager_filter):
        """
        Removing one of multiple filters keeps other filters active.

        Verifies:
            - Partial filter removal works correctly
        """
        state = state_manager_filter.get_state_for_vue()

        # Apply two filters
        state.update(
            create_filter_state(
                page=1,
                column_filters=[
                    {"field": "category", "type": "in", "value": ["A"]},
                    {"field": "score", "type": ">=", "value": 300.0},
                ],
            )
        )
        result_two_filters = filter_table_component._prepare_vue_data(state)
        count_two_filters = result_two_filters["_pagination"]["total_rows"]

        # Remove score filter, keep category
        state.update(
            create_filter_state(
                page=1,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result_one_filter = filter_table_component._prepare_vue_data(state)
        count_one_filter = result_one_filter["_pagination"]["total_rows"]

        # Should have more rows with one filter
        assert count_one_filter > count_two_filters
        assert count_one_filter == 100  # All category A

    def test_clear_restores_pagination(
        self, filter_table_component, state_manager_filter
    ):
        """
        Clearing filters restores full pagination metadata.

        Verifies:
            - total_rows and total_pages restored to original values
        """
        state = state_manager_filter.get_state_for_vue()

        # Apply restrictive filter
        state.update(
            create_filter_state(
                page=1,
                page_size=50,
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
            )
        )
        result_filtered = filter_table_component._prepare_vue_data(state)
        assert result_filtered["_pagination"]["total_rows"] == 100
        assert result_filtered["_pagination"]["total_pages"] == 2

        # Clear filters
        state.update(create_filter_state(page=1, page_size=50, column_filters=[]))
        result_cleared = filter_table_component._prepare_vue_data(state)

        assert result_cleared["_pagination"]["total_rows"] == 500
        assert result_cleared["_pagination"]["total_pages"] == 10
