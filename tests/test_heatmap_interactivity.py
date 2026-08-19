"""A Heatmap declared with `interactivity` must be able to answer a click.

No test constructed a Heatmap with `interactivity=` at all, which is how a page could
declare a heatmap, wire it into a state manager, and get nothing at all from a click
without anything going red.

Two properties matter, and the second is easy to lose:

1. The interactivity column reaches the Vue payload -- on the zoomed-out path *and*
   the zoomed path, which select their points through different code.
2. The value on a drawn point is the value from a real source row. Heatmap
   downsampling selects rows rather than aggregating them, so this holds; if it ever
   started binning, a clicked point would carry a fabricated identifier.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap


@pytest.fixture
def scan_map() -> pl.LazyFrame:
    """An MS1-map shape: many points per scan, each carrying its scan id."""
    import random

    random.seed(7)
    rows = {"rt": [], "mz": [], "intensity": [], "scan_id": []}
    for scan_id in range(100, 140):
        rt = 100.0 + scan_id
        for _ in range(200):
            rows["rt"].append(rt)
            rows["mz"].append(random.uniform(200, 2000))
            rows["intensity"].append(random.uniform(10, 100_000))
            rows["scan_id"].append(scan_id)
    return pl.LazyFrame(rows)


def _heatmap(data, cache_dir, cache_id="interactive", **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        interactivity={"scan": "scan_id"},
        **kwargs,
    )


class TestInteractivityColumnReachesVue:
    def test_present_without_zoom(self, mock_streamlit, temp_cache_dir, scan_map):
        plot = _heatmap(scan_map, temp_cache_dir)

        payload = plot._prepare_vue_data({})

        assert "scan_id" in payload["heatmapData"].columns

    def test_present_with_zoom(self, mock_streamlit, temp_cache_dir, scan_map):
        plot = _heatmap(scan_map, temp_cache_dir, cache_id="interactive_zoom")

        zoomed = plot._prepare_vue_data(
            {"heatmap_zoom": {"xRange": [210.0, 230.0], "yRange": [500.0, 1500.0]}}
        )

        assert "scan_id" in zoomed["heatmapData"].columns

    def test_declared_mapping_reaches_component_args(
        self, mock_streamlit, temp_cache_dir, scan_map
    ):
        """Vue's click handler returns early on an empty mapping, so this is what
        decides whether a click does anything at all."""
        plot = _heatmap(scan_map, temp_cache_dir, cache_id="interactive_args")

        args = plot._get_component_args()

        assert args["interactivity"] == {"scan": "scan_id"}


class TestDrawnPointsCarryRealValues:
    def test_every_drawn_scan_id_exists_in_the_source(
        self, mock_streamlit, temp_cache_dir, scan_map
    ):
        plot = _heatmap(scan_map, temp_cache_dir, cache_id="interactive_real")
        source = set(scan_map.collect()["scan_id"].to_list())

        drawn = set(plot._prepare_vue_data({})["heatmapData"]["scan_id"].tolist())

        assert drawn, "no points were drawn"
        assert drawn <= source, f"fabricated scan ids: {sorted(drawn - source)}"

    def test_a_drawn_point_matches_its_source_row(
        self, mock_streamlit, temp_cache_dir, scan_map
    ):
        plot = _heatmap(scan_map, temp_cache_dir, cache_id="interactive_row")
        collected = scan_map.collect()

        drawn = plot._prepare_vue_data({})["heatmapData"]
        point = drawn.iloc[0]
        matches = collected.filter(
            (pl.col("rt") == point["rt"]) & (pl.col("mz") == point["mz"])
        )

        assert matches.height >= 1, "drawn point is not a source row"
        assert point["scan_id"] in matches["scan_id"].to_list()


class TestInteractivitySurvivesReconstruction:
    def test_round_trips_through_the_cache(
        self, mock_streamlit, temp_cache_dir, scan_map
    ):
        _heatmap(scan_map, temp_cache_dir, cache_id="interactive_recon")

        restored = Heatmap(cache_id="interactive_recon", cache_path=str(temp_cache_dir))

        assert restored._interactivity == {"scan": "scan_id"}
        assert "scan_id" in restored._prepare_vue_data({})["heatmapData"].columns
