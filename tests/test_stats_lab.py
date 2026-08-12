"""Tests for modules.stats_lab. This module had zero prior test coverage
despite driving user-facing statistical verdicts (t-test/ANOVA/chi-square/
Pearson) — this file both locks down that existing behavior and covers the
new non-parametric alternatives (Mann-Whitney U, Kruskal-Wallis, Spearman)
that close normality_warnings()'s previous dead end: a warning that a
test's assumption is violated, with no valid next step offered.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import stats_lab


# ── suggest_test() ────────────────────────────────────────────────────────
def test_suggest_test_numeric_numeric_is_pearson():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    types = {"a": "numeric", "b": "numeric"}
    result = stats_lab.suggest_test(df, types, "a", "b")
    assert result["test"] == "pearson"


def test_suggest_test_two_groups_is_ttest():
    df = pd.DataFrame({"val": [1, 2, 3, 4], "grp": ["x", "x", "y", "y"]})
    types = {"val": "numeric", "grp": "categorical"}
    result = stats_lab.suggest_test(df, types, "val", "grp")
    assert result["test"] == "ttest"
    assert result["numeric_col"] == "val"
    assert result["cat_col"] == "grp"


def test_suggest_test_three_groups_is_anova():
    df = pd.DataFrame({"val": [1, 2, 3, 4, 5, 6], "grp": ["x", "x", "y", "y", "z", "z"]})
    types = {"val": "numeric", "grp": "categorical"}
    result = stats_lab.suggest_test(df, types, "val", "grp")
    assert result["test"] == "anova"


def test_suggest_test_categorical_categorical_is_chi2():
    df = pd.DataFrame({"a": ["x", "y", "x", "y"], "b": ["p", "q", "p", "q"]})
    types = {"a": "categorical", "b": "categorical"}
    result = stats_lab.suggest_test(df, types, "a", "b")
    assert result["test"] == "chi2"


def test_suggest_test_one_group_errors():
    df = pd.DataFrame({"val": [1, 2, 3], "grp": ["x", "x", "x"]})
    types = {"val": "numeric", "grp": "categorical"}
    result = stats_lab.suggest_test(df, types, "val", "grp")
    assert "error" in result


def test_suggest_test_too_many_groups_errors():
    df = pd.DataFrame({"val": range(20), "grp": [str(i) for i in range(20)]})
    types = {"val": "numeric", "grp": "categorical"}
    result = stats_lab.suggest_test(df, types, "val", "grp")
    assert "error" in result


# ── run_ttest() / run_anova() / run_chi2() / run_pearson() ──────────────
def test_run_ttest_detects_real_difference():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "val": np.concatenate([rng.normal(0, 1, 200), rng.normal(5, 1, 200)]),
        "grp": ["a"] * 200 + ["b"] * 200,
    })
    result = stats_lab.run_ttest(df, "val", "grp")
    assert result["test"] == "ttest"
    assert result["p_value"] < 0.001
    assert result["effect_size_label"] == "large"


def test_run_ttest_wrong_group_count_errors():
    df = pd.DataFrame({"val": [1, 2, 3], "grp": ["x", "y", "z"]})
    result = stats_lab.run_ttest(df, "val", "grp")
    assert "error" in result


def test_run_anova_detects_real_difference():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "val": np.concatenate([rng.normal(0, 1, 100), rng.normal(5, 1, 100), rng.normal(10, 1, 100)]),
        "grp": ["a"] * 100 + ["b"] * 100 + ["c"] * 100,
    })
    result = stats_lab.run_anova(df, "val", "grp")
    assert result["test"] == "anova"
    assert result["p_value"] < 0.001


def test_run_chi2_independent_columns_not_significant():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({
        "a": rng.choice(["x", "y"], 500),
        "b": rng.choice(["p", "q"], 500),
    })
    result = stats_lab.run_chi2(df, "a", "b")
    assert result["test"] == "chi2"
    assert result["p_value"] > 0.01  # true null, should usually not reject


def test_run_pearson_perfect_correlation():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10]})
    result = stats_lab.run_pearson(df, "a", "b")
    assert result["statistic"] == pytest.approx(1.0)
    assert result["effect_size_label"] == "large"


def test_run_pearson_too_few_points_errors():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = stats_lab.run_pearson(df, "a", "b")
    assert "error" in result


# ── run_mannwhitney() ─────────────────────────────────────────────────────
def test_run_mannwhitney_detects_real_shift():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "val": np.concatenate([rng.normal(0, 1, 200), rng.normal(5, 1, 200)]),
        "grp": ["a"] * 200 + ["b"] * 200,
    })
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert result["test"] == "mannwhitney"
    assert result["p_value"] < 0.001
    assert result["effect_size_name"] == "rank-biserial r"
    assert abs(result["effect_size"]) > 0.5


def test_run_mannwhitney_identical_groups_not_significant():
    rng = np.random.default_rng(4)
    vals = rng.normal(0, 1, 400)
    df = pd.DataFrame({"val": vals, "grp": ["a"] * 200 + ["b"] * 200})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert result["p_value"] > 0.01


def test_run_mannwhitney_wrong_group_count_errors():
    df = pd.DataFrame({"val": [1, 2, 3], "grp": ["x", "y", "z"]})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert "error" in result


def test_run_mannwhitney_rank_biserial_sign_direction():
    # group "a" is entirely below group "b" -> every comparison favors b ->
    # rank-biserial should be strongly negative (a ranks lower than b).
    df = pd.DataFrame({"val": [1, 2, 3, 10, 11, 12], "grp": ["a", "a", "a", "b", "b", "b"]})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert result["effect_size"] == pytest.approx(-1.0)


def test_run_mannwhitney_has_no_normality_key():
    df = pd.DataFrame({"val": [1, 2, 3, 4], "grp": ["a", "a", "b", "b"]})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert "normality" not in result


def test_run_mannwhitney_reports_medians():
    df = pd.DataFrame({"val": [1, 2, 3, 10, 20, 30], "grp": ["a", "a", "a", "b", "b", "b"]})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert result["medians"]["a"] == 2
    assert result["medians"]["b"] == 20


# ── run_kruskal() ──────────────────────────────────────────────────────────
def test_run_kruskal_detects_real_difference():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({
        "val": np.concatenate([rng.normal(0, 1, 100), rng.normal(5, 1, 100), rng.normal(10, 1, 100)]),
        "grp": ["a"] * 100 + ["b"] * 100 + ["c"] * 100,
    })
    result = stats_lab.run_kruskal(df, "val", "grp")
    assert result["test"] == "kruskal"
    assert result["p_value"] < 0.001
    assert result["effect_size_name"] == "epsilon-squared"
    assert result["effect_size"] > 0.14  # large


def test_run_kruskal_identical_groups_not_significant():
    rng = np.random.default_rng(6)
    vals = rng.normal(0, 1, 300)
    df = pd.DataFrame({"val": vals, "grp": ["a"] * 100 + ["b"] * 100 + ["c"] * 100})
    result = stats_lab.run_kruskal(df, "val", "grp")
    assert result["p_value"] > 0.01


def test_run_kruskal_too_few_groups_errors():
    df = pd.DataFrame({"val": [1, 2, 3], "grp": ["x", "x", "x"]})
    result = stats_lab.run_kruskal(df, "val", "grp")
    assert "error" in result


def test_run_kruskal_effect_size_never_negative():
    # Near-null data can push the raw epsilon-squared formula slightly
    # below zero; the function should floor it at 0.
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"val": rng.normal(0, 1, 60), "grp": ["a"] * 20 + ["b"] * 20 + ["c"] * 20})
    result = stats_lab.run_kruskal(df, "val", "grp")
    assert result["effect_size"] >= 0.0


# ── run_spearman() ─────────────────────────────────────────────────────────
def test_run_spearman_monotonic_nonlinear_relationship():
    # y = x^3 is perfectly monotonic but not linear — Spearman should catch
    # the full rank correlation even though Pearson's r would be < 1.
    x = np.array([1, 2, 3, 4, 5])
    y = x ** 3
    df = pd.DataFrame({"a": x, "b": y})
    result = stats_lab.run_spearman(df, "a", "b")
    assert result["statistic"] == pytest.approx(1.0)
    pearson_result = stats_lab.run_pearson(df, "a", "b")
    assert result["statistic"] >= pearson_result["statistic"]


def test_run_spearman_too_few_points_errors():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = stats_lab.run_spearman(df, "a", "b")
    assert "error" in result


# ── NONPARAMETRIC_ALTERNATIVE / has_nonparametric_alternative() ──────────
def test_has_nonparametric_alternative_true_for_parametric_tests():
    assert stats_lab.has_nonparametric_alternative("ttest")
    assert stats_lab.has_nonparametric_alternative("anova")
    assert stats_lab.has_nonparametric_alternative("pearson")


def test_has_nonparametric_alternative_false_for_chi2():
    assert not stats_lab.has_nonparametric_alternative("chi2")


def test_has_nonparametric_alternative_false_for_unknown():
    assert not stats_lab.has_nonparametric_alternative("not_a_real_test")


# ── run_nonparametric_alternative() dispatch ──────────────────────────────
def test_run_nonparametric_alternative_from_ttest_suggestion():
    df = pd.DataFrame({"val": [1, 2, 3, 4, 10, 11, 12, 13], "grp": ["a"] * 4 + ["b"] * 4})
    suggestion = {"test": "ttest", "numeric_col": "val", "cat_col": "grp"}
    result = stats_lab.run_nonparametric_alternative(df, suggestion)
    assert result["test"] == "mannwhitney"


def test_run_nonparametric_alternative_from_anova_suggestion():
    df = pd.DataFrame({
        "val": [1, 2, 3, 10, 11, 12, 20, 21, 22],
        "grp": ["a"] * 3 + ["b"] * 3 + ["c"] * 3,
    })
    suggestion = {"test": "anova", "numeric_col": "val", "cat_col": "grp"}
    result = stats_lab.run_nonparametric_alternative(df, suggestion)
    assert result["test"] == "kruskal"


def test_run_nonparametric_alternative_from_pearson_suggestion():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10]})
    suggestion = {"test": "pearson", "col_a": "a", "col_b": "b"}
    result = stats_lab.run_nonparametric_alternative(df, suggestion)
    assert result["test"] == "spearman"


def test_run_nonparametric_alternative_from_chi2_suggestion_errors():
    df = pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]})
    suggestion = {"test": "chi2", "col_a": "a", "col_b": "b"}
    result = stats_lab.run_nonparametric_alternative(df, suggestion)
    assert "error" in result


def test_run_nonparametric_alternative_unknown_test_errors():
    result = stats_lab.run_nonparametric_alternative(pd.DataFrame(), {"test": "not_real"})
    assert "error" in result


def test_run_nonparametric_alternative_missing_test_key_errors():
    result = stats_lab.run_nonparametric_alternative(pd.DataFrame(), {})
    assert "error" in result


# ── interpret_result() with new test types ────────────────────────────────
def test_interpret_result_mannwhitney_significant():
    df = pd.DataFrame({
        "val": list(range(20)) + list(range(100, 120)),
        "grp": ["a"] * 20 + ["b"] * 20,
    })
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    text = stats_lab.interpret_result(result)
    assert "Significant" in text
    assert "distributions" in text


def test_interpret_result_kruskal_wording():
    df = pd.DataFrame({
        "val": list(range(10)) + list(range(100, 110)) + list(range(200, 210)),
        "grp": ["a"] * 10 + ["b"] * 10 + ["c"] * 10,
    })
    result = stats_lab.run_kruskal(df, "val", "grp")
    text = stats_lab.interpret_result(result)
    assert "group distributions" in text


def test_interpret_result_spearman_wording():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10]})
    result = stats_lab.run_spearman(df, "a", "b")
    text = stats_lab.interpret_result(result)
    assert "monotonic correlation" in text


def test_interpret_result_propagates_error():
    assert stats_lab.interpret_result({"error": "boom"}) == "boom"


# ── nonparametric_notes() ─────────────────────────────────────────────────
def test_nonparametric_notes_flags_small_groups():
    df = pd.DataFrame({"val": [1, 2, 3, 10, 11], "grp": ["a", "a", "a", "b", "b"]})
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    notes = stats_lab.nonparametric_notes(result)
    assert notes
    assert "'b' (n=2)" in notes[0]


def test_nonparametric_notes_silent_for_large_groups():
    rng = np.random.default_rng(8)
    df = pd.DataFrame({
        "val": np.concatenate([rng.normal(0, 1, 50), rng.normal(2, 1, 50)]),
        "grp": ["a"] * 50 + ["b"] * 50,
    })
    result = stats_lab.run_mannwhitney(df, "val", "grp")
    assert stats_lab.nonparametric_notes(result) == []


def test_nonparametric_notes_silent_for_spearman():
    # Spearman has no "groups" key at all — must not KeyError.
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})  # too few points -> error result
    result = stats_lab.run_spearman(df, "a", "b")
    assert stats_lab.nonparametric_notes(result) == []


def test_nonparametric_notes_silent_on_error_result():
    assert stats_lab.nonparametric_notes({"error": "boom"}) == []


def test_nonparametric_notes_silent_for_parametric_results():
    df = pd.DataFrame({"val": [1, 2, 3, 4], "grp": ["a", "a", "b", "b"]})
    result = stats_lab.run_ttest(df, "val", "grp")
    assert stats_lab.nonparametric_notes(result) == []


# ── TEST_LABELS / effect-size threshold tables stay in sync ──────────────
@pytest.mark.parametrize("test_key", ["mannwhitney", "kruskal", "spearman"])
def test_new_tests_have_labels_and_thresholds(test_key):
    assert test_key in stats_lab.TEST_LABELS
    assert test_key in stats_lab._EFFECT_SIZE_THRESHOLDS
