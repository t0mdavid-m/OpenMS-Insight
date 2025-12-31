"""Contract test: all components must include componentType in _get_component_args().

This test ensures that _get_component_args() returns a dict with componentType,
which is required by App.vue for component selection.
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
def test_get_component_args_includes_component_type(
    mock_streamlit, temp_cache_dir, request, ComponentClass, data_fixture, extra_kwargs
):
    """_get_component_args must include componentType for Vue component selection."""
    data = request.getfixturevalue(data_fixture)

    component = ComponentClass(
        cache_id=f"test_{ComponentClass.__name__}_args",
        data=data,
        cache_path=str(temp_cache_dir),
        **extra_kwargs,
    )

    args = component._get_component_args()

    assert "componentType" in args, f"{ComponentClass.__name__} missing componentType"
    assert isinstance(args["componentType"], str), "componentType must be string"
    assert len(args["componentType"]) > 0, "componentType must not be empty"
