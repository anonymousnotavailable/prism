"""Tests for modules.did — Difference-in-Differences estimation, the
before/after + treatment/control counterpart to modules.causal_inference's
cross-sectional propensity score matching. Both answer "what's the real
effect of the treatment", but DiD works off panel/repeated-observation data
(two or more time periods) instead of matching similar units at one point
in time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.did import estimate_diff_in_differences, narrate_diff_in_differences
from modules.visualization import plot_diff_in_diff, plot_did_pre_trend


def _classic_panel(n_per_cell=200, true_effect=4.0, seed=0):
    """Textbook 2x2 DiD setup: two groups (treated/control), two periods
    (pre/post). Both groups share the same underlying trend (+2 from pre to
    post) and the same baseline level difference (treated group runs 3
    units higher throughout) — the only thing that should show up in the
    DiD estimate is `true_effect`, applied only to the treated group in the
    post period.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for group in ("treated", "control"):
        base = 10.0 + (3.0 if group == "treated" else 0.0)
        for period in ("pre", "post"):
            trend = 2.0 if period == "post" else 0.0
            effect = true_effect if (group == "treated" and period == "post") else 0.0
            outcome = base + trend + effect + rng.normal(0, 1.5, n_per_cell)
            rows.append(pd.DataFrame({"group": group, "period": period, "outcome": outcome}))
    return pd.concat(rows, ignore_index=True), true_effect


def _panel_with_diverging_pretrend(n_per_cell=150, seed=1):
    """Treated group is already trending up faster than control *before*
    treatment starts — a parallel-trends violation. Three pre-periods
    (t0, t1, t2) then a post period.
    """
    rng = np.random.default_rng(seed)
    rows = []
    periods = ["t0", "t1", "t2", "post"]
    for group in ("treated", "control"):
        for i, period in enumerate(periods):
            slope = 3.0 if group == "treated" else 0.5  # treated already trending up faster pre-treatment
            outcome = 10.0 + slope * i + rng.normal(0, 1.0, n_per_cell)
            rows.append(pd.DataFrame({"group": group, "period": period, "outcome": outcome}))
    return pd.concat(rows, ignore_index=True)


