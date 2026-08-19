"""Derive the gallery's example dataset from published source data.

This is a one-time, offline **derivation** (see CONTEXT.md): it turns published
mass-spectrometry data into the small, clean tables the gallery's examples render.
It is deliberately not part of CI or of the Docker build -- its inputs are published
measurements that never change, and running it requires multi-gigabyte downloads.

Sources
-------
FLASHApp (top-down, FLASHDeconv)
    Parquet files shipped in OpenMS/FLASHApp under
    ``example-data/workspaces/default/flashdeconv/cache/files/example_fd/``.
    These are FLASHApp's *internal cache* format -- one row per scan with nested
    list columns -- so they are exploded into long format here.

ProteomeXchange PXD044981 (bottom-up, MaxQuant)
    "Benchmarking DIA data analysis workflows": UPS2 protein standard spiked into a
    constant yeast background at five ratios, three replicate DDA runs each.
    We use the authors' own MaxQuant search results from ``DDA.7z``.

Usage
-----
    python tools/derive_example_dataset.py \
        --flashapp   <dir with FLASHApp *.pq> \
        --maxquant   <MaxQuant combined/txt dir> \
        --out        <output dir> \
        --version    v1

Outputs ``<out>/openms-insight-example-data-<version>.tar.gz`` plus its SHA-256 and a
``manifest.json`` recording provenance for every table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from datetime import date
from pathlib import Path
from typing import Any, Dict

import numpy as np
import polars as pl

# The peptide backing the SequenceView and MirrorPlot examples: a tryptic peptide of
# human carbonic anhydrase 2 (P00918), one of the UPS2 spike-in proteins, so the same
# molecule appears in the volcano plot. Chosen for complete fragment coverage.
SHOWCASE_PEPTIDE = "ILNNGHAFNVEFDDSQDK"

# Volcano contrast: highest vs lowest UPS2 spike-in level, three replicates each.
GROUP_A = "ratio01_DDA"  # lowest spike-in
GROUP_B = "ratio10_DDA"  # highest spike-in
MIN_REPLICATES = 2  # per group, to admit a protein to the test


# --------------------------------------------------------------------------- #
# FLASHApp: top-down FLASHDeconv results
# --------------------------------------------------------------------------- #
def derive_flashdeconv(src: Path, out: Path) -> Dict[str, Any]:
    """Explode FLASHApp's per-scan cache format into long tables."""
    out.mkdir(parents=True, exist_ok=True)

    scan_table = pl.read_parquet(src / "scan_table.pq")
    # Rounded for display: this table is rendered as text, and full binary float
    # expansion (3901.4208984375) is noise rather than precision. 10 ms on retention
    # time and 0.1 mDa on mass are both far below anything the instrument resolves.
    scans = scan_table.select(
        pl.col("Scan").cast(pl.Int32).alias("scan_id"),
        pl.col("MSLevel").cast(pl.Int8).alias("ms_level"),
        pl.col("RT").round(2).cast(pl.Float64).alias("rt"),
        pl.col("PrecursorMass").round(4).cast(pl.Float64).alias("precursor_mass"),
        pl.col("#Masses").cast(pl.Int32).alias("n_masses"),
    ).sort("scan_id")
    scans.write_parquet(out / "scans.parquet", compression="zstd")

    # MS1 map: already long (mass, rt, intensity). Carries only a retention time, so
    # attach the scan each point was acquired in -- that gives the heatmap the same
    # 'scan' identifier the scan table and spectrum plot use, and turns clicking the
    # map into a real cross-component link rather than a dead end.
    #
    # The join key is retention time rounded to 2 dp, matching the scan table above.
    # Consecutive MS1 scans here are ~4 s apart, so 10 ms of rounding cannot make the
    # match ambiguous. Rounding is applied before the Float32 downcast: 2 dp is not
    # representable in Float32, so rounding afterwards would not line up.
    ms1_scans = scans.filter(pl.col("ms_level") == 1).select(
        pl.col("rt").alias("_rt_key"), "scan_id"
    )
    ms1 = (
        pl.read_parquet(src / "ms1_raw_heatmap.pq")
        .with_columns(pl.col("rt").cast(pl.Float64).round(2).alias("_rt_key"))
        .join(ms1_scans, on="_rt_key", how="left")
        .select(
            pl.col("rt").cast(pl.Float32),
            pl.col("mass").cast(pl.Float32),
            pl.col("intensity").cast(pl.Float32),
            pl.col("scan_id").cast(pl.Int32),
        )
        .sort("rt")
    )
    unmatched = ms1["scan_id"].null_count()
    if unmatched:
        raise RuntimeError(
            f"{unmatched} MS1 map points did not match a scan on retention time. "
            "The rounding used for the join no longer lines up with the scan table."
        )
    ms1.write_parquet(out / "ms1_map.parquet", compression="zstd")

    # Deconvolved peaks: one row per scan with list columns -> one row per peak.
    peaks = (
        pl.read_parquet(src / "deconv_spectrum.pq")
        .join(scan_table.select(["index", "Scan"]), on="index", how="left")
        .select(
            pl.col("Scan").cast(pl.Int32).alias("scan_id"),
            pl.col("MonoMass").alias("mass"),
            pl.col("SumIntensity").alias("intensity"),
        )
        .explode(["mass", "intensity"])
        .drop_nulls("mass")
        .with_columns(
            pl.col("mass").cast(pl.Float64),
            pl.col("intensity").cast(pl.Float32),
        )
        .sort(["scan_id", "mass"])
        .with_row_index("peak_id")
        .select(["scan_id", "peak_id", "mass", "intensity"])
    )
    peaks.write_parquet(out / "deconv_peaks.parquet", compression="zstd")

    return {
        "scans.parquet": {
            "rows": scans.height,
            "columns": scans.columns,
            "description": "One row per MS scan: retention time, MS level, precursor "
            "mass and deconvolved mass count.",
            "derived_from": "scan_table.pq",
            "transformation": "Renamed to snake_case and downcast; no filtering.",
        },
        "ms1_map.parquet": {
            "rows": ms1.height,
            "columns": ms1.columns,
            "description": "MS1 retention-time x neutral-mass intensity map, with "
            "the scan each point was acquired in.",
            "derived_from": "ms1_raw_heatmap.pq + scan_table.pq",
            "transformation": "Renamed and downcast to Float32; joined scan_id on "
            "retention time rounded to 2 dp (MS1 scans are ~4 s apart, so the "
            "match is unambiguous); sorted by rt.",
        },
        "deconv_peaks.parquet": {
            "rows": peaks.height,
            "columns": peaks.columns,
            "description": "Deconvolved neutral-mass peaks, one row per peak.",
            "derived_from": "deconv_spectrum.pq + scan_table.pq",
            "transformation": "Exploded nested list columns into long format and "
            "joined scan numbers; assigned a stable peak_id.",
        },
    }


