"""Line plot: a single deconvolved spectrum."""

from src import layout
from src.dataset import scan

from openms_insight import LinePlot


def example(sm):
    LinePlot(
        cache_id="spectrum",
        data=scan("flashdeconv/deconv_peaks"),
        filters={"scan": "scan_id"},
        filter_defaults={"scan": 3371},
        interactivity={"peak": "peak_id"},
        x_column="mass",
        y_column="intensity",
        x_label="Neutral mass (Da)",
        y_label="Intensity",
    )(state_manager=sm)


layout.render(
    title="Line plot",
    summary=(
        "One deconvolved MS2 spectrum, drawn as a centroid stick plot. This is scan "
        "3371 — 122 neutral masses from an 11,874 Da proteoform."
    ),
    example=example,
    component=LinePlot,
    used=[
        "cache_id",
        "data",
        "filters",
        "filter_defaults",
        "interactivity",
        "x_column",
        "y_column",
        "x_label",
        "y_label",
    ],
    tables=["flashdeconv/deconv_peaks.parquet"],
    notes=(
        "`filter_defaults` matters more than it looks. The plot filters on the `scan` "
        "identifier, which nothing has set yet on this page — without a default it "
        "would render empty on first load."
    ),
)
