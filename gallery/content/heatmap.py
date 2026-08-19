"""Heatmap: an MS1 retention-time x mass map."""

from src import layout
from src.dataset import scan

from openms_insight import Heatmap


def example(sm):
    Heatmap(
        cache_id="ms1_map",
        data=scan("flashdeconv/ms1_map"),
        x_column="rt",
        y_column="mass",
        intensity_column="intensity",
        x_label="Retention time (s)",
        y_label="Neutral mass (Da)",
        colorscale="Portland",
    )(state_manager=sm)


layout.render(
    title="Heatmap",
    summary=(
        "The full MS1 map of the run: 608,134 points of retention time against neutral "
        "mass, coloured by intensity. Zoom in and the component fetches a finer "
        "resolution level rather than redrawing everything."
    ),
    example=example,
    component=Heatmap,
    used=[
        "cache_id",
        "data",
        "x_column",
        "y_column",
        "intensity_column",
        "x_label",
        "y_label",
        "colorscale",
    ],
    tables=["flashdeconv/ms1_map.parquet"],
    notes=(
        "Nothing in this example mentions downsampling. Preprocessing builds the "
        "resolution levels once, by cascading each level down from the one above it, "
        "so the raw points are read a single time."
    ),
)
