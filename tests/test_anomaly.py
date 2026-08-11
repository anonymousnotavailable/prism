"""Tests for modules.anomaly — IsolationForest-based row flagging, plus the
ensemble (IsolationForest + LOF + DBSCAN) consensus detector."""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.anomaly import (
    ENSEMBLE_METHODS,
    ENSEMBLE_MIN_ROWS,
    MIN_ROWS_REQUIRED,
    SHAP_MAX_ROWS_TO_EXPLAIN,
    aggregate_top_drivers,
    build_driver_chart,
    find_anomalies,
    find_anomalies_ensemble,
    fingerprint_flagged,
    narrate_anomalies,
    narrate_ensemble_disagreement,
    shap_is_available,
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


# --- SHAP-based per-feature anomaly attribution -----------------------------
# `find_anomalies` upgrades its naive "largest deviation from median" reason
# with real SHAP TreeExplainer attribution when the library is available and
# the flagged set is small enough — these tests pin that behavior without
# requiring every environment to have shap installed (they skip gracefully).

def _multi_feature_outlier_df(n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    df = pd.DataFrame(
        {
            "revenue": rng.normal(loc=1000, scale=50, size=n),
            "headcount": rng.normal(loc=20, scale=3, size=n),
            "noise": rng.normal(size=n),
        }
    )
    # row 0 is extreme on revenue AND headcount, ordinary on noise —
    # a real multi-feature driver should surface both, not just one.
    df.loc[0, "revenue"] = 100_000.0
    df.loc[0, "headcount"] = 500.0
    return df


def test_shap_is_available_matches_import():
    import importlib.util

    assert shap_is_available() == (importlib.util.find_spec("shap") is not None)


def test_find_anomalies_reason_mentions_multiple_top_drivers_when_shap_available():
    if not shap_is_available():
        import pytest

        pytest.skip("shap not installed in this environment")
    df = _multi_feature_outlier_df()
    flagged, error = find_anomalies(
        df, {"revenue": "numeric", "headcount": "numeric", "noise": "numeric"}
    )
    assert error is None
    assert 0 in flagged.index
    reason = flagged.loc[0, "anomaly_reason"]
    # both planted drivers should be named — a naive single-feature heuristic
    # would only ever mention one of them.
    assert "revenue" in reason and "headcount" in reason


def test_find_anomalies_top_drivers_column_present_when_shap_available():
    if not shap_is_available():
        import pytest

        pytest.skip("shap not installed in this environment")
    df = _multi_feature_outlier_df()
    flagged, _ = find_anomalies(
        df, {"revenue": "numeric", "headcount": "numeric", "noise": "numeric"}
    )
    assert "anomaly_top_drivers" in flagged.columns
    drivers = flagged.loc[0, "anomaly_top_drivers"]
    assert isinstance(drivers, list) and len(drivers) >= 1
    assert {"feature", "shap_abs", "direction"} <= drivers[0].keys()
    # ranked descending by |shap value|
    magnitudes = [d["shap_abs"] for d in drivers]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_find_anomalies_still_works_when_shap_explanation_fails(monkeypatch):
    # Simulate a shap failure (e.g. incompatible version) — find_anomalies
    # must fall back to the naive single-feature reason, never raise.
    import modules.anomaly as anomaly_mod

    monkeypatch.setattr(anomaly_mod, "_shap_matrix_for_rows", lambda *a, **k: None)
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert "anomaly_reason" in flagged.columns
    assert "anomaly_top_drivers" not in flagged.columns or flagged["anomaly_top_drivers"].isna().all()


def test_find_anomalies_skips_shap_above_row_cap(monkeypatch):
    # Enrichment is bounded so a huge flagged set can't blow up runtime —
    # verify the cap is actually respected rather than just documented.
    import modules.anomaly as anomaly_mod

    calls = []
    monkeypatch.setattr(
        anomaly_mod,
        "_shap_matrix_for_rows",
        lambda *a, **k: calls.append(1) or None,
    )
    monkeypatch.setattr(anomaly_mod, "SHAP_MAX_ROWS_TO_EXPLAIN", 0)
    df = _clean_df_with_one_outlier()
    flagged, error = find_anomalies(df, {"value": "numeric", "label": "categorical"})
    assert error is None
    assert not calls  # never attempted — the cap short-circuits before calling shap


def test_aggregate_top_drivers_ranks_by_frequency_then_magnitude():
    flagged = pd.DataFrame(
        {
            "anomaly_top_drivers": [
                [{"feature": "revenue", "shap_abs": 5.0, "direction": "above"}],
                [{"feature": "revenue", "shap_abs": 3.0, "direction": "above"}],
                [{"feature": "headcount", "shap_abs": 9.0, "direction": "below"}],
            ]
        }
    )
    agg = aggregate_top_drivers(flagged)
    assert agg[0]["feature"] == "revenue"  # flagged as the #1 driver twice
    assert agg[0]["count"] == 2
    assert agg[1]["feature"] == "headcount"
    assert agg[1]["count"] == 1


def test_aggregate_top_drivers_empty_without_column():
    assert aggregate_top_drivers(pd.DataFrame({"value": [1, 2]})) == []


def test_build_driver_chart_none_when_no_drivers():
    assert build_driver_chart([]) is None


def test_build_driver_chart_returns_figure_for_real_drivers():
    agg = [{"feature": "revenue", "count": 3, "avg_abs_shap": 4.2}]
    fig = build_driver_chart(agg)
    assert fig is not None


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
