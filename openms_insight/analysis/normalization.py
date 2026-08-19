import polars as pl


def transform_data(
    quantification_data: pl.LazyFrame, metadata: pl.DataFrame, strategy: str
) -> pl.LazyFrame:
    """Applies a mathematical transformation to every sample column.

    Args:
        quantification_data: Wide-format data with one column per sample.
        metadata: Sample metadata with a "sample_id" column.
        strategy: One of "None", "log2", "log10", "square_root",
            "cube_root". "log2"/"log10" add 1 before taking the log to
            avoid `-inf` for zero-intensity values.

    Returns:
        `quantification_data` with each sample column transformed in place.
        Returned unchanged if `strategy` is falsy or "None".

    Raises:
        ValueError: If `strategy` is not one of the supported values.
    """
    if not strategy or strategy == "None":
        return quantification_data

    sample_cols = metadata.select("sample_id").to_series().to_list()

    if strategy == "log2":
        # Fixed: Use native python '+' operator instead of non-existent '.plus()' method
        exprs = [(pl.col(col) + 1).log(2).alias(col) for col in sample_cols]
    elif strategy == "log10":
        # Fixed: Standardized to native math operators for Polars Expressions
        exprs = [(pl.col(col) + 1).log(10).alias(col) for col in sample_cols]
    elif strategy == "square_root":
        exprs = [pl.col(col).sqrt().alias(col) for col in sample_cols]
    elif strategy == "cube_root":
        exprs = [pl.col(col).cbrt().alias(col) for col in sample_cols]
    else:
        raise ValueError(f"Unknown transformation strategy: {strategy}")

    return quantification_data.with_columns(exprs)


