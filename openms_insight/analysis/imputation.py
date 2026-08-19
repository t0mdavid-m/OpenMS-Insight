import polars as pl


def impute_mar(
    quantification_data: pl.LazyFrame,
    metadata: pl.DataFrame,
    group_column: str = "group",
    strategy: str = "median",
) -> pl.LazyFrame:
    """MAR (Missing At Random) imputation.

    Fills missing values (both explicit nulls and zeros, which are treated
    as missing) using a per-biological-group statistic (mean or median
    computed from the other samples in the same group).

    Args:
        quantification_data: Wide-format data with one column per sample.
        metadata: Sample metadata with a "sample_id" column and a group
            column (name given by `group_column`) mapping each sample to
            its biological group.
        group_column: Column in `metadata` naming the biological group for
            each sample (default: "group").
        strategy: Either "mean" or "median" (default: "median") - which
            per-group statistic to fill missing values with.

    Returns:
        `quantification_data` with zeros converted to nulls and missing
        values filled from their group's mean/median.

    Raises:
        ValueError: If `strategy` is not "mean" or "median".
    """
    unique_groups = (
        metadata.select(group_column).to_series().unique().drop_nulls().to_list()
    )
    unique_groups = [g for g in unique_groups if g not in ["", "NA"]]

    impute_exprs = []
    sample_cols = metadata.select("sample_id").to_series().to_list()

    # Treat zeros as actual nulls
    nullified_lazy = quantification_data.with_columns(
        [
            pl.when(pl.col(col) == 0).then(None).otherwise(pl.col(col)).alias(col)
            for col in sample_cols
        ]
    )

    for group in unique_groups:
        group_samples = (
            metadata.filter(pl.col(group_column) == group)
            .select("sample_id")
            .to_series()
            .to_list()
        )

        if not group_samples:
            continue

        if strategy == "mean":
            group_fill_expr = pl.mean_horizontal(group_samples)
        elif strategy == "median":
            # Use a list-based operation instead of pl.median_horizontal to avoid errors
            group_fill_expr = pl.concat_list(group_samples).list.median()
        else:
            raise ValueError("Strategy must be either 'mean' or 'median'")

        for col in group_samples:
            impute_exprs.append(pl.col(col).fill_null(group_fill_expr).alias(col))

    return nullified_lazy.with_columns(impute_exprs)


def impute_smallest_value(
    quantification_data: pl.LazyFrame, metadata: pl.DataFrame, scope: str = "row"
) -> pl.LazyFrame:
    """MNAR (Missing Not At Random) imputation via smallest observed value.

    Fills values below the detection limit (both explicit nulls and zeros,
    which are treated as missing) with the smallest observed value, on the
    assumption that missingness in MS data is often due to values falling
    below the instrument's detection limit rather than random loss.

    Args:
        quantification_data: Wide-format data with one column per sample.
        metadata: Sample metadata with a "sample_id" column.
        scope: Either "row" (default) to fill with that row/feature's own
            minimum across samples - falling back to the global minimum for
            rows that are entirely missing - or "global" to always fill
            with the smallest value observed anywhere in the data.

    Returns:
        `quantification_data` with zeros converted to nulls and missing
        values filled per `scope`. Returned unchanged if `metadata` has no
        sample columns.

    Raises:
        ValueError: If `scope` is not "row" or "global".
    """
    sample_cols = metadata.select("sample_id").to_series().to_list()
    if not sample_cols:
        return quantification_data

    nullified_lazy = quantification_data.with_columns(
        [
            pl.when(pl.col(col) == 0).then(None).otherwise(pl.col(col)).alias(col)
            for col in sample_cols
        ]
    )

    if scope == "row":
        row_min_expr = pl.min_horizontal(sample_cols)
        global_min_expr = pl.min_horizontal([pl.col(col).min() for col in sample_cols])
        final_fill_expr = row_min_expr.fill_null(global_min_expr)

        return nullified_lazy.with_columns(
            [pl.col(col).fill_null(final_fill_expr).alias(col) for col in sample_cols]
        )

    elif scope == "global":
        global_min_expr = pl.min_horizontal([pl.col(col).min() for col in sample_cols])
        return nullified_lazy.with_columns(
            [pl.col(col).fill_null(global_min_expr).alias(col) for col in sample_cols]
        )
    else:
        raise ValueError("Scope must be either 'row' or 'global'")
