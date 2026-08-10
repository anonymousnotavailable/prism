"""Tests for modules.anomaly — IsolationForest-based row flagging and
Gemini-narrated anomaly explanations."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import (
    MIN_ROWS_REQUIRED,
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


# ── Anomaly narration ───────────────────────────────────────────────────────

class _FakeGeminiResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeGeminiModel:
    """Minimal stand-in for a genai.GenerativeModel — records the prompt it
    was called with and returns a canned response, so narrate_anomalies can
    be tested end-to-end without a live API key or network access.
    """

    def __init__(self, text: str = "These rows look unusual — verify against source data."):
        self._text = text
        self.last_contents = None

    def generate_content(self, contents):
        self.last_contents = contents
        return _FakeGeminiResponse(self._text)


def _flagged_with_reasons() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "value": [5000.0, 4800.0, 10.0],
            "anomaly_reason": [
                "value is 98.2x above the column median.",
                "value is 94.1x above the column median.",
                "value is 5.0x below the column median.",
            ],
        }
    )


def test_format_anomalies_text_empty_flagged_set():
    assert "No anomalies" in format_anomalies_text(None)
    assert "No anomalies" in format_anomalies_text(pd.DataFrame())


def test_format_anomalies_text_summarizes_count_and_reasons():
    text = format_anomalies_text(_flagged_with_reasons())
    assert "3 row(s)" in text
    assert "above the column median" in text


def test_narrate_anomalies_without_model_returns_error():
    narration, error = narrate_anomalies(None, _flagged_with_reasons())
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_with_empty_flagged_df_short_circuits_without_a_call():
    model = _FakeGeminiModel()
    narration, error = narrate_anomalies(model, pd.DataFrame())
    assert error is None
    assert "no anomalies" in narration.lower() or "nothing" in narration.lower()
    assert model.last_contents is None  # never called Gemini for an empty set


def test_narrate_anomalies_calls_gemini_and_returns_stripped_text():
    model = _FakeGeminiModel(text="  Three rows stand out — verify source data.  ")
    narration, error = narrate_anomalies(model, _flagged_with_reasons())
    assert error is None
    assert narration == "Three rows stand out — verify source data."
    assert model.last_contents is not None
