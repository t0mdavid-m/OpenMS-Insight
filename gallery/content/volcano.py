"""Volcano plot: differential abundance with a known ground truth."""

from src import layout
from src.dataset import scan

from openms_insight import VolcanoPlot


def example(sm):
    VolcanoPlot(
        cache_id="volcano",
        data=scan("pxd044981/proteins"),
        log2fc_column="log2FC",
        pvalue_column="padj",
        label_column="protein_id",
        interactivity={"protein": "protein_id"},
        y_label="-log10 adjusted p",
    )(state_manager=sm, fc_threshold=1.0, p_threshold=0.05)


layout.render(
    title="Volcano plot",
    summary=(
        "2,463 proteins from a UPS2 spike-in benchmark: a defined protein standard "
        "added to a constant yeast background at two levels, three replicates each. "
        "The background should sit at zero and the spike-ins should move — which is "
        "exactly what you see."
    ),
    example=example,
    component=VolcanoPlot,
    used=[
        "cache_id",
        "data",
        "log2fc_column",
        "pvalue_column",
        "label_column",
        "interactivity",
        "y_label",
    ],
    tables=["pxd044981/proteins.parquet"],
    notes=(
        "This dataset has a ground truth, which is rare and useful. Yeast background "
        "proteins centre on a log2 fold change of −0.11; the 23 UPS2 spike-ins sit at "
        "+3.37. Eleven proteins clear both thresholds and ten of them are genuine "
        "spike-ins — one false positive, and a recall of 43% that is honest for "
        "label-free DDA at three replicates."
    ),
)
