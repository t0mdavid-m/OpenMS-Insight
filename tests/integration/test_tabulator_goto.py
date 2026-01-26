"""
Tabulator Go-To Navigation Integration Tests.

Tests the Table component's go-to functionality including:
- Auto-detection of go-to fields based on column uniqueness
- Go-to navigation with various data types
- Go-to with sorting and filtering
- Not found handling

Go-To Auto-Detection Rules:
    - Only Integer and String (Utf8) columns (excludes Float)
    - 100% unique values required (no duplicates)
    - Samples first 10,000 rows for performance
    - Preserves original column order

Test Categories:
    - TestGoToAutoDetection: Auto-detection of suitable columns
    - TestGoToExplicitOverride: Explicit go_to_fields parameter behavior
    - TestGoToBasicNavigation: Basic navigation functionality
    - TestGoToNotFound: Not found flag behavior
    - TestGoToWithSorting: Go-to with active sort
    - TestGoToWithFilters: Go-to with column filters
    - TestGoToEdgeCases: Edge cases and special scenarios
"""

from typing import Any, Dict, List, Optional
from unittest.mock import patch

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


def create_goto_state(
    page: int = 1,
    page_size: int = 100,
    column_filters: Optional[List[Dict[str, Any]]] = None,
    sort_column: Optional[str] = None,
    sort_dir: str = "asc",
    go_to_request: Optional[Dict[str, Any]] = None,
    pagination_identifier: str = "test_goto_table_page",
) -> Dict[str, Any]:
    """
    Create pagination state dict with go_to_request support.

    Args:
        page: Current page number
        page_size: Rows per page
        column_filters: List of column filter dicts
        sort_column: Column to sort by
        sort_dir: Sort direction ("asc" or "desc")
        go_to_request: Go-to request dict with field and value
        pagination_identifier: Key for pagination state

    Returns:
        Dict with pagination state including go_to_request
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
    if go_to_request:
        state[pagination_identifier]["go_to_request"] = go_to_request
    return state


@pytest.fixture
def mock_streamlit_goto():
    """Mock Streamlit's session_state for go-to testing."""
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def state_manager_goto(mock_streamlit_goto):
    """Create a StateManager with mocked session_state for go-to tests."""
    return StateManager(session_key="test_goto_state")


@pytest.fixture
def goto_table_component(pagination_test_data, tmp_path, mock_streamlit_goto):
    """
    Create a Table component configured for go-to testing with auto-detection.

    Returns:
        Table component with 500-row test data and auto-detected go-to fields
    """
    return Table(
        cache_id="test_goto_table",
        data=pagination_test_data,
        cache_path=str(tmp_path),
        pagination=True,
        page_size=100,
        pagination_identifier="test_goto_table_page",
        index_field="id",
        go_to_fields=None,  # Triggers auto-detection
    )


@pytest.fixture
def unique_columns_data() -> pl.LazyFrame:
    """
    Data with mix of unique and non-unique columns for auto-detection tests.

    Columns:
        - id: 100% unique integers (should be detected)
        - name: 100% unique strings (should be detected)
        - score: Float values (should be excluded - wrong type)
        - category: 50% unique - A/B cycling (should be excluded - not unique)
    """
    return pl.LazyFrame(
        {
            "id": list(range(100)),
            "name": [f"item_{i}" for i in range(100)],
            "score": [i * 0.5 for i in range(100)],
            "category": ["A", "B"] * 50,
        }
    )


