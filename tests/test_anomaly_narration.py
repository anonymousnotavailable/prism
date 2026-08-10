"""Tests for modules.anomaly's Gemini narration layer (agentic-EDA theme,
Run 3): turns IsolationForest-flagged rows into a plain-English narrative +
suggested next action, cached per fingerprint of the flagged set so repeat
renders/clicks never re-hit the Gemini free tier for the same result.
"""
from __future__ import annotations

import pandas as pd

from modules.anomaly import anomaly_fingerprint, narrate_anomalies


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Mimics genai's GenerativeModel.generate_content, counting calls so
    tests can assert the caching layer actually avoids repeat calls."""

    def __init__(self, text="Your data has a few unusual rows worth a look."):
        self.text = text
        self.calls = 0

    def generate_content(self, contents):
        self.calls += 1
        return _FakeResponse(self.text)


def _flagged_df():
    return pd.DataFrame(
        {
            "value": [5000.0, -300.0],
            "label": ["x", "y"],
            "anomaly_reason": [
                "value is 100.0x above the column median.",
                "value is 6.0x below the column median.",
            ],
        },
        index=[0, 7],
    )


def test_narrate_anomalies_without_model_returns_error():
    narration, error = narrate_anomalies(None, _flagged_df())
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_with_empty_frame_short_circuits_without_calling_gemini():
    model = _FakeModel()
    narration, error = narrate_anomalies(model, pd.DataFrame())
    assert error is None
    assert "no anomalies" in narration.lower() or "clean" in narration.lower()
    assert model.calls == 0


def test_narrate_anomalies_calls_gemini_and_returns_text():
    model = _FakeModel(text="Two rows stand out: an extreme high and low value in 'value'.")
    narration, error = narrate_anomalies(model, _flagged_df())
    assert error is None
    assert "extreme" in narration.lower()
    assert model.calls == 1


def test_narrate_anomalies_propagates_gemini_errors():
    class _BrokenModel:
        def generate_content(self, contents):
            raise RuntimeError("quota exceeded")

    narration, error = narrate_anomalies(_BrokenModel(), _flagged_df())
    assert narration == ""
    assert error is not None


def test_anomaly_fingerprint_stable_for_same_flagged_set():
    df = _flagged_df()
    assert anomaly_fingerprint(df) == anomaly_fingerprint(df.copy())


def test_anomaly_fingerprint_differs_for_different_flagged_sets():
    df_a = _flagged_df()
    df_b = _flagged_df()
    df_b["anomaly_reason"] = ["different reason.", "different reason 2."]
    assert anomaly_fingerprint(df_a) != anomaly_fingerprint(df_b)


def test_anomaly_fingerprint_handles_empty_frame():
    assert anomaly_fingerprint(pd.DataFrame()) is not None
