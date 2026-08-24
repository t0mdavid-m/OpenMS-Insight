"""Linking: fragment matches annotate a mirror plot."""

import polars as pl
from src import layout
from src.dataset import scan

from openms_insight import MirrorPlot, SequenceView


def example(sm):
    matches = SequenceView(
        cache_id="linked_psm",
        sequence_data=("ILNNGHAFNVEFDDSQDK", 2),
        peaks_data=scan("pxd044981/psm_peaks").filter(pl.col("scan_id") == 44672),
        annotation_config={"ion_types": ["b", "y"], "tolerance": 20.0},
    )(key="sv", state_manager=sm)

    mirror = MirrorPlot(
        cache_id="linked_mirror",
        data=scan("pxd044981/psm_peaks"),
        filters_top={"psm_top": "scan_id"},
        filter_defaults_top={"psm_top": 44672},
        filters_bottom={"psm_bottom": "scan_id"},
        filter_defaults_bottom={"psm_bottom": 47417},
        # Annotations are keyed by the interactivity column's value, so the mirror
        # plot has to name that column for the matches to land anywhere.
        interactivity={"peak": "peak_id"},
        x_column="mass",
        y_column="intensity",
        title_top="Scan 44672",
        title_bottom="Scan 47417",
        x_label="Fragment m/z",
    )

    if matches.annotations is not None:
        mirror.set_top_dynamic_annotations(
            {
                row["peak_id"]: {"highlight": True, "annotation": row["annotation"]}
                for row in matches.annotations.to_dicts()
            }
        )

    mirror(key="mirror", state_manager=sm)


layout.render(
    title="Sequence → mirror plot",
    summary=(
        "The sequence view matches fragment ions in the browser and hands the matches "
        "back to Python, which uses them to label the top half of the mirror plot. "
        "Both halves are real PSMs of the same peptide from different runs."
    ),
    example=example,
    component=None,
    tables=["pxd044981/psm_peaks.parquet"],
    notes=(
        "Annotations deliberately live outside the disk cache. They are recomputed and "
        "re-applied on every render, and contribute to a separate hash used to decide "
        "whether cached data is still valid — so changing the peptide relabels the "
        "plot without rebuilding the cache."
    ),
)
