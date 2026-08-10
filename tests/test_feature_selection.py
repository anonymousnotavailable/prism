"""Tests for modules.feature_selection — rank-aggregated feature importance
for ML Lab (mutual information + statistical test + L1/Lasso), used to
recommend a feature subset before running baseline models.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.feature_selection import rank_features


def _classification_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    signal = rng.normal(size=n)
    target = (signal + rng.normal(scale=0.3, size=n) > 0).astype(int)
    return pd.DataFrame({
        "signal": signal,
        "noise1": rng.normal(size=n),
        "noise2": rng.normal(size=n),
        "category": rng.choice(["a", "b", "c"], size=n),
        "target": target,
    })


def _regression_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    signal = rng.normal(size=n)
    target = 3 * signal + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({
        "signal": signal,
        "noise1": rng.normal(size=n),
        "noise2": rng.normal(size=n),
        "target": target,
    })


def test_rank_features_classification_ranks_signal_above_noise():
    df = _classification_df()
    result = rank_features(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    assert result["error"] is None
    ranked_names = [r["feature"] for r in result["ranked"]]
    assert ranked_names[0] == "signal"
    assert "signal" in result["recommended_features"]


def test_rank_features_regression_ranks_signal_above_noise():
    df = _regression_df()
    result = rank_features(df, ["signal", "noise1", "noise2"], "target", "regression")
    assert result["error"] is None
    ranked_names = [r["feature"] for r in result["ranked"]]
    assert ranked_names[0] == "signal"


def test_rank_features_returns_all_requested_features():
    df = _classification_df()
    features = ["signal", "noise1", "noise2", "category"]
    result = rank_features(df, features, "target", "classification")
    assert {r["feature"] for r in result["ranked"]} == set(features)


def test_rank_features_recommended_k_is_bounded():
    df = _classification_df()
    features = ["signal", "noise1", "noise2", "category"]
    result = rank_features(df, features, "target", "classification")
    assert 1 <= result["recommended_k"] <= len(features)
    assert len(result["recommended_features"]) == result["recommended_k"]


def test_rank_features_errors_with_no_feature_columns():
    df = _classification_df()
    result = rank_features(df, [], "target", "classification")
    assert result["error"] is not None
    assert result["ranked"] == []


def test_rank_features_errors_with_single_class_target():
    df = _classification_df()
    df["target"] = 1
    result = rank_features(df, ["signal", "noise1"], "target", "classification")
    assert result["error"] is not None


def test_rank_features_errors_with_too_few_rows():
    df = _classification_df(n=5)
    result = rank_features(df, ["signal", "noise1"], "target", "classification")
    assert result["error"] is not None


def test_rank_features_drops_rows_with_missing_values():
    df = _classification_df()
    df.loc[0:10, "signal"] = np.nan
    result = rank_features(df, ["signal", "noise1"], "target", "classification")
    assert result["error"] is None


def test_rank_features_handles_all_missing_feature_column():
    df = _classification_df()
    df["allnull"] = np.nan
    result = rank_features(df, ["signal", "allnull"], "target", "classification")
    # allnull should be dropped from consideration, not crash the whole run
    assert result["error"] is None
    ranked_names = {r["feature"] for r in result["ranked"]}
    assert "allnull" not in ranked_names
