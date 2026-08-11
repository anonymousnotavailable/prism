"""Tests for modules.bayesian_ab — Bayesian A/B testing via the beta-binomial
conjugate model. Complements modules.stats_lab's frequentist chi-square test
(which answers "is the difference in conversion rate statistically
significant") with the Bayesian framing: a posterior distribution per
variant, a credible interval, P(treatment beats control), and an
expected-loss decision signal — the "probability B beats A" style popularized
by tools like VWO/Optimizely.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.bayesian_ab import (
    bayesian_ab_test,
    beta_posterior,
    expected_loss,
    lift_distribution,
    narrate_bayesian_ab,
    posterior_summary,
    prob_b_beats_a,
)
from modules.visualization import plot_bayesian_ab_posteriors


def _ab_frame(n_control=2000, n_treatment=2000, p_control=0.10, p_treatment=0.10, seed=0):
    rng = np.random.default_rng(seed)
    control = pd.DataFrame({
        "variant": "control",
        "converted": rng.binomial(1, p_control, n_control),
    })
    treatment = pd.DataFrame({
        "variant": "treatment",
        "converted": rng.binomial(1, p_treatment, n_treatment),
    })
    return pd.concat([control, treatment], ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────
# beta_posterior / posterior_summary
# ─────────────────────────────────────────────────────────────────────────
def test_beta_posterior_conjugate_update():
    alpha, beta = beta_posterior(successes=60, trials=100, prior_alpha=1.0, prior_beta=1.0)
    assert alpha == pytest.approx(61.0)
    assert beta == pytest.approx(41.0)


def test_beta_posterior_custom_prior():
    alpha, beta = beta_posterior(successes=5, trials=10, prior_alpha=2.0, prior_beta=3.0)
    assert alpha == pytest.approx(7.0)
    assert beta == pytest.approx(8.0)


def test_beta_posterior_rejects_invalid_counts():
    with pytest.raises(ValueError):
        beta_posterior(successes=20, trials=10)


def test_posterior_summary_uniform_prior_mean():
    summary = posterior_summary(alpha=1.0, beta=1.0)
    assert summary["mean"] == pytest.approx(0.5)
    assert summary["ci_low"] < 0.5 < summary["ci_high"]
    # For Beta(1,1) the 95% CI is exactly [0.025, 0.975]
    assert summary["ci_low"] == pytest.approx(0.025, abs=1e-3)
    assert summary["ci_high"] == pytest.approx(0.975, abs=1e-3)


def test_posterior_summary_mode_undefined_near_boundary():
    # alpha or beta <= 1 -> mode is not well-defined (U-shaped or monotonic density)
    summary = posterior_summary(alpha=1.0, beta=5.0)
    assert summary["mode"] is None


def test_posterior_summary_narrows_with_more_data():
    narrow = posterior_summary(alpha=501, beta=501)   # ~1000 observations
    wide = posterior_summary(alpha=6, beta=6)          # ~10 observations
    assert (narrow["ci_high"] - narrow["ci_low"]) < (wide["ci_high"] - wide["ci_low"])


# ─────────────────────────────────────────────────────────────────────────
# prob_b_beats_a
# ─────────────────────────────────────────────────────────────────────────
def test_prob_b_beats_a_identical_posteriors_is_half():
    result = prob_b_beats_a(50, 50, 50, 50, random_state=1)
    assert result["value"] == pytest.approx(0.5, abs=0.02)


def test_prob_b_beats_a_clear_winner_close_to_one():
    # B has a dramatically higher posterior mean and both are tightly estimated.
    result = prob_b_beats_a(alpha_a=100, beta_a=900, alpha_b=300, beta_b=700, random_state=1)
    assert result["value"] > 0.999


def test_prob_b_beats_a_complementary_with_swap():
    a_to_b = prob_b_beats_a(80, 120, 130, 170, random_state=1)["value"]
    b_to_a = prob_b_beats_a(130, 170, 80, 120, random_state=1)["value"]
    assert (a_to_b + b_to_a) == pytest.approx(1.0, abs=0.02)


def test_prob_b_beats_a_exact_method_used_for_small_integer_params():
    result = prob_b_beats_a(alpha_a=11, beta_a=91, alpha_b=21, beta_b=81, random_state=1)
    assert result["method"] == "exact"


def test_prob_b_beats_a_exact_and_monte_carlo_agree():
    exact = prob_b_beats_a(alpha_a=11, beta_a=91, alpha_b=21, beta_b=81, random_state=1)
    # Force Monte Carlo by importing the private helper directly.
    from modules.bayesian_ab import _prob_b_beats_a_monte_carlo
    mc_value = _prob_b_beats_a_monte_carlo(11, 91, 21, 81, n_samples=500_000, random_state=1)
    assert exact["value"] == pytest.approx(mc_value, abs=0.01)


def test_prob_b_beats_a_falls_back_to_monte_carlo_for_large_params():
    result = prob_b_beats_a(alpha_a=50_000, beta_a=50_000, alpha_b=50_500, beta_b=49_500, random_state=1)
    assert result["method"] == "monte_carlo"


# ─────────────────────────────────────────────────────────────────────────
# expected_loss
# ─────────────────────────────────────────────────────────────────────────
def test_expected_loss_nonnegative():
    loss = expected_loss(50, 50, 80, 40, random_state=1)
    assert loss["choose_control"] >= 0
    assert loss["choose_treatment"] >= 0


def test_expected_loss_favors_the_better_variant():
    # Treatment posterior is clearly better -> loss of choosing treatment should be
    # much smaller than the loss of choosing control.
    loss = expected_loss(alpha_a=100, beta_a=900, alpha_b=300, beta_b=700, random_state=1)
    assert loss["choose_treatment"] < loss["choose_control"]


def test_expected_loss_symmetric_when_identical():
    loss = expected_loss(50, 50, 50, 50, random_state=1)
    assert loss["choose_treatment"] == pytest.approx(loss["choose_control"], abs=0.01)


# ─────────────────────────────────────────────────────────────────────────
# lift_distribution
# ─────────────────────────────────────────────────────────────────────────
def test_lift_distribution_positive_when_treatment_better():
    lift = lift_distribution(alpha_a=100, beta_a=900, alpha_b=300, beta_b=700, random_state=1)
    assert lift["absolute_mean"] > 0
    assert lift["relative_mean"] > 0
    assert lift["absolute_ci_low"] < lift["absolute_mean"] < lift["absolute_ci_high"]


# ─────────────────────────────────────────────────────────────────────────
# bayesian_ab_test — app-facing entry point
# ─────────────────────────────────────────────────────────────────────────
def test_bayesian_ab_test_recovers_known_effect():
    df = _ab_frame(n_control=3000, n_treatment=3000, p_control=0.08, p_treatment=0.12, seed=0)
    result = bayesian_ab_test(df, "variant", "converted")
    assert result["ok"]
    assert result["control_value"] == "control"
    assert result["treatment_value"] == "treatment"
    assert result["prob_treatment_beats_control"]["value"] > 0.99
    # True rates (0.08, 0.12) should fall inside their own 95% credible intervals
    ctrl_summary = result["control"]["summary"]
    trt_summary = result["treatment"]["summary"]
    assert ctrl_summary["ci_low"] < 0.08 < ctrl_summary["ci_high"]
    assert trt_summary["ci_low"] < 0.12 < trt_summary["ci_high"]
    assert "treatment" in result["recommendation"]


def test_bayesian_ab_test_no_difference_is_inconclusive():
    df = _ab_frame(n_control=300, n_treatment=300, p_control=0.10, p_treatment=0.10, seed=3)
    result = bayesian_ab_test(df, "variant", "converted")
    assert result["ok"]
    p = result["prob_treatment_beats_control"]["value"]
    assert 0.05 < p < 0.95


def test_bayesian_ab_test_missing_columns():
    df = _ab_frame(n_control=50, n_treatment=50)
    result = bayesian_ab_test(df, "nope", "converted")
    assert not result["ok"]
    assert "not found" in result["error"]


def test_bayesian_ab_test_non_binary_outcome():
    df = _ab_frame(n_control=50, n_treatment=50)
    df["converted"] = np.random.default_rng(0).integers(0, 3, len(df))  # 3 distinct values
    result = bayesian_ab_test(df, "variant", "converted")
    assert not result["ok"]
    assert "2 values" in result["error"]


def test_bayesian_ab_test_too_few_rows_per_variant():
    df = _ab_frame(n_control=5, n_treatment=5)
    result = bayesian_ab_test(df, "variant", "converted", min_trials_per_variant=10)
    assert not result["ok"]
    assert "Not enough rows" in result["error"]


def test_bayesian_ab_test_more_than_two_levels_requires_explicit_values():
    df = _ab_frame(n_control=200, n_treatment=200)
    extra = pd.DataFrame({"variant": "control_v2", "converted": np.random.default_rng(0).binomial(1, 0.1, 200)})
    df = pd.concat([df, extra], ignore_index=True)
    result = bayesian_ab_test(df, "variant", "converted")
    assert not result["ok"]
    assert "control_value" in result["error"]

    # Now with explicit values, it should work.
    result2 = bayesian_ab_test(df, "variant", "converted", control_value="control", treatment_value="treatment")
    assert result2["ok"]


def test_bayesian_ab_test_same_column_twice_errors_gracefully():
    # Regression test: passing the same column name for both variant_col and
    # success_col used to crash (df[[col, col]] selects a duplicate-column
    # DataFrame, not a Series, breaking downstream .unique()/.dropna() calls)
    # instead of failing cleanly.
    df = pd.DataFrame({"flag": ["yes"] * 20 + ["no"] * 20})
    result = bayesian_ab_test(df, "flag", "flag")
    assert not result["ok"]
    assert "different columns" in result["error"]


def test_bayesian_ab_test_empty_dataframe():
    result = bayesian_ab_test(pd.DataFrame(), "variant", "converted")
    assert not result["ok"]


def test_bayesian_ab_test_rejects_nonpositive_prior():
    df = _ab_frame(n_control=50, n_treatment=50)
    result = bayesian_ab_test(df, "variant", "converted", prior_alpha=0)
    assert not result["ok"]


def test_bayesian_ab_test_custom_prior_shifts_posterior_with_thin_data():
    df = _ab_frame(n_control=15, n_treatment=15, p_control=0.5, p_treatment=0.5, seed=9)
    weak_prior = bayesian_ab_test(df, "variant", "converted", prior_alpha=1, prior_beta=1)
    strong_skeptical_prior = bayesian_ab_test(df, "variant", "converted", prior_alpha=1, prior_beta=99)
    # A strongly skeptical (low-rate) prior should pull the posterior mean down relative to a flat prior.
    assert strong_skeptical_prior["control"]["summary"]["mean"] < weak_prior["control"]["summary"]["mean"]


# ─────────────────────────────────────────────────────────────────────────
# narrate_bayesian_ab
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    df = _ab_frame(n_control=100, n_treatment=100)
    result = bayesian_ab_test(df, "variant", "converted")
    text, error = narrate_bayesian_ab(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    text, error = narrate_bayesian_ab(object(), {"ok": False, "error": "boom"})
    assert text == ""
    assert error is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    df = _ab_frame(n_control=100, n_treatment=100)
    result = bayesian_ab_test(df, "variant", "converted")

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_bayesian_ab(object(), result)
    assert error is None
    assert text == "It works."
    assert "variant" in captured["prompt"]


# ─────────────────────────────────────────────────────────────────────────
# Chart
# ─────────────────────────────────────────────────────────────────────────
def test_plot_bayesian_ab_posteriors_returns_figure_with_two_traces():
    df = _ab_frame(n_control=200, n_treatment=200, p_control=0.1, p_treatment=0.2, seed=2)
    result = bayesian_ab_test(df, "variant", "converted")
    fig = plot_bayesian_ab_posteriors(result)
    assert fig is not None
    assert len(fig.data) == 2


def test_plot_bayesian_ab_posteriors_none_for_failed_result():
    fig = plot_bayesian_ab_posteriors({"ok": False, "error": "boom"})
    assert fig is None