# --------------------------------------------------------------------------- #
# PXD044981: differential abundance for the volcano plot
# --------------------------------------------------------------------------- #
def derive_volcano(txt: Path, out: Path) -> Dict[str, Any]:
    """Protein-level differential abundance from MaxQuant evidence.txt.

    MaxQuant merged the three replicate runs of each spike-in ratio into a single
    experiment, so protein-level LFQ columns carry no replicates. We therefore
    aggregate ``evidence.txt`` per (protein, raw file), which recovers n=3 per group
    and makes a genuine Welch t-test possible.
    """
    from scipy.stats import ttest_ind
    from statsmodels.stats.multitest import multipletests

    evidence = (
        pl.scan_csv(txt / "evidence.txt", separator="\t", infer_schema_length=0)
        .select(
            [
                "Leading razor protein",
                "Gene names",
                "Raw file",
                "Intensity",
                "Reverse",
                "Potential contaminant",
            ]
        )
        .with_columns(
            pl.col("Reverse").fill_null(""),
            pl.col("Potential contaminant").fill_null(""),
            pl.col("Intensity").cast(pl.Float64, strict=False),
        )
        .filter((pl.col("Reverse") != "+") & (pl.col("Potential contaminant") != "+"))
        .drop_nulls("Intensity")
        .filter(pl.col("Intensity") > 0)
        .collect()
    )

    genes = evidence.group_by("Leading razor protein").agg(
        pl.col("Gene names").drop_nulls().first().alias("gene")
    )
    matrix = (
        evidence.group_by(["Leading razor protein", "Raw file"])
        .agg(pl.col("Intensity").sum().alias("intensity"))
        .pivot(values="intensity", index="Leading razor protein", on="Raw file")
    )

    run_columns = [c for c in matrix.columns if c != "Leading razor protein"]
    log_intensity = np.log2(matrix.select(run_columns).to_numpy())
    # Median-normalise each run to remove loading differences between injections.
    log_intensity = (
        log_intensity
        - np.nanmedian(log_intensity, axis=0, keepdims=True)
        + np.nanmedian(log_intensity)
    )

    a_idx = [i for i, c in enumerate(run_columns) if GROUP_A in c]
    b_idx = [i for i, c in enumerate(run_columns) if GROUP_B in c]
    if not a_idx or not b_idx:
        raise SystemExit(f"Could not find runs for {GROUP_A} / {GROUP_B}")

    a, b = log_intensity[:, a_idx], log_intensity[:, b_idx]
    testable = ((~np.isnan(a)).sum(1) >= MIN_REPLICATES) & (
        (~np.isnan(b)).sum(1) >= MIN_REPLICATES
    )
    log2fc = np.nanmean(b, 1) - np.nanmean(a, 1)
    _, pvalue = ttest_ind(b, a, axis=1, nan_policy="omit", equal_var=False)
    pvalue = np.asarray(pvalue, dtype=float)

    valid = testable & np.isfinite(pvalue) & np.isfinite(log2fc)
    padj = np.full_like(pvalue, np.nan)
    padj[valid] = multipletests(pvalue[valid], method="fdr_bh")[1]

    proteins = (
        pl.DataFrame(
            {
                "protein_id": matrix["Leading razor protein"],
                "log2FC": log2fc,
                "pvalue": pvalue,
                "padj": padj,
                "n_a": (~np.isnan(a)).sum(1),
                "n_b": (~np.isnan(b)).sum(1),
            }
        )
        .filter(pl.Series(valid))
        .join(genes, left_on="protein_id", right_on="Leading razor protein", how="left")
        # UPS2 spike-in proteins carry a 'ups' suffix in this FASTA; everything else
        # is the constant yeast background. This is the dataset's ground truth.
        .with_columns(
            pl.col("protein_id")
            .str.to_lowercase()
            .str.contains("ups")
            .alias("spike_in")
        )
        .with_columns(pl.col("gene").fill_null(""))
        .sort("padj")
    )
    proteins.write_parquet(out / "proteins.parquet", compression="zstd")

    n_spike = int(proteins["spike_in"].sum())
    significant = proteins.filter(
        (pl.col("padj") < 0.05) & (pl.col("log2FC").abs() > 1)
    )
    return {
        "proteins.parquet": {
            "rows": proteins.height,
            "columns": proteins.columns,
            "description": (
                f"Protein-level differential abundance, {GROUP_B} vs {GROUP_A} "
                f"(UPS2 spike-in, highest vs lowest level), three replicates each. "
                f"{n_spike} spike-in proteins against a constant yeast background; "
                f"{significant.height} proteins significant at padj<0.05 and "
                f"|log2FC|>1, of which {int(significant['spike_in'].sum())} are "
                f"true spike-ins."
            ),
            "derived_from": "evidence.txt",
            "transformation": (
                "Removed reverse hits and contaminants; summed evidence intensities "
                "per (leading razor protein, raw file); log2-transformed and "
                "median-normalised each run; Welch t-test across three replicates "
                "per group; Benjamini-Hochberg FDR correction."
            ),
        }
    }


