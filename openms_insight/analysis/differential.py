"""Group comparison in one call: filter, impute, transform/normalize/scale, test, adjust.

Chains the functions of :mod:`openms_insight.analysis` with one settings dict, so
every app that compares conditions (proteins, proteoforms, metabolite features,
...) runs the same steps with the same settings and defaults. It implements the
comparison chain (B3) of the quantification spec in OpenMS/streamlit-template
(``docs/quantification-spec.md``).

Streamlit-free: apps call :func:`run_differential` wherever they like and keep
the returned tables in their own store.
"""

from __future__ import annotations

import pandas as pd
import polars as pl

from openms_insight.analysis.filter import (
    filter_low_abundance,
    filter_low_repeatability,
    filter_low_variance,
)
from openms_insight.analysis.imputation import impute_mar, impute_smallest_value
from openms_insight.analysis.normalization import (
    normalize_samples,
    scale_data,
    transform_data,
)
from openms_insight.analysis.statistics import (
    adjust_fdr_lazy,
    calculate_statistical_tests,
)

STAT_COLUMNS = ["log2FC", "p-value", "p-adj", "stat"]

# Keys of the intermediate tables, in chain order.
STEPS = ["filtered_df", "imputed_df", "normalized_df", "statistics_df"]

# Group label of samples that take no part in the comparison.
UNASSIGNED = "Unassigned"

DEFAULT_SETTINGS = {
    "postproc-filter-method": "Low Repeatability",
    "postproc-filter-abundance-percentile": 10.0,
    "postproc-filter-max-missing": 50.0,
    "postproc-filter-variance-percentile": 10.0,
    "postproc-impute-class": "MNAR (Missing Not At Random)",
    "postproc-impute-mar-strategy": "median",
    "postproc-impute-mnar-scope": "row",
    "postproc-transform": "log2",
    "postproc-normalization": "median",
    "postproc-scaling": "None",
    "postproc-stat-test": "limma_like",
    "postproc-fdr": "BH",
}

SETTING_KEYS = list(DEFAULT_SETTINGS)

# Choices of every setting that has a fixed set; the percentages are 0-100.
OPTIONS = {
    "postproc-filter-method": ["Low Repeatability", "Low Abundance", "Low Variance"],
    "postproc-impute-class": [
        "MNAR (Missing Not At Random)",
        "MAR (Missing At Random)",
    ],
    "postproc-impute-mar-strategy": ["median", "mean"],
    "postproc-impute-mnar-scope": ["row", "global"],
    "postproc-transform": ["None", "log2", "log10", "square_root", "cube_root"],
    "postproc-normalization": [
        "None",
        "sum",
        "median",
        "pqn",
        "reference_feature",
        "quantile",
    ],
    "postproc-scaling": [
        "None",
        "mean_centering",
        "auto_scaling",
        "pareto_scaling",
        "range_scaling",
    ],
    "postproc-stat-test": ["limma_like", "welch", "paired", "anova"],
    "postproc-fdr": ["BH", "Bonferroni", "None"],
}

TWO_GROUP_TESTS = ["limma_like", "welch", "paired"]
MULTI_GROUP_TESTS = ["limma_like", "anova"]


def resolve_settings(params: dict, defaults: dict | None = None) -> dict:
    """Settings from ``params`` where present, ``defaults`` for the rest."""
    defaults = (
        DEFAULT_SETTINGS if defaults is None else {**DEFAULT_SETTINGS, **defaults}
    )
    return {k: params.get(k, defaults[k]) for k in SETTING_KEYS}


def strip_stat_columns(df: pd.DataFrame) -> pd.DataFrame:
    """``df`` without the columns a previous test added."""
    return df.drop(columns=[c for c in STAT_COLUMNS if c in df.columns])


def tests_for(n_groups: int) -> list[str]:
    """Tests that fit ``n_groups`` conditions."""
    return TWO_GROUP_TESTS if n_groups == 2 else MULTI_GROUP_TESTS


def _pairs_match(sample_group_map: dict, replicates: dict | None) -> bool:
    """True when both conditions have the same set of replicate numbers."""
    by_group: dict[str, list] = {}
    for sample, group in sample_group_map.items():
        if group == UNASSIGNED:
            continue
        by_group.setdefault(group, []).append(
            None if replicates is None else replicates.get(sample)
        )
    if len(by_group) != 2:
        return False
    first, second = by_group.values()
    if len(first) != len(second):
        return False
    if replicates is None:
        return True
    if None in first or None in second:
        return False
    return sorted(first) == sorted(second) and len(set(first)) == len(first)


