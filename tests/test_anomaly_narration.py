"""Tests for modules.anomaly's Gemini narration layer (agentic-EDA slice).

The narration path only ever sends aggregated reason strings to Gemini
(never raw row values), and is meant to be fingerprint-cached by callers —
these tests cover the deterministic pieces (summarization, fingerprinting)
plus the narration function's control flow with a fake Gemini client.
"""
from __future__ import annotations

import pandas as pd
import pytest

from modules.anomaly import (
    anomaly_fingerprint,
    narrate_anomalies,
    summarize_flagged,
)


def _flagged_df():
    return pd.DataFrame(
        {
            "amount": [5000.0, 4800.0, 10.0],
            "age": [30, 31, 999],
            "anomaly_reason": [
                "amount is 12.4x above the column median.",
                "amount is 11.9x above the column median.",
                "age is 33.1x above the column median.",
            ],
        },
        index=[3, 7, 19],
    )


def test_summarize_flagged_counts_reason_columns():
    summary = summarize_flagged(_flagged_df())
    assert summary["n_flagged"] == 3
    # "amount" is the driving column for 2 of the 3 flagged rows.
    assert summary["top_columns"][0][0] == "amount"
    assert summary["top_columns"][0][1] == 2


def test_summarize_flagged_handles_empty_frame():
    empty = pd.DataFrame(columns=["a", "anomaly_reason"])
    summary = summarize_flagged(empty)
    assert summary["n_flagged"] == 0
    assert summary["top_columns"] == []


def test_anomaly_fingerprint_is_deterministic():
    flagged = _flagged_df()
    fp1 = anomaly_fingerprint(flagged, total_rows=200)
    fp2 = anomaly_fingerprint(flagged, total_rows=200)
    assert fp1 == fp2


def test_anomaly_fingerprint_changes_with_different_flagged_set():
    flagged = _flagged_df()
    fp_full = anomaly_fingerprint(flagged, total_rows=200)
    fp_subset = anomaly_fingerprint(flagged.iloc[:2], total_rows=200)
    assert fp_full != fp_subset


def test_anomaly_fingerprint_changes_with_total_rows():
    flagged = _flagged_df()
    fp_a = anomaly_fingerprint(flagged, total_rows=200)
    fp_b = anomaly_fingerprint(flagged, total_rows=500)
    assert fp_a != fp_b


def test_narrate_anomalies_no_model():
    text, error = narrate_anomalies(None, _flagged_df(), total_rows=200)
    assert text == ""
    assert error is not None


def test_narrate_anomalies_no_anomalies_short_circuits_without_gemini_call(monkeypatch):
    calls = []

    def fake_call_gemini(model, contents):
        calls.append(contents)
        return "should not be called", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)

    empty = pd.DataFrame(columns=["a", "anomaly_reason"])
    text, error = narrate_anomalies(object(), empty, total_rows=200)
    assert error is None
    assert "no anomalies" in text.lower() or "clean" in text.lower()
    assert calls == []  # no Gemini call for the trivial "nothing flagged" case


def test_narrate_anomalies_success(monkeypatch):
    captured = {}

    def fake_call_gemini(model, contents):
        captured["contents"] = contents
        return "Two rows show unusually high amount values — worth a manual check.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)

    text, error = narrate_anomalies(object(), _flagged_df(), total_rows=200)
    assert error is None
    assert "amount" in text.lower() or "unusually" in text.lower()
    # The prompt must carry the aggregated reason/column info, not raw PII-risk values.
    assert "amount" in captured["contents"]
    assert "3" in captured["contents"]  # n_flagged referenced somewhere


def test_narrate_anomalies_propagates_gemini_error(monkeypatch):
    def fake_call_gemini(model, contents):
        return "", "rate limited"

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)

    text, error = narrate_anomalies(object(), _flagged_df(), total_rows=200)
    assert text == ""
    assert error == "rate limited"
