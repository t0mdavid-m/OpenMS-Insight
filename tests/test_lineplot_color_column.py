"""A LinePlot can colour each highlighted peak from a column."""

import polars as pl
import pytest

from openms_insight import LinePlot


def _data():
    return pl.LazyFrame(
        {
            "peak_id": [1, 2, 3],
            "mz": [341.3, 501.1, 913.8],
            "intensity": [10.0, 20.0, 30.0],
            "matched": [True, False, True],
            "ion": ["a-B2", "", "w3"],
            "color": ["#0072B2", None, "#D55E00"],
        }
    )


def test_colors_reach_the_browser(mock_streamlit, temp_cache_dir):
    plot = LinePlot(
        cache_id="colors", data=_data(), x_column="mz", y_column="intensity",
        highlight_column="matched", annotation_column="ion", color_column="color",
        interactivity={"peak": "peak_id"}, cache_path=str(temp_cache_dir),
    )
    assert plot._get_component_args()["colorColumn"] == "color"
    frame = plot._prepare_vue_data({})["plotData"]
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    assert list(frame["color"])[0] == "#0072B2"

    restored = LinePlot(cache_id="colors", cache_path=str(temp_cache_dir))
    assert restored._get_component_args()["colorColumn"] == "color"


def test_missing_color_column_rejected(mock_streamlit, temp_cache_dir):
    with pytest.raises(ValueError, match="color_column"):
        LinePlot(
            cache_id="nocolors", data=_data(), x_column="mz", y_column="intensity",
            color_column="series", cache_path=str(temp_cache_dir),
        )
