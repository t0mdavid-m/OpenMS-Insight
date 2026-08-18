"""Shape and contract tests for openms_insight.analysis.filter.

Each filter documents that it returns the caller's frame with rows removed and
its own temporary per-group columns dropped. These tests assert exactly that,
plus the argument validation, and nothing about which rows survive.
"""

import pytest

from openms_insight.analysis.filter import (
    filter_low_abundance,
    filter_low_repeatability,
    filter_low_variance,
)

SAMPLE_COLUMNS = ["s1", "s2", "s3", "s4", "s5", "s6"]

FILTERS = [
    (filter_low_abundance, {"threshold_percentile": 10.0}),
    (filter_low_repeatability, {"max_missing_ratio": 0.5}),
    (filter_low_variance, {"threshold_percentile": 10.0}),
]


@pytest.mark.parametrize(
    "filter_fn,kwargs", FILTERS, ids=[fn.__name__ for fn, _ in FILTERS]
)
def test_filters_preserve_schema_and_never_grow(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    filter_fn,
    kwargs,
):
    result = filter_fn(
        sample_quantification_data, sample_quantification_metadata, **kwargs
    )
    out = assert_analysis_contract(result, sample_quantification_data, max_rows=5)

    assert set(out.columns) == set(
        sample_quantification_data.collect_schema().names()
    ), f"{filter_fn.__name__} changed the column set"
    for column in SAMPLE_COLUMNS:
        assert column in out.columns


@pytest.mark.parametrize(
    "filter_fn,kwargs", FILTERS, ids=[fn.__name__ for fn, _ in FILTERS]
)
def test_filters_return_input_unchanged_without_groups(
    sample_quantification_data,
    unusable_metadata,
    assert_analysis_contract,
    filter_fn,
    kwargs,
):
    """Every filter documents that unusable metadata is a pass-through."""
    result = filter_fn(sample_quantification_data, unusable_metadata, **kwargs)
    assert_analysis_contract(result, sample_quantification_data, rows=5)
