"""Tests for modules.feature_selection — mutual information, L1-based, and
RFE feature ranking for ML Lab, combined into a single composite score.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.feature_selection import build_ranking_chart, rank_features, select_top_k


def _classification_df(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    informative = rng.normal(size=n)
    noise1 = rng.normal(size=n)
    noise2 = rng.normal(size=n)
    category = rng.choice(["a", "b", "c"], size=n)
    # target is a deterministic-ish function of `informative` only
    target = (informative + rng.normal(scale=0.1, size=n) > 0).astype(int)
    return pd.DataFrame(
        {"informative": informative, "noise1": noise1, "noise2": noise2, "category": category, "target": target}
    )


def _regression_df(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    informative = rng.normal(size=n)
    noise1 = rng.normal(size=n)
    noise2 = rng.normal(size=n)
    target = informative * 5 + rng.normal(scale=0.2, size=n)
    return pd.DataFrame({"informative": informative, "noise1": noise1, "noise2": noise2, "target": target})


def test_rank_features_ranks_informative_feature_highest_classification():
    df = _classification_df()
    ranked = rank_features(df, ["informative", "noise1", "noise2", "category"], "target", "classification")
    assert list(ranked["feature"])[0] == "informative"
    assert set(ranked["feature"]) == {"informative", "noise1", "noise2", "category"}


def test_rank_features_ranks_informative_feature_highest_regression():
    df = _regression_df()
    ranked = rank_features(df, ["informative", "noise1", "noise2"], "target", "regression")
    assert list(ranked["feature"])[0] == "informative"


def test_rank_features_output_has_expected_columns():
    df = _classification_df()
    ranked = rank_features(df, ["informative", "noise1", "category"], "target", "classification")
    for col in ["feature", "mutual_info", "l1_score", "rfe_selected", "composite_score"]:
        assert col in ranked.columns


def test_rank_features_handles_categorical_columns_without_crashing():
    df = _classification_df()
    ranked = rank_features(df, ["category", "informative"], "target", "classification")
    assert len(ranked) == 2


def test_rank_features_handles_constant_column():
    df = _classification_df()
    df["constant"] = 1
    ranked = rank_features(df, ["informative", "constant"], "target", "classification")
    # constant column should not crash the pipeline, and should rank at/near the bottom
    assert "constant" in set(ranked["feature"])
    assert ranked.iloc[-1]["feature"] == "constant" or ranked.iloc[0]["feature"] == "informative"


def test_rank_features_raises_clear_error_with_fewer_than_two_features():
    df = _classification_df()
    with pytest.raises(ValueError):
        rank_features(df, ["informative"], "target", "classification")


def test_select_top_k_returns_correct_count_and_order():
    df = _classification_df()
    ranked = rank_features(df, ["informative", "noise1", "noise2", "category"], "target", "classification")
    top2 = select_top_k(ranked, 2)
    assert top2 == list(ranked.sort_values("composite_score", ascending=False)["feature"])[:2]


def test_select_top_k_caps_at_available_features():
    df = _classification_df()
    ranked = rank_features(df, ["informative", "noise1"], "target", "classification")
    assert len(select_top_k(ranked, 10)) == 2


def test_build_ranking_chart_returns_a_figure_with_one_bar_per_feature():
    df = _classification_df()
    ranked = rank_features(df, ["informative", "noise1", "noise2", "category"], "target", "classification")
    fig = build_ranking_chart(ranked)
    assert len(fig.data[0].x) == len(ranked)