def valid_test(
    test: str,
    n_groups: int,
    sample_group_map: dict | None = None,
    replicates: dict | None = None,
) -> str:
    """``test`` if it fits the design, else ``limma_like``.

    ``paired`` pairs replicate *n* of one condition with replicate *n* of the
    other, so it also needs both conditions to have the same replicate numbers
    (or, without ``replicates``, the same number of samples). Pass
    ``sample_group_map`` to have that checked.
    """
    if test not in tests_for(n_groups):
        return "limma_like"
    if test == "paired" and sample_group_map is not None:
        if not _pairs_match(sample_group_map, replicates):
            return "limma_like"
    return test


def describe_settings(settings: dict, entity: str = "protein") -> list[str]:
    """One plain-language line per step, for showing what was run.

    ``entity`` is the singular noun of a row (``"protein"``, ``"proteoform"``,
    ``"feature"``).
    """
    plural = f"{entity}s"
    method = settings["postproc-filter-method"]
    if method == "Low Repeatability":
        kept = 100 - float(settings["postproc-filter-max-missing"])
        filt = (
            f"kept {plural} measured in at least {kept:g} % of the samples of at "
            "least one group"
        )
    elif method == "Low Abundance":
        pct = float(settings["postproc-filter-abundance-percentile"])
        filt = f"removed the {pct:g} % least abundant {plural}"
    else:
        pct = float(settings["postproc-filter-variance-percentile"])
        filt = f"removed the {pct:g} % least variable {plural}"
    if settings["postproc-impute-class"].startswith("MNAR"):
        imp = (
            f"filled missing values with the {entity}'s lowest measured value "
            "(assumes they were too faint to detect)"
            if settings["postproc-impute-mnar-scope"] == "row"
            else "filled missing values with the lowest value of the whole dataset"
        )
    else:
        imp = (
            "filled missing values with the group "
            f"{settings['postproc-impute-mar-strategy']}"
        )
    norm = (
        f"{settings['postproc-transform']} transform, "
        f"{settings['postproc-normalization']} normalization"
    )
    if settings["postproc-scaling"] != "None":
        norm += f", {settings['postproc-scaling']} scaling"
    stat = (
        f"{settings['postproc-stat-test']} test, "
        f"{settings['postproc-fdr']} correction for multiple testing"
    )
    return [
        f"**Filtering:** {filt}",
        f"**Missing values:** {imp}",
        f"**Normalization:** {norm}",
        f"**Statistics:** {stat}",
    ]


def _metadata(sample_cols, sample_group_map, replicates) -> pl.DataFrame:
    """Sample -> group table, ordered by group and replicate.

    The paired test pairs samples by their position within each group, so the
    order is what makes replicate n of one group meet replicate n of the other.
    """
    rows = [
        {
            "sample_id": s,
            "group": sample_group_map[s],
            "_replicate": None if replicates is None else replicates.get(s),
            "_order": i,
        }
        for i, s in enumerate(sample_cols)
    ]
    metadata = pl.DataFrame(
        rows,
        schema={
            "sample_id": pl.String,
            "group": pl.String,
            "_replicate": pl.Int64,
            "_order": pl.Int64,
        },
    )
    sort_by = ["group", "_replicate", "_order"] if replicates else ["group", "_order"]
    return metadata.sort(sort_by, nulls_last=True).select("sample_id", "group")


