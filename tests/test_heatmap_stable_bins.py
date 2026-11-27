"""A Heatmap whose data grows (a live acquisition adding scans) keeps the points
it showed: the downsampling grid stays put, so a refresh only adds points.

Binning over the data's own range moved every bin edge with each new scan, and
the map showed a different sample of points after every refresh.
"""

import math
import random

import polars as pl
import pytest

from openms_insight import Heatmap
from openms_insight.preprocessing.compression import stable_grid


@pytest.mark.parametrize(
    "value_range,bins",
    [((0.0, 10.0), 400), ((3.7, 12.1), 237), ((-5.0, 5.0), 10), ((1000.0, 51000.0), 421)],
)
def test_stable_grid_covers_range_with_at_most_bins(value_range, bins):
    (start, end), count = stable_grid(value_range, bins)
    assert 1 <= count <= bins
    assert start <= value_range[0] and end > value_range[1]
    width = (end - start) / count
    assert math.log2(width) == int(math.log2(width))  # a power of two
    assert start / width == int(start / width)  # starts on a multiple of it


def test_stable_grid_keeps_edges_as_range_grows():
    (start, end), count = stable_grid((0.0, 10.0), 400)
    width = (end - start) / count
    for high in (10.5, 11.0, 12.0, 12.4):  # width doubles once the range passes 12.5
        (s, e), c = stable_grid((0.0, high), 400)
        assert (e - s) / c == width and s == start


def test_stable_grid_degenerate_range():
    assert stable_grid((5.0, 5.0), 10) == ((5.0, 5.0), 10)


def _scans(n_scans, seed=1):
    rng = random.Random(seed)
    rows = []
    for scan in range(n_scans):
        for _ in range(120):
            rows.append((scan * 0.01, rng.uniform(1000, 50000), rng.lognormvariate(10, 2)))
    return pl.DataFrame(rows, schema=["rt", "mass", "intensity"], orient="row").with_row_index("id")


def _shown(cache_dir, data, cache_id, **kwargs):
    plot = Heatmap(
        cache_id=cache_id,
        data=data.lazy(),
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mass",
        intensity_column="intensity",
        min_points=2000,
        **kwargs,
    )
    return set(plot._get_levels()[0].collect()["id"].to_list())


@pytest.mark.parametrize("stable,min_kept", [(True, 0.9), (False, 0.0)])
def test_refresh_keeps_the_points_shown(mock_streamlit, temp_cache_dir, stable, min_kept):
    before = _scans(1000)
    after = _scans(1030)  # 30 more scans: the same rows, then new ones
    shown_before = _shown(temp_cache_dir, before, f"a{stable}", stable_bins=stable)
    shown_after = _shown(temp_cache_dir, after, f"b{stable}", stable_bins=stable)
    kept = len(shown_before & shown_after) / len(shown_before)
    assert kept >= min_kept
    if not stable:
        # What the stable grid fixes: most points shown before were swapped out
        assert kept < 0.9
