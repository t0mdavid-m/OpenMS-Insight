"""Heatmap.set_markers(): points drawn over the heatmap (e.g. precursors)."""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap
from openms_insight.rendering.bridge import _payload_cache_key


@pytest.fixture
def points() -> pl.LazyFrame:
    rows = {"rt": [], "mz": [], "intensity": []}
    for i in range(50):
        for j in range(20):
            rows["rt"].append(float(i))
            rows["mz"].append(100.0 + 10 * j)
            rows["intensity"].append(float(1 + i * j))
    return pl.LazyFrame(rows)


@pytest.fixture
def precursors() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "rt": [2.0, 22.0, 42.0],
            "precursor_mz": [110.5, 150.5, 250.5],
            "id_idx": [3, 4, 5],
            "sequence": ["PEPTIDE", "SEQUENCE", None],
        }
    )


def _heatmap(data, cache_dir, cache_id):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
    )


def _set(plot, precursors, **kwargs):
    return plot.set_markers(
        precursors,
        x_column="rt",
        y_column="precursor_mz",
        id_column="id_idx",
        text_column="sequence",
        **kwargs,
    )


def test_no_markers_by_default(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "nomarker")
    assert "markerData" not in plot._prepare_vue_data({})
    assert "markers" not in plot._get_component_args()
    assert plot._get_render_key() is None


def test_markers_reach_vue_with_renamed_columns(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _set(
        _heatmap(points, temp_cache_dir, "marker"),
        precursors,
        selection="identification",
        label="Identifications",
        show_text=True,
    )

    markers = plot._prepare_vue_data({})["markerData"]

    assert list(markers.columns) == ["x", "y", "id", "text"]
    assert markers["id"].tolist() == [3, 4, 5]
    assert markers["text"].tolist()[:2] == ["PEPTIDE", "SEQUENCE"]
    args = plot._get_component_args()["markers"]
    assert args["selection"] == "identification"
    assert args["label"] == "Identifications"
    assert args["showText"] is True
    assert args["symbol"] == "diamond"


def test_only_markers_in_the_zoom_are_sent(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _set(_heatmap(points, temp_cache_dir, "markerzoom"), precursors)

    payload = plot._prepare_vue_data(
        {"heatmap_zoom": {"xRange": [20.0, 30.0], "yRange": [140.0, 200.0]}}
    )

    assert payload["markerData"]["id"].tolist() == [4]


def test_a_zoom_on_one_axis_keeps_the_other_whole(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _set(_heatmap(points, temp_cache_dir, "markerxzoom"), precursors)

    payload = plot._prepare_vue_data(
        {"heatmap_zoom": {"xRange": [20.0, 45.0], "yRange": [-1, -1]}}
    )

    assert payload["markerData"]["id"].tolist() == [4, 5]


def test_markers_and_boxes_together(mock_streamlit, temp_cache_dir, points, precursors):
    plot = _set(_heatmap(points, temp_cache_dir, "markerbox"), precursors)
    plot.set_boxes(
        pl.DataFrame({"x0": [1.0], "x1": [3.0], "y0": [110.0], "y1": [111.0]})
    )

    payload = plot._prepare_vue_data({})

    assert len(payload["boxData"]) == 1
    assert len(payload["markerData"]) == 3


def test_max_markers_keeps_the_first(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _set(
        _heatmap(points, temp_cache_dir, "markermax"), precursors, max_markers=2
    )
    assert plot._prepare_vue_data({})["markerData"]["id"].tolist() == [3, 4]


def test_new_markers_change_the_payload_key(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _set(_heatmap(points, temp_cache_dir, "markerkey"), precursors)
    first = plot._get_render_key()
    _set(plot, precursors.head(1))
    one = _payload_cache_key(plot, {}, set())
    _set(plot, precursors)
    assert _payload_cache_key(plot, {}, set()) != one
    assert plot._get_render_key() == first


def test_none_removes_the_markers(mock_streamlit, temp_cache_dir, points, precursors):
    plot = _set(_heatmap(points, temp_cache_dir, "markernone"), precursors)
    plot.set_markers(None)
    assert "markerData" not in plot._prepare_vue_data({})
    assert plot._get_render_key() is None


def test_selection_needs_an_id(mock_streamlit, temp_cache_dir, points, precursors):
    plot = _heatmap(points, temp_cache_dir, "markersel")
    with pytest.raises(ValueError):
        plot.set_markers(
            precursors,
            x_column="rt",
            y_column="precursor_mz",
            selection="identification",
        )


def test_show_text_needs_a_text_column(
    mock_streamlit, temp_cache_dir, points, precursors
):
    plot = _heatmap(points, temp_cache_dir, "markertext")
    with pytest.raises(ValueError):
        plot.set_markers(
            precursors, x_column="rt", y_column="precursor_mz", show_text=True
        )
