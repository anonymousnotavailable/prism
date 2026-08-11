"""Tests for modules.survival — Kaplan-Meier survival curves and the
log-rank test. The classic "time-to-event" analysis (customer tenure until
churn, time until a machine fails, time until a loan defaults) that every
other statistical tool in Prism sidesteps: modules/domains.py's flag_churn
answers "has this user gone quiet by a fixed cutoff?", which throws away
exactly the information survival analysis is built to use — that a user who
signed up last week and hasn't churned *yet* is not the same evidence as one
who signed up two years ago and hasn't churned either (right-censoring).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.survival import (
    compute_kaplan_meier,
    log_rank_test,
    narrate_survival,
    survival_analysis,
)
from modules.visualization import plot_kaplan_meier


def _simple_durations_events():
    """Textbook 6-subject example (Klein & Moeschberger style): a mix of
    events and censored observations, small enough to hand-verify.
    Durations: 2, 3, 4(c), 5, 6(c), 7 — events at 2, 3, 5, 7; censored at 4, 6.
    """
    durations = np.array([2, 3, 4, 5, 6, 7])
    events = np.array([1, 1, 0, 1, 0, 1])
    return durations, events


def _two_group_panel(n=200, hazard_ratio=2.5, seed=0):
    """Group B has a higher hazard (shorter survival) than Group A by
    construction — exponential survival times, group A with rate 1, group B
    with rate `hazard_ratio` (higher rate = shorter expected survival =
    higher hazard). A administrative censoring time caps observation.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for group, rate in (("A", 1.0), ("B", hazard_ratio)):
        true_times = rng.exponential(1 / rate, n)
        censor_time = 1.5
        observed = np.minimum(true_times, censor_time)
        event = (true_times <= censor_time).astype(int)
        rows.append(pd.DataFrame({"group": group, "duration": observed, "event": event}))
    return pd.concat(rows, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────
# compute_kaplan_meier
# ─────────────────────────────────────────────────────────────────────────
def test_km_survival_starts_at_one_and_is_nonincreasing():
    durations, events = _simple_durations_events()
    result = compute_kaplan_meier(durations, events)
    assert result["ok"] is True
    curve = result["curve"]
    survs = [row["survival"] for row in curve]
    assert all(s2 <= s1 + 1e-9 for s1, s2 in zip(survs, survs[1:]))
    assert survs[0] <= 1.0


def test_km_hand_verified_values():
    """Manually verified product-limit estimate for the 6-subject example:
    S(2) = 5/6, S(3) = 5/6 * 4/5 = 4/6, S(5) = 4/6 * 2/3 = 4/9, S(7) = 4/9 * 0 = 0
    (at t=7 the single remaining subject at risk has the event, so survival
    drops to 0 — no one is left).
    """
    durations, events = _simple_durations_events()
    result = compute_kaplan_meier(durations, events)
    curve_by_time = {row["time"]: row["survival"] for row in result["curve"]}
    assert curve_by_time[2] == pytest.approx(5 / 6)
    assert curve_by_time[3] == pytest.approx(4 / 6)
    assert curve_by_time[5] == pytest.approx(4 / 9)
    assert curve_by_time[7] == pytest.approx(0.0, abs=1e-9)


def test_km_censoring_reduces_risk_set_without_a_survival_drop():
    """Censored observations (t=4, t=6) should not appear as event rows in
    the curve at all under the standard convention — only event times get
    a row — but they should reduce n_at_risk for subsequent event times.
    """
    durations, events = _simple_durations_events()
    result = compute_kaplan_meier(durations, events)
    times_in_curve = [row["time"] for row in result["curve"]]
    assert 4 not in times_in_curve
    assert 6 not in times_in_curve
    # at t=5: subjects with duration >= 5 are {5, 6, 7} = 3 at risk (4 was censored out at t=4)
    row5 = next(r for r in result["curve"] if r["time"] == 5)
    assert row5["n_at_risk"] == 3


def test_km_median_survival_time():
    durations, events = _simple_durations_events()
    result = compute_kaplan_meier(durations, events)
    # survival crosses 0.5 at t=5 (4/9 ~ 0.444 <= 0.5, previous point 4/6 ~ 0.667 > 0.5)
    assert result["median_survival"] == 5


def test_km_median_survival_none_when_never_reached():
    """All-censored-before-crossing-0.5 case: survival never drops to <= 0.5."""
    durations = np.array([1, 2, 3, 4, 5])
    events = np.array([0, 0, 0, 0, 0])  # everyone censored, no events at all
    result = compute_kaplan_meier(durations, events)
    assert result["ok"] is True
    assert result["median_survival"] is None
    assert result["curve"] == []  # no event times -> no curve rows (flat at 1.0 throughout)


def test_km_empty_input():
    result = compute_kaplan_meier(np.array([]), np.array([]))
    assert result["ok"] is False


def test_km_greenwood_se_present_and_nonnegative():
    durations, events = _simple_durations_events()
    result = compute_kaplan_meier(durations, events)
    for row in result["curve"]:
        assert row["se"] >= 0
        assert 0.0 <= row["ci_low"] <= row["survival"] <= row["ci_high"] <= 1.0


# ─────────────────────────────────────────────────────────────────────────
# log_rank_test
# ─────────────────────────────────────────────────────────────────────────
def test_log_rank_detects_real_hazard_difference():
    df = _two_group_panel(n=300, hazard_ratio=3.0)
    result = log_rank_test(df["duration"].to_numpy(), df["event"].to_numpy(), df["group"].to_numpy())
    assert result["ok"] is True
    assert result["p_value"] < 0.01
    assert result["df"] == 1


def test_log_rank_no_difference_when_groups_identical_hazard():
    # seed=4 picked deterministically (see module history) to land comfortably
    # non-significant under the null — the log-rank p-value is uniformly
    # distributed under H0, so *some* seeds will land under 0.05 by chance;
    # test_log_rank_p_value_is_calibrated_under_null below is the real
    # correctness check (mean p-value across many seeds ~= 0.5).
    df = _two_group_panel(n=300, hazard_ratio=1.0, seed=4)
    result = log_rank_test(df["duration"].to_numpy(), df["event"].to_numpy(), df["group"].to_numpy())
    assert result["ok"] is True
    assert result["p_value"] > 0.05


def test_log_rank_p_value_is_calibrated_under_null():
    """Under a true null (identical hazards), the log-rank p-value should
    be ~uniform(0,1) — its mean across many independent draws should land
    near 0.5. This is the real statistical-correctness check (a single
    seed's p-value alone can't distinguish "correct and unlucky" from
    "miscalibrated"); a badly-built test statistic would show a mean far
    from 0.5 or a wildly wrong false-positive rate.
    """
    pvals = [
        log_rank_test(df["duration"].to_numpy(), df["event"].to_numpy(), df["group"].to_numpy())["p_value"]
        for df in (_two_group_panel(n=300, hazard_ratio=1.0, seed=s) for s in range(30))
    ]
    assert 0.35 < np.mean(pvals) < 0.65


def test_log_rank_three_groups_df():
    rng = np.random.default_rng(5)
    rows = []
    for group, rate in (("A", 1.0), ("B", 1.0), ("C", 1.0)):
        times = rng.exponential(1 / rate, 100)
        observed = np.minimum(times, 1.5)
        event = (times <= 1.5).astype(int)
        rows.append(pd.DataFrame({"group": group, "duration": observed, "event": event}))
    df = pd.concat(rows, ignore_index=True)
    result = log_rank_test(df["duration"].to_numpy(), df["event"].to_numpy(), df["group"].to_numpy())
    assert result["ok"] is True
    assert result["df"] == 2


def test_log_rank_observed_minus_expected_sums_near_zero():
    df = _two_group_panel(n=150, hazard_ratio=2.0, seed=7)
    result = log_rank_test(df["duration"].to_numpy(), df["event"].to_numpy(), df["group"].to_numpy())
    total_o_minus_e = sum(g["observed"] - g["expected"] for g in result["groups"])
    assert total_o_minus_e == pytest.approx(0.0, abs=1e-6)


def test_log_rank_needs_at_least_two_groups():
    result = log_rank_test(np.array([1, 2, 3]), np.array([1, 1, 1]), np.array(["A", "A", "A"]))
    assert result["ok"] is False


def test_log_rank_needs_at_least_one_event():
    result = log_rank_test(np.array([1, 2, 3, 4]), np.array([0, 0, 0, 0]), np.array(["A", "A", "B", "B"]))
    assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────
# survival_analysis — the app-facing entry point (validation + orchestration)
# ─────────────────────────────────────────────────────────────────────────
def test_survival_analysis_overall_no_group():
    df = _two_group_panel(n=100, hazard_ratio=1.0, seed=11)
    result = survival_analysis(df, "duration", "event")
    assert result["ok"] is True
    assert result["log_rank"] is None
    assert "overall" in result
    assert result["overall"]["n"] == 200


def test_survival_analysis_with_group():
    df = _two_group_panel(n=100, hazard_ratio=3.0, seed=13)
    result = survival_analysis(df, "duration", "event", group_col="group")
    assert result["ok"] is True
    assert set(result["groups"].keys()) == {"A", "B"}
    assert result["log_rank"]["ok"] is True


def test_survival_analysis_missing_columns():
    df = _two_group_panel(n=20, seed=17)
    result = survival_analysis(df, "nope", "event")
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_survival_analysis_empty_df():
    result = survival_analysis(pd.DataFrame(), "duration", "event")
    assert result["ok"] is False


def test_survival_analysis_negative_durations_rejected():
    df = pd.DataFrame({"duration": [1, -2, 3, 4, 5], "event": [1, 1, 0, 1, 1]})
    result = survival_analysis(df, "duration", "event")
    assert result["ok"] is False
    assert "negative" in result["error"].lower()


def test_survival_analysis_event_col_not_binary():
    df = pd.DataFrame({"duration": [1, 2, 3, 4, 5], "event": [0, 1, 2, 1, 0]})
    result = survival_analysis(df, "duration", "event")
    assert result["ok"] is False


def test_survival_analysis_event_col_yes_no_coerced():
    df = pd.DataFrame(
        {"duration": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "event": ["Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No"]}
    )
    result = survival_analysis(df, "duration", "event")
    assert result["ok"] is True


def test_survival_analysis_too_few_rows():
    df = pd.DataFrame({"duration": [1, 2], "event": [1, 0]})
    result = survival_analysis(df, "duration", "event", min_rows=10)
    assert result["ok"] is False


def test_survival_analysis_group_too_many_levels():
    df = _two_group_panel(n=20, seed=19)
    df["group_fine"] = [f"g{i}" for i in range(len(df))]  # every row its own group
    result = survival_analysis(df, "duration", "event", group_col="group_fine", max_group_levels=6)
    assert result["ok"] is False


def test_survival_analysis_drops_missing_values():
    df = _two_group_panel(n=100, seed=23)
    df.loc[0:5, "duration"] = np.nan
    result = survival_analysis(df, "duration", "event")
    assert result["ok"] is True
    assert result["overall"]["n"] == 194


def test_survival_analysis_caps_huge_input():
    """Handle huge files explicitly: sample down rather than hang or crash
    on a very large dataset, same convention as market_basket's basket cap."""
    rng = np.random.default_rng(29)
    n = 60000
    df = pd.DataFrame({
        "duration": rng.exponential(1, n),
        "event": rng.integers(0, 2, n),
    })
    result = survival_analysis(df, "duration", "event", max_rows=20000)
    assert result["ok"] is True
    assert result["overall"]["n"] <= 20000
    assert any("sampled" in w.lower() for w in result["warnings"])


# ─────────────────────────────────────────────────────────────────────────
# plot_kaplan_meier
# ─────────────────────────────────────────────────────────────────────────
def test_plot_km_overall_one_trace():
    df = _two_group_panel(n=50, seed=41)
    result = survival_analysis(df, "duration", "event")
    fig = plot_kaplan_meier(result)
    assert fig is not None
    assert len(fig.data) == 1


def test_plot_km_by_group_multiple_traces():
    df = _two_group_panel(n=50, hazard_ratio=2.0, seed=43)
    result = survival_analysis(df, "duration", "event", group_col="group")
    fig = plot_kaplan_meier(result)
    assert fig is not None
    assert len(fig.data) == 2


def test_plot_km_none_on_failed_result():
    assert plot_kaplan_meier({"ok": False, "error": "boom"}) is None
    assert plot_kaplan_meier(None) is None


# ─────────────────────────────────────────────────────────────────────────
# narrate_survival
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    df = _two_group_panel(n=50, seed=31)
    result = survival_analysis(df, "duration", "event")
    text, error = narrate_survival(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    text, error = narrate_survival(object(), {"ok": False, "error": "boom"})
    assert text == ""
    assert error is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    df = _two_group_panel(n=50, hazard_ratio=3.0, seed=37)
    result = survival_analysis(df, "duration", "event", group_col="group")

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "Group B churns faster.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_survival(object(), result)
    assert error is None
    assert text == "Group B churns faster."
    assert "duration" in captured["prompt"]
