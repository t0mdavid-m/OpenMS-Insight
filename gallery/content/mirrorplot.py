"""Mirror plot: two spectra of the same proteoform, face to face."""

from src import layout
from src.dataset import scan

from openms_insight import MirrorPlot


def example(sm):
    MirrorPlot(
        cache_id="mirror",
        data=scan("flashdeconv/deconv_peaks"),
        filters_top={"scan_top": "scan_id"},
        filter_defaults_top={"scan_top": 3371},
        filters_bottom={"scan_bottom": "scan_id"},
        filter_defaults_bottom={"scan_bottom": 3373},
        interactivity={"peak": "peak_id"},
        x_column="mass",
        y_column="intensity",
        title_top="Scan 3371",
        title_bottom="Scan 3373",
        x_label="Neutral mass (Da)",
    )(state_manager=sm)


layout.render(
    title="Mirror plot",
    summary=(
        "Two MS2 spectra of the same 11,874 Da proteoform, acquired six seconds apart. "
        "Each half filters independently, so they can show any two spectra; a click "
        "selects a peak on either side."
    ),
    example=example,
    component=MirrorPlot,
    used=[
        "cache_id",
        "data",
        "filters_top",
        "filter_defaults_top",
        "filters_bottom",
        "filter_defaults_bottom",
        "interactivity",
        "x_column",
        "y_column",
        "title_top",
        "title_bottom",
        "x_label",
    ],
    tables=["flashdeconv/deconv_peaks.parquet"],
    notes=(
        "Both halves read one table and one column — the two sides are simply "
        "different *values* of `scan_id`. The y-axis flip happens in the browser; the "
        "cache stores positive intensities for both halves."
    ),
)
