"""Shape and contract tests for openms_insight.analysis.imputation.

Imputation must preserve the frame's shape and fill the gaps it was asked to
fill; the *values* it chooses are not asserted here.
"""

import polars as pl
import pytest

from openms_insight.analysis.imputation import impute_mar, impute_smallest_value

SAMPLE_COLUMNS = ["s1", "s2", "s3", "s4", "s5", "s6"]


def _missing_count(frame: pl.DataFrame) -> int:
    return int(frame.select(SAMPLE_COLUMNS).null_count().sum_horizontal().item())


@pytest.mark.parametrize("strategy", ["mean", "median"])
def test_impute_mar_fills_gaps_without_changing_shape(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    strategy,
):
    before = _missing_count(sample_quantification_data.collect())
    assert before > 0, "fixture should contain missing values to impute"

    result = impute_mar(
        sample_quantification_data, sample_quantification_metadata, strategy=strategy
    )
    out = assert_analysis_contract(result, sample_quantification_data, rows=5)

    assert set(out.columns) == set(sample_quantification_data.collect_schema().names())
    assert _missing_count(out) == 0, (
        f"{strategy} imputation left gaps that every group could fill"
    )


@pytest.mark.parametrize("scope", ["row", "global"])
def test_impute_smallest_value_fills_gaps_without_changing_shape(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    scope,
):
    result = impute_smallest_value(
        sample_quantification_data, sample_quantification_metadata, scope=scope
    )
    out = assert_analysis_contract(result, sample_quantification_data, rows=5)

    assert set(out.columns) == set(sample_quantification_data.collect_schema().names())
    assert _missing_count(out) == 0, f"{scope} imputation left gaps"


def test_impute_mar_rejects_unknown_strategy(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="'mean' or 'median'"):
        impute_mar(
            sample_quantification_data,
            sample_quantification_metadata,
            strategy="not_a_strategy",
        )


def test_impute_smallest_value_rejects_unknown_scope(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="'row' or 'global'"):
        impute_smallest_value(
            sample_quantification_data,
            sample_quantification_metadata,
            scope="not_a_scope",
        )
