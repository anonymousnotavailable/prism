"""Tests for modules.mllab's Feature Selection Engine — mutual information,
L1-based selection, and RFE cross-checked into a consensus vote per feature,
plus the Gemini narration layer explaining why features were kept/dropped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.mllab import (
    FEATURE_SELECTION_METHODS,
    FEATURE_SELECTION_MIN_ROWS,
    build_votes_chart,
    fingerprint_selection,
    narrate_feature_selection,
    recommended_features,
    run_feature_selection,
)


def _classification_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    signal = rng.normal(size=n)
    noise1 = rng.normal(size=n)
    noise2 = rng.normal(size=n)
    category = rng.choice(["a", "b", "c"], size=n)
    target = (signal + rng.normal(scale=0.1, size=n) > 0).astype(int)
    return pd.DataFrame(
        {
            "signal": signal,
            "noise1": noise1,
            "noise2": noise2,
            "category": category,
            "target": target,
        }
    )


def _regression_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    signal = rng.normal(size=n)
    noise1 = rng.normal(size=n)
    noise2 = rng.normal(size=n)
    target = 3.0 * signal + rng.normal(scale=0.1, size=n)
    return pd.DataFrame({"signal": signal, "noise1": noise1, "noise2": noise2, "target": target})


# --- run_feature_selection -------------------------------------------------

def test_run_feature_selection_ranks_the_real_signal_column_first_classification():
    df = _classification_df()
    result, error = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    assert error is None
    assert result is not None
    assert result.iloc[0]["feature"] == "signal"
    assert set(result["feature"]) == {"signal", "noise1", "noise2", "category"}


def test_run_feature_selection_ranks_the_real_signal_column_first_regression():
    df = _regression_df()
    result, error = run_feature_selection(df, ["signal", "noise1", "noise2"], "target", "regression")
    assert error is None
    assert result.iloc[0]["feature"] == "signal"


def test_run_feature_selection_has_expected_columns():
    df = _classification_df()
    result, error = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    assert error is None
    for col in ("feature", "mutual_info", "mutual_info_norm", "mutual_info_selected", "l1_coef", "l1_selected", "rfe_selected", "rfe_rank", "votes"):
        assert col in result.columns
    assert result["votes"].between(0, len(FEATURE_SELECTION_METHODS)).all()


def test_run_feature_selection_errors_with_fewer_than_two_features():
    df = _classification_df()
    result, error = run_feature_selection(df, ["signal"], "target", "classification")
    assert result is None
    assert error is not None


def test_run_feature_selection_errors_below_min_rows():
    df = _classification_df(n=FEATURE_SELECTION_MIN_ROWS - 1)
    result, error = run_feature_selection(df, ["signal", "noise1"], "target", "classification")
    assert result is None
    assert error is not None


def test_run_feature_selection_handles_a_constant_feature_without_crashing():
    df = _classification_df()
    df["constant"] = 1.0
    result, error = run_feature_selection(df, ["signal", "noise1", "constant"], "target", "classification")
    assert error is None
    assert "constant" in result["feature"].values


def test_run_feature_selection_drops_rows_with_missing_target():
    df = _classification_df()
    df.loc[0:5, "target"] = np.nan
    result, error = run_feature_selection(df, ["signal", "noise1"], "target", "classification")
    assert error is None
    assert result is not None


def test_run_feature_selection_handles_string_classification_target():
    df = _classification_df()
    df["target"] = df["target"].map({0: "no", 1: "yes"})
    result, error = run_feature_selection(df, ["signal", "noise1", "noise2"], "target", "classification")
    assert error is None
    assert result.iloc[0]["feature"] == "signal"


# --- recommended_features ---------------------------------------------------

def test_recommended_features_returns_majority_vote_features():
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    picked = recommended_features(result)
    assert "signal" in picked
    assert len(picked) >= 1


def test_recommended_features_never_returns_empty_when_result_nonempty():
    df = _regression_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2"], "target", "regression")
    picked = recommended_features(result)
    assert len(picked) > 0


def test_recommended_features_handles_none_result():
    assert recommended_features(None) == []


# --- fingerprint_selection ---------------------------------------------------

def test_fingerprint_is_stable_for_the_same_result():
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    assert fingerprint_selection(result) == fingerprint_selection(result)


def test_fingerprint_changes_when_votes_change():
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    other = result.copy()
    other.loc[0, "votes"] = 0
    assert fingerprint_selection(result) != fingerprint_selection(other)


def test_fingerprint_handles_none():
    assert fingerprint_selection(None) == "empty"


# --- narrate_feature_selection ------------------------------------------------

def test_narrate_feature_selection_with_no_model_returns_error():
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1"], "target", "classification")
    text, error = narrate_feature_selection(None, result)
    assert text == ""
    assert error is not None


def test_narrate_feature_selection_with_none_result_is_friendly_not_an_error():
    class _FakeModel:
        pass

    text, error = narrate_feature_selection(_FakeModel(), None)
    assert error is None
    assert "no" in text.lower() or "nothing" in text.lower()


def test_narrate_feature_selection_calls_gemini_and_returns_text(monkeypatch):
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2"], "target", "classification")

    def fake_call_gemini(model, prompt):
        assert "signal" in prompt
        return "Signal is the strongest driver.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_feature_selection(object(), result)
    assert error is None
    assert "Signal" in text


# --- build_votes_chart --------------------------------------------------------

def test_build_votes_chart_returns_a_figure():
    df = _classification_df()
    result, _ = run_feature_selection(df, ["signal", "noise1", "noise2", "category"], "target", "classification")
    fig = build_votes_chart(result)
    assert fig is not None
    assert len(fig.data) >= 1
