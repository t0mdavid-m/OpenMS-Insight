"""Tests for openms_insight.analysis.differential (the comparison chain).

Synthetic data with a known answer: a few rows are four times as abundant in
one condition, the rest only carry noise. The chain has to find exactly those,
follow its settings, continue from tables already made and fall back to a test
that fits the design.
"""

import numpy as np
import pandas as pd
import pytest

from openms_insight.analysis.differential import (
    DEFAULT_SETTINGS,
    OPTIONS,
    SETTING_KEYS,
    STEPS,
    comparison_groups,
    count_significant,
    describe_settings,
    resolve_settings,
    run_differential,
    valid_test,
)
from openms_insight.analysis.differential import (
    tests_for as fitting_tests,
)

N_ROWS = 200
CHANGED = 10
SAMPLES = ["a1", "a2", "a3", "b1", "b2", "b3"]
GROUPS = {"a1": "A", "a2": "A", "a3": "A", "b1": "B", "b2": "B", "b3": "B"}
REPLICATES = {"a1": 1, "a2": 2, "a3": 3, "b1": 1, "b2": 2, "b3": 3}


def _abundances(seed: int = 7, missing: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.uniform(1e5, 1e8, N_ROWS)
    values = {}
    for sample in SAMPLES:
        noise = rng.lognormal(0.0, 0.05, N_ROWS)
        fold = np.ones(N_ROWS)
        if GROUPS[sample] == "B":
            fold[:CHANGED] = 4.0
        values[sample] = base * fold * noise
    df = pd.DataFrame(values)
    df.insert(0, "id", [f"row{i}" for i in range(N_ROWS)])
    df["mass"] = np.arange(N_ROWS, dtype=float)
    for i in range(missing):
        # missing in both conditions, so no condition is complete
        df.loc[N_ROWS - 1 - i, ["a1", "b1"]] = np.nan
    return df


def test_finds_exactly_the_changed_rows():
    out = run_differential(_abundances(), GROUPS, "id")
    stats = out["statistics_df"]
    up, down = count_significant(stats, fc=1.0, padj=0.05)
    assert (up, down) == (CHANGED, 0)
    hits = set(stats.loc[(stats["p-adj"] <= 0.05) & (stats["log2FC"] >= 1), "id"])
    assert hits == {f"row{i}" for i in range(CHANGED)}


def test_returns_every_step_and_what_was_applied():
    out = run_differential(_abundances(), GROUPS, "id")
    for key in STEPS:
        assert isinstance(out[key], pd.DataFrame)
    assert out["stat_test"] == "limma_like"
    assert out["normalized_transform"] == "log2"
    assert out["normalization"] == "median"
    # annotation columns travel through the chain
    assert "mass" in out["statistics_df"].columns


def test_unassigned_samples_stay_out_of_the_comparison():
    groups = {**GROUPS, "b3": "Unassigned"}
    out = run_differential(_abundances(), groups, "id")
    assert out["stat_test"] == "limma_like"
    assert len(out["statistics_df"]) == N_ROWS


def test_needs_two_conditions():
    with pytest.raises(ValueError, match="two conditions"):
        run_differential(_abundances(), dict.fromkeys(SAMPLES, "A"), "id")


def test_filter_follows_its_setting():
    df = _abundances(missing=5)
    strict = run_differential(df, GROUPS, "id", {"postproc-filter-max-missing": 0.0})
    lenient = run_differential(df, GROUPS, "id")
    assert len(strict["filtered_df"]) == N_ROWS - 5
    assert len(lenient["filtered_df"]) == N_ROWS


def test_empty_filter_result_names_the_entity():
    df = _abundances()
    df.loc[:, "a1"] = np.nan
    df.loc[:, "b1"] = np.nan
    with pytest.raises(ValueError, match="No proteoform passed"):
        run_differential(
            df,
            GROUPS,
            "id",
            {"postproc-filter-max-missing": 0.0},
            entity="proteoform",
        )


def test_continues_from_done_steps():
    first = run_differential(_abundances(), GROUPS, "id")
    marker = first["normalized_df"].copy()
    again = run_differential(
        _abundances(seed=99),
        GROUPS,
        "id",
        done={"normalized_df": marker, "not-a-step": 1},
    )
    # the chain starts after the given table, so the other input is ignored
    pd.testing.assert_frame_equal(again["normalized_df"], marker)
    assert "filtered_df" not in again
    assert "not-a-step" not in again


def test_reference_feature_without_a_feature_falls_back_to_median():
    out = run_differential(
        _abundances(), GROUPS, "id", {"postproc-normalization": "reference_feature"}
    )
    assert out["normalization"] == "median"
    out = run_differential(
        _abundances(),
        GROUPS,
        "id",
        {"postproc-normalization": "reference_feature"},
        reference_feature="row100",
    )
    assert out["normalization"] == "reference_feature"


def test_paired_test_pairs_by_replicate():
    settings = {"postproc-stat-test": "paired"}
    natural = run_differential(
        _abundances(), GROUPS, "id", settings, replicates=REPLICATES
    )
    # B's columns in another order: pairing by position would now pair a1 with b3
    shuffled_df = _abundances()[["id", "a1", "a2", "a3", "b3", "b1", "b2", "mass"]]
    shuffled = run_differential(
        shuffled_df, GROUPS, "id", settings, replicates=REPLICATES
    )
    by_position = run_differential(shuffled_df, GROUPS, "id", settings)
    assert natural["stat_test"] == shuffled["stat_test"] == "paired"
    np.testing.assert_allclose(
        natural["statistics_df"]["p-value"], shuffled["statistics_df"]["p-value"]
    )
    assert not np.allclose(
        natural["statistics_df"]["p-value"], by_position["statistics_df"]["p-value"]
    )


def test_paired_falls_back_when_replicates_do_not_match():
    replicates = {**REPLICATES, "b3": 4}
    out = run_differential(
        _abundances(),
        GROUPS,
        "id",
        {"postproc-stat-test": "paired"},
        replicates=replicates,
    )
    assert out["stat_test"] == "limma_like"


@pytest.mark.parametrize(
    ("test", "n_groups", "expected"),
    [
        ("welch", 2, "welch"),
        ("anova", 2, "limma_like"),
        ("anova", 3, "anova"),
        ("welch", 3, "limma_like"),
        ("unknown", 2, "limma_like"),
    ],
)
def test_valid_test_fits_the_number_of_conditions(test, n_groups, expected):
    assert valid_test(test, n_groups) == expected


def test_valid_test_paired_needs_equal_groups():
    uneven = {"a1": "A", "a2": "A", "b1": "B"}
    assert valid_test("paired", 2, uneven) == "limma_like"
    assert valid_test("paired", 2, GROUPS) == "paired"
    assert valid_test("paired", 2, GROUPS, REPLICATES) == "paired"


def test_settings_defaults_and_options():
    assert resolve_settings({}) == DEFAULT_SETTINGS
    assert resolve_settings({"postproc-fdr": "None", "other": 1})["postproc-fdr"] == (
        "None"
    )
    assert SETTING_KEYS == list(DEFAULT_SETTINGS)
    for key, choices in OPTIONS.items():
        assert DEFAULT_SETTINGS[key] in choices
    assert fitting_tests(2) == ["limma_like", "welch", "paired"]
    assert fitting_tests(3) == ["limma_like", "anova"]


def test_describe_settings_uses_the_entity():
    lines = describe_settings(DEFAULT_SETTINGS, entity="proteoform")
    assert len(lines) == 4
    assert "proteoforms measured in at least 50 %" in lines[0]
    assert "proteoform's lowest measured value" in lines[1]
    assert lines[2].endswith("log2 transform, median normalization")
    assert "limma_like test, BH correction" in lines[3]


def test_comparison_groups_orders_the_fold_change():
    assert comparison_groups(GROUPS, SAMPLES) == ("A", "B")
    assert comparison_groups(dict.fromkeys(SAMPLES, "A"), SAMPLES) is None
