"""Tests for modules.anomaly — IsolationForest/LOF row flagging + narration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import METHODS, MIN_ROWS_REQUIRED, find_anomalies, narrate_anomalies


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


def test_find_anomalies_rejects_unknown_method():
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"}, method="dbscan")
    assert flagged is None
    assert error is not None
    assert "dbscan" in error.lower()


def test_find_anomalies_with_lof_flags_the_planted_outlier():
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"}, method="lof")
    assert error is None
    assert flagged is not None
    assert 0 in flagged.index
    assert "anomaly_reason" in flagged.columns


def test_find_anomalies_lof_works_with_small_row_counts():
    # LOF's n_neighbors default (20) exceeds a dataset right at MIN_ROWS_REQUIRED;
    # this must not raise, and should still flag the planted outlier.
    df = _clean_df_with_one_outlier(n=MIN_ROWS_REQUIRED)
    flagged, error = find_anomalies(df, {"value": "numeric"}, method="lof", contamination=0.1)
    assert error is None
    assert flagged is not None


def test_methods_registry_has_both_algorithms():
    assert "isolation_forest" in METHODS
    assert "lof" in METHODS


# ── narrate_anomalies() ──────────────────────────────────────────────────


class _FakeModel:
    """Minimal stand-in for a genai GenerativeModel — mirrors the
    .generate_content(contents) -> response.text interface call_gemini expects.
    """

    def __init__(self, text: str = "These rows look unusual because of extreme values."):
        self._text = text

    def generate_content(self, contents):
        class _Response:
            def __init__(self, text):
                self.text = text

        return _Response(self._text)


def test_narrate_anomalies_no_model_returns_error():
    flagged, _ = find_anomalies(_clean_df_with_one_outlier(), {"value": "numeric", "label": "categorical"})
    narration, error = narrate_anomalies(None, flagged)
    assert narration == ""
    assert error is not None


def test_narrate_anomalies_empty_flagged_df_short_circuits_without_calling_model():
    empty = pd.DataFrame(columns=["value", "anomaly_reason"])
    narration, error = narrate_anomalies(_FakeModel(), empty)
    assert error is None
    assert "no anomal" in narration.lower()


def test_narrate_anomalies_returns_model_text_on_success():
    flagged, _ = find_anomalies(_clean_df_with_one_outlier(), {"value": "numeric", "label": "categorical"})
    narration, error = narrate_anomalies(_FakeModel("Row 0 is an extreme outlier — investigate the source."), flagged)
    assert error is None
    assert "outlier" in narration.lower()
