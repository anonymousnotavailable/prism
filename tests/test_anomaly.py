"""Tests for modules.anomaly — IsolationForest-based row flagging + narration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import (
    MIN_ROWS_REQUIRED,
    deterministic_narration,
    find_anomalies,
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


# ── Narration ────────────────────────────────────────────────────────────


def _flagged_df_with_shared_driver():
    df = pd.DataFrame({
        "amount": [5000.0, 4800.0, 51.0],
        "anomaly_reason": [
            "'amount' is 98.0x above the column median.",
            "'amount' is 94.1x above the column median.",
            "Unusual combination of values across numeric columns.",
        ],
    })
    return df


def test_narrate_anomalies_returns_error_when_no_model():
    flagged = _flagged_df_with_shared_driver()
    narration, error = narrate_anomalies(None, flagged, n_total=50)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_handles_empty_flagged_df():
    empty = pd.DataFrame(columns=["value", "anomaly_reason"])
    narration, error = narrate_anomalies(object(), empty, n_total=50)
    assert error is None
    assert "no anomalies" in narration.lower() or "no anomalies were flagged" in narration.lower()


def test_narrate_anomalies_requires_anomaly_reason_column():
    df = pd.DataFrame({"value": [1.0, 2.0]})
    narration, error = narrate_anomalies(object(), df, n_total=50)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_propagates_call_gemini_error(monkeypatch):
    import modules.ai_analyst as ai_analyst

    monkeypatch.setattr(ai_analyst, "call_gemini", lambda model, contents: ("", "quota exceeded"))
    flagged = _flagged_df_with_shared_driver()
    narration, error = narrate_anomalies(object(), flagged, n_total=50)
    assert narration == ""
    assert error == "quota exceeded"


def test_narrate_anomalies_returns_trimmed_text_on_success(monkeypatch):
    import modules.ai_analyst as ai_analyst

    monkeypatch.setattr(ai_analyst, "call_gemini", lambda model, contents: ("  a narrative.  ", None))
    flagged = _flagged_df_with_shared_driver()
    narration, error = narrate_anomalies(object(), flagged, n_total=50)
    assert error is None
    assert narration == "a narrative."


def test_deterministic_narration_empty_flagged():
    empty = pd.DataFrame(columns=["value", "anomaly_reason"])
    text = deterministic_narration(empty, n_total=50)
    assert "no anomalies" in text.lower()


def test_deterministic_narration_identifies_shared_driver():
    flagged = _flagged_df_with_shared_driver()
    text = deterministic_narration(flagged, n_total=100)
    assert "amount" in text
    assert "3" in text  # n_flagged
    assert "100" in text  # n_total


def test_deterministic_narration_handles_no_parseable_driver():
    flagged = pd.DataFrame({
        "value": [1.0, 2.0],
        "anomaly_reason": ["Unusual combination of values across numeric columns."] * 2,
    })
    text = deterministic_narration(flagged, n_total=20)
    assert "no single driver" in text.lower()
