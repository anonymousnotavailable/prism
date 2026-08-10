"""
Time Series Decomposition (STL) — pytest suite (ported from
eval/stl_decomposition_eval.py; see test_auto_insights.py's module
docstring for why this port happened).
"""

import numpy as np
import pandas as pd
import pytest

from modules.forecasting import (
    build_decomposition_chart,
    can_decompose,
    decompose_series,
    decomposition_verdict,
    prepare_series,
)


@pytest.fixture(scope="module")
def series_data():
    np.random.seed(42)
    n_days = 365 * 3
    dates = pd.date_range("2023-01-01", periods=n_days, freq="D")
    trend_component = np.linspace(100, 200, n_days)
    seasonal_component = 20 * np.sin(2 * np.pi * np.arange(n_days) / 7)
    noise = np.random.normal(0, 5, n_days)
    values = trend_component + seasonal_component + noise
    df = pd.DataFrame({"date": dates, "value": values})
    series, freq, prep_error = prepare_series(df, "date", "value")
    return {"n_days": n_days, "series": series, "freq": freq, "prep_error": prep_error, "trend_component": trend_component}


def test_prepare_series_infers_daily_frequency(series_data):
    assert series_data["prep_error"] is None
    assert series_data["freq"] == "D"
    assert len(series_data["series"]) == series_data["n_days"]


def test_can_decompose_gate(series_data):
    ok, reason = can_decompose(series_data["series"], "D")
    assert ok is True
    assert reason is None

    ok_short, reason_short = can_decompose(series_data["series"].iloc[:10], "D")
    assert ok_short is False
    assert reason_short is not None

    ok_no_freq, _ = can_decompose(series_data["series"], "unknown_freq")
    assert ok_no_freq is False


@pytest.fixture(scope="module")
def decomp(series_data):
    return decompose_series(series_data["series"], series_data["freq"])


def test_decompose_series_recovers_known_components(series_data, decomp):
    series = series_data["series"]
    assert "error" not in decomp
    assert all(k in decomp for k in ["trend", "seasonal", "resid", "observed"])
    assert len(decomp["trend"]) == len(series)

    reconstructed = decomp["trend"] + decomp["seasonal"] + decomp["resid"]
    max_diff = float(np.max(np.abs(reconstructed.values - series.values)))
    assert max_diff < 1e-6

    trend_corr = float(np.corrcoef(decomp["trend"].values, series_data["trend_component"])[0, 1])
    assert trend_corr > 0.9

    assert decomp["seasonal_period"] == 7
    assert 0 <= decomp["trend_strength"] <= 1
    assert 0 <= decomp["seasonal_strength"] <= 1
    assert decomp["trend_strength"] > 0.5
    assert decomp["seasonal_strength"] > 0.5


def test_decompose_series_weak_seasonality_on_noise():
    np.random.seed(1)
    n_days = 365 * 3
    dates = pd.date_range("2023-01-01", periods=n_days, freq="D")
    flat_df = pd.DataFrame({"date": dates, "value": np.random.normal(50, 2, n_days)})
    flat_series, flat_freq, _ = prepare_series(flat_df, "date", "value")
    flat_decomp = decompose_series(flat_series, flat_freq)
    assert "error" not in flat_decomp
    assert flat_decomp["seasonal_strength"] < 0.5


def test_insufficient_data_handled_without_crash():
    tiny_df = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=10, freq="D"), "value": range(10)})
    tiny_series, tiny_freq, tiny_prep_error = prepare_series(tiny_df, "date", "value")
    if tiny_prep_error is None:
        assert "error" in decompose_series(tiny_series, tiny_freq)
    # else: prepare_series already rejected the too-short series — also valid.


def test_decomposition_verdict_mentions_key_figures(decomp):
    verdict_text = decomposition_verdict(decomp)
    assert "Trend strength" in verdict_text
    assert "Seasonal strength" in verdict_text
    assert "7" in verdict_text


def test_build_decomposition_chart(decomp):
    fig = build_decomposition_chart(decomp, "Test Decomposition")
    assert fig is not None
    assert len(fig.data) == 4


def test_non_robust_mode_also_works(series_data):
    decomp_nonrobust = decompose_series(series_data["series"], series_data["freq"], robust=False)
    assert "error" not in decomp_nonrobust
