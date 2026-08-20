"""Sequence view: fragment-ion matching against a peptide."""

import polars as pl
from src import layout
from src.dataset import scan

from openms_insight import SequenceView


def example(sm):
    SequenceView(
        cache_id="psm",
        sequence_data=("ILNNGHAFNVEFDDSQDK", 2),
        peaks_data=scan("pxd044981/psm_peaks").filter(pl.col("scan_id") == 44672),
        interactivity={"peak": "peak_id"},
        annotation_config={"ion_types": ["b", "y"], "tolerance": 20.0},
        title="Carbonic anhydrase 2 (P00918), scan 44672",
    )(state_manager=sm)


layout.render(
    title="Sequence view",
    summary=(
        "A tryptic peptide of human carbonic anhydrase 2 — one of the UPS2 spike-in "
        "proteins flagged on the volcano page — with its 58 observed fragment masses "
        "matched to b and y ions in the browser."
    ),
    example=example,
    component=SequenceView,
    used=[
        "cache_id",
        "sequence_data",
        "peaks_data",
        "interactivity",
        "annotation_config",
        "title",
    ],
    tables=["pxd044981/psm_peaks.parquet", "pxd044981/psm_sequences.parquet"],
    notes=(
        "Fragment matching happens in the browser, not in Python. The component "
        "returns the matches it found, which is what lets another component annotate "
        "itself with them — see **Sequence → mirror plot**.\n\n"
        "The sequence and charge are written out as literals above; they come from "
        "`psm_sequences` (shown under **Data**), which this example never has to read. "
        "Peaks here are "
        "singly-charged m/z values, so `deconvolved` stays at its default of `False` "
        "and charge states 1 to 2 are considered."
    ),
)
