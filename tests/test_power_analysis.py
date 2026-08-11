"""Tests for modules.power_analysis — forward-looking sample-size/power
planning for two-sample mean comparisons (Cohen's d via statsmodels'
TTestIndPower) and two-sample proportion comparisons (NormalIndPower +
proportion_effectsize). The frequentist counterpart to modules.bayesian_ab:
where Bayesian A/B testing can be checked at any time without a peeking
penalty, this tool answers the question a fixed-N frequentist test design
needs answered up front — how many samples to collect before starting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.power_analysis import (
    achieved_power_means,
    achieved_power_proportions,
    auto_select_inputs,
    cohens_d,
    effect_size_from_means,
    effect_size_from_proportions,
    narrate_power_analysis,
    plan_power_means,
    plan_power_proportions,
    required_n_means,
    required_n_proportions,
)
from modules.visualization import plot_power_curve


# ─────────────────────────────────────────────────────────────────────────
# required_n_means / achieved_power_means — core statsmodels wrappers
# ─────────────────────────────────────────────────────────────────────────
def test_required_n_means_matches_textbook_medium_effect():
    # Textbook value: Cohen's d=0.5, alpha=0.05, power=0.8, two-sided,
    # equal groups -> ~64 per group (a widely-cited reference number).
    n = required_n_means(effect_size=0.5, power=0.8, alpha=0.05)
    assert 60 <= n <= 68


def test_required_n_means_decreases_with_larger_effect():
    n_small_effect = required_n_means(effect_size=0.2, power=0.8, alpha=0.05)
    n_large_effect = required_n_means(effect_size=0.8, power=0.8, alpha=0.05)
    assert n_large_effect < n_small_effect


def test_required_n_means_increases_with_target_power():
    n_low_power = required_n_means(effect_size=0.5, power=0.6, alpha=0.05)
    n_high_power = required_n_means(effect_size=0.5, power=0.95, alpha=0.05)
    assert n_high_power > n_low_power


def test_achieved_power_means_round_trips_with_required_n():
    n = required_n_means(effect_size=0.5, power=0.8, alpha=0.05)
    power = achieved_power_means(n1=n, effect_size=0.5, alpha=0.05)
    # n was ceil()'d up, so achieved power should be >= the target, not exactly equal.
    assert power >= 0.8 - 1e-6


def test_achieved_power_means_increases_with_n():
    low = achieved_power_means(n1=20, effect_size=0.5, alpha=0.05)
    high = achieved_power_means(n1=200, effect_size=0.5, alpha=0.05)
    assert high > low


def test_required_n_means_uses_absolute_effect_size():
    # Sign of the effect shouldn't matter for a two-sided sample-size calc.
    n_pos = required_n_means(effect_size=0.5, power=0.8, alpha=0.05)
    n_neg = required_n_means(effect_size=-0.5, power=0.8, alpha=0.05)
    assert n_pos == pytest.approx(n_neg)


# ─────────────────────────────────────────────────────────────────────────
# required_n_proportions / achieved_power_proportions
# ─────────────────────────────────────────────────────────────────────────
def test_required_n_proportions_decreases_with_larger_gap():
    n_small_gap = required_n_proportions(p1=0.10, p2=0.11, power=0.8, alpha=0.05)
    n_large_gap = required_n_proportions(p1=0.10, p2=0.30, power=0.8, alpha=0.05)
    assert n_large_gap < n_small_gap


def test_achieved_power_proportions_round_trips_with_required_n():
    n = required_n_proportions(p1=0.10, p2=0.15, power=0.8, alpha=0.05)
    power = achieved_power_proportions(n1=n, p1=0.10, p2=0.15, alpha=0.05)
    assert power >= 0.8 - 1e-6


def test_required_n_proportions_symmetric_in_p1_p2_order():
    n_ab = required_n_proportions(p1=0.10, p2=0.15, power=0.8, alpha=0.05)
    n_ba = required_n_proportions(p1=0.15, p2=0.10, power=0.8, alpha=0.05)
    assert n_ab == pytest.approx(n_ba)


# ─────────────────────────────────────────────────────────────────────────
# cohens_d / effect_size_from_means
# ─────────────────────────────────────────────────────────────────────────
def test_cohens_d_matches_manual_pooled_formula():
    d = cohens_d(mean_a=10.0, std_a=2.0, n_a=50, mean_b=12.0, std_b=2.0, n_b=50)
    assert d == pytest.approx(1.0, abs=1e-9)  # equal std, diff of 2, std=2 -> d=1.0


def test_cohens_d_zero_pooled_std_returns_zero():
    d = cohens_d(mean_a=5.0, std_a=0.0, n_a=10, mean_b=5.0, std_b=0.0, n_b=10)
    assert d == 0.0


def test_effect_size_from_means_recovers_known_d():
    rng = np.random.default_rng(0)
    n = 2000
    df = pd.DataFrame({
        "group": ["a"] * n + ["b"] * n,
        "value": np.concatenate([rng.normal(10, 2, n), rng.normal(12, 2, n)]),  # true d = 1.0
    })
    result = effect_size_from_means(df, value_col="value", group_col="group")
    assert result["ok"]
    assert result["cohens_d"] == pytest.approx(1.0, abs=0.1)
    assert result["n_a"] == n
    assert result["n_b"] == n


def test_effect_size_from_means_explicit_group_values():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "group": np.repeat(["x", "y", "z"], 500),
        "value": np.concatenate([rng.normal(0, 1, 500), rng.normal(1, 1, 500), rng.normal(5, 1, 500)]),
    })
    result = effect_size_from_means(df, value_col="value", group_col="group", group_a="x", group_b="y")
    assert result["ok"]
    assert result["cohens_d"] == pytest.approx(1.0, abs=0.15)


def test_effect_size_from_means_too_few_rows():
    df = pd.DataFrame({"group": ["a", "a", "b", "b"], "value": [1.0, 2.0, 3.0, 4.0]})
    result = effect_size_from_means(df, value_col="value", group_col="group", min_rows=5)
    assert not result["ok"]


def test_effect_size_from_means_missing_column():
    df = pd.DataFrame({"group": ["a", "b"], "value": [1.0, 2.0]})
    result = effect_size_from_means(df, value_col="nope", group_col="group")
    assert not result["ok"]


def test_effect_size_from_means_wrong_level_count():
    df = pd.DataFrame({"group": ["a"] * 20, "value": np.arange(20.0)})
    result = effect_size_from_means(df, value_col="value", group_col="group")
    assert not result["ok"]


def test_effect_size_from_means_same_column_twice_errors_gracefully():
    # Regression test: passing the same column name for both value_col and
    # group_col used to crash (df[[col, col]] selects a duplicate-column
    # DataFrame, not a Series, breaking .unique() downstream) instead of
    # failing cleanly.
    df = pd.DataFrame({"group": ["a"] * 10 + ["b"] * 10})
    result = effect_size_from_means(df, value_col="group", group_col="group")
    assert not result["ok"]
    assert "different columns" in result["error"]


# ─────────────────────────────────────────────────────────────────────────
# effect_size_from_proportions
# ─────────────────────────────────────────────────────────────────────────
def test_effect_size_from_proportions_recovers_known_rates():
    rng = np.random.default_rng(2)
    n = 3000
    df = pd.DataFrame({
        "group": ["control"] * n + ["treatment"] * n,
        "converted": np.concatenate([
            rng.binomial(1, 0.10, n).astype(str),
            rng.binomial(1, 0.15, n).astype(str),
        ]),
    })
    df["converted"] = df["converted"].map({"1": "yes", "0": "no"})
    result = effect_size_from_proportions(df, success_col="converted", group_col="group",
                                           group_a="control", group_b="treatment")
    assert result["ok"]
    assert result["p_a"] == pytest.approx(0.10, abs=0.02)
    assert result["p_b"] == pytest.approx(0.15, abs=0.02)


def test_effect_size_from_proportions_non_binary_outcome():
    df = pd.DataFrame({
        "group": ["a"] * 30 + ["b"] * 30,
        "converted": list(range(30)) + list(range(30)),  # way more than 2 distinct values
    })
    result = effect_size_from_proportions(df, success_col="converted", group_col="group")
    assert not result["ok"]


def test_effect_size_from_proportions_same_column_twice_errors_gracefully():
    # Regression test, same class of bug as the means version above.
    df = pd.DataFrame({"flag": ["yes"] * 10 + ["no"] * 10})
    result = effect_size_from_proportions(df, success_col="flag", group_col="flag")
    assert not result["ok"]
    assert "different columns" in result["error"]


# ─────────────────────────────────────────────────────────────────────────
# plan_power_means — app-facing entry point
# ─────────────────────────────────────────────────────────────────────────
def test_plan_power_means_solve_n_manual_effect_size():
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=0.5,
                               alpha=0.05, target_power=0.8)
    assert result["ok"]
    assert result["metric_type"] == "mean"
    assert 60 <= result["required_n_per_group"] <= 68
    assert len(result["power_curve"]) > 1


def test_plan_power_means_solve_power_manual_effect_size():
    result = plan_power_means(mode="solve_power", effect_size_source="manual", effect_size=0.5,
                               alpha=0.05, n_per_group=64)
    assert result["ok"]
    assert result["achieved_power"] == pytest.approx(0.8, abs=0.02)


def test_plan_power_means_solve_n_from_pilot_data():
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "group": ["a"] * n + ["b"] * n,
        "value": np.concatenate([rng.normal(10, 2, n), rng.normal(11, 2, n)]),  # d ~ 0.5
    })
    result = plan_power_means(mode="solve_n", effect_size_source="data", df=df,
                               value_col="value", group_col="group", target_power=0.8)
    assert result["ok"]
    assert result["effect_size_source"] == "data"
    assert result["pilot"]["n_a"] == n
    assert result["required_n_per_group"] > 0


def test_plan_power_means_missing_effect_size_errors():
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=None)
    assert not result["ok"]


def test_plan_power_means_solve_power_missing_n_errors():
    result = plan_power_means(mode="solve_power", effect_size_source="manual", effect_size=0.5, n_per_group=None)
    assert not result["ok"]


def test_plan_power_means_invalid_mode_errors():
    result = plan_power_means(mode="bogus", effect_size_source="manual", effect_size=0.5)
    assert not result["ok"]


def test_plan_power_means_invalid_alpha_errors():
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=0.5, alpha=1.5)
    assert not result["ok"]


# ─────────────────────────────────────────────────────────────────────────
# plan_power_proportions — app-facing entry point
# ─────────────────────────────────────────────────────────────────────────
def test_plan_power_proportions_solve_n_manual():
    result = plan_power_proportions(mode="solve_n", effect_size_source="manual", p1=0.10, p2=0.15,
                                     alpha=0.05, target_power=0.8)
    assert result["ok"]
    assert result["metric_type"] == "proportion"
    assert result["required_n_per_group"] > 0


def test_plan_power_proportions_solve_power_manual():
    n = required_n_proportions(p1=0.10, p2=0.15, power=0.8, alpha=0.05)
    result = plan_power_proportions(mode="solve_power", effect_size_source="manual", p1=0.10, p2=0.15,
                                     alpha=0.05, n_per_group=n)
    assert result["ok"]
    assert result["achieved_power"] >= 0.79


def test_plan_power_proportions_from_pilot_data():
    rng = np.random.default_rng(3)
    n = 1000
    df = pd.DataFrame({
        "group": ["control"] * n + ["treatment"] * n,
        "converted": np.concatenate([rng.binomial(1, 0.1, n), rng.binomial(1, 0.15, n)]),
    })
    df["converted"] = df["converted"].map({1: "yes", 0: "no"})
    result = plan_power_proportions(mode="solve_n", effect_size_source="data", df=df,
                                     success_col="converted", group_col="group",
                                     group_a="control", group_b="treatment")
    assert result["ok"]
    assert result["pilot"]["p_a"] == pytest.approx(0.1, abs=0.03)


def test_plan_power_proportions_out_of_range_probability_errors():
    result = plan_power_proportions(mode="solve_n", effect_size_source="manual", p1=1.2, p2=0.5)
    assert not result["ok"]


def test_plan_power_proportions_identical_rates_errors():
    result = plan_power_proportions(mode="solve_n", effect_size_source="manual", p1=0.1, p2=0.1)
    assert not result["ok"]


# ─────────────────────────────────────────────────────────────────────────
# narrate_power_analysis
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=0.5)
    text, error = narrate_power_analysis(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    text, error = narrate_power_analysis(object(), {"ok": False, "error": "boom"})
    assert text == ""
    assert error is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=0.5)

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_power_analysis(object(), result)
    assert error is None
    assert text == "It works."
    assert "power" in captured["prompt"].lower()


# ─────────────────────────────────────────────────────────────────────────
# Chart
# ─────────────────────────────────────────────────────────────────────────
def test_plot_power_curve_solve_n_returns_figure_with_marker():
    result = plan_power_means(mode="solve_n", effect_size_source="manual", effect_size=0.5)
    fig = plot_power_curve(result)
    assert fig is not None
    assert len(fig.data) == 2  # curve line + "this plan" marker


def test_plot_power_curve_solve_power_returns_figure():
    result = plan_power_means(mode="solve_power", effect_size_source="manual", effect_size=0.5, n_per_group=64)
    fig = plot_power_curve(result)
    assert fig is not None


def test_plot_power_curve_none_for_failed_result():
    fig = plot_power_curve({"ok": False, "error": "boom"})
    assert fig is None


# ─────────────────────────────────────────────────────────────────────────
# auto_select_inputs — Atlas's zero-configuration voice/typed invocation
# ─────────────────────────────────────────────────────────────────────────
def test_auto_select_inputs_prefers_means_when_both_available():
    df = pd.DataFrame({
        "group": ["a", "b"] * 20,
        "revenue": list(range(40)),
        "converted": ["yes", "no"] * 20,
    })
    picked = auto_select_inputs(df, {"group": "categorical", "revenue": "numeric", "converted": "categorical"})
    assert picked == {"metric_type": "mean", "value_col": "revenue", "group_col": "group"}


def test_auto_select_inputs_falls_back_to_proportions_when_no_numeric_column():
    df = pd.DataFrame({"group": ["a", "b"] * 20, "converted": ["yes", "no"] * 20})
    picked = auto_select_inputs(df, {"group": "categorical", "converted": "categorical"})
    assert picked == {"metric_type": "proportion", "success_col": "converted", "group_col": "group"}


def test_auto_select_inputs_none_when_no_eligible_group_column():
    df = pd.DataFrame({"revenue": list(range(10)), "user_id": [f"u{i}" for i in range(10)]})
    picked = auto_select_inputs(df, {"revenue": "numeric", "user_id": "text"})
    assert picked is None


def test_auto_select_inputs_none_for_empty_or_missing_types():
    assert auto_select_inputs(pd.DataFrame(), {}) is None
    assert auto_select_inputs(None, {}) is None


def test_auto_select_inputs_group_column_excluded_from_its_own_pairing():
    # A binary column can itself look like a valid group column (2 levels
    # falls within the 2-8 range) — must never be paired with itself as
    # both the group and the outcome.
    df = pd.DataFrame({"flag": ["yes", "no"] * 20})
    picked = auto_select_inputs(df, {"flag": "categorical"})
    assert picked is None
