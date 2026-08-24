"""Table: server-side pagination, sorting, filtering and CSV export."""

from src import layout
from src.dataset import scan

from openms_insight import Table


def example(sm):
    Table(
        cache_id="scans",
        data=scan("flashdeconv/scans"),
        index_field="scan_id",
        interactivity={"scan": "scan_id"},
        column_definitions=[
            {"field": "scan_id", "title": "Scan", "sorter": "number"},
            {"field": "ms_level", "title": "MS level", "sorter": "number"},
            {"field": "rt", "title": "RT (s)", "sorter": "number"},
            {"field": "precursor_mass", "title": "Precursor mass", "sorter": "number"},
            {"field": "n_masses", "title": "Masses", "sorter": "number"},
        ],
    )(state_manager=sm)


layout.render(
    title="Table",
    summary=(
        "Every MS scan in a top-down FLASHDeconv run. Pagination, sorting and column "
        "filters are handled in Python against the Parquet cache, so the browser only "
        "ever receives one page of rows."
    ),
    example=example,
    component=Table,
    used=["cache_id", "data", "index_field", "interactivity", "column_definitions"],
    tables=["flashdeconv/scans.parquet"],
    notes=(
        "Clicking a row writes the `scan` identifier into the shared selection state. "
        "On its own that does nothing visible -- see **Scan table -> spectrum** for "
        "what another component does with it."
    ),
)
