"""Tests for modules.mllab.run_conformal_regression — split-conformal
prediction intervals for regression baselines in ML Lab.

Split-conformal prediction gives a distribution-free coverage guarantee:
fit a model on a training fold, compute nonconformity scores (|residual|)
on a held-out calibration fold, take the (1-alpha) quantile of those
scores, then widen every test-set point prediction by that fixed amount.
The guarantee is *marginal* coverage — across many draws, the empirical
coverage on the test set should land close to the target (1-alpha) — so
these tests check the empirical coverage is within a generous tolerance
band of the target rather than requiring an exact match (it's a
statistical guarantee, not a deterministic one).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.mllab import build_conformal_chart, conformal_verdict, run_conformal_regression


def _regression_df(n: int = 600, seed: int = 0, noise: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    cat = rng.choice(["a", "b", "c"], size=n)
    target = 3 * x1 - 2 * x2 + rng.normal(scale=noise, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "cat": cat, "target": target})


# --- coverage guarantee ------------------------------------------------

def test_empirical_coverage_near_target_on_large_dataset():
    df = _regression_df(n=1500, seed=1)
    result = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.1)
    assert "error" not in result
    assert result["target_coverage"] == 0.9
    # Marginal guarantee — allow a wide-ish tolerance band since this is a
    # single draw, not an average over many repeated splits.
    assert 0.80 <= result["empirical_coverage"] <= 0.99


def test_lower_alpha_gives_wider_intervals_than_higher_alpha():
    df = _regression_df(n=1200, seed=2)
    tight = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.3)  # 70% coverage
    wide = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.05)  # 95% coverage
    assert wide["mean_interval_width"] > tight["mean_interval_width"]


def test_noisier_target_gives_wider_intervals():
    tight_df = _regression_df(n=800, seed=3, noise=0.5)
    wide_df = _regression_df(n=800, seed=3, noise=5.0)
    tight = run_conformal_regression(tight_df, ["x1", "x2", "cat"], "target", alpha=0.1)
    wide = run_conformal_regression(wide_df, ["x1", "x2", "cat"], "target", alpha=0.1)
    assert wide["mean_interval_width"] > tight["mean_interval_width"]


# --- shape / contract ---------------------------------------------------

def test_predictions_frame_has_expected_columns_and_bounds():
    df = _regression_df(n=500, seed=4)
    result = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.1)
    preds = result["predictions"]
    assert list(preds.columns) == ["actual", "predicted", "lower", "upper"]
    assert (preds["lower"] <= preds["predicted"]).all()
    assert (preds["predicted"] <= preds["upper"]).all()
    assert len(preds) == result["n_test"]


def test_split_sizes_sum_to_available_rows():
    df = _regression_df(n=500, seed=5)
    result = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.1)
    assert result["n_train"] + result["n_calib"] + result["n_test"] == 500


# --- edge cases -----------------------------------------------------------

def test_too_few_rows_returns_error_not_exception():
    df = _regression_df(n=10, seed=6)
    result = run_conformal_regression(df, ["x1", "x2"], "target", alpha=0.1)
    assert "error" in result


def test_non_numeric_target_returns_error():
    df = _regression_df(n=500, seed=7)
    df["target"] = df["target"].apply(lambda v: "hi" if v > 0 else "lo")
    result = run_conformal_regression(df, ["x1", "x2"], "target", alpha=0.1)
    assert "error" in result


def test_all_null_target_returns_error():
    df = _regression_df(n=500, seed=8)
    df["target"] = np.nan
    result = run_conformal_regression(df, ["x1", "x2"], "target", alpha=0.1)
    assert "error" in result


def test_invalid_alpha_returns_error():
    df = _regression_df(n=500, seed=9)
    for bad_alpha in (0.0, 1.0, -0.1, 1.5):
        result = run_conformal_regression(df, ["x1", "x2"], "target", alpha=bad_alpha)
        assert "error" in result


def test_nan_rows_in_features_are_dropped_not_fatal():
    df = _regression_df(n=500, seed=10)
    df.loc[0:20, "x1"] = np.nan
    result = run_conformal_regression(df, ["x1", "x2"], "target", alpha=0.1)
    assert "error" not in result
    assert result["n_train"] + result["n_calib"] + result["n_test"] <= 500


# --- chart / verdict helpers ------------------------------------------

def test_build_conformal_chart_returns_figure_with_traces():
    df = _regression_df(n=500, seed=11)
    result = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.1)
    fig = build_conformal_chart(result)
    assert len(fig.data) >= 2  # at minimum: interval band + actual points


def test_conformal_verdict_mentions_coverage_percentage():
    df = _regression_df(n=800, seed=12)
    result = run_conformal_regression(df, ["x1", "x2", "cat"], "target", alpha=0.1)
    verdict = conformal_verdict(result)
    assert "90%" in verdict or "0.9" in verdict
    assert isinstance(verdict, str) and len(verdict) > 0


def test_conformal_verdict_handles_error_result_gracefully():
    result = {"error": "not enough data"}
    verdict = conformal_verdict(result)
    assert isinstance(verdict, str)
