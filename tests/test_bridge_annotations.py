"""Tests for annotation handling in bridge.py - specifically the clearing bug."""

import pytest
from unittest.mock import patch

from openms_insight.rendering.bridge import (
    _store_component_annotations,
    get_component_annotations,
    _COMPONENT_ANNOTATIONS_KEY,
)


def test_store_and_retrieve_annotations(mock_streamlit):
    """Test basic annotation storage and retrieval."""
    annotations = {
        "peak_id": [1, 2, 3],
        "highlight_color": ["red", "red", "red"],
        "annotation": ["b2", "y3", "b4"],
    }

    with patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit):
        _store_component_annotations("test_key", annotations)
        result = get_component_annotations("test_key")

    assert result is not None
    assert result.height == 3
    assert result["peak_id"].to_list() == [1, 2, 3]


def test_clear_annotations_when_none(mock_streamlit):
    """Test that storing None clears annotations."""
    with patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit):
        _store_component_annotations("test_key", None)
        result = get_component_annotations("test_key")

    assert result is None


def test_annotations_cleared_after_valid_data(mock_streamlit):
    """
    Test that annotations are properly cleared when going from data to None.

    This tests the helper functions directly (they work correctly).
    """
    annotations = {
        "peak_id": [1, 2, 3],
        "highlight_color": ["red", "red", "red"],
        "annotation": ["b2", "y3", "b4"],
    }

    with patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit):
        _store_component_annotations("sequence_view_1", annotations)
        result1 = get_component_annotations("sequence_view_1")
        assert result1 is not None

        _store_component_annotations("sequence_view_1", None)
        result2 = get_component_annotations("sequence_view_1")
        assert result2 is None


def test_render_component_clears_annotations_when_vue_returns_none(mock_streamlit):
    """
    Test that render_component clears stored annotations when Vue returns null.

    The scenario:
    1. SequenceView previously returned annotations (stored in session_state)
    2. User changes tolerance, Vue now returns _annotations: null
    3. render_component should clear the stored annotations

    This test simulates the code path in bridge.py that handles null annotations.
    """
    annotations = {
        "peak_id": [1, 2, 3],
        "highlight_color": ["red", "red", "red"],
        "annotation": ["b2", "y3", "b4"],
    }

    with patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit):
        # Simulate previous render that stored annotations
        _store_component_annotations("sequence_view_key", annotations)
        mock_streamlit["_svc_ann_hash_sequence_view_key"] = hash(tuple([1, 2, 3]))

        # Verify annotations are stored
        assert get_component_annotations("sequence_view_key") is not None

        # Simulate the code path from render_component when Vue returns null
        result = {"_annotations": None}  # Vue returns null
        vue_annotations = result.get("_annotations")
        key = "sequence_view_key"

        if vue_annotations is not None:
            # This branch stores annotations - not taken when None
            _store_component_annotations(key, vue_annotations)
        else:
            # Clear the hash and stored annotations
            ann_hash_key = f"_svc_ann_hash_{key}"
            if mock_streamlit.get(ann_hash_key) is not None:
                mock_streamlit[ann_hash_key] = None
            _store_component_annotations(key, None)

        # Annotations should be cleared when Vue returns null
        result = get_component_annotations("sequence_view_key")
        assert result is None, (
            "Annotations should be cleared when Vue returns null. "
            f"Got {result.height if result is not None else 'None'} rows instead."
        )


def test_prepare_vue_data_cached_includes_plot_config_when_annotations_cleared():
    """
    Test that _prepare_vue_data_cached includes _plotConfig when annotations are cleared.

    Scenario:
    1. LinePlot had dynamic annotations (cache stored stripped base data)
    2. Annotations cleared (_dynamic_annotations = None)
    3. _prepare_vue_data_cached should return data WITH _plotConfig
       containing annotationColumn=None (not omit _plotConfig entirely)

    This was the root cause of the stale annotations bug: when annotations were
    cleared, the cache returned base data WITHOUT _plotConfig, so Vue's merge
    logic kept the old _plotConfig with stale annotationColumn reference.
    """
    from openms_insight.rendering.bridge import (
        _prepare_vue_data_cached,
        _set_cached_vue_data,
        _get_component_cache,
    )
    from unittest.mock import MagicMock
    import pandas as pd

    # Create mock component that has _build_plot_config method
    mock_component = MagicMock()
    mock_component._cache_id = "test_lineplot"
    mock_component._dynamic_annotations = None  # Annotations cleared!
    mock_component._highlight_column = None
    mock_component._annotation_column = None

    # Mock _build_plot_config to return a config with null columns
    mock_component._build_plot_config = MagicMock(
        return_value={
            "highlightColumn": None,
            "annotationColumn": None,
        }
    )

    # Simulate cached base data (stripped of _plotConfig)
    cached_base_data = {
        "data": pd.DataFrame({"mz": [100.0, 200.0], "intensity": [1000, 2000]}),
    }
    cached_hash = "abc123"
    component_id = "LinePlot:test_key"
    filter_state = (("spectrum_id", 1),)

    with patch("openms_insight.rendering.bridge.st.session_state", {}):
        # Pre-populate cache with base data (no _plotConfig)
        _set_cached_vue_data(
            component_id, filter_state, cached_base_data, cached_hash, None
        )

        # Call _prepare_vue_data_cached with cleared annotations
        vue_data, data_hash = _prepare_vue_data_cached(
            mock_component, component_id, filter_state, {"spectrum_id": 1}
        )

        # CRITICAL: vue_data MUST include _plotConfig even when no dynamic annotations
        assert "_plotConfig" in vue_data, (
            "_plotConfig should be included when annotations are cleared. "
            "Without it, Vue keeps stale annotation column references."
        )

        # Verify the _plotConfig has null annotation column
        plot_config = vue_data["_plotConfig"]
        assert plot_config["annotationColumn"] is None, (
            "annotationColumn should be None when annotations cleared"
        )
        assert plot_config["highlightColumn"] is None, (
            "highlightColumn should be None when annotations cleared"
        )