def _panel_with_parallel_pretrend(n_per_cell=150, true_effect=5.0, seed=2):
    """Both groups trend identically pre-treatment (parallel trends holds),
    then the treated group jumps by true_effect in the post period.
    """
    rng = np.random.default_rng(seed)
    rows = []
    periods = ["t0", "t1", "t2", "post"]
    for group in ("treated", "control"):
        base = 10.0 + (2.0 if group == "treated" else 0.0)
        for i, period in enumerate(periods):
            trend = 1.0 * i  # identical slope for both groups
            effect = true_effect if (group == "treated" and period == "post") else 0.0
            outcome = base + trend + effect + rng.normal(0, 1.0, n_per_cell)
            rows.append(pd.DataFrame({"group": group, "period": period, "outcome": outcome}))
    return pd.concat(rows, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────
# estimate_diff_in_differences — happy path
# ─────────────────────────────────────────────────────────────────────────
def test_recovers_true_effect_within_tolerance():
    df, true_effect = _classic_panel()
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is True
    assert result["did_estimate"] == pytest.approx(true_effect, abs=0.6)
    assert result["ci_low"] < result["did_estimate"] < result["ci_high"]
    assert result["p_value"] < 0.05


def test_cell_means_and_ns_reported():
    df, _ = _classic_panel(n_per_cell=50)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert set(result["cell_means"].keys()) == {"treated_pre", "treated_post", "control_pre", "control_post"}
    assert result["cell_ns"]["treated_pre"] == 50
    assert result["cell_ns"]["control_post"] == 50


def test_naive_diff_in_means_matches_regression_estimate():
    """The 2x2 OLS-with-interaction estimate should equal the textbook
    (treated_post - treated_pre) - (control_post - control_pre) formula —
    they're mathematically identical for the unweighted 2x2 case, so this
    is a correctness check on the regression construction, not just a
    plausibility check.
    """
    df, _ = _classic_panel(n_per_cell=80)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    m = result["cell_means"]
    manual = (m["treated_post"] - m["treated_pre"]) - (m["control_post"] - m["control_pre"])
    assert result["did_estimate"] == pytest.approx(manual, abs=1e-6)


def test_control_value_auto_detected():
    df, _ = _classic_panel(n_per_cell=30)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["control_value"] == "control"


# ─────────────────────────────────────────────────────────────────────────
# estimate_diff_in_differences — failure / validation paths (never raises)
# ─────────────────────────────────────────────────────────────────────────
def test_empty_dataframe():
    result = estimate_diff_in_differences(pd.DataFrame(), "group", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is False


def test_missing_column():
    df, _ = _classic_panel(n_per_cell=10)
    result = estimate_diff_in_differences(df, "nope", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_non_numeric_outcome():
    df, _ = _classic_panel(n_per_cell=10)
    df["outcome"] = df["outcome"].astype(str)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is False
    assert "numeric" in result["error"].lower()


def test_group_col_more_than_two_values():
    df, _ = _classic_panel(n_per_cell=10)
    df.loc[0, "group"] = "third"
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is False
    assert "2 groups" in result["error"] or "two groups" in result["error"].lower()


def test_invalid_treated_value():
    df, _ = _classic_panel(n_per_cell=10)
    result = estimate_diff_in_differences(df, "group", "nonexistent", "period", "pre", "post", "outcome")
    assert result["ok"] is False


def test_invalid_period_values():
    df, _ = _classic_panel(n_per_cell=10)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "nope", "post", "outcome")
    assert result["ok"] is False
    assert "period" in result["error"].lower()


def test_pre_and_post_period_must_differ():
    df, _ = _classic_panel(n_per_cell=10)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "pre", "outcome")
    assert result["ok"] is False


def test_too_few_units_in_a_cell():
    df, _ = _classic_panel(n_per_cell=3)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome", min_cell_size=5)
    assert result["ok"] is False
    assert "not enough" in result["error"].lower()


def test_missing_values_dropped_not_crashing():
    df, _ = _classic_panel(n_per_cell=50)
    df.loc[0:5, "outcome"] = np.nan
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["ok"] is True


# ─────────────────────────────────────────────────────────────────────────
# Parallel-trends pre-trend check
# ─────────────────────────────────────────────────────────────────────────
def test_pretrend_check_flags_diverging_trends():
    df = _panel_with_diverging_pretrend()
    result = estimate_diff_in_differences(
        df, "group", "treated", "period", "t2", "post", "outcome",
        pre_trend_periods=["t0", "t1", "t2"],
    )
    assert result["ok"] is True
    pretrend = result["pre_trend_check"]
    assert pretrend is not None
    assert pretrend["ok"] is True
    assert pretrend["p_value"] < 0.05
    assert pretrend["diverging"] is True


def test_pretrend_check_passes_on_parallel_trends():
    df = _panel_with_parallel_pretrend()
    result = estimate_diff_in_differences(
        df, "group", "treated", "period", "t2", "post", "outcome",
        pre_trend_periods=["t0", "t1", "t2"],
    )
    pretrend = result["pre_trend_check"]
    assert pretrend is not None
    assert pretrend["ok"] is True
    assert pretrend["diverging"] is False
    assert result["did_estimate"] == pytest.approx(5.0, abs=0.6)


def test_pretrend_check_none_when_not_requested():
    df, _ = _classic_panel(n_per_cell=30)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert result["pre_trend_check"] is None


def test_pretrend_check_needs_at_least_two_periods():
    df = _panel_with_parallel_pretrend()
    result = estimate_diff_in_differences(
        df, "group", "treated", "period", "t2", "post", "outcome",
        pre_trend_periods=["t0"],
    )
    assert result["pre_trend_check"]["ok"] is False


def test_pretrend_check_caveat_text_present():
    df = _panel_with_parallel_pretrend()
    result = estimate_diff_in_differences(
        df, "group", "treated", "period", "t2", "post", "outcome",
        pre_trend_periods=["t0", "t1", "t2"],
    )
    assert "caveat" in result["pre_trend_check"]
    assert result["pre_trend_check"]["caveat"]


# ─────────────────────────────────────────────────────────────────────────
# Warnings
# ─────────────────────────────────────────────────────────────────────────
def test_small_sample_warning():
    df, _ = _classic_panel(n_per_cell=6)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome", min_cell_size=5)
    assert result["ok"] is True
    assert any("small" in w.lower() for w in result["warnings"])


def test_no_small_sample_warning_when_plenty_of_data():
    df, _ = _classic_panel(n_per_cell=200)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    assert not any("small" in w.lower() for w in result["warnings"])


# ─────────────────────────────────────────────────────────────────────────
# narrate_diff_in_differences
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    df, _ = _classic_panel(n_per_cell=30)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    text, error = narrate_diff_in_differences(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    result = {"ok": False, "error": "boom"}
    text, error = narrate_diff_in_differences(object(), result)
    assert text == ""
    assert error is not None


# ─────────────────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────────────────
def test_plot_diff_in_diff_returns_figure_with_three_traces():
    df, _ = _classic_panel(n_per_cell=30)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")
    fig = plot_diff_in_diff(result)
    assert fig is not None
    assert len(fig.data) == 3  # control, treated actual, treated counterfactual


def test_plot_diff_in_diff_none_on_failed_result():
    assert plot_diff_in_diff({"ok": False, "error": "boom"}) is None
    assert plot_diff_in_diff(None) is None


def test_plot_did_pre_trend_returns_none_on_empty_df():
    assert plot_did_pre_trend({"ok": True}, "group", "outcome", pd.DataFrame()) is None
    assert plot_did_pre_trend({"ok": True}, "group", "outcome", None) is None


def test_plot_did_pre_trend_returns_figure():
    means_df = pd.DataFrame(
        {"period": ["t0", "t1", "t0", "t1"], "group": ["treated", "treated", "control", "control"], "mean": [1.0, 2.0, 1.0, 1.9]}
    )
    fig = plot_did_pre_trend({"ok": True}, "group", "outcome", means_df)
    assert fig is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    df, _ = _classic_panel(n_per_cell=30)
    result = estimate_diff_in_differences(df, "group", "treated", "period", "pre", "post", "outcome")

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_diff_in_differences(object(), result)
    assert error is None
    assert text == "It works."
    assert "group" in captured["prompt"]
