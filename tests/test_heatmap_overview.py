"""Heatmap `overview=True`: a raster of the whole map, sent while it is zoomed.

The browser draws the raster as a small picture in a corner of the plot and
frames the zoomed region on it.
"""

from __future__ import annotations

import base64

import numpy as np
import polars as pl
import pytest

from openms_insight import Heatmap
from openms_insight.preprocessing.overview import overview_raster

ZOOM = {"heatmap_zoom": {"xRange": [100.0, 200.0], "yRange": [1000.0, 5000.0]}}


def _cells(raster):
    cells = np.frombuffer(base64.b64decode(raster["cells"]), dtype=np.uint8)
    return cells.reshape(raster["height"], raster["width"])


def test_raster_keeps_the_highest_intensity_of_a_cell():
    data = pl.DataFrame(
        {
            "x": [0.0, 0.0, 10.0, 10.0],
            "y": [0.0, 0.0, 0.0, 10.0],
            "z": [9.0, 99.0, 0.0, 999.0],
        }
    )
    raster = overview_raster(data, "x", "y", "z", log_scale=True, width=4, height=2)
    cells = _cells(raster)

    assert raster["x"] == [0.0, 10.0] and raster["y"] == [0.0, 10.0]
    # Row 0 is the lowest y; the point at x=0 shows its highest value (99),
    # placed between the weakest cell (0, as log10 of nothing) and the strongest
    assert cells[0, 0] == 1 + round(np.log10(99) / np.log10(999) * 254)
    assert cells[1, 3] == 255
    # A point of zero intensity still shows
    assert cells[0, 3] == 1
    # Cells without a point stay empty
    assert cells[0, 1] == 0 and cells[1, 0] == 0


def test_raster_without_intensity_marks_every_filled_cell():
    data = pl.DataFrame({"x": [1.0, 2.0], "y": [5.0, 5.0]})
    raster = overview_raster(data, "x", "y", None, width=2, height=1)

    assert raster["y"] == [4.5, 5.5]
    assert _cells(raster).tolist() == [[255, 255]]


def test_raster_of_no_points_is_none():
    empty = pl.DataFrame({"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64})
    assert overview_raster(empty, "x", "y") is None
    nan = pl.DataFrame({"x": [float("nan")], "y": [1.0]})
    assert overview_raster(nan, "x", "y") is None


@pytest.fixture
def peaks() -> pl.LazyFrame:
    n = 30_000
    return pl.LazyFrame(
        {
            "rt": [float(i % 3000) for i in range(n)],
            "mz": [1000.0 + (i * 7919) % 20000 for i in range(n)],
            "intensity": [float((i * 31) % 997) for i in range(n)],
            "sample": ["A" if i % 2 else "B" for i in range(n)],
        }
    )


def _heatmap(data, cache_dir, cache_id, **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        min_points=1000,
        **kwargs,
    )


def test_overview_is_sent_only_while_zoomed(mock_streamlit, temp_cache_dir, peaks):
    plot = _heatmap(peaks, temp_cache_dir, "overview", overview=True)

    assert plot._get_component_args()["overview"] is True
    assert "overview" not in plot._prepare_vue_data({})
    raster = plot._prepare_vue_data(ZOOM)["overview"]
    # The whole map, not the zoomed region
    assert raster["x"][0] < 50.0 and raster["x"][1] > 2900.0
    assert raster["y"][0] < 1100.0 and raster["y"][1] > 20000.0
    assert _cells(raster).any()


def test_no_overview_by_default(mock_streamlit, temp_cache_dir, peaks):
    plot = _heatmap(peaks, temp_cache_dir, "no-overview")

    assert "overview" not in plot._get_component_args()
    assert "overview" not in plot._prepare_vue_data(ZOOM)


def test_overview_follows_filters(mock_streamlit, temp_cache_dir, peaks):
    plot = _heatmap(
        peaks, temp_cache_dir, "overview-filter", overview=True, filters={"s": "sample"}
    )
    a = plot._prepare_vue_data({**ZOOM, "s": "A"})
    b = plot._prepare_vue_data({**ZOOM, "s": "B"})

    assert a["overview"]["cells"] != b["overview"]["cells"]
    assert a["_hash"] != b["_hash"]


def test_overview_is_render_time_only(mock_streamlit, temp_cache_dir, peaks):
    _heatmap(peaks, temp_cache_dir, "overview-cache")
    reloaded = _heatmap(peaks, temp_cache_dir, "overview-cache", overview=True)

    assert "overview" in reloaded._prepare_vue_data(ZOOM)
