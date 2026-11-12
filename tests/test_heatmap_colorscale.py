"""Heatmap.set_colorscale(): another colour scale without a cache rebuild."""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap


@pytest.fixture
def points() -> pl.LazyFrame:
    rows = {"rt": [], "mz": [], "intensity": []}
    for i in range(30):
        for j in range(10):
            rows["rt"].append(float(i))
            rows["mz"].append(100.0 + 10 * j)
            rows["intensity"].append(float(1 + i * j))
    return pl.LazyFrame(rows)


def _heatmap(data, cache_dir, cache_id, **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        **kwargs,
    )


def test_constructor_scale_by_default(mock_streamlit, temp_cache_dir, points):
    args = _heatmap(points, temp_cache_dir, "cs_default")._get_component_args()
    assert args["colorscale"] == "Portland"
    assert args["reversescale"] is False


def test_a_named_scale_reaches_vue(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "cs_named")
    assert plot.set_colorscale("Viridis", reversescale=True) is plot
    args = plot._get_component_args()
    assert args["colorscale"] == "Viridis"
    assert args["reversescale"] is True


def test_reversescale_none_keeps_the_setting(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "cs_keep", reversescale=True)
    plot.set_colorscale("Hot")
    assert plot._get_component_args()["reversescale"] is True


def test_stops_are_sent_as_pairs(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "cs_stops")
    plot.set_colorscale([(0, "#000000"), (0.5, "#ff0000"), (1, "#ffffff")])
    assert plot._get_component_args()["colorscale"] == [
        [0.0, "#000000"],
        [0.5, "#ff0000"],
        [1.0, "#ffffff"],
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "",
        [[0, "#000"]],
        [[0, "#000"], [0.5, "#fff"]],
        [[0.2, "#000"], [1, "#fff"]],
        [[0, "#000"], [0.8, "#888"], [0.4, "#aaa"], [1, "#fff"]],
        [[0, "#000", "x"], [1, "#fff"]],
    ],
)
def test_bad_scales_are_refused(mock_streamlit, temp_cache_dir, points, bad):
    plot = _heatmap(points, temp_cache_dir, "cs_bad")
    with pytest.raises(ValueError):
        plot.set_colorscale(bad)


def test_the_cache_is_not_rebuilt(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "cs_cache")
    files = sorted(temp_cache_dir.rglob("*"))
    stamps = [f.stat().st_mtime_ns for f in files]
    plot.set_colorscale("Jet")
    plot._prepare_vue_data({})
    assert sorted(temp_cache_dir.rglob("*")) == files
    assert [f.stat().st_mtime_ns for f in files] == stamps
    # A later page run builds the component as before and finds its cache
    again = _heatmap(points, temp_cache_dir, "cs_cache")
    assert again._get_component_args()["colorscale"] == "Portland"
    assert [f.stat().st_mtime_ns for f in files] == stamps
