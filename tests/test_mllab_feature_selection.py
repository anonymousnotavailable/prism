"""Tests for mllab.select_features — a Feature Selection Engine that ranks
candidate features by relevance to a target using three independent methods
(mutual information, L1-regularized coefficients, and RFE), then reports
where they agree. Consensus is a stronger signal than any single method:
mirrors the same agreement-over-single-model pattern anomaly.py's ensemble
mode already uses in this codebase.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.mllab import select_features


def _regression_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    strong = rng.normal(size=n)
    weak_noise = rng.normal(size=n)
    another_noise = rng.normal(size=n)
    target = strong * 5 + rng.normal(scale=0.5, size=n)
    return pd.DataFrame(
        {"strong_feature": strong, "noise_a": weak_noise, "noise_b": another_noise, "target": target}
    )


def test_ranks_a_genuinely_predictive_feature_above_pure_noise():
    df = _regression_df()
    column_types = {"strong_feature": "numeric", "noise_a": "numeric", "noise_b": "numeric", "target": "numeric"}

    out = select_features(df, column_types, ["strong_feature", "noise_a", "noise_b"], "target", "regression")

    assert out["error"] is None
    ranking = out["ranking"]
    top_feature = ranking.sort_values("consensus_rank").iloc[0]["feature"]
    assert top_feature == "strong_feature"


def test_recommended_features_include_the_strong_signal():
    df = _regression_df()
    column_types = {"strong_feature": "numeric", "noise_a": "numeric", "noise_b": "numeric", "target": "numeric"}

    out = select_features(df, column_types, ["strong_feature", "noise_a", "noise_b"], "target", "regression")

    assert "strong_feature" in out["recommended"]


def test_classification_task_runs_without_error():
    rng = np.random.default_rng(1)
    n = 200
    x = rng.normal(size=n)
    y = (x > 0).astype(int)
    noise = rng.normal(size=n)
    df = pd.DataFrame({"x": x, "noise": noise, "label": y})
    column_types = {"x": "numeric", "noise": "numeric", "label": "categorical"}

    out = select_features(df, column_types, ["x", "noise"], "label", "classification")

    assert out["error"] is None
    assert set(out["ranking"]["feature"]) == {"x", "noise"}


def test_handles_categorical_features_via_encoding():
    df = pd.DataFrame(
        {
            "category": ["a", "b", "a", "b"] * 25,
            "value": list(range(100)),
            "target": [1, 0, 1, 0] * 25,
        }
    )
    column_types = {"category": "categorical", "value": "numeric", "target": "categorical"}

    out = select_features(df, column_types, ["category", "value"], "target", "classification")

    assert out["error"] is None
    assert len(out["ranking"]) == 2


def test_returns_error_with_fewer_than_two_features():
    df = pd.DataFrame({"a": range(50), "target": range(50)})
    column_types = {"a": "numeric", "target": "numeric"}

    out = select_features(df, column_types, ["a"], "target", "regression")

    assert out["error"] is not None
    assert out["ranking"] is None


def test_never_raises_on_degenerate_input():
    df = pd.DataFrame({"a": [1, 1, 1], "b": [2, 2, 2], "target": [3, 3, 3]})
    column_types = {"a": "numeric", "b": "numeric", "target": "numeric"}

    out = select_features(df, column_types, ["a", "b"], "target", "regression")

    # Constant columns/target: must degrade gracefully, never throw.
    assert "error" in out
