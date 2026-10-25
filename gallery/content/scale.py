"""Scale: how the heatmap survives large maps."""

import streamlit as st
from src import layout
from src.dataset import scan

from openms_insight import Heatmap

detail = st.select_slider(
    "Points held at the coarsest level",
    options=[5_000, 20_000, 50_000, 100_000],
    value=20_000,
    help="Preprocessing builds resolution levels down from the raw data. This sets "
    "the size of the level shown when fully zoomed out.",
)


def example(sm):
    Heatmap(
        cache_id=f"scale_{detail}",
        data=scan("flashdeconv/ms1_map"),
        x_column="rt",
        y_column="mass",
        intensity_column="intensity",
        min_points=detail,
        interactivity={"scan": "scan_id"},
        x_label="Retention time (s)",
        y_label="Neutral mass (Da)",
    )(state_manager=sm)


layout.render(
    title="Large heatmaps",
    summary=(
        "The same 608,134-point MS1 map, rebuilt at a different coarsest resolution. "
        "Move the slider and the cache is rebuilt for that setting; zoom in and finer "
        "levels are served as you go."
    ),
    example=example,
    component=Heatmap,
    used=[
        "cache_id",
        "data",
        "x_column",
        "y_column",
        "intensity_column",
        "min_points",
        "interactivity",
    ],
    tables=["flashdeconv/ms1_map.parquet"],
    notes=(
        "Being straight about the numbers: this example dataset holds 608,134 points, "
        "not millions. What the page demonstrates is the *mechanism* — levels are "
        "built by cascading, each one downsampled from the level above using shared "
        "bin boundaries, so the raw points are read exactly once no matter how many "
        "levels are produced. That is what makes the approach hold up at millions of "
        "points; a larger public dataset would show it off better, but would not "
        "change the code above by a single line."
    ),
)
