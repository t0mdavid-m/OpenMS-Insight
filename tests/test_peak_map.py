"""PeakMap: a Heatmap whose points can also be drawn in 3D.

Both drawings show the payload of the Heatmap it is built on, so zoom,
selection, filter and colours are shared; the marked points carry their
intensity, the height of their stem in 3D.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap, PeakMap


@pytest.fixture
def peaks() -> pl.LazyFrame:
    n = 20_000
    return pl.LazyFrame(
        {
            "rt": [float(i % 2000) for i in range(n)],
            "mz": [400.0 + (i * 7919) % 1600 for i in range(n)],
            "intensity": [float((i * 31) % 997) + 1.0 for i in range(n)],
            "peak_id": list(range(n)),
        }
    )


def _map(cls, data, cache_dir, cache_id, **kwargs):
    return cls(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        min_points=1000,
        **kwargs,
    )


def test_args_offer_the_3d_view(mock_streamlit, temp_cache_dir, peaks):
    plot = _map(PeakMap, peaks, temp_cache_dir, "pm", z_label="Intensity (counts)")
    args = plot._get_component_args()

    assert args["componentType"] == "PlotlyHeatmap"
    assert args["view3d"] is True
    assert args["initialView"] == "2d"
    assert args["zLabel"] == "Intensity (counts)"


def test_initial_view_3d(mock_streamlit, temp_cache_dir, peaks):
    plot = _map(PeakMap, peaks, temp_cache_dir, "pm3", view="3d")
    assert plot._get_component_args()["initialView"] == "3d"


def test_unknown_view_is_refused(mock_streamlit, temp_cache_dir, peaks):
    with pytest.raises(ValueError, match="view"):
        _map(PeakMap, peaks, temp_cache_dir, "bad", view="4d")


def test_heatmap_args_have_no_3d_view(mock_streamlit, temp_cache_dir, peaks):
    assert "view3d" not in _map(Heatmap, peaks, temp_cache_dir, "hm")._get_component_args()


def test_same_points_as_the_heatmap(mock_streamlit, temp_cache_dir, peaks):
    zoom = {"heatmap_zoom": {"xRange": [100.0, 400.0], "yRange": [500.0, 900.0]}}
    heatmap = _map(Heatmap, peaks, temp_cache_dir / "a", "same")
    peak_map = _map(PeakMap, peaks, temp_cache_dir / "b", "same")

    for state in ({}, zoom):
        expected = heatmap._prepare_vue_data(state)["heatmapData"]
        got = peak_map._prepare_vue_data(state)["heatmapData"]
        assert got.equals(expected)


def test_marked_point_carries_its_intensity(mock_streamlit, temp_cache_dir, peaks):
    peak_map = _map(PeakMap, peaks, temp_cache_dir, "mark", highlight={"peak": "peak_id"})
    heatmap = _map(Heatmap, peaks, temp_cache_dir / "h", "mark", highlight={"peak": "peak_id"})

    peak = 1234
    marked = peak_map._prepare_vue_data({"peak": peak})["highlightPoints"]
    assert marked == {
        "x": [float(peak % 2000)],
        "y": [400.0 + (peak * 7919) % 1600],
        "z": [float((peak * 31) % 997) + 1.0],
    }
    # A Heatmap sends x and y only, as before
    assert set(heatmap._prepare_vue_data({"peak": peak})["highlightPoints"]) == {"x", "y"}
    assert peak_map._prepare_vue_data({})["highlightPoints"] == {"x": [], "y": [], "z": []}


def test_reloads_from_cache(mock_streamlit, temp_cache_dir, peaks):
    _map(PeakMap, peaks, temp_cache_dir, "reload", highlight={"peak": "peak_id"})
    reloaded = PeakMap(cache_id="reload", cache_path=str(temp_cache_dir), view="3d")

    assert reloaded._get_component_args()["initialView"] == "3d"
    assert reloaded._prepare_vue_data({"peak": 5})["highlightPoints"]["z"] == [float((5 * 31) % 997) + 1.0]


def test_signature_lists_every_option():
    import inspect

    params = inspect.signature(PeakMap.__init__).parameters
    for name in ("zoom_identifier", "highlight", "x_column", "view", "z_label"):
        assert name in params
