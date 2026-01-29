"""
Heatmap Render Order Integration Tests.

Tests the low_values_on_top parameter that controls which points are
prioritized during downsampling and displayed on top.
"""

from unittest.mock import patch
import polars as pl
import pytest
from openms_insight import Heatmap
from openms_insight.core.state import StateManager


class MockSessionState(dict):
    pass


@pytest.fixture
def mock_streamlit():
    mock_session_state = MockSessionState()
    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def state_manager(mock_streamlit):
    return StateManager(session_key="test_state")


@pytest.fixture
def heatmap_data_with_scores() -> pl.LazyFrame:
    """Heatmap data with known intensity values for ordering tests."""
    return pl.LazyFrame({
        "rt": [1.0, 2.0, 3.0, 4.0, 5.0],
        "mz": [100.0, 200.0, 300.0, 400.0, 500.0],
        "intensity": [1000.0, 500.0, 2000.0, 100.0, 1500.0],
        "scan_id": [1, 1, 1, 1, 1],
    })


class TestLowValuesOnTopDefault:
    """Default behavior - backward compatibility."""

    def test_default_high_values_on_top(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """Default: high intensity values sorted last (on top)."""
        heatmap = Heatmap(
            cache_id="test_default",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
        )
        state = state_manager.get_state_for_vue()
        result = heatmap._prepare_vue_data(state)

        intensities = result["heatmapData"]["intensity"].tolist()
        # Ascending sort: low first, high last (high on top)
        assert intensities == sorted(intensities)

    def test_explicit_false_same_as_default(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """Explicit low_values_on_top=False same as default."""
        heatmap = Heatmap(
            cache_id="test_explicit_false",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=False,
        )
        state = state_manager.get_state_for_vue()
        result = heatmap._prepare_vue_data(state)

        intensities = result["heatmapData"]["intensity"].tolist()
        assert intensities == sorted(intensities)


class TestLowValuesOnTopEnabled:
    """low_values_on_top=True inverts ordering."""

    def test_low_values_sorted_last(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """low_values_on_top=True: low values sorted last (on top)."""
        heatmap = Heatmap(
            cache_id="test_low_on_top",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=True,
        )
        state = state_manager.get_state_for_vue()
        result = heatmap._prepare_vue_data(state)

        intensities = result["heatmapData"]["intensity"].tolist()
        # Descending sort: high first, low last (low on top)
        assert intensities == sorted(intensities, reverse=True)

    def test_lowest_value_is_last_row(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """The lowest intensity value should be the last row (drawn on top)."""
        heatmap = Heatmap(
            cache_id="test_lowest_last",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=True,
        )
        state = state_manager.get_state_for_vue()
        result = heatmap._prepare_vue_data(state)

        intensities = result["heatmapData"]["intensity"].tolist()
        assert intensities[-1] == min(intensities)  # Last = lowest = on top


class TestLowValuesOnTopCacheInvalidation:
    """Changing low_values_on_top invalidates cache."""

    def test_different_caches_for_different_settings(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """Different low_values_on_top settings create different caches."""
        # Create with default
        heatmap1 = Heatmap(
            cache_id="test_cache_inv",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=False,
        )
        result1 = heatmap1._prepare_vue_data(state_manager.get_state_for_vue())

        # Create with inverted - should regenerate cache
        heatmap2 = Heatmap(
            cache_id="test_cache_inv",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=True,
        )
        result2 = heatmap2._prepare_vue_data(state_manager.get_state_for_vue())

        # Different orderings
        assert result1["heatmapData"]["intensity"].tolist() != \
               result2["heatmapData"]["intensity"].tolist()


class TestLowValuesOnTopCacheReconstruction:
    """Cache reconstruction preserves low_values_on_top setting."""

    def test_setting_restored_from_cache(
        self, heatmap_data_with_scores, state_manager, tmp_path
    ):
        """low_values_on_top restored when loading from cache."""
        # Create with low_values_on_top=True
        heatmap1 = Heatmap(
            cache_id="test_restore",
            data=heatmap_data_with_scores,
            cache_path=str(tmp_path),
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            low_values_on_top=True,
        )
        result1 = heatmap1._prepare_vue_data(state_manager.get_state_for_vue())

        # Reconstruct from cache (no data)
        heatmap2 = Heatmap(
            cache_id="test_restore",
            cache_path=str(tmp_path),
        )
        result2 = heatmap2._prepare_vue_data(state_manager.get_state_for_vue())

        # Same ordering (descending)
        assert result1["heatmapData"]["intensity"].tolist() == \
               result2["heatmapData"]["intensity"].tolist()
        # Verify it's descending (low on top)
        intensities = result2["heatmapData"]["intensity"].tolist()
        assert intensities == sorted(intensities, reverse=True)
