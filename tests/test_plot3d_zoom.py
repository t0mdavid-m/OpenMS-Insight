"""Plot3D: the region another plot is zoomed to, and the most intense points."""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Plot3D


@pytest.fixture
def peaks() -> pl.LazyFrame:
    rows = {"rt": [], "mz": [], "intensity": [], "scan": []}
    for i in range(20):
        for j in range(10):
            rows["rt"].append(float(i))
            rows["mz"].append(100.0 + 10 * j)
            rows["intensity"].append(float(1 + i * 10 + j))
            rows["scan"].append(i)
    return pl.LazyFrame(rows)


def _plot(data, cache_dir, cache_id, **kwargs):
    return Plot3D(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        z_column="intensity",
        **kwargs,
    )


def _points(plot, state):
    return plot._prepare_vue_data(state)["plotData"]


def test_without_zoom_identifier_everything_is_sent(
    mock_streamlit, temp_cache_dir, peaks
):
    plot = _plot(peaks, temp_cache_dir, "p3_all")
    assert len(_points(plot, {"peak_zoom": {"xRange": [2, 3]}})) == 200
    assert "peak_zoom" not in plot.get_state_dependencies()


def test_the_zoom_selects_the_region(mock_streamlit, temp_cache_dir, peaks):
    plot = _plot(peaks, temp_cache_dir, "p3_zoom", zoom_identifier="peak_zoom")
    assert "peak_zoom" in plot.get_state_dependencies()
    points = _points(
        plot, {"peak_zoom": {"xRange": [2.0, 4.0], "yRange": [115.0, 135.0]}}
    )
    assert sorted(set(points["rt"])) == [2.0, 3.0, 4.0]
    assert sorted(set(points["mz"])) == [120.0, 130.0]


def test_a_zoom_on_one_axis_keeps_the_other_whole(
    mock_streamlit, temp_cache_dir, peaks
):
    plot = _plot(peaks, temp_cache_dir, "p3_x", zoom_identifier="peak_zoom")
    points = _points(plot, {"peak_zoom": {"xRange": [5.0, 6.0], "yRange": [-1, -1]}})
    assert len(points) == 20
    assert _points(plot, {"peak_zoom": None}).shape[0] == 200


def test_zoom_columns_name_other_columns(mock_streamlit, temp_cache_dir, peaks):
    plot = _plot(
        peaks,
        temp_cache_dir,
        "p3_cols",
        zoom_identifier="peak_zoom",
        zoom_columns=("scan", "mz"),
    )
    points = _points(plot, {"peak_zoom": {"x": [0, 1]}})
    assert sorted(set(points["rt"])) == [0.0, 1.0]


def test_max_points_keeps_the_most_intense_in_order(
    mock_streamlit, temp_cache_dir, peaks
):
    plot = _plot(
        peaks, temp_cache_dir, "p3_top", zoom_identifier="peak_zoom", max_points=5
    )
    points = _points(plot, {"peak_zoom": {"xRange": [0.0, 1.0]}})
    assert points["intensity"].tolist() == [16.0, 17.0, 18.0, 19.0, 20.0]
    assert len(_points(plot, {})) == 5


def test_a_new_zoom_changes_the_hash(mock_streamlit, temp_cache_dir, peaks):
    plot = _plot(peaks, temp_cache_dir, "p3_hash", zoom_identifier="peak_zoom")
    one = plot._prepare_vue_data({"peak_zoom": {"xRange": [0.0, 1.0]}})["_hash"]
    two = plot._prepare_vue_data({"peak_zoom": {"xRange": [2.0, 3.0]}})["_hash"]
    assert one != two


def test_the_options_are_not_cache_configuration(mock_streamlit, temp_cache_dir, peaks):
    plain = _plot(peaks, temp_cache_dir, "p3_cfg")
    zoomed = _plot(
        peaks, temp_cache_dir, "p3_cfg", zoom_identifier="peak_zoom", max_points=3
    )
    assert plain._get_cache_config() == zoomed._get_cache_config()


@pytest.mark.parametrize("kwargs", [{"zoom_columns": ("rt",)}, {"max_points": 0}])
def test_bad_options_are_refused(mock_streamlit, temp_cache_dir, peaks, kwargs):
    with pytest.raises(ValueError):
        _plot(peaks, temp_cache_dir, "p3_bad", **kwargs)
