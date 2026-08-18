"""Tests for ClusteredHeatmap's handling of incomplete matrices.

scipy's linkage rejects non-finite values with "The condensed distance matrix
must contain only finite values", which says nothing about the caller's data.
The component checks first and explains what to do instead.
"""

import pytest

from openms_insight import ClusteredHeatmap


def test_clustering_rejects_missing_values_with_actionable_error(
    mock_streamlit,
    temp_cache_dir,
    sample_quantification_data,
    sample_quantification_metadata,
):
    with pytest.raises(ValueError, match="missing values"):
        ClusteredHeatmap(
            cache_id="test_clustered_heatmap_missing",
            data=sample_quantification_data,
            metadata=sample_quantification_metadata,
            id_col="feature",
            cache_path=str(temp_cache_dir),
        )


def test_missing_values_are_allowed_when_not_clustering(
    mock_streamlit,
    temp_cache_dir,
    sample_quantification_data,
    sample_quantification_metadata,
):
    """An unclustered heatmap renders gaps fine, so the guard must not fire."""
    component = ClusteredHeatmap(
        cache_id="test_clustered_heatmap_unclustered",
        data=sample_quantification_data,
        metadata=sample_quantification_metadata,
        id_col="feature",
        row_cluster=False,
        col_cluster=False,
        cache_path=str(temp_cache_dir),
    )
    result = component._prepare_vue_data({})
    assert "_hash" in result