def normalize_samples(
    quantification_data: pl.LazyFrame,
    metadata: pl.DataFrame,
    strategy: str,
    id_col: str,
    reference_feature: str | None = None,
) -> pl.LazyFrame:
    """Aligns samples via column-wise size-factor correction.

    Args:
        quantification_data: Wide-format data with one column per sample.
        metadata: Sample metadata with a "sample_id" column.
        strategy: One of "None", "sum", "median", "pqn" (Probabilistic
            Quotient Normalization), "reference_feature", "quantile".
        id_col: Column in `quantification_data` identifying each row
            (feature/protein). Only used by the "reference_feature"
            strategy to look up `reference_feature`.
        reference_feature: Row identifier (matched against `id_col`) to use
            as the normalization reference. Required when
            `strategy="reference_feature"`; ignored otherwise.

    Returns:
        `quantification_data` with each sample column normalized in place
        and any temporary working columns dropped. Returned unchanged if
        `strategy` is falsy or "None".

    Raises:
        ValueError: If `strategy` is not one of the supported values, or if
            `strategy="reference_feature"` and `reference_feature` is not
            provided or not found in `quantification_data`.
    """
    if not strategy or strategy == "None":
        return quantification_data

    sample_cols = metadata.select("sample_id").to_series().to_list()

    if strategy == "sum":
        # Calculate target mean of all column sums lazily
        col_sums = [pl.col(col).sum() for col in sample_cols]
        target_sum_expr = pl.sum_horizontal(col_sums) / len(sample_cols)

        return quantification_data.with_columns(
            [
                (pl.col(col) / pl.col(col).sum() * target_sum_expr).alias(col)
                for col in sample_cols
            ]
        )

    elif strategy == "median":
        # Align columns based on global median target using list aggregation
        col_medians = [pl.col(col).median() for col in sample_cols]
        target_median_expr = pl.sum_horizontal(col_medians) / len(sample_cols)

        return quantification_data.with_columns(
            [
                (pl.col(col) + (target_median_expr - pl.col(col).median())).alias(col)
                for col in sample_cols
            ]
        )

    elif strategy == "pqn":
        # Probabilistic Quotient Normalization
        # 1. Create a reference pseudo-spectrum (row-wise median across samples)
        lazy_ref = quantification_data.with_columns(
            [pl.concat_list(sample_cols).list.median().alias("_pqn_ref")]
        )

        # 2. Calculate quotients for each column relative to the reference
        # Avoid division by zero by nullifying 0
        quotient_exprs = [
            (
                pl.col(col)
                / pl.when(pl.col("_pqn_ref") == 0)
                .then(None)
                .otherwise(pl.col("_pqn_ref"))
            ).alias(f"_q_{col}")
            for col in sample_cols
        ]
        lazy_quotients = lazy_ref.with_columns(quotient_exprs)

        # 3. Median of quotients per sample is the dilution factor
        dilution_exprs = [
            pl.col(f"_q_{col}").median().fill_null(1.0).alias(f"_d_{col}")
            for col in sample_cols
        ]

        # 4. Final division inside the lazy chain and clean up temp columns
        final_exprs = [
            (pl.col(col) / pl.col(f"_d_{col}").first()).alias(col)
            for col in sample_cols
        ]

        temp_cols = (
            [f"_q_{col}" for col in sample_cols]
            + [f"_d_{col}" for col in sample_cols]
            + ["_pqn_ref"]
        )

        return (
            lazy_quotients.with_columns(dilution_exprs)
            .with_columns(final_exprs)
            .drop(temp_cols)
        )

    elif strategy == "reference_feature":
        if not reference_feature:
            raise ValueError(
                "reference_feature must be provided when using reference_feature normalization."
            )

        sample_cols = metadata.select("sample_id").to_series().to_list()

        # ------------------------------------------------------------
        # Validate that the reference protein exists
        # ------------------------------------------------------------
        reference_count = (
            quantification_data.filter(pl.col(id_col) == reference_feature)
            .select(pl.len().alias("count"))
            .collect()
            .item()
        )

        if reference_count == 0:
            raise ValueError(
                f"Reference protein '{reference_feature}' was not found in column '{id_col}'."
            )

        # ------------------------------------------------------------
        # Extract reference protein rows
        # If duplicated, use mean intensity across duplicates
        # ------------------------------------------------------------
        reference_row = quantification_data.filter(pl.col(id_col) == reference_feature)

        ref_exprs = [pl.col(col).mean().alias(f"_ref_{col}") for col in sample_cols]

        reference_values = reference_row.select(ref_exprs)

        # ------------------------------------------------------------
        # Attach reference values to every row
        # ------------------------------------------------------------
        joined = quantification_data.join(reference_values, how="cross")

        # ------------------------------------------------------------
        # Normalize each sample column
        # Sample / ReferenceProtein
        # ------------------------------------------------------------
        normalized_exprs = [
            (
                pl.col(col)
                / pl.when(pl.col(f"_ref_{col}") == 0)
                .then(None)
                .otherwise(pl.col(f"_ref_{col}"))
            ).alias(col)
            for col in sample_cols
        ]

        temp_cols = [f"_ref_{col}" for col in sample_cols]

        return joined.with_columns(normalized_exprs).drop(temp_cols)

    elif strategy == "quantile":
        # Quantile normalization: reshape every sample column to share the same
        # value distribution. The reference distribution is the row-wise mean,
        # across samples, of each sample's sorted values (i.e. the average of
        # the smallest values across samples, the average of the 2nd-smallest
        # values across samples, and so on). Each sample's original values are
        # then replaced by the reference value at their own rank position.
        #
        # Ties are broken by row order (`rank(method="ordinal")` assigns unique
        # 1..n ranks), which is a simplification versus tools like R's
        # `preprocessCore::normalize.quantiles`, which average tied ranks.
        sorted_cols = [f"_sorted_{col}" for col in sample_cols]
        rank_cols = [f"_rank_{col}" for col in sample_cols]

        with_sorted = (
            quantification_data.with_columns(
                [
                    pl.col(col).sort().alias(sorted_col)
                    for col, sorted_col in zip(sample_cols, sorted_cols, strict=True)
                ]
            )
            .with_columns([pl.mean_horizontal(sorted_cols).alias("_qref")])
            .with_columns(
                [
                    (pl.col(col).rank(method="ordinal").cast(pl.Int64) - 1).alias(
                        rank_col
                    )
                    for col, rank_col in zip(sample_cols, rank_cols, strict=True)
                ]
            )
        )

        return with_sorted.with_columns(
            [
                pl.col("_qref").gather(pl.col(rank_col)).alias(col)
                for col, rank_col in zip(sample_cols, rank_cols, strict=True)
            ]
        ).drop(sorted_cols + rank_cols + ["_qref"])

    else:
        raise ValueError(f"Unknown sample normalization strategy: {strategy}")