# --------------------------------------------------------------------------- #
# PXD044981: fragment spectra for SequenceView and MirrorPlot
# --------------------------------------------------------------------------- #
def derive_psms(txt: Path, out: Path) -> Dict[str, Any]:
    """Fragment peak lists for the showcase peptide, one row per peak."""
    psms = (
        pl.scan_csv(txt / "msms.txt", separator="\t", infer_schema_length=0)
        .select(
            [
                "Raw file",
                "Scan number",
                "Sequence",
                "Modified sequence",
                "Proteins",
                "Charge",
                "m/z",
                "Score",
                "Matches",
                "Masses",
                "Intensities",
                "Reverse",
            ]
        )
        .with_columns(
            pl.col("Reverse").fill_null(""),
            pl.col("Score").cast(pl.Float64, strict=False),
        )
        .filter((pl.col("Reverse") != "+") & (pl.col("Sequence") == SHOWCASE_PEPTIDE))
        .sort("Score", descending=True)
        .head(6)
        .collect(engine="streaming")
    )
    if psms.is_empty():
        raise SystemExit(f"Showcase peptide {SHOWCASE_PEPTIDE} not found in msms.txt")

    peak_rows, sequence_rows = [], []
    for psm in psms.to_dicts():
        scan_id = int(psm["Scan number"])
        masses = [float(x) for x in psm["Masses"].split(";") if x]
        intensities = [float(x) for x in psm["Intensities"].split(";") if x]
        ions = (psm["Matches"] or "").split(";")
        for i, (mass, intensity) in enumerate(zip(masses, intensities)):
            peak_rows.append(
                {
                    "scan_id": scan_id,
                    "peak_id": i,
                    "mass": mass,
                    "intensity": intensity,
                    "ion": ions[i] if i < len(ions) else "",
                }
            )
        sequence_rows.append(
            {
                "sequence_id": scan_id,
                "scan_id": scan_id,
                "sequence": psm["Sequence"],
                "precursor_charge": int(psm["Charge"]),
                "precursor_mz": float(psm["m/z"]),
                "protein_id": psm["Proteins"],
                "score": float(psm["Score"]),
                "raw_file": psm["Raw file"],
            }
        )

    peaks = pl.DataFrame(peak_rows).with_columns(
        pl.col("scan_id").cast(pl.Int32),
        pl.col("peak_id").cast(pl.Int32),
        pl.col("mass").cast(pl.Float64),
        pl.col("intensity").cast(pl.Float32),
    )
    sequences = pl.DataFrame(sequence_rows).with_columns(
        pl.col("sequence_id").cast(pl.Int32),
        pl.col("scan_id").cast(pl.Int32),
        pl.col("precursor_charge").cast(pl.Int8),
    )
    peaks.write_parquet(out / "psm_peaks.parquet", compression="zstd")
    sequences.write_parquet(out / "psm_sequences.parquet", compression="zstd")

    return {
        "psm_peaks.parquet": {
            "rows": peaks.height,
            "columns": peaks.columns,
            "description": (
                f"Singly-charged fragment m/z peaks for {len(sequence_rows)} spectra "
                f"of peptide {SHOWCASE_PEPTIDE} (human carbonic anhydrase 2, "
                f"UPS2 spike-in P00918), with MaxQuant's matched ion labels."
            ),
            "derived_from": "msms.txt",
            "transformation": "Split semicolon-separated Masses/Intensities/Matches "
            "into one row per peak.",
        },
        "psm_sequences.parquet": {
            "rows": sequences.height,
            "columns": sequences.columns,
            "description": "Peptide sequence, precursor charge and score per spectrum.",
            "derived_from": "msms.txt",
            "transformation": "One row per selected PSM.",
        },
    }


