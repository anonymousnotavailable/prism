"""Tests for modules.anomaly — IsolationForest-based row flagging, the LOF/DBSCAN
ensemble that extends it, and the Gemini narration pass over the ensemble result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.anomaly import (
    MIN_ROWS_REQUIRED,
    find_anomalies,
    find_anomalies_dbscan,
    find_anomalies_lof,
    narrate_anomalies,
    run_ensemble_detection,
)


def _clean_df_with_one_outlier(n: int = 50) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    values = rng.normal(loc=50, scale=2, size=n)
    values[0] = 5000.0  # obvious, extreme outlier
    return pd.DataFrame({"value": values, "label": ["x"] * n})


def test_find_anomalies_flags_the_planted_outlier():
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert flagged is not None
    assert 0 in flagged.index
    assert "anomaly_reason" in flagged.columns


def test_find_anomalies_errors_below_min_rows():
    df = pd.DataFrame({"value": range(MIN_ROWS_REQUIRED - 1)})
    flagged, error = find_anomalies(df, {"value": "numeric"})
    assert flagged is None
    assert error is not None


def test_find_anomalies_errors_with_no_numeric_columns():
    df = pd.DataFrame({"label": ["a"] * 20})
    flagged, error = find_anomalies(df, {"label": "categorical"})
    assert flagged is None
    assert error is not None


def test_find_anomalies_returns_empty_frame_when_nothing_flagged():
    # tight contamination + perfectly uniform data -> may legitimately find none
    df = pd.DataFrame({"value": [50.0] * 30})
    flagged, error = find_anomalies(df, {"value": "numeric"}, contamination=0.01)
    assert error is None
    assert flagged is not None  # empty df is a valid "no anomalies" result


# ── LocalOutlierFactor ──────────────────────────────────────────────────────


def test_find_anomalies_lof_flags_the_planted_outlier():
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies_lof(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert flagged is not None
    assert 0 in flagged.index
    assert "anomaly_reason" in flagged.columns


def test_find_anomalies_lof_errors_below_min_rows():
    df = pd.DataFrame({"value": range(MIN_ROWS_REQUIRED - 1)})
    flagged, error = find_anomalies_lof(df, {"value": "numeric"})
    assert flagged is None
    assert error is not None


def test_find_anomalies_lof_errors_with_no_numeric_columns():
    df = pd.DataFrame({"label": ["a"] * 20})
    flagged, error = find_anomalies_lof(df, {"label": "categorical"})
    assert flagged is None
    assert error is not None


# ── DBSCAN ───────────────────────────────────────────────────────────────────


def test_find_anomalies_dbscan_flags_the_planted_outlier():
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies_dbscan(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert flagged is not None
    assert 0 in flagged.index
    assert "anomaly_reason" in flagged.columns


def test_find_anomalies_dbscan_errors_below_min_rows():
    df = pd.DataFrame({"value": range(MIN_ROWS_REQUIRED - 1)})
    flagged, error = find_anomalies_dbscan(df, {"value": "numeric"})
    assert flagged is None
    assert error is not None


def test_find_anomalies_dbscan_handles_uniform_data_without_crashing():
    # zero-variance column -> a naive eps heuristic could divide by zero
    df = pd.DataFrame({"value": [50.0] * 30})
    flagged, error = find_anomalies_dbscan(df, {"value": "numeric"})
    assert error is None
    assert flagged is not None


# ── Ensemble ─────────────────────────────────────────────────────────────────


def test_run_ensemble_detection_ranks_the_planted_outlier_highest_agreement():
    df = _clean_df_with_one_outlier()
    result, error = run_ensemble_detection(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert result is not None
    assert not result.empty
    assert {"agreement_count", "anomaly_reason", "isolation_forest", "lof", "dbscan"} <= set(result.columns)
    # the planted outlier should be flagged by all three methods and sorted first
    assert result.index[0] == 0
    assert result.loc[0, "agreement_count"] == 3
    # sorted descending by agreement
    assert result["agreement_count"].is_monotonic_decreasing


def test_run_ensemble_detection_errors_below_min_rows():
    df = pd.DataFrame({"value": range(MIN_ROWS_REQUIRED - 1)})
    result, error = run_ensemble_detection(df, {"value": "numeric"})
    assert result is None
    assert error is not None


def test_run_ensemble_detection_returns_empty_frame_when_nothing_flagged_by_any_method():
    df = pd.DataFrame({"value": [50.0] * 30})
    result, error = run_ensemble_detection(df, {"value": "numeric"}, contamination=0.01)
    assert error is None
    assert result is not None
    assert result.empty


# ── Narration ────────────────────────────────────────────────────────────────


def test_narrate_anomalies_no_model_returns_error():
    df = _clean_df_with_one_outlier()
    result, _ = run_ensemble_detection(df, {"value": "numeric", "label": "categorical"})
    narration, error = narrate_anomalies(None, result)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_empty_result_short_circuits_without_calling_gemini():
    empty = pd.DataFrame()
    narration, error = narrate_anomalies(object(), empty)
    assert error is None
    assert "no" in narration.lower() or "clean" in narration.lower()


def test_narrate_anomalies_calls_gemini_and_returns_its_text(monkeypatch):
    df = _clean_df_with_one_outlier()
    result, _ = run_ensemble_detection(df, {"value": "numeric", "label": "categorical"})

    def fake_call_gemini(model, prompt):
        assert "value" in prompt  # the flagged column should reach the prompt
        return "These rows share an extreme value in 'value'.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    narration, error = narrate_anomalies(object(), result)
    assert error is None
    assert "extreme value" in narration
