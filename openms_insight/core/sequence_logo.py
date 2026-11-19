"""Letter heights of a sequence logo, computed from aligned sequences.

At each position the residues' frequencies ``f`` are compared with a
background ``q``: the position's information content is the relative entropy
``IC = sum(f * log2(f / q))`` in bits, and each residue is drawn ``f * IC``
high (``units="bits"``). With a uniform background over an alphabet of ``N``
residues this is ``log2(N) - H``, the usual logo. ``units="probability"``
draws the frequencies themselves. Streamlit-free.
"""

import math
from typing import Any

import polars as pl

#: The 20 standard amino acids.
PROTEIN = "ACDEFGHIKLMNPQRSTVWY"
#: DNA and RNA.
DNA = "ACGT"
RNA = "ACGU"

UNITS = ("bits", "probability")

#: Default colours: amino acids by chemistry, nucleotides as usual.
DEFAULT_COLORS: dict[str, str] = {
    # hydrophobic
    **dict.fromkeys("AVLIMFWC", "#7d8590"),
    # polar
    **dict.fromkeys("STYNQ", "#2e7d32"),
    "G": "#7b1fa2",
    "P": "#7b1fa2",
    # basic
    **dict.fromkeys("KRH", "#1565c0"),
    # acidic
    **dict.fromkeys("DE", "#c62828"),
}
NUCLEOTIDE_COLORS = {"A": "#2e7d32", "C": "#1565c0", "G": "#f9a825", "T": "#c62828"}
NUCLEOTIDE_COLORS["U"] = NUCLEOTIDE_COLORS["T"]


def normalize_alphabet(alphabet: str | None) -> str:
    """``"protein"``, ``"dna"``, ``"rna"`` or the residues themselves."""
    if alphabet is None or alphabet == "protein":
        return PROTEIN
    if alphabet == "dna":
        return DNA
    if alphabet == "rna":
        return RNA
    if not isinstance(alphabet, str) or not alphabet:
        raise ValueError("alphabet must be 'protein', 'dna', 'rna' or its residues")
    residues = "".join(dict.fromkeys(alphabet))
    if len(residues) < 2:
        raise ValueError("alphabet needs at least two residues")
    return residues


def normalize_background(background: Any, alphabet: str) -> dict[str, float]:
    """The background frequencies, summing to 1: uniform, or a dict per residue."""
    if background is None or background == "uniform":
        return dict.fromkeys(alphabet, 1.0 / len(alphabet))
    if not isinstance(background, dict):
        raise ValueError("background must be 'uniform' or a dict residue -> frequency")
    unknown = [r for r in background if r not in alphabet]
    if unknown:
        raise ValueError(f"background has residues outside the alphabet: {unknown}")
    values = {r: float(background.get(r, 0.0)) for r in alphabet}
    if any(v <= 0 or math.isnan(v) for v in values.values()):
        missing = [r for r, v in values.items() if not v > 0]
        raise ValueError(f"background needs a frequency above 0 for {missing}")
    total = sum(values.values())
    return {r: v / total for r, v in values.items()}


def default_colors(alphabet: str) -> dict[str, str]:
    """Colours for the residues of ``alphabet``."""
    table = NUCLEOTIDE_COLORS if set(alphabet) <= set("ACGTU") else DEFAULT_COLORS
    return {r: table.get(r, "#616161") for r in alphabet}


def max_height(units: str, alphabet: str) -> float:
    """Height of the y axis: what a fully conserved position carries against a
    uniform background (log2 of the alphabet's size), or 1. A position over a
    skewed background can carry more; the axis then grows to it."""
    if units == "probability":
        return 1.0
    return math.log2(len(alphabet))


def logo_frame(
    data: pl.LazyFrame | pl.DataFrame,
    sequence_column: str,
    alphabet: str,
    background: dict[str, float],
    units: str = "bits",
    weight_column: str | None = None,
) -> pl.DataFrame:
    """One row per position and residue: ``position`` (0-based), ``residue``,
    ``count`` (weighted), ``frequency`` and ``height``, residues of a position
    from the lowest letter to the highest. Characters outside the alphabet
    (gaps, ``X``) are not counted; a position without any residue is left out.
    """
    if units not in UNITS:
        raise ValueError(f"units must be one of {UNITS}, got {units!r}")
    frame = data.lazy() if isinstance(data, pl.DataFrame) else data
    weight = pl.col(weight_column).cast(pl.Float64) if weight_column else pl.lit(1.0)
    counts = (
        frame.select(
            pl.col(sequence_column).cast(pl.Utf8).str.split("").alias("residue"),
            weight.alias("weight"),
        )
        .drop_nulls("residue")
        .with_columns(pl.int_ranges(pl.col("residue").list.len()).alias("position"))
        .explode(["residue", "position"])
        .filter(pl.col("residue").is_in(list(alphabet)))
        .group_by("position", "residue")
        .agg(pl.col("weight").sum().alias("count"))
        .filter(pl.col("count") > 0)
        .collect()
    )
    schema = {
        "position": pl.Int64,
        "residue": pl.Utf8,
        "count": pl.Float64,
        "frequency": pl.Float64,
        "height": pl.Float64,
    }
    if counts.height == 0:
        return pl.DataFrame(schema=schema)
    q = pl.col("q")
    counts = counts.join(
        pl.DataFrame(
            {"residue": list(background), "q": list(background.values())},
            schema={"residue": pl.Utf8, "q": pl.Float64},
        ),
        on="residue",
        how="left",
    ).with_columns(
        pl.col("position").cast(pl.Int64),
        pl.col("count").cast(pl.Float64),
        (pl.col("count") / pl.col("count").sum().over("position")).alias("frequency"),
    )
    if units == "bits":
        counts = counts.with_columns(
            (pl.col("frequency") * (pl.col("frequency") / q).log(2))
            .sum()
            .over("position")
            .clip(lower_bound=0.0)
            .alias("ic")
        ).with_columns((pl.col("frequency") * pl.col("ic")).alias("height"))
    else:
        counts = counts.with_columns(pl.col("frequency").alias("height"))
    return counts.sort(
        ["position", "height", "residue"], descending=[False, False, True]
    ).select(list(schema))
