"""Tests for modules.forecasting's STL decomposition additions.

Ported from eval/stl_decomposition_eval.py (see .prism/audit_2026-08-10.md).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.forecasting import (
    build_decomposition_chart,
    can_decompose,
    decompose_series,
    decomposition_verdict,
    prepare_series,
)

N_DAYS = 365 * 3


def _make_seasonal_df():
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-01", periods=N_DAYS, freq="D")
    trend_component = np.linspace(100, 200, N_DAYS)
    seasonal_component = 20 * np.sin(2 * np.pi * np.arange(N_DAYS) / 7)  # weekly cycle
    noise = rng.normal(0, 5, N_DAYS)
    values = trend_component + seasonal_component + noise
    return pd.DataFrame({"date": dates, "value": values}), trend_component


def test_prepare_series_infers_daily_frequency():
    df, _ = _make_seasonal_df()
    series, freq, prep_error = prepare_series(df, "date", "value")
    assert prep_error is None
    assert freq == "D"
    assert len(series) == N_DAYS


def test_can_decompose_gate_checks():
    df, _ = _make_seasonal_df()
    series, freq, _ = prepare_series(df, "date", "value")

    ok, reason = can_decompose(series, freq)
    assert ok is True
    assert reason is None

    ok_short, reason_short = can_decompose(series.iloc[:10], freq)
    assert ok_short is False
    assert reason_short is not None

    ok_no_freq, _ = can_decompose(series, "unknown_freq")
    assert ok_no_freq is False


def test_decompose_series_recovers_known_components():
    df, trend_component = _make_seasonal_df()
    series, freq, _ = prepare_series(df, "date", "value")
    decomp = decompose_series(series, freq)

    assert "error" not in decomp
    assert all(k in decomp for k in ["trend", "seasonal", "resid", "observed"])
    assert len(decomp["trend"]) == len(series)

    # STL is additive: observed ≈ trend + seasonal + resid
    reconstructed = decomp["trend"] + decomp["seasonal"] + decomp["resid"]
    max_diff = float(np.max(np.abs(reconstructed.values - series.values)))
    assert max_diff < 1e-6

    trend_corr = float(np.corrcoef(decomp["trend"].values, trend_component)[0, 1])
    assert trend_corr > 0.9

    assert decomp["seasonal_period"] == 7
    assert 0 <= decomp["trend_strength"] <= 1
    assert 0 <= decomp["seasonal_strength"] <= 1
    assert decomp["trend_strength"] > 0.5
    assert decomp["seasonal_strength"] > 0.5


def test_decompose_series_weak_seasonality_on_pure_noise():
    rng = np.random.default_rng(1)
    dates = pd.date_range("2023-01-01", periods=N_DAYS, freq="D")
    flat_df = pd.DataFrame({"date": dates, "value": rng.normal(50, 2, N_DAYS)})
    flat_series, flat_freq, _ = prepare_series(flat_df, "date", "value")
    flat_decomp = decompose_series(flat_series, flat_freq)
    assert "error" not in flat_decomp
    assert flat_decomp["seasonal_strength"] < 0.5


def test_insufficient_data_handled_without_crashing():
    tiny_df = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=10, freq="D"), "value": range(10)})
    tiny_series, tiny_freq, tiny_prep_error = prepare_series(tiny_df, "date", "value")
    if tiny_prep_error is None:
        tiny_decomp = decompose_series(tiny_series, tiny_freq)
        assert "error" in tiny_decomp
    # else: prepare_series already rejected the too-short series — also valid.


def test_decomposition_verdict_mentions_key_stats():
    df, _ = _make_seasonal_df()
    series, freq, _ = prepare_series(df, "date", "value")
    decomp = decompose_series(series, freq)
    verdict_text = decomposition_verdict(decomp)
    assert "Trend strength" in verdict_text
    assert "Seasonal strength" in verdict_text
    assert "7" in verdict_text


def test_build_decomposition_chart_has_four_traces():
    df, _ = _make_seasonal_df()
    series, freq, _ = prepare_series(df, "date", "value")
    decomp = decompose_series(series, freq)
    fig = build_decomposition_chart(decomp, "Test Decomposition")
    assert fig is not None
    assert len(fig.data) == 4


def test_non_robust_mode_also_works():
    df, _ = _make_seasonal_df()
    series, freq, _ = prepare_series(df, "date", "value")
    decomp_nonrobust = decompose_series(series, freq, robust=False)
    assert "error" not in decomp_nonrobust
