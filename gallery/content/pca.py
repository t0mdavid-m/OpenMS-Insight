"""PCA: samples arranged by how alike their proteomes are."""

from src import layout
from src.dataset import scan, table

from openms_insight import PCAPlot


def example(sm):
    PCAPlot(
        cache_id="sample_pca",
        data=scan("pxd044981/quant_matrix"),
        metadata=table("pxd044981/samples"),
        interactivity={"sample": "sample_id"},
        title="UPS2 spike-in series",
    )(state_manager=sm)


layout.render(
    title="PCA",
    summary=(
        "Fifteen DDA runs of the same yeast background with a UPS2 protein standard "
        "spiked in at five levels, three replicates each. Every run is one point, "
        "placed by 2,062 protein abundances and coloured by spike-in level."
    ),
    example=example,
    component=PCAPlot,
    used=["cache_id", "data", "metadata", "interactivity", "title"],
    tables=["pxd044981/quant_matrix.parquet", "pxd044981/samples.parquet"],
    notes=(
        "Two tables, joined by name: the quantification matrix has one column per "
        "sample, and `metadata` says which group each of those columns belongs to. "
        "The component matches them on `sample_id`, so the column names in the matrix "
        "are the contract between the two.\n\n"
        "Read the plot honestly. PC1 does order the spike-in levels — |ρ| ≈ 0.84 "
        "between level and PC1 — but adjacent levels overlap and replicates scatter "
        "widely. That is the dataset, not the method: only 22 of these 2,062 proteins "
        "change by design, and the constant yeast background contributes most of the "
        "variance PCA is fitting. Restricted to those 22 the same runs order almost "
        "perfectly (|ρ| ≈ 0.98), which is what the **Clustered heatmap** page shows. "
        "The sign of a principal component is arbitrary, so only the magnitude means "
        "anything."
    ),
)