def scale_data(
    quantification_data: pl.LazyFrame, metadata: pl.DataFrame, strategy: str
) -> pl.LazyFrame:
    """Applies row-wise (per-feature) centering and/or variance scaling.

    Args:
        quantification_data: Wide-format data with one column per sample.
        metadata: Sample metadata with a "sample_id" column.
        strategy: One of "None", "mean_centering", "auto_scaling"
            (mean-centering + unit variance), "pareto_scaling"
            (mean-centering + sqrt(std) scaling), "range_scaling"
            (min-max scaling to [0, 1]).

    Returns:
        `quantification_data` with each sample column scaled in place and
        any temporary working columns dropped. Returned unchanged if
        `strategy` is falsy or "None".

    Raises:
        ValueError: If `strategy` is not one of the supported values.
    """
    if not strategy or strategy == "None":
        return quantification_data

    sample_cols = metadata.select("sample_id").to_series().to_list()

    # Pre-calculate horizontal structural vectors (Mean & Std Dev per row)
    lazy_metrics = quantification_data.with_columns(
        [
            pl.mean_horizontal(sample_cols).alias("_row_mean"),
            pl.concat_list(sample_cols).list.var().sqrt().alias("_row_std"),
        ]
    ).with_columns(
        [
            # Prevent division by zero errors
            pl.when(pl.col("_row_std") == 0)
            .then(1.0)
            .otherwise(pl.col("_row_std"))
            .alias("_row_std")
        ]
    )

    if strategy == "mean_centering":
        scaled_lazy = lazy_metrics.with_columns(
            [(pl.col(col) - pl.col("_row_mean")).alias(col) for col in sample_cols]
        )
    elif strategy == "auto_scaling":
        scaled_lazy = lazy_metrics.with_columns(
            [
                ((pl.col(col) - pl.col("_row_mean")) / pl.col("_row_std")).alias(col)
                for col in sample_cols
            ]
        )
    elif strategy == "pareto_scaling":
        scaled_lazy = lazy_metrics.with_columns(
            [
                ((pl.col(col) - pl.col("_row_mean")) / pl.col("_row_std").sqrt()).alias(
                    col
                )
                for col in sample_cols
            ]
        )
    elif strategy == "range_scaling":
        lazy_range = quantification_data.with_columns(
            [
                pl.min_horizontal(sample_cols).alias("_row_min"),
                pl.max_horizontal(sample_cols).alias("_row_max"),
            ]
        ).with_columns(
            [
                pl.when(pl.col("_row_max") - pl.col("_row_min") == 0)
                .then(1.0)
                .otherwise(pl.col("_row_max") - pl.col("_row_min"))
                .alias("_row_range")
            ]
        )

        scaled_lazy = lazy_range.with_columns(
            [
                ((pl.col(col) - pl.col("_row_min")) / pl.col("_row_range")).alias(col)
                for col in sample_cols
            ]
        )
        return scaled_lazy.drop(["_row_min", "_row_max", "_row_range"])
    else:
        raise ValueError(f"Unknown data scaling strategy: {strategy}")

    return scaled_lazy.drop(["_row_mean", "_row_std"])
