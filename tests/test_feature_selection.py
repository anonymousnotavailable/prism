"""Tests for modules.feature_selection — a 3-method consensus ranking
(mutual information, L1-regularized coefficients, recursive feature
elimination) of which features matter most for a chosen target, same
self-verifying-ensemble pattern as anomaly.find_anomalies_ensemble()."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.feature_selection import (
    METHODS,
    MIN_FEATURES_REQUIRED,
    MIN_ROWS_REQUIRED,
    build_ranking_chart,
    fingerprint_ranking,
    is_available,
    narrate_feature_ranking,
    rank_features,
)


def _regression_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    target = 3 * signal + rng.normal(0, 0.1, n)  # strong linear relationship
    return pd.DataFrame(
        {
            "signal_col": signal,
            "noise_col": noise,
            "category_col": rng.choice(["a", "b", "c"], n),
            "target": target,
        }
    )


def _classification_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    signal = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    label = (signal + rng.normal(0, 0.2, n) > 0).astype(int).astype(str)
    return pd.DataFrame({"signal_col": signal, "noise_col": noise, "label": label})


REGRESSION_TYPES = {"signal_col": "numeric", "noise_col": "numeric", "category_col": "categorical", "target": "numeric"}
CLASSIFICATION_TYPES = {"signal_col": "numeric", "noise_col": "numeric", "label": "categorical"}


# --- rank_features: happy paths -------------------------------------------

def test_rank_features_regression_ranks_the_true_signal_first():
    df = _regression_df()
    result, error = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    assert error is None
    assert result is not None
    assert result["ranking"][0]["feature"] == "signal_col"
    assert "signal_col" in result["top_k"]


def test_rank_features_classification_ranks_the_true_signal_first():
    df = _classification_df()
    result, error = rank_features(df, ["signal_col", "noise_col"], "label", CLASSIFICATION_TYPES, "classification")
    assert error is None
    assert result["ranking"][0]["feature"] == "signal_col"


def test_rank_features_consensus_score_is_between_0_and_1():
    df = _regression_df()
    result, error = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    assert error is None
    for row in result["ranking"]:
        assert 0.0 <= row["consensus_score"] <= 1.0
        assert 0 <= row["votes"] <= len(METHODS)


def test_rank_features_ranking_sorted_descending_by_consensus_score():
    df = _regression_df()
    result, _ = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    scores = [row["consensus_score"] for row in result["ranking"]]
    assert scores == sorted(scores, reverse=True)


# --- rank_features: failure states -----------------------------------------

def test_rank_features_errors_below_min_rows():
    df = _regression_df(n=MIN_ROWS_REQUIRED - 1)
    result, error = rank_features(df, ["signal_col", "noise_col"], "target", REGRESSION_TYPES, "regression")
    assert result is None
    assert error is not None


def test_rank_features_errors_with_too_few_usable_features():
    df = pd.DataFrame({"only_col": np.random.default_rng(0).normal(0, 1, 50), "target": np.random.default_rng(1).normal(0, 1, 50)})
    result, error = rank_features(df, ["only_col"], "target", {"only_col": "numeric", "target": "numeric"}, "regression")
    assert result is None
    assert error is not None
    assert "feature" in error.lower()


def test_rank_features_drops_constant_column():
    df = _regression_df()
    df["constant_col"] = 1
    types = {**REGRESSION_TYPES, "constant_col": "numeric"}
    result, error = rank_features(df, ["signal_col", "noise_col", "constant_col"], "target", types, "regression")
    assert error is None
    dropped_names = [d["feature"] for d in result["dropped_features"]]
    assert "constant_col" in dropped_names
    assert "constant_col" not in [row["feature"] for row in result["ranking"]]


def test_rank_features_drops_high_cardinality_id_like_column():
    df = _regression_df()
    df["id_col"] = [f"row_{i}" for i in range(len(df))]
    types = {**REGRESSION_TYPES, "id_col": "categorical"}
    result, error = rank_features(df, ["signal_col", "noise_col", "id_col"], "target", types, "regression")
    assert error is None
    dropped_names = [d["feature"] for d in result["dropped_features"]]
    assert "id_col" in dropped_names


def test_rank_features_drops_rows_with_nan_target_but_still_runs():
    df = _regression_df(n=60)
    df.loc[:5, "target"] = np.nan
    result, error = rank_features(df, ["signal_col", "noise_col"], "target", REGRESSION_TYPES, "regression")
    assert error is None
    assert result["n_rows_used"] == 54


def test_rank_features_errors_when_too_few_rows_remain_after_dropping_nan_target():
    df = _regression_df(n=MIN_ROWS_REQUIRED + 5)
    df.loc[: len(df) - 6, "target"] = np.nan  # leaves fewer than MIN_ROWS_REQUIRED
    result, error = rank_features(df, ["signal_col", "noise_col"], "target", REGRESSION_TYPES, "regression")
    assert result is None
    assert error is not None


def test_rank_features_degrades_gracefully_when_one_method_raises(monkeypatch):
    import modules.feature_selection as fs

    def _boom(*_args, **_kwargs):
        raise ValueError("simulated failure")

    monkeypatch.setattr(fs, "mutual_info_regression", _boom)
    df = _regression_df()
    result, error = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    assert error is None  # the other two methods still produced a result
    assert result is not None
    assert "mutual_info" in result["method_errors"]
    assert result["ranking"][0]["feature"] == "signal_col"


# --- fingerprint_ranking ----------------------------------------------------

def test_fingerprint_ranking_is_stable_for_the_same_result():
    df = _regression_df()
    result, _ = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    assert fingerprint_ranking(result) == fingerprint_ranking(result)


def test_fingerprint_ranking_changes_with_different_top_features():
    df1 = _regression_df()
    df2 = _classification_df()
    r1, _ = rank_features(df1, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    r2, _ = rank_features(df2, ["signal_col", "noise_col"], "label", CLASSIFICATION_TYPES, "classification")
    assert fingerprint_ranking(r1) != fingerprint_ranking(r2)


def test_fingerprint_ranking_handles_none():
    assert fingerprint_ranking(None) == "empty"


# --- narrate_feature_ranking -------------------------------------------------

def test_narrate_feature_ranking_without_model_returns_error():
    df = _regression_df()
    result, _ = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    narration, error = narrate_feature_ranking(None, result)
    assert narration == ""
    assert error is not None


def test_narrate_feature_ranking_with_no_result_skips_gemini():
    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called with no ranking result")

    narration, error = narrate_feature_ranking(_ShouldNotBeCalled(), None)
    assert error is not None
    assert narration == ""


def test_narrate_feature_ranking_calls_gemini_with_top_feature_names():
    df = _regression_df()
    result, _ = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")

    class _FakeResponse:
        text = "signal_col dominates the ranking because it has a strong linear relationship with the target."

    class _FakeModel:
        def generate_content(self, contents):
            assert "signal_col" in contents
            return _FakeResponse()

    narration, error = narrate_feature_ranking(_FakeModel(), result)
    assert error is None
    assert "signal_col" in narration


# --- build_ranking_chart -----------------------------------------------------

def test_build_ranking_chart_returns_a_figure_with_one_bar_per_feature():
    df = _regression_df()
    result, _ = rank_features(df, ["signal_col", "noise_col", "category_col"], "target", REGRESSION_TYPES, "regression")
    fig = build_ranking_chart(result)
    assert len(fig.data) >= 1
    assert len(fig.data[0].x) == len(result["ranking"])


# --- is_available ------------------------------------------------------------

def test_is_available_reflects_sklearn_import():
    assert is_available() in (True, False)