def run_differential(
    abundances: pd.DataFrame,
    sample_group_map: dict,
    id_col: str,
    settings: dict | None = None,
    done: dict | None = None,
    entity: str = "protein",
    replicates: dict | None = None,
    reference_feature: str | None = None,
) -> dict:
    """Run the comparison chain and return every intermediate table.

    Args:
        abundances: One row per entity, ``id_col`` plus one column per sample
            with raw (not log) abundances; other columns are carried along.
        sample_group_map: Sample column -> condition. Samples mapped to
            ``"Unassigned"`` (or missing) stay in the tables but take no part
            in the comparison.
        id_col: Column identifying each row.
        settings: The ``postproc-*`` settings; missing keys take
            ``DEFAULT_SETTINGS``.
        done: Step tables (keys of ``STEPS``) already produced, e.g. by step
            pages that run one step at a time; the chain continues after the
            latest of them.
        entity: Singular noun of a row, used in error messages.
        replicates: Sample column -> biological replicate number. The paired
            test pairs samples by it; without it, by column order.
        reference_feature: Row id for ``reference_feature`` normalization;
            without one that strategy falls back to ``median``.

    Returns:
        ``filtered_df``, ``imputed_df``, ``normalized_df``, ``statistics_df``
        (pandas), plus ``normalized_transform`` (the transform applied),
        ``normalization`` (the strategy applied) and ``stat_test`` (the test
        applied, after :func:`valid_test`).

    Raises:
        ValueError: when the samples do not form at least two conditions, or
            no row passes the filter.
    """
    settings = resolve_settings(settings or {})
    done = {k: v for k, v in (done or {}).items() if k in STEPS and v is not None}
    # Steps before the latest finished one are not needed any more
    last_done = max((STEPS.index(k) for k in done), default=-1)
    skip = set(STEPS[: last_done + 1])
    sample_cols = [
        c
        for c in abundances.columns
        if sample_group_map.get(c, UNASSIGNED) != UNASSIGNED
    ]
    groups = sorted({sample_group_map[s] for s in sample_cols})
    if len(groups) < 2:
        raise ValueError(
            "Comparing needs samples of at least two conditions "
            "(e.g. control and treated)."
        )
    metadata = _metadata(sample_cols, sample_group_map, replicates)

    out = dict(done)
    out.setdefault("normalized_transform", settings["postproc-transform"])

    if "filtered_df" not in skip:
        data = pl.from_pandas(strip_stat_columns(abundances)).lazy()
        method = settings["postproc-filter-method"]
        if method == "Low Abundance":
            data = filter_low_abundance(
                quantification_data=data,
                metadata=metadata,
                group_column="group",
                threshold_percentile=float(
                    settings["postproc-filter-abundance-percentile"]
                ),
            )
        elif method == "Low Variance":
            data = filter_low_variance(
                quantification_data=data,
                metadata=metadata,
                group_column="group",
                threshold_percentile=float(
                    settings["postproc-filter-variance-percentile"]
                ),
            )
        else:
            data = filter_low_repeatability(
                quantification_data=data,
                metadata=metadata,
                group_column="group",
                max_missing_ratio=float(settings["postproc-filter-max-missing"])
                / 100.0,
            )
        out["filtered_df"] = strip_stat_columns(data.collect().to_pandas())
        if out["filtered_df"].empty:
            raise ValueError(
                f"No {entity} passed the filter. Relax it, e.g. allow more "
                "missing values."
            )

    if "imputed_df" not in skip:
        data = pl.from_pandas(out["filtered_df"]).lazy()
        if settings["postproc-impute-class"].startswith("MAR"):
            data = impute_mar(
                quantification_data=data,
                metadata=metadata,
                group_column="group",
                strategy=settings["postproc-impute-mar-strategy"],
            )
        else:
            data = impute_smallest_value(
                quantification_data=data,
                metadata=metadata,
                scope=settings["postproc-impute-mnar-scope"],
            )
        out["imputed_df"] = strip_stat_columns(data.collect().to_pandas())

    normalization = settings["postproc-normalization"]
    if normalization == "reference_feature" and not reference_feature:
        normalization = "median"
    out.setdefault("normalization", normalization)
    if "normalized_df" not in skip:
        data = transform_data(
            quantification_data=pl.from_pandas(out["imputed_df"]).lazy(),
            metadata=metadata,
            strategy=settings["postproc-transform"],
        )
        data = normalize_samples(
            quantification_data=data,
            metadata=metadata,
            strategy=normalization,
            id_col=id_col,
            reference_feature=reference_feature,
        )
        data = scale_data(
            quantification_data=data,
            metadata=metadata,
            strategy=settings["postproc-scaling"],
        )
        out["normalized_df"] = strip_stat_columns(data.collect().to_pandas())
        out["normalized_transform"] = settings["postproc-transform"]
        out["normalization"] = normalization

    compared = {s: sample_group_map[s] for s in sample_cols}
    out["stat_test"] = valid_test(
        settings["postproc-stat-test"], len(groups), compared, replicates
    )
    if "statistics_df" not in skip:
        data = calculate_statistical_tests(
            quantification_data=pl.from_pandas(out["normalized_df"]).lazy(),
            metadata=metadata,
            method=out["stat_test"],
        )
        data = adjust_fdr_lazy(
            quantification_data=data, strategy=settings["postproc-fdr"]
        )
        out["statistics_df"] = data.collect().to_pandas()
    return out


def count_significant(
    statistics_df: pd.DataFrame, fc: float = 1.0, padj: float = 0.05
) -> tuple[int, int]:
    """Rows up and down at ``|log2FC| >= fc`` and adjusted p-value ``<= padj``."""
    df = statistics_df.dropna(subset=["log2FC", "p-adj"])
    sig = df["p-adj"] <= padj
    return int((sig & (df["log2FC"] >= fc)).sum()), int(
        (sig & (df["log2FC"] <= -fc)).sum()
    )


def comparison_groups(sample_group_map: dict, sample_cols: list) -> tuple | None:
    """(reference, compared) conditions behind the sign of log2FC.

    :func:`calculate_statistical_tests` subtracts the alphabetically first
    group's mean from the last one's, so a positive log2FC means higher in the
    last group.
    """
    groups = sorted(
        {
            sample_group_map[s]
            for s in sample_cols
            if sample_group_map.get(s, UNASSIGNED) != UNASSIGNED
        }
    )
    if len(groups) < 2:
        return None
    return groups[0], groups[-1]
