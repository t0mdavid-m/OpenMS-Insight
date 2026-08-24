"""Clustered heatmap: the spike-in proteins, grouped by how they behave."""

from src import layout
from src.dataset import scan, table

from openms_insight import ClusteredHeatmap


def example(sm):
    ClusteredHeatmap(
        cache_id="spike_in_clusters",
        data=scan("pxd044981/spike_in_matrix"),
        id_col="protein_id",
        metadata=table("pxd044981/samples"),
        title="UPS2 spike-in proteins",
        intensity_label="log2 intensity",
    )(state_manager=sm)


layout.render(
    title="Clustered heatmap",
    summary=(
        "The 22 UPS2 proteins across all 15 runs, with both axes hierarchically "
        "clustered. Every spike-in level's three replicates end up side by side — "
        "five groups of three, recovered from the numbers alone."
    ),
    example=example,
    component=ClusteredHeatmap,
    used=["cache_id", "data", "id_col", "metadata", "title", "intensity_label"],
    tables=[
        "pxd044981/spike_in_matrix.parquet",
        "pxd044981/samples.parquet",
    ],
    notes=(
        "`id_col` names the row identity; every *other* column is treated as a "
        "sample. That is why the matrix carries nothing else — an extra annotation "
        "column would be read as another run.\n\n"
        "The column dendrogram is the honest test here. Clustering is given only the "
        "numbers, never the group labels; those are used solely to colour the bar "
        "along the top. All five levels come back as contiguous blocks of three, so "
        "that is a result rather than an arrangement. The *order* of the blocks is "
        "not — a dendrogram can be rotated at any branch, so read which runs group "
        "together, not which group sits on the left.\n\n"
        "One row is `P00918ups`, carbonic anhydrase 2 — the same protein whose "
        "peptide backs the **Sequence view** and **Mirror plot** pages, and a "
        "significant hit on the **Volcano plot**."
    ),
)
