"""Tests for modules.mllab.run_cross_validation — k-fold cross-validation
for ML Lab's baseline model comparison, replacing/augmenting the single
80/20 train/test split with a StratifiedKFold (classification) or KFold
(regression) mean +/- std estimate, computed via a leakage-safe sklearn
Pipeline (preprocessing refit inside every fold, not once up front).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.mllab import build_cv_score_chart, cv_verdict, run_cross_validation


def _classification_df(n: int = 300, seed: int = 0, n_classes: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    cat = rng.choice(["a", "b", "c"], size=n)
    if n_classes == 2:
        target = (x1 + rng.normal(scale=0.3, size=n) > 0).astype(int)
    else:
        score = x1 + rng.normal(scale=0.3, size=n)
        target = pd.cut(score, bins=n_classes, labels=[f"c{i}" for i in range(n_classes)])
    return pd.DataFrame({"x1": x1, "x2": x2, "cat": cat, "target": target})


def _regression_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    cat = rng.choice(["a", "b", "c"], size=n)
    target = 3 * x1 - 2 * x2 + rng.normal(scale=1.0, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "cat": cat, "target": target})


# --- basic shape / contract ------------------------------------------------

def test_classification_returns_both_models_with_mean_and_std():
    df = _classification_df()
    result = run_cross_validation(df, ["x1", "x2", "cat"], "target", "classification", k=5)
    assert "error" not in result
    assert result["k"] == 5
    assert set(result["results"].keys()) == {"Baseline", "Random Forest"}
    for model_name in ("Baseline", "Random Forest"):
        for metric in ("accuracy", "f1"):
            entry = result["results"][model_name][metric]
            assert 0.0 <= entry["mean"] <= 1.0
            assert entry["std"] >= 0.0
            assert len(entry["scores"]) == 5


def test_regression_returns_both_models_with_rmse_and_r2():
    df = _regression_df()
    result = run_cross_validation(df, ["x1", "x2", "cat"], "target", "regression", k=5)
    assert "error" not in result
    for model_name in ("Baseline", "Random Forest"):
        assert result["results"][model_name]["rmse"]["mean"] >= 0.0
        assert len(result["results"][model_name]["r2"]["scores"]) == 5


def test_informative_features_beat_pure_noise_on_average_r2():
    rng = np.random.default_rng(1)
    n = 400
    informative = rng.normal(size=n)
    noise = rng.normal(size=n)
    target = 5 * informative + rng.normal(scale=0.2, size=n)
    df = pd.DataFrame({"informative": informative, "noise": noise, "target": target})
    result = run_cross_validation(df, ["informative"], "target", "regression", k=5)
    assert result["results"]["Random Forest"]["r2"]["mean"] > 0.5


# --- k handling -------------------------------------------------------------

def test_k_is_reduced_and_flagged_when_exceeding_min_class_count():
    df = _classification_df(n=60, seed=2)
    # Force a rare class with only 2 members.
    df.loc[df.index[:2], "target"] = 2
    result = run_cross_validation(df, ["x1", "x2"], "target", "classification", k=10)
    assert "error" not in result
    assert result["k"] <= 2
    assert result["k_reduced"] is True


def test_k_too_small_returns_error():
    df = _regression_df(n=100, seed=3)
    result = run_cross_validation(df, ["x1", "x2"], "target", "regression", k=1)
    assert "error" in result


# --- edge cases ---------------------------------------------------------

def test_too_few_rows_returns_error_not_exception():
    df = _regression_df(n=8, seed=4)
    result = run_cross_validation(df, ["x1", "x2"], "target", "regression", k=5)
    assert "error" in result


def test_single_class_target_returns_error():
    df = _classification_df(n=100, seed=5)
    df["target"] = 1
    result = run_cross_validation(df, ["x1", "x2"], "target", "classification", k=5)
    assert "error" in result


def test_empty_feature_list_returns_error():
    df = _regression_df(n=100, seed=6)
    result = run_cross_validation(df, [], "target", "regression", k=5)
    assert "error" in result


def test_nan_rows_dropped_not_fatal():
    df = _regression_df(n=200, seed=7)
    df.loc[0:10, "x1"] = np.nan
    result = run_cross_validation(df, ["x1", "x2"], "target", "regression", k=5)
    assert "error" not in result
    assert result["n_samples"] <= 200


# --- chart / verdict helpers ------------------------------------------

def test_build_cv_score_chart_returns_figure_with_per_model_traces():
    df = _classification_df()
    result = run_cross_validation(df, ["x1", "x2", "cat"], "target", "classification", k=5)
    fig = build_cv_score_chart(result, "accuracy")
    assert len(fig.data) == 2  # one box trace per model


def test_cv_verdict_mentions_k_and_is_nonempty_string():
    df = _classification_df()
    result = run_cross_validation(df, ["x1", "x2", "cat"], "target", "classification", k=5)
    verdict = cv_verdict(result)
    assert isinstance(verdict, str) and len(verdict) > 0
    assert "5" in verdict


def test_cv_verdict_handles_error_result_gracefully():
    result = {"error": "not enough data"}
    verdict = cv_verdict(result)
    assert isinstance(verdict, str)
