"""Tests for modules.mllab.rank_features — the Feature Selection Engine
(mutual information / L1 / RFE consensus ranking) added to ML Lab in Run 3.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.mllab import MIN_ROWS_FOR_SELECTION, rank_features


def _regression_df(n=200, seed=42):
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)  # strongly informative: y depends on this
    x2 = rng.normal(0, 1, n)  # pure noise, unrelated to y
    noise_cat = rng.choice(["A", "B", "C"], n)  # unrelated categorical
    y = 4 * x1 + rng.normal(0, 0.5, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "cat_noise": noise_cat, "y": y})


def _classification_df(n=200, seed=42):
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)  # noise
    y = (x1 + rng.normal(0, 0.3, n) > 0).astype(int)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_rank_features_ranks_informative_feature_highest_regression():
    df = _regression_df()
    result, error = rank_features(df, ["x1", "x2", "cat_noise"], "y", "regression")
    assert error is None
    ranking = result["ranking"]
    assert [r["feature"] for r in ranking][0] == "x1"
    assert "x1" in result["recommended"]


def test_rank_features_ranks_informative_feature_highest_classification():
    df = _classification_df()
    result, error = rank_features(df, ["x1", "x2"], "y", "classification")
    assert error is None
    assert result["ranking"][0]["feature"] == "x1"
    assert "x1" in result["recommended"]


def test_rank_features_consensus_scores_are_normalized():
    df = _regression_df()
    result, error = rank_features(df, ["x1", "x2", "cat_noise"], "y", "regression")
    assert error is None
    for row in result["ranking"]:
        assert 0.0 <= row["consensus_score"] <= 1.0
        assert 0.0 <= row["mutual_info_score"] <= 1.0
        assert 0.0 <= row["l1_score"] <= 1.0
        assert 0.0 <= row["rfe_score"] <= 1.0


def test_rank_features_recommends_at_least_one_feature():
    df = _regression_df()
    result, _ = rank_features(df, ["x1", "x2", "cat_noise"], "y", "regression")
    assert len(result["recommended"]) >= 1


def test_rank_features_single_feature_is_trivially_recommended():
    df = _regression_df()
    result, error = rank_features(df, ["x1"], "y", "regression")
    assert error is None
    assert result["ranking"][0]["feature"] == "x1"
    assert result["recommended"] == ["x1"]


def test_rank_features_errors_below_min_rows():
    df = _regression_df(n=MIN_ROWS_FOR_SELECTION - 1)
    result, error = rank_features(df, ["x1", "x2"], "y", "regression")
    assert result is None
    assert error is not None


def test_rank_features_errors_with_no_feature_columns():
    df = _regression_df()
    result, error = rank_features(df, [], "y", "regression")
    assert result is None
    assert error is not None


def test_rank_features_handles_missing_values_without_crashing():
    df = _regression_df()
    df.loc[0:10, "x1"] = np.nan
    result, error = rank_features(df, ["x1", "x2", "cat_noise"], "y", "regression")
    assert error is None
    assert len(result["ranking"]) == 3


def test_rank_features_ranking_covers_every_requested_column():
    df = _regression_df()
    result, _ = rank_features(df, ["x1", "x2", "cat_noise"], "y", "regression")
    assert {r["feature"] for r in result["ranking"]} == {"x1", "x2", "cat_noise"}