# --------------------------------------------------------------------------- #
# Packaging
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flashapp", type=Path, required=True)
    parser.add_argument("--maxquant", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    stage = args.out / f"openms-insight-example-data-{args.version}"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "flashdeconv").mkdir(parents=True)
    (stage / "pxd044981").mkdir(parents=True)

    print("Deriving FLASHDeconv tables ...")
    flash = derive_flashdeconv(args.flashapp, stage / "flashdeconv")
    print("Deriving differential abundance ...")
    volcano = derive_volcano(args.maxquant, stage / "pxd044981")
    print("Deriving fragment spectra ...")
    psms = derive_psms(args.maxquant, stage / "pxd044981")

    manifest = {
        "name": "openms-insight-example-data",
        "version": args.version,
        "generated": date.today().isoformat(),
        "license": "BSD-3-Clause (OpenMS); source data as cited below",
        "sources": {
            "flashapp": {
                "repository": "https://github.com/OpenMS/FLASHApp",
                "path": "example-data/workspaces/default/flashdeconv/"
                "cache/files/example_fd/",
                "kind": "Top-down FLASHDeconv results (internal cache format)",
                "sample": "TODO: provenance of example_fd.mzML not documented "
                "upstream; confirm with FLASHApp maintainers.",
            },
            "pxd044981": {
                "accession": "PXD044981",
                "title": "Benchmarking DIA data analysis workflows",
                "url": "https://www.ebi.ac.uk/pride/archive/projects/PXD044981",
                "doi": "10.1021/acs.jproteome.4c00048",
                "file": "DDA.7z -> combined_DDA_LFQ_MBR_onlyUPS2Excl2023",
                "kind": "MaxQuant search results from DDA runs",
                "design": "UPS2 protein standard spiked into constant yeast "
                "background at five ratios, three replicate DDA runs each; "
                "Q Exactive HF.",
            },
        },
        "tables": {
            **{f"flashdeconv/{k}": v for k, v in flash.items()},
            **{f"pxd044981/{k}": v for k, v in {**volcano, **psms}.items()},
        },
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    tarball = args.out / f"openms-insight-example-data-{args.version}.tar.gz"
    print(f"Writing {tarball.name} ...")
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(stage, arcname=stage.name)
    checksum = sha256(tarball)
    (args.out / f"{tarball.name}.sha256").write_text(f"{checksum}  {tarball.name}\n")

    print(f"\n{tarball}")
    print(f"  size     {tarball.stat().st_size / 1e6:.1f} MB")
    print(f"  sha256   {checksum}")
    for name, info in manifest["tables"].items():
        print(f"  {name:36s} {info['rows']:>9,d} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
