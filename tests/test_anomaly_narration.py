"""Tests for modules.anomaly's Gemini narration of flagged anomaly rows —
the agentic-EDA slice: turning IsolationForest's raw flags into a plain-
English narration + suggested next action, without any extra statistical
computation (that's insight_verifier's job elsewhere).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.anomaly import find_anomalies, format_anomalies_text, narrate_anomalies


def _flagged_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    values = rng.normal(loc=50, scale=2, size=50)
    values[0] = 5000.0
    values[1] = -3000.0
    df = pd.DataFrame({"value": values, "label": ["x"] * 50})
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    return flagged


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeModel:
    """Stands in for a genai.GenerativeModel — records the prompt it was
    called with and returns a canned response, mirroring how
    modules.ai_analyst.call_gemini expects model.generate_content to behave.
    """

    def __init__(self, reply: str = "Two rows look extreme relative to the rest — worth a manual check."):
        self.reply = reply
        self.last_contents = None

    def generate_content(self, contents):
        self.last_contents = contents
        return _FakeResponse(self.reply)


class _RaisingModel:
    def generate_content(self, contents):
        raise RuntimeError("simulated Gemini outage")


def test_format_anomalies_text_includes_row_count_and_reasons():
    flagged = _flagged_df()
    text = format_anomalies_text(flagged, total_rows=50)
    assert f"{len(flagged)}" in text
    assert "50" in text
    # every flagged row's reason should show up in the summary
    for reason in flagged["anomaly_reason"]:
        assert reason in text


def test_format_anomalies_text_handles_no_anomalies():
    empty = pd.DataFrame(columns=["value", "label", "anomaly_reason"])
    text = format_anomalies_text(empty, total_rows=50)
    assert "no anomal" in text.lower()


def test_narrate_anomalies_returns_text_on_success():
    flagged = _flagged_df()
    model = _FakeModel()
    narration, error = narrate_anomalies(model, flagged, total_rows=50)
    assert error is None
    assert narration == model.reply
    # the prompt handed to Gemini should actually describe the flagged rows,
    # not just a generic "narrate this" instruction
    assert "anomaly_reason" not in model.last_contents  # raw column name shouldn't leak into the prose ask
    assert "50" in model.last_contents


def test_narrate_anomalies_returns_error_without_model():
    flagged = _flagged_df()
    narration, error = narrate_anomalies(None, flagged, total_rows=50)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_handles_empty_flagged_set_without_calling_gemini():
    empty = pd.DataFrame(columns=["value", "label", "anomaly_reason"])
    model = _FakeModel()
    narration, error = narrate_anomalies(model, empty, total_rows=50)
    assert error is None
    assert narration  # deterministic "looks clean" message
    assert model.last_contents is None  # never called Gemini for a trivially clean result


def test_narrate_anomalies_surfaces_gemini_errors_gracefully():
    flagged = _flagged_df()
    narration, error = narrate_anomalies(_RaisingModel(), flagged, total_rows=50)
    assert narration == ""
    assert error is not None
    assert "outage" in error or "failed" in error.lower()
