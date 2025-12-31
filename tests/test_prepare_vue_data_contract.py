"""Contract test: all components must return dict with _hash key from _prepare_vue_data.

This test ensures that _prepare_vue_data returns a dict (not a tuple) with an embedded
_hash key, which is required by bridge.py._prepare_vue_data_cached().
"""

import pytest

from openms_insight import Heatmap, LinePlot, Table, VolcanoPlot


@pytest.mark.parametrize(
    "ComponentClass,data_fixture,extra_kwargs",
    [
        (Table, "sample_table_data", {}),
        (
            LinePlot,
            "sample_lineplot_data",
            {"x_column": "mass", "y_column": "intensity"},
        ),
        (
            Heatmap,
            "sample_heatmap_data",
            {
                "x_column": "retention_time",
                "y_column": "mz",
                "intensity_column": "intensity",
            },
        ),
        (
            VolcanoPlot,
            "sample_volcanoplot_data",
            {"log2fc_column": "log2FC", "pvalue_column": "pvalue"},
        ),
    ],
)
def test_prepare_vue_data_returns_dict_with_hash(
    mock_streamlit, temp_cache_dir, request, ComponentClass, data_fixture, extra_kwargs
):
    """_prepare_vue_data must return dict with _hash key, not tuple."""
    data = request.getfixturevalue(data_fixture)

    component = ComponentClass(
        cache_id=f"test_{ComponentClass.__name__}_contract",
        data=data,
        cache_path=str(temp_cache_dir),
        **extra_kwargs,
    )

    result = component._prepare_vue_data({})

    assert isinstance(
        result, dict
    ), f"{ComponentClass.__name__} returned {type(result)}, expected dict"
    assert "_hash" in result, f"{ComponentClass.__name__} missing _hash key"
    assert isinstance(
        result["_hash"], str
    ), f"{ComponentClass.__name__} _hash must be string"
