"""Tests for modules.anomaly's ensemble outlier detection —
IsolationForest + LocalOutlierFactor + DBSCAN consensus voting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import MIN_ROWS_REQUIRED, find_anomalies_ensemble


def _clean_df_with_planted_outliers(n: int = 80, n_outliers: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    values = rng.normal(loc=50, scale=2, size=n)
    second = rng.normal(loc=10, scale=1, size=n)
    # plant extreme, obvious outliers across both columns
    for i in range(n_outliers):
        values[i] = 5000.0 + i * 100
        second[i] = -500.0 - i * 50
    return pd.DataFrame({"value": values, "value2": second, "label": ["x"] * n})


def test_ensemble_flags_planted_outliers_with_high_consensus():
    df = _clean_df_with_planted_outliers()
    result, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "value2": "numeric", "label": "categorical"}
    )
    assert error is None
    assert result is not None
    # the planted extreme rows should be present with a consensus_count >= 2 (of 3 methods)
    planted = result.loc[result.index.isin([0, 1, 2])]
    assert len(planted) == 3
    assert (planted["consensus_count"] >= 2).all()
    assert "methods_flagged" in result.columns


def test_ensemble_summary_reports_per_method_counts():
    df = _clean_df_with_planted_outliers()
    result, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "value2": "numeric", "label": "categorical"}
    )
    assert error is None
    assert set(summary.keys()) >= {"isolation_forest", "local_outlier_factor", "dbscan"}
    for method_count in summary.values():
        assert method_count >= 0


def test_ensemble_errors_below_min_rows():
    df = pd.DataFrame({"value": range(MIN_ROWS_REQUIRED - 1)})
    result, summary, error = find_anomalies_ensemble(df, {"value": "numeric"})
    assert result is None
    assert error is not None


def test_ensemble_errors_with_no_numeric_columns():
    df = pd.DataFrame({"label": ["a"] * 20})
    result, summary, error = find_anomalies_ensemble(df, {"label": "categorical"})
    assert result is None
    assert error is not None


def test_ensemble_returns_empty_frame_when_nothing_flagged():
    df = pd.DataFrame({"value": [50.0] * 30, "value2": [10.0] * 30})
    result, summary, error = find_anomalies_ensemble(
        df, {"value": "numeric", "value2": "numeric"}, contamination=0.01
    )
    assert error is None
    assert result is not None  # empty df is a valid "no anomalies" result


def test_ensemble_consensus_count_never_exceeds_method_count():
    df = _clean_df_with_planted_outliers()
    result, _, error = find_anomalies_ensemble(
        df, {"value": "numeric", "value2": "numeric", "label": "categorical"}
    )
    assert error is None
    assert (result["consensus_count"] <= 3).all()
    assert (result["consensus_count"] >= 1).all()


def test_ensemble_high_confidence_rows_are_flagged_by_majority():
    df = _clean_df_with_planted_outliers()
    result, _, error = find_anomalies_ensemble(
        df, {"value": "numeric", "value2": "numeric", "label": "categorical"}
    )
    assert error is None
    high_conf = result[result["consensus_count"] >= 2]
    # the 3 planted extreme outliers must all be high-confidence
    assert set([0, 1, 2]).issubset(set(high_conf.index))
