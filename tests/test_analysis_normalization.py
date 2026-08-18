"""Shape and contract tests for openms_insight.analysis.normalization.

Every strategy of every stage is exercised. The assertions cover the frame's
shape and the strategy validation each function documents, not the numbers
produced.
"""

import pytest

from openms_insight.analysis.normalization import (
    normalize_samples,
    scale_data,
    transform_data,
)

SAMPLE_COLUMNS = ["s1", "s2", "s3", "s4", "s5", "s6"]

TRANSFORM_STRATEGIES = ["None", "log2", "log10", "square_root", "cube_root"]
NORMALIZE_STRATEGIES = ["None", "sum", "median", "pqn", "reference_feature", "quantile"]
SCALE_STRATEGIES = [
    "None",
    "mean_centering",
    "auto_scaling",
    "pareto_scaling",
    "range_scaling",
]


@pytest.mark.parametrize("strategy", TRANSFORM_STRATEGIES)
def test_transform_preserves_shape(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    strategy,
):
    result = transform_data(
        sample_quantification_data, sample_quantification_metadata, strategy=strategy
    )
    out = assert_analysis_contract(result, sample_quantification_data, rows=5)
    assert set(out.columns) == set(sample_quantification_data.collect_schema().names())


@pytest.mark.parametrize("strategy", NORMALIZE_STRATEGIES)
def test_normalize_preserves_shape(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    strategy,
):
    result = normalize_samples(
        sample_quantification_data,
        sample_quantification_metadata,
        strategy=strategy,
        id_col="feature",
        reference_feature="f2",
    )
    out = assert_analysis_contract(result, sample_quantification_data, rows=5)
    assert set(out.columns) == set(sample_quantification_data.collect_schema().names())


@pytest.mark.parametrize("strategy", SCALE_STRATEGIES)
def test_scale_preserves_shape(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    strategy,
):
    result = scale_data(
        sample_quantification_data, sample_quantification_metadata, strategy=strategy
    )
    out = assert_analysis_contract(result, sample_quantification_data, rows=5)
    assert set(out.columns) == set(sample_quantification_data.collect_schema().names())


def test_transform_rejects_unknown_strategy(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="Unknown transformation strategy"):
        transform_data(
            sample_quantification_data,
            sample_quantification_metadata,
            strategy="not_a_strategy",
        )


def test_normalize_rejects_unknown_strategy(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="Unknown sample normalization strategy"):
        normalize_samples(
            sample_quantification_data,
            sample_quantification_metadata,
            strategy="not_a_strategy",
            id_col="feature",
        )


def test_scale_rejects_unknown_strategy(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="Unknown data scaling strategy"):
        scale_data(
            sample_quantification_data,
            sample_quantification_metadata,
            strategy="not_a_strategy",
        )
