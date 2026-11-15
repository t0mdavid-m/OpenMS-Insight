"""SeriesPlot ``highlight``: the selected rows marked over the series."""

import polars as pl
import pytest

from openms_insight import SeriesPlot


@pytest.fixture
def values():
    return pl.DataFrame(
        {
            "run": ["r1", "r1", "r1", "r2", "r2", "r2"],
            "intensity": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
            "found": [
                "detected",
                "matched",
                "detected",
                "detected",
                "detected",
                "matched",
            ],
            "feature": [10, 11, 12, 10, 11, 12],
        }
    )


def _box(tmp_path, data, **kwargs):
    return SeriesPlot(
        cache_id="box",
        cache_path=str(tmp_path),
        data=data.lazy(),
        x_column="run",
        y_column="intensity",
        series_column="found",
        mode="box",
        highlight={"feature": "feature"},
        **kwargs,
    )


def test_marks_the_selected_rows(tmp_path, values):
    plot = _box(tmp_path, values)
    assert "feature" in plot.get_state_dependencies()
    points = plot._prepare_vue_data({"feature": 11})["highlightPoints"]
    assert points["x"] == ["r1", "r2"]
    assert points["y"] == [2.0, 2.5]
    assert points["series"] == ["matched", "detected"]


def test_nothing_marked_without_a_selection(tmp_path, values):
    points = _box(tmp_path, values)._prepare_vue_data({})["highlightPoints"]
    assert points["x"] == [] and points["y"] == []


def test_several_selected_and_hash_follows(tmp_path, values):
    plot = _box(tmp_path, values)
    one = plot._prepare_vue_data({"feature": 10})
    two = plot._prepare_vue_data({"feature": [10, 12]})
    assert len(two["highlightPoints"]["x"]) == 4
    assert one["_hash"] != two["_hash"]


def test_highlight_data_searched_instead_of_the_plotted_rows(tmp_path, values):
    # Boxes from fewer rows than can be marked: feature 11 is not plotted
    plot = _box(
        tmp_path, values.filter(pl.col("feature") != 11), highlight_data=values.lazy()
    )
    assert plot._prepare_vue_data({"feature": 11})["highlightPoints"]["y"] == [2.0, 2.5]


def test_kept_in_the_cache(tmp_path, values):
    _box(tmp_path, values, highlight_data=values)
    cached = SeriesPlot(cache_id="box", cache_path=str(tmp_path))
    assert cached._prepare_vue_data({"feature": 12})["highlightPoints"]["y"] == [
        3.0,
        3.5,
    ]


def test_highlight_data_needs_highlight(tmp_path, values):
    with pytest.raises(ValueError):
        SeriesPlot(
            cache_id="x",
            cache_path=str(tmp_path),
            data=values.lazy(),
            x_column="run",
            y_column="intensity",
            highlight_data=values,
        )