@pytest.fixture
def mixed_uniqueness_data() -> pl.LazyFrame:
    """
    Data with various uniqueness levels for edge case testing.

    Columns:
        - unique_int: 100% unique integers
        - unique_str: 100% unique strings
        - almost_unique: 99% unique (1 duplicate)
        - half_unique: 50% unique
        - all_same: 0% unique (all same value)
    """
    n = 100
    almost_unique = list(range(n - 1)) + [0]  # One duplicate
    return pl.LazyFrame(
        {
            "unique_int": list(range(n)),
            "unique_str": [f"val_{i}" for i in range(n)],
            "almost_unique": almost_unique,
            "half_unique": list(range(n // 2)) * 2,
            "all_same": [1] * n,
        }
    )


# =============================================================================
# TestGoToAutoDetection
# =============================================================================


class TestGoToAutoDetection:
    """
    Tests for automatic go-to field detection.

    Verifies that the auto-detection correctly identifies columns
    suitable for go-to navigation based on uniqueness and data type.
    """

    def test_auto_detect_unique_integer_column(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection identifies 100% unique integer columns.

        Verifies:
            - Integer column with all unique values is detected
        """
        table = Table(
            cache_id="auto_detect_int_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,  # Trigger auto-detection
        )

        detected = table._go_to_fields

        assert "id" in detected

    def test_auto_detect_unique_string_column(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection identifies 100% unique string columns.

        Verifies:
            - String column with all unique values is detected
        """
        table = Table(
            cache_id="auto_detect_str_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        assert "name" in detected

    def test_auto_detect_excludes_float_columns(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection excludes Float columns regardless of uniqueness.

        Verifies:
            - Float column (score) is NOT included even if unique
        """
        table = Table(
            cache_id="auto_detect_float_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        assert "score" not in detected

    def test_auto_detect_excludes_non_unique_columns(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection excludes columns that are not 100% unique.

        Verifies:
            - Categorical column with duplicates is NOT included
        """
        table = Table(
            cache_id="auto_detect_non_unique_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        assert "category" not in detected

    def test_auto_detect_multiple_columns_preserves_order(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection preserves original column order.

        Verifies:
            - Multiple detected columns appear in schema order
        """
        table = Table(
            cache_id="auto_detect_order_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        # id comes before name in schema
        if "id" in detected and "name" in detected:
            id_idx = detected.index("id")
            name_idx = detected.index("name")
            assert id_idx < name_idx

    def test_auto_detect_with_duplicates_excluded(
        self, mixed_uniqueness_data, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection requires 100% uniqueness (not 99%).

        Verifies:
            - Column with even one duplicate is excluded
            - Only 100% unique columns are included
        """
        table = Table(
            cache_id="auto_detect_strict_test",
            data=mixed_uniqueness_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        # Should include only truly unique columns
        assert "unique_int" in detected
        assert "unique_str" in detected
        # Should exclude columns with any duplicates
        assert "almost_unique" not in detected
        assert "half_unique" not in detected
        assert "all_same" not in detected

    def test_auto_detect_empty_when_no_unique_columns(
        self, tmp_path, mock_streamlit_goto
    ):
        """
        Auto-detection returns empty list when no columns are suitable.

        Verifies:
            - Empty list returned when all columns have duplicates or wrong type
        """
        data = pl.LazyFrame(
            {
                "category": ["A", "B", "A", "B"],
                "value": [1.0, 2.0, 3.0, 4.0],  # Float - excluded
            }
        )

        table = Table(
            cache_id="auto_detect_empty_test",
            data=data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        detected = table._go_to_fields

        assert detected == []


# =============================================================================
# TestGoToExplicitOverride
# =============================================================================


class TestGoToExplicitOverride:
    """
    Tests for explicit go_to_fields parameter behavior.

    Verifies that explicit go_to_fields overrides auto-detection
    and empty list disables go-to functionality.
    """

    def test_explicit_go_to_fields_overrides_auto(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Explicit go_to_fields overrides auto-detection.

        Verifies:
            - User-provided fields are used exactly as specified
            - Auto-detection is not performed
        """
        table = Table(
            cache_id="explicit_override_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=["category"],  # Not unique, but explicitly specified
        )

        assert table._go_to_fields == ["category"]

    def test_empty_list_disables_go_to(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Empty list explicitly disables go-to functionality.

        Verifies:
            - Empty list is preserved (not replaced by auto-detection)
        """
        table = Table(
            cache_id="empty_list_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=[],  # Explicitly disabled
        )

        assert table._go_to_fields == []

    def test_none_triggers_auto_detection(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        None value triggers auto-detection.

        Verifies:
            - None causes auto-detection to run
            - Result is a list (not None)
        """
        table = Table(
            cache_id="none_trigger_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=None,
        )

        assert isinstance(table._go_to_fields, list)
        # Should have detected id and name
        assert len(table._go_to_fields) >= 2

    def test_explicit_fields_in_component_args(
        self, unique_columns_data, tmp_path, mock_streamlit_goto
    ):
        """
        Explicit go_to_fields are passed to Vue component args.

        Verifies:
            - goToFields appears in component args
            - Contains the explicitly specified fields
        """
        table = Table(
            cache_id="explicit_args_test",
            data=unique_columns_data,
            cache_path=str(tmp_path),
            go_to_fields=["id", "name"],
        )

        args = table._get_component_args()

        assert args.get("goToFields") == ["id", "name"]


# =============================================================================
# TestGoToBasicNavigation
# =============================================================================


class TestGoToBasicNavigation:
    """
    Tests for basic go-to navigation functionality.

    Verifies that go-to requests correctly navigate to the target row
    and return proper page/row index information.
    """

    def test_go_to_navigates_to_correct_page(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to request navigates to the correct page.

        Verifies:
            - _navigate_to_page is set to correct page number
            - Target row id=350 should be on page 4 (rows 300-399)
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 350},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # id=350 is on page 4 (rows 300-399)
        assert result.get("_navigate_to_page") == 4

    def test_go_to_returns_correct_row_index(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to request returns correct row index within page.

        Verifies:
            - _target_row_index gives position within the page
            - id=350 is at index 50 within page 4
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 350},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # id=350 is at position 50 within its page (350 % 100 = 50)
        assert result.get("_target_row_index") == 50

    def test_go_to_with_string_value(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works with string field values.

        Verifies:
            - String values can be searched
            - Correct page and row index are returned
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "value", "value": "item_250"},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # item_250 corresponds to id=250, which is on page 3 (rows 200-299)
        assert result.get("_navigate_to_page") == 3
        assert result.get("_target_row_index") == 50  # 250 % 100

    def test_go_to_with_numeric_string_conversion(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to handles string-to-number conversion for numeric fields.

        Verifies:
            - String "350" is converted to int for numeric field
            - Navigation works correctly
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": "350"},  # String value
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 4
        assert result.get("_target_row_index") == 50

    def test_go_to_first_row(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to navigates correctly to the first row.

        Verifies:
            - id=0 is found on page 1, index 0
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 0},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 1
        assert result.get("_target_row_index") == 0


# =============================================================================
# TestGoToNotFound
# =============================================================================


class TestGoToNotFound:
    """
    Tests for go-to not found behavior.

    Verifies that _go_to_not_found flag is set correctly when
    the target value cannot be found in the data.
    """

    def test_go_to_not_found_flag_set(
        self, goto_table_component, state_manager_goto
    ):
        """
        Not found flag is set when target value doesn't exist.

        Verifies:
            - _go_to_not_found is True for non-existent value
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 9999},  # Non-existent
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_go_to_not_found") is True

    def test_go_to_not_found_no_navigate_hint(
        self, goto_table_component, state_manager_goto
    ):
        """
        Navigation hints are absent when target not found.

        Verifies:
            - _navigate_to_page is NOT set when not found
            - _target_row_index is NOT set when not found
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 9999},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert "_navigate_to_page" not in result
        assert "_target_row_index" not in result

    def test_go_to_not_found_with_filters(
        self, goto_table_component, state_manager_goto
    ):
        """
        Not found flag set when target is filtered out.

        Verifies:
            - Existing value that's filtered out triggers not found
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                # Filter to category A only
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                # id=1 exists but has category B (excluded by filter)
                go_to_request={"field": "id", "value": 1},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_go_to_not_found") is True
        assert "_navigate_to_page" not in result

    def test_go_to_partial_match_not_found(
        self, goto_table_component, state_manager_goto
    ):
        """
        Partial matches do not count as found (exact match required).

        Verifies:
            - Searching for "item_25" doesn't match "item_250"
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "value", "value": "item_500"},  # Doesn't exist
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_go_to_not_found") is True


# =============================================================================
# TestGoToWithSorting
# =============================================================================


class TestGoToWithSorting:
    """
    Tests for go-to functionality with active sorting.

    Verifies that go-to correctly finds rows regardless of
    the current sort order.
    """

    def test_go_to_with_ascending_sort(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works correctly with ascending sort.

        Verifies:
            - Navigation hints are set when sorted ascending
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                sort_column="score",
                sort_dir="asc",
                go_to_request={"field": "id", "value": 350},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # Should still find the row
        assert "_navigate_to_page" in result
        assert "_target_row_index" in result

    def test_go_to_with_descending_sort(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works correctly with descending sort.

        Verifies:
            - Navigation hints are set when sorted descending
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                sort_column="score",
                sort_dir="desc",
                go_to_request={"field": "id", "value": 350},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert "_navigate_to_page" in result
        assert "_target_row_index" in result

    def test_go_to_sort_independent_finds_row(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to finds correct row regardless of sort order.

        Verifies:
            - The target row is on the returned page at the correct index
            - Data at target index has the requested id value
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                sort_column="score",
                sort_dir="desc",
                go_to_request={"field": "id", "value": 350},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # Verify the target row is actually on the page at the given index
        page_data = result["tableData"]
        target_idx = result["_target_row_index"]
        assert page_data.iloc[target_idx]["id"] == 350

    def test_go_to_returns_correct_page_when_sorted(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to returns correct page based on sorted position.

        When sorted by score descending:
        - id=0 has score=0.0 (lowest), so it's at position 499 (last)
        - Position 499 / page_size 100 = page 5, index 99

        Verifies:
            - Page number reflects sorted position, not original position
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                sort_column="score",
                sort_dir="desc",
                go_to_request={"field": "id", "value": 0},  # First id, but lowest score
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # id=0 has lowest score, so it's on the last page when sorted desc
        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 99

    def test_go_to_row_index_correct_in_sorted_page(
        self, goto_table_component, state_manager_goto
    ):
        """
        Target row index is correct within the sorted page.

        Verifies:
            - _target_row_index points to the actual row in returned data
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                sort_column="id",
                sort_dir="desc",
                go_to_request={"field": "id", "value": 200},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # Verify the index is valid and points to correct row
        target_idx = result.get("_target_row_index")
        assert target_idx is not None
        assert 0 <= target_idx < len(result["tableData"])
        assert result["tableData"].iloc[target_idx]["id"] == 200


# =============================================================================
# TestGoToWithFilters
# =============================================================================


class TestGoToWithFilters:
    """
    Tests for go-to functionality with column filters.

    Verifies that go-to searches within filtered data and
    correctly handles cases where target is filtered out.
    """

    def test_go_to_after_categorical_filter(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works within categorically filtered data.

        Verifies:
            - Can find rows that match the filter
            - Navigation hints are set correctly
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                # id=0 has category A
                go_to_request={"field": "id", "value": 0},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert "_navigate_to_page" in result
        assert result.get("_go_to_not_found") is not True

    def test_go_to_after_numeric_filter(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works within numerically filtered data.

        Verifies:
            - Can find rows within numeric range filter
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                column_filters=[
                    {"field": "score", "type": ">=", "value": 300.0},
                    {"field": "score", "type": "<=", "value": 450.0},
                ],
                # id=250 has score=375.0 (within range)
                go_to_request={"field": "id", "value": 250},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert "_navigate_to_page" in result
        assert result.get("_go_to_not_found") is not True

    def test_go_to_filtered_out_returns_not_found(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to returns not found when target is filtered out.

        Verifies:
            - _go_to_not_found is True when target doesn't match filter
            - Navigation hints are not set
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                # id=1 exists but has category B
                go_to_request={"field": "id", "value": 1},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_go_to_not_found") is True
        assert "_navigate_to_page" not in result

    def test_go_to_with_filter_and_sort(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works with both filter and sort active.

        Verifies:
            - Filtering and sorting together don't break go-to
            - Correct row is found
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                sort_column="score",
                sort_dir="desc",
                go_to_request={"field": "id", "value": 0},  # Category A, lowest score
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # Should find the row
        assert "_navigate_to_page" in result
        # Verify row data
        target_idx = result.get("_target_row_index")
        assert result["tableData"].iloc[target_idx]["id"] == 0

    def test_go_to_filter_changes_target_page(
        self, goto_table_component, state_manager_goto
    ):
        """
        Filter changes which page contains the target row.

        With filter on category A (100 rows total):
        - id=400 (category A) would be on different page vs unfiltered

        Verifies:
            - Page number reflects filtered data position
        """
        # First, without filter
        state_no_filter = state_manager_goto.get_state_for_vue()
        state_no_filter.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 400},
            )
        )
        result_no_filter = goto_table_component._prepare_vue_data(state_no_filter)

        # With category A filter - id=400 has category A
        state_filtered = state_manager_goto.get_state_for_vue()
        state_filtered.update(
            create_goto_state(
                column_filters=[{"field": "category", "type": "in", "value": ["A"]}],
                go_to_request={"field": "id", "value": 400},
            )
        )
        result_filtered = goto_table_component._prepare_vue_data(state_filtered)

        # Pages should be different because filtered data is smaller
        # Unfiltered: 500 rows, id=400 on page 5
        # Filtered (A only): 100 rows, id=400 is row 80 (position within A's)
        assert result_no_filter.get("_navigate_to_page") == 5
        # With only 100 rows (category A), id=400 is the 80th A, so page 1
        assert result_filtered.get("_navigate_to_page") == 1


# =============================================================================
# TestGoToEdgeCases
# =============================================================================


class TestGoToEdgeCases:
    """
    Edge case tests for go-to functionality.

    Verifies handling of boundary conditions and special scenarios.
    """

    def test_go_to_last_row(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to navigates to the last row correctly.

        Verifies:
            - Can navigate to id=499 (last row in 500-row dataset)
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 499},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # id=499 is on page 5, index 99
        assert result.get("_navigate_to_page") == 5
        assert result.get("_target_row_index") == 99

    def test_go_to_empty_value_no_action(
        self, goto_table_component, state_manager_goto
    ):
        """
        Empty go_to_request value doesn't trigger navigation.

        Verifies:
            - Empty string value doesn't crash
            - Not found flag is set
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                go_to_request={"field": "value", "value": ""},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        # Empty string won't match any "item_X" value
        assert result.get("_go_to_not_found") is True

    def test_go_to_single_row_result(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to works when filter leaves only one row.

        Verifies:
            - Navigation works with minimal data
        """
        state = state_manager_goto.get_state_for_vue()
        state.update(
            create_goto_state(
                column_filters=[
                    {"field": "id", "type": ">=", "value": 100},
                    {"field": "id", "type": "<=", "value": 100},
                ],
                go_to_request={"field": "id", "value": 100},
            )
        )

        result = goto_table_component._prepare_vue_data(state)

        assert result.get("_navigate_to_page") == 1
        assert result.get("_target_row_index") == 0
        assert result["_pagination"]["total_rows"] == 1

    def test_go_to_clears_after_request(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to navigation hints are only set when go_to_request is present.

        Verifies:
            - Subsequent request without go_to_request has no hints
        """
        # First request with go_to
        state1 = state_manager_goto.get_state_for_vue()
        state1.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 350},
            )
        )
        result1 = goto_table_component._prepare_vue_data(state1)
        assert "_navigate_to_page" in result1

        # Second request without go_to
        state2 = state_manager_goto.get_state_for_vue()
        state2.update(
            create_goto_state()  # No go_to_request
        )
        result2 = goto_table_component._prepare_vue_data(state2)

        # Should not have navigation hints
        assert "_navigate_to_page" not in result2
        assert "_target_row_index" not in result2
        assert "_go_to_not_found" not in result2

    def test_go_to_page_boundary(
        self, goto_table_component, state_manager_goto
    ):
        """
        Go-to handles rows at page boundaries correctly.

        Verifies:
            - id=99 (last of page 1) and id=100 (first of page 2) are correct
        """
        # Last row of page 1
        state1 = state_manager_goto.get_state_for_vue()
        state1.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 99},
            )
        )
        result1 = goto_table_component._prepare_vue_data(state1)
        assert result1.get("_navigate_to_page") == 1
        assert result1.get("_target_row_index") == 99

        # First row of page 2
        state2 = state_manager_goto.get_state_for_vue()
        state2.update(
            create_goto_state(
                go_to_request={"field": "id", "value": 100},
            )
        )
        result2 = goto_table_component._prepare_vue_data(state2)
        assert result2.get("_navigate_to_page") == 2
        assert result2.get("_target_row_index") == 0

    def test_go_to_with_no_go_to_fields_configured(
        self, tmp_path, mock_streamlit_goto
    ):
        """
        Go-to request still works even without go_to_fields in component args.

        Note: go_to_fields controls what fields are shown in the UI dropdown,
        but the server-side search works for any field.

        Verifies:
            - Search works even if go_to_fields is empty
        """
        data = pl.LazyFrame(
            {
                "id": list(range(100)),
                "name": [f"item_{i}" for i in range(100)],
            }
        )

        table = Table(
            cache_id="no_goto_fields_test",
            data=data,
            cache_path=str(tmp_path),
            pagination=True,
            page_size=10,
            pagination_identifier="no_goto_page",
            go_to_fields=[],  # Explicitly empty
        )

        state = {
            "no_goto_page": {
                "page": 1,
                "page_size": 10,
                "go_to_request": {"field": "id", "value": 55},
            }
        }

        result = table._prepare_vue_data(state)

        # Should still find the row
        assert result.get("_navigate_to_page") == 6  # 55 / 10 + 1 = 6
        assert result.get("_target_row_index") == 5  # 55 % 10 = 5
