"""Linking: a table selection drives a plot."""

from src import layout
from src.dataset import scan

from openms_insight import LinePlot, Table


def example(sm):
    Table(
        cache_id="linked_scans",
        data=scan("flashdeconv/scans"),
        index_field="scan_id",
        interactivity={"scan": "scan_id"},
        page_size=8,
        column_definitions=[
            {"field": "scan_id", "title": "Scan", "sorter": "number"},
            {"field": "ms_level", "title": "MS level", "sorter": "number"},
            {"field": "rt", "title": "RT (s)", "sorter": "number"},
            {"field": "precursor_mass", "title": "Precursor mass", "sorter": "number"},
        ],
    )(key="scans", state_manager=sm)

    LinePlot(
        cache_id="linked_spectrum",
        data=scan("flashdeconv/deconv_peaks"),
        filters={"scan": "scan_id"},
        filter_defaults={"scan": 3371},
        x_column="mass",
        y_column="intensity",
        x_label="Neutral mass (Da)",
    )(key="spectrum", state_manager=sm)


layout.render(
    title="Scan table → spectrum",
    summary=(
        "Click any row and the spectrum below follows. This is the pattern most "
        "mass-spectrometry interfaces are built from, and it is the reason this "
        "package exists."
    ),
    example=example,
    component=None,
    tables=["flashdeconv/scans.parquet", "flashdeconv/deconv_peaks.parquet"],
    notes=(
        "There is no callback and no event handler. The table *writes* the `scan` "
        "identifier on click; the plot *reads* it as a filter. The only thing "
        "connecting them is that both name the same string — expand **Live selection "
        "state** below and click a row to watch it change."
    ),
)
