"""Tests for modules.anomaly — IsolationForest-based row flagging, plus the
ensemble (IsolationForest + LOF + DBSCAN) consensus detector."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import (
    AUTO_RUN_MAX_ROWS,
    ENSEMBLE_METHODS,
    ENSEMBLE_MIN_ROWS,
    MIN_ROWS_REQUIRED,
    auto_run_on_upload,
    find_anomalies,
    find_anomalies_ensemble,
    fingerprint_flagged,
    narrate_anomalies,
    narrate_ensemble_disagreement,
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


# --- find_anomalies_ensemble ----------------------------------------------

def _ensemble_df(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    values = rng.normal(loc=50, scale=2, size=n)
    other = rng.normal(loc=10, scale=1, size=n)
    # a planted extreme point every method should agree is an outlier
    values[0], other[0] = 5000.0, 500.0
    return pd.DataFrame({"value": values, "other": other, "label": ["x"] * n})


def test_find_anomalies_ensemble_flags_the_planted_outlier_by_all_methods():
    df = _ensemble_df()
    consensus, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric", "label": "categorical"}
    )
    assert error is None
    assert consensus is not None and 0 in consensus.index
    assert consensus.loc[0, "consensus_count"] == len(ENSEMBLE_METHODS)
    assert set(summary.keys()) == set(ENSEMBLE_METHODS)
    for method_stats in summary.values():
        assert "flagged_count" in method_stats and "pct" in method_stats


def test_find_anomalies_ensemble_consensus_sorted_descending():
    df = _ensemble_df()
    consensus, _, error = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric", "label": "categorical"}
    )
    assert error is None
    counts = consensus["consensus_count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_find_anomalies_ensemble_errors_below_min_rows():
    df = pd.DataFrame({"value": range(ENSEMBLE_MIN_ROWS - 1), "other": range(ENSEMBLE_MIN_ROWS - 1)})
    consensus, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric"}
    )
    assert consensus is None and summary is None
    assert error is not None


def test_find_anomalies_ensemble_errors_with_no_numeric_columns():
    df = pd.DataFrame({"label": ["a"] * 30})
    consensus, summary, error = find_anomalies_ensemble(df, {"label": "categorical"})
    assert consensus is None and summary is None
    assert error is not None


def test_find_anomalies_ensemble_needs_at_least_two_numeric_columns():
    # distance-based methods (LOF/DBSCAN) are meaningless on a single axis
    # the same way IsolationForest still works on — document the stricter
    # requirement rather than silently degrading.
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"value": rng.normal(size=30)})
    consensus, summary, error = find_anomalies_ensemble(df, {"value": "numeric"})
    assert consensus is None and summary is None
    assert error is not None


def test_find_anomalies_ensemble_returns_empty_when_nothing_flagged():
    df = pd.DataFrame({"value": [50.0] * 30, "other": [10.0] * 30})
    consensus, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric"}, contamination=0.01
    )
    assert error is None
    assert consensus is not None and consensus.empty
    assert summary is not None


# --- narrate_ensemble_disagreement -----------------------------------------

def test_narrate_ensemble_disagreement_without_model_returns_error():
    df = _ensemble_df()
    consensus, summary, _ = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric", "label": "categorical"}
    )
    narration, error = narrate_ensemble_disagreement(None, consensus, summary)
    assert narration == ""
    assert error is not None


def test_narrate_ensemble_disagreement_with_no_flagged_rows_skips_gemini():
    empty = pd.DataFrame({"value": [], "other": [], "anomaly_reason": [], "consensus_count": []})
    summary = {m: {"flagged_count": 0, "pct": 0.0} for m in ENSEMBLE_METHODS}

    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called when nothing was flagged")

    narration, error = narrate_ensemble_disagreement(_ShouldNotBeCalled(), empty, summary)
    assert error is None
    assert "no anomal" in narration.lower()


def test_narrate_ensemble_disagreement_calls_gemini_with_method_summary():
    df = _ensemble_df()
    consensus, summary, _ = find_anomalies_ensemble(
        df, {"value": "numeric", "other": "numeric", "label": "categorical"}
    )

    class _FakeResponse:
        text = "Isolation Forest and LOF agree on the global outlier; DBSCAN is stricter."

    class _FakeModel:
        def generate_content(self, contents):
            assert "isolation" in contents.lower() and "lof" in contents.lower()
            return _FakeResponse()

    narration, error = narrate_ensemble_disagreement(_FakeModel(), consensus, summary)
    assert error is None
    assert "agree" in narration.lower()


# --- auto_run_on_upload -----------------------------------------------------
# Zero-click auto-EDA: the same ensemble consensus as find_anomalies_ensemble,
# but silently no-op instead of erroring outside the bounds where it's safe
# to run unattended on every upload.

def test_auto_run_on_upload_flags_the_planted_outlier():
    df = _ensemble_df()
    consensus, summary = auto_run_on_upload(
        df, {"value": "numeric", "other": "numeric", "label": "categorical"}
    )
    assert consensus is not None and 0 in consensus.index
    assert consensus.loc[0, "consensus_count"] == len(ENSEMBLE_METHODS)
    assert summary is not None and set(summary.keys()) == set(ENSEMBLE_METHODS)


def test_auto_run_on_upload_matches_manual_ensemble_result():
    df = _ensemble_df()
    column_types = {"value": "numeric", "other": "numeric", "label": "categorical"}
    auto_consensus, auto_summary = auto_run_on_upload(df, column_types)
    manual_consensus, manual_summary, error = find_anomalies_ensemble(df, column_types)
    assert error is None
    assert auto_consensus.equals(manual_consensus)
    assert auto_summary == manual_summary


def test_auto_run_on_upload_silently_skips_below_min_rows():
    df = pd.DataFrame({"value": range(ENSEMBLE_MIN_ROWS - 1), "other": range(ENSEMBLE_MIN_ROWS - 1)})
    consensus, summary = auto_run_on_upload(df, {"value": "numeric", "other": "numeric"})
    assert consensus is None and summary is None


def test_auto_run_on_upload_silently_skips_above_auto_run_cap():
    # Above AUTO_RUN_MAX_ROWS, LOF/DBSCAN's pairwise-distance cost is too
    # expensive to run unattended on every upload — must no-op, not error,
    # so the upload flow never blocks or shows a scary banner for this.
    rng = np.random.default_rng(3)
    n = AUTO_RUN_MAX_ROWS + 1
    df = pd.DataFrame({"value": rng.normal(size=n), "other": rng.normal(size=n)})
    consensus, summary = auto_run_on_upload(df, {"value": "numeric", "other": "numeric"})
    assert consensus is None and summary is None


def test_auto_run_on_upload_silently_skips_with_fewer_than_two_numeric_columns():
    rng = np.random.default_rng(4)
    df = pd.DataFrame({"value": rng.normal(size=30), "label": ["x"] * 30})
    consensus, summary = auto_run_on_upload(df, {"value": "numeric", "label": "categorical"})
    assert consensus is None and summary is None


def test_auto_run_on_upload_never_raises_on_unexpected_failure(monkeypatch):
    df = _ensemble_df()
    column_types = {"value": "numeric", "other": "numeric", "label": "categorical"}

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated sklearn failure")

    monkeypatch.setattr("modules.anomaly.find_anomalies_ensemble", _boom)
    consensus, summary = auto_run_on_upload(df, column_types)
    assert consensus is None and summary is None
