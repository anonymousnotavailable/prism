"""Tests for modules.anomaly — IsolationForest-based row flagging."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.anomaly import (
    MIN_ROWS_REQUIRED,
    anomaly_fingerprint,
    find_anomalies,
    format_anomalies_text,
    narrate_anomalies,
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


# ---------------------------------------------------------------------------
# Anomaly narration — Gemini-powered plain-English explanation of flagged rows
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Stands in for a genai model — records the prompt it was called with."""

    def __init__(self, reply="Two rows show extreme deviations. Investigate the value column."):
        self.reply = reply
        self.last_contents = None

    def generate_content(self, contents):
        self.last_contents = contents
        return _FakeResponse(self.reply)


def _flagged_frame():
    df = _clean_df_with_one_outlier()
    flagged, _ = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    return flagged


def test_format_anomalies_text_summarizes_flagged_rows():
    flagged = _flagged_frame()
    text = format_anomalies_text(flagged, total_rows=50)
    assert f"{len(flagged)} of 50" in text
    assert "value" in text  # the column that drove the flag should be named


def test_format_anomalies_text_handles_empty_result():
    empty = pd.DataFrame(columns=["value", "anomaly_reason"])
    assert "No anomalies" in format_anomalies_text(empty, total_rows=50)


def test_narrate_anomalies_short_circuits_on_empty_result_no_gemini_call():
    empty = pd.DataFrame(columns=["value", "anomaly_reason"])
    model = _FakeModel()
    text, error = narrate_anomalies(model, empty, total_rows=50)
    assert error is None
    assert "No anomalies" in text
    assert model.last_contents is None  # never called Gemini — nothing to explain


def test_narrate_anomalies_errors_without_result():
    model = _FakeModel()
    text, error = narrate_anomalies(model, None, total_rows=50)
    assert text == ""
    assert error is not None
    assert model.last_contents is None


def test_narrate_anomalies_errors_without_model():
    flagged = _flagged_frame()
    text, error = narrate_anomalies(None, flagged, total_rows=50)
    assert text == ""
    assert error is not None


def test_narrate_anomalies_calls_gemini_and_returns_stripped_text():
    flagged = _flagged_frame()
    model = _FakeModel(reply="  The value column has one extreme outlier. Investigate it.  ")
    text, error = narrate_anomalies(model, flagged, total_rows=50)
    assert error is None
    assert text == "The value column has one extreme outlier. Investigate it."
    assert model.last_contents is not None
    assert "value" in model.last_contents  # the reason summary made it into the prompt


def test_narrate_anomalies_propagates_gemini_errors(monkeypatch):
    flagged = _flagged_frame()

    def _boom(model, contents):
        return "", "Daily free-tier quota exceeded for the Gemini API."

    monkeypatch.setattr("modules.ai_analyst.call_gemini", _boom)
    text, error = narrate_anomalies(_FakeModel(), flagged, total_rows=50)
    assert text == ""
    assert error == "Daily free-tier quota exceeded for the Gemini API."


def test_anomaly_fingerprint_stable_for_same_result():
    flagged = _flagged_frame()
    fp1 = anomaly_fingerprint(flagged)
    fp2 = anomaly_fingerprint(flagged.copy())
    assert fp1 == fp2  # same index -> same fingerprint, safe to cache narration on


def test_anomaly_fingerprint_differs_for_different_flagged_indices():
    # Fingerprint is a function of the flagged row index, not row content —
    # a re-run flagging a different set of rows must invalidate the cache.
    df1 = pd.DataFrame({"value": [1, 2, 3], "anomaly_reason": ["a", "b", "c"]}, index=[0, 5, 10])
    df2 = pd.DataFrame({"value": [1, 2, 3], "anomaly_reason": ["a", "b", "c"]}, index=[1, 6, 11])
    assert anomaly_fingerprint(df1) != anomaly_fingerprint(df2)


def test_anomaly_fingerprint_handles_none_and_empty():
    assert anomaly_fingerprint(None) == anomaly_fingerprint(pd.DataFrame())
