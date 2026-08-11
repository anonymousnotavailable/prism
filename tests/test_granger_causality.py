"""Tests for modules.granger_causality — does one time series' past help
predict another's future ("Granger causality"), the time-series-precedence
counterpart to modules.causal_inference's cross-sectional propensity-score
matching and modules.did's before/after panel comparison. Tests predictive
precedence, not true causation — every result explicitly says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.granger_causality import (
    build_granger_chart,
    difference_until_stationary,
    granger_verdict,
    narrate_granger_causality,
    prepare_pair,
    run_granger_causality,
)


def _lagged_causal_frame(n=250, seed=0, coef=0.7):
    """x's lag-1 value feeds into y (x Granger-causes y); both series are
    stationary AR(1)-ish processes so no differencing should be needed.
    y does NOT feed back into x, so the reverse test should come up empty.
    """
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    y = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.5 * x[t - 1] + rng.normal(scale=1.0)
    for t in range(1, n):
        y[t] = 0.3 * y[t - 1] + coef * x[t - 1] + rng.normal(scale=1.0)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame({"date": dates, "x": x, "y": y})
    return df


def _independent_frame(n=200, seed=3):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    y = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.4 * x[t - 1] + rng.normal(scale=1.0)
        y[t] = 0.4 * y[t - 1] + rng.normal(scale=1.0)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"date": dates, "x": x, "y": y})


def _random_walk_causal_frame(n=250, seed=1):
    """Non-stationary (random-walk) pair where x's *change* drives y's
    change — differencing should be required to reveal the relationship."""
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.normal(size=n))
    y = np.zeros(n)
    for t in range(2, n):
        y[t] = y[t - 1] + 0.8 * (x[t - 1] - x[t - 2]) + rng.normal(scale=0.5)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"date": dates, "x": x, "y": y})


# ─────────────────────────────────────────────────────────────────────────
# prepare_pair
# ─────────────────────────────────────────────────────────────────────────
def test_prepare_pair_basic():
    df = _lagged_causal_frame(n=100)
    aligned, freq, error = prepare_pair(df, "date", "x", "y")
    assert error is None
    assert freq is not None
    assert list(aligned.columns) == ["x", "y"]
    assert len(aligned) >= 90


def test_prepare_pair_too_few_points():
    df = _lagged_causal_frame(n=10)
    aligned, freq, error = prepare_pair(df, "date", "x", "y")
    assert aligned is None
    assert error is not None


def test_prepare_pair_all_null():
    df = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=5), "x": [np.nan] * 5, "y": [np.nan] * 5})
    aligned, freq, error = prepare_pair(df, "date", "x", "y")
    assert aligned is None
    assert "No non-null" in error


# ─────────────────────────────────────────────────────────────────────────
# difference_until_stationary
# ─────────────────────────────────────────────────────────────────────────
def test_difference_already_stationary_no_diff_needed():
    rng = np.random.default_rng(0)
    values = np.zeros(200)
    for t in range(1, 200):
        values[t] = 0.3 * values[t - 1] + rng.normal()
    series = pd.Series(values)
    diffed, d, p_before, p_after = difference_until_stationary(series)
    assert d == 0
    assert p_before < 0.05


def test_difference_random_walk_needs_one_diff():
    rng = np.random.default_rng(1)
    series = pd.Series(np.cumsum(rng.normal(size=200)))
    diffed, d, p_before, p_after = difference_until_stationary(series)
    assert d >= 1
    assert p_after < 0.05


def test_difference_caps_at_max_diff():
    rng = np.random.default_rng(2)
    # Integrated of order 2 (cumulative sum of a random walk) — should hit
    # the cap rather than loop indefinitely searching for stationarity.
    series = pd.Series(np.cumsum(np.cumsum(rng.normal(size=200))))
    diffed, d, p_before, p_after = difference_until_stationary(series, max_diff=2)
    assert d <= 2


# ─────────────────────────────────────────────────────────────────────────
# run_granger_causality
# ─────────────────────────────────────────────────────────────────────────
def test_granger_forward_significant_reverse_not():
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y")
    assert result["ok"]
    assert result["forward"]["significant"]
    assert result["forward"]["p_value"] < 0.01
    assert not result["reverse"]["significant"]
    assert not result["feedback"]
    assert result["cause_col"] == "x"
    assert result["effect_col"] == "y"


def test_granger_detects_relationship_after_differencing():
    df = _random_walk_causal_frame(n=250, seed=1)
    result = run_granger_causality(df, "date", "x", "y")
    assert result["ok"]
    assert result["differencing"]["applied_d"] >= 1
    assert result["forward"]["significant"]


def test_granger_independent_series_neither_significant():
    df = _independent_frame(n=200, seed=3)
    result = run_granger_causality(df, "date", "x", "y")
    assert result["ok"]
    assert not result["forward"]["significant"]
    assert not result["reverse"]["significant"]
    assert not result["feedback"]


def test_granger_same_column_errors():
    df = _lagged_causal_frame(n=100)
    result = run_granger_causality(df, "date", "x", "x")
    assert not result["ok"]
    assert "error" in result


def test_granger_insufficient_data_errors():
    df = _lagged_causal_frame(n=15)
    result = run_granger_causality(df, "date", "x", "y")
    assert not result["ok"]


def test_granger_constant_column_handled_gracefully():
    df = _lagged_causal_frame(n=150)
    df["x"] = 5.0  # constant — ADF/VAR would otherwise choke on a singular matrix
    result = run_granger_causality(df, "date", "x", "y")
    assert not result["ok"]
    assert "error" in result


def test_granger_respects_max_lag():
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y", max_lag=2)
    assert result["ok"]
    assert result["selected_lag"] <= 2


# ─────────────────────────────────────────────────────────────────────────
# granger_verdict
# ─────────────────────────────────────────────────────────────────────────
def test_verdict_forward_only():
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y")
    text = granger_verdict(result)
    assert "x" in text and "y" in text
    assert "predict" in text.lower() or "help" in text.lower()


def test_verdict_neither_significant():
    df = _independent_frame(n=200, seed=3)
    result = run_granger_causality(df, "date", "x", "y")
    text = granger_verdict(result)
    assert "no" in text.lower()


def test_verdict_failed_result():
    text = granger_verdict({"ok": False, "error": "boom"})
    assert "boom" in text


# ─────────────────────────────────────────────────────────────────────────
# build_granger_chart
# ─────────────────────────────────────────────────────────────────────────
def test_build_chart_returns_figure():
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y")
    fig = build_granger_chart(result)
    assert fig is not None
    assert len(fig.data) >= 1


def test_build_chart_failed_result_returns_none():
    fig = build_granger_chart({"ok": False, "error": "boom"})
    assert fig is None


# ─────────────────────────────────────────────────────────────────────────
# narrate_granger_causality
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y")
    text, error = narrate_granger_causality(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    text, error = narrate_granger_causality(object(), {"ok": False, "error": "boom"})
    assert text == ""
    assert error is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    df = _lagged_causal_frame(n=250, seed=0)
    result = run_granger_causality(df, "date", "x", "y")

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_granger_causality(object(), result)
    assert error is None
    assert text == "It works."
    assert "granger" in captured["prompt"].lower() or "predict" in captured["prompt"].lower()
