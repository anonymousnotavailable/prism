"""Tests for modules.anomaly — IsolationForest-based row flagging."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import MIN_ROWS_REQUIRED, find_anomalies, fingerprint_flagged, narrate_anomalies


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


# --- fingerprint_flagged -------------------------------------------------

def test_fingerprint_is_stable_for_the_same_result():
    df = _clean_df_with_one_outlier()
    flagged, _ = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    assert fingerprint_flagged(flagged) == fingerprint_flagged(flagged)


def test_fingerprint_changes_when_flagged_rows_change():
    df = _clean_df_with_one_outlier()
    flagged, _ = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    other = flagged.drop(index=flagged.index[0]) if len(flagged) else flagged
    if other.equals(flagged):
        # only one flagged row (common with a single planted outlier) — compare
        # against a genuinely different frame instead so the test still means something
        other = pd.DataFrame({"value": [1.0], "label": ["y"], "anomaly_reason": ["different"]})
    assert fingerprint_flagged(flagged) != fingerprint_flagged(other)


def test_fingerprint_of_empty_frame_is_stable():
    empty = pd.DataFrame({"value": [], "label": [], "anomaly_reason": []})
    assert fingerprint_flagged(empty) == fingerprint_flagged(empty.copy())


# --- narrate_anomalies ---------------------------------------------------

def test_narrate_anomalies_without_model_returns_error():
    df = _clean_df_with_one_outlier()
    flagged, _ = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    narration, error = narrate_anomalies(None, flagged)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_with_no_flagged_rows_skips_gemini():
    empty = pd.DataFrame({"value": [], "label": [], "anomaly_reason": []})

    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called when nothing was flagged")

    narration, error = narrate_anomalies(_ShouldNotBeCalled(), empty)
    assert error is None
    assert "no anomalies" in narration.lower()


def test_narrate_anomalies_calls_gemini_with_flagged_summary():
    df = _clean_df_with_one_outlier()
    flagged, _ = find_anomalies(df, {"value": "numeric", "label": "categorical"})

    class _FakeResponse:
        text = "These rows look off because of extreme values. Consider reviewing them."

    class _FakeModel:
        def generate_content(self, contents):
            assert "flagged" in contents.lower() or "anomal" in contents.lower()
            return _FakeResponse()

    narration, error = narrate_anomalies(_FakeModel(), flagged)
    assert error is None
    assert "review" in narration.lower()
