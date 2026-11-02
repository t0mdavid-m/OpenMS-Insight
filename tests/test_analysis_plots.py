"""Smoke tests for openms_insight.analysis.plots: each figure builds and is labelled."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("plotly")

from openms_insight.analysis import plots  # noqa: E402

SAMPLES = ["a1", "a2", "b1", "b2"]
GROUPS = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}


@pytest.fixture
def table():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(rng.uniform(1e4, 1e6, (30, 4)), columns=SAMPLES)
    df.iloc[:5, 0] = np.nan
    return df


def test_filter_threshold_curve(table):
    fig = plots.filter_threshold_curve(
        lambda t: int(30 - t), [0, 10, 20], 10, 30, "Threshold", entities="Features"
    )
    assert fig.layout.title.text == "Features kept at each threshold"
    assert list(fig.data[0].y) == [30, 20, 10]


def test_missingness_vs_intensity(table):
    fig = plots.missingness_vs_intensity(table, SAMPLES, entities="Proteoforms")
    assert "5 of 30 proteoforms have gaps" in fig.layout.title.text


def test_imputed_value_preview(table):
    after = table.fillna(1e4)
    fig = plots.imputed_value_preview(table, after, SAMPLES)
    assert {trace.name for trace in fig.data} == {"Observed", "Imputed"}


def test_sample_distributions(table):
    after = np.log2(table.fillna(1e4))
    fig = plots.sample_distributions(table, after, SAMPLES, GROUPS, after_is_log=True)
    assert {trace.name for trace in fig.data} == {"A", "B"}


def test_pvalue_histogram():
    stats = pd.DataFrame({"p-value": np.linspace(0, 1, 40)})
    fig = plots.pvalue_histogram(stats, entities="Features")
    assert fig.layout.yaxis.title.text == "Features"
