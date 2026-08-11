"""Tests for rolling-origin (walk-forward) forecast backtesting in
modules/forecasting.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import forecasting


def _trend_series(n=120, freq="D", noise=0.5, seed=0) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    values = 100 + np.arange(n) * 0.5 + rng.normal(0, noise, n)
    return pd.Series(values, index=idx).asfreq(freq)


def _short_series(n=6) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(np.arange(n, dtype=float), index=idx).asfreq("D")


class TestCanBacktest:
    def test_enough_history_returns_true(self):
        series = _trend_series(n=120)
        ok, reason = forecasting.can_backtest(series, "D", horizon=14)
        assert ok is True
        assert reason is None

    def test_too_short_returns_false_with_reason(self):
        series = _short_series()
        ok, reason = forecasting.can_backtest(series, "D", horizon=14)
        assert ok is False
        assert isinstance(reason, str) and len(reason) > 0

    def test_horizon_larger_than_series_returns_false(self):
        series = _trend_series(n=20)
        ok, reason = forecasting.can_backtest(series, "D", horizon=50)
        assert ok is False


class TestRollingOriginBacktest:
    def test_low_noise_trend_gives_low_error(self):
        series = _trend_series(n=150, noise=0.2, seed=1)
        result = forecasting.rolling_origin_backtest(series, "D", horizon=14, n_windows=5)
        assert "error" not in result
        assert result["n_windows_run"] >= 2
        assert result["mean_mape"] is not None
        assert result["mean_mape"] < 15  # clean trend should backtest very accurately

    def test_windows_list_has_expected_shape(self):
        series = _trend_series(n=150, noise=0.2, seed=1)
        result = forecasting.rolling_origin_backtest(series, "D", horizon=14, n_windows=4)
        assert len(result["windows"]) == result["n_windows_run"]
        for w in result["windows"]:
            assert "origin" in w
            assert "train_size" in w
            assert "mae" in w and w["mae"] >= 0
            assert "rmse" in w and w["rmse"] >= 0
            assert "model_used" in w

    def test_requests_more_windows_than_possible_still_works(self):
        series = _trend_series(n=60, noise=0.2, seed=2)
        result = forecasting.rolling_origin_backtest(series, "D", horizon=10, n_windows=50)
        assert "error" not in result
        assert result["n_windows_run"] >= 2
        # should have silently capped, not crashed or produced overlapping/invalid windows
        assert result["n_windows_run"] < 50

    def test_too_little_history_returns_error(self):
        series = _short_series()
        result = forecasting.rolling_origin_backtest(series, "D", horizon=14, n_windows=5)
        assert "error" in result

    def test_rmse_at_least_mae(self):
        # Mathematical property: RMSE >= MAE always (Jensen's inequality).
        series = _trend_series(n=150, noise=3.0, seed=3)
        result = forecasting.rolling_origin_backtest(series, "D", horizon=14, n_windows=5)
        assert "error" not in result
        for w in result["windows"]:
            assert w["rmse"] >= w["mae"] - 1e-9

    def test_mape_handles_near_zero_actuals_without_inf(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="D")
        values = np.concatenate([np.zeros(50), np.arange(50, dtype=float)])
        series = pd.Series(values, index=idx).asfreq("D")
        result = forecasting.rolling_origin_backtest(series, "D", horizon=10, n_windows=3)
        if "error" not in result:
            for w in result["windows"]:
                if w["mape"] is not None:
                    assert np.isfinite(w["mape"])

    def test_does_not_mutate_input_series(self):
        series = _trend_series(n=100, seed=4)
        original = series.copy()
        forecasting.rolling_origin_backtest(series, "D", horizon=10, n_windows=3)
        pd.testing.assert_series_equal(series, original)


class TestBacktestVerdict:
    def test_excellent_band(self):
        assert "excellent" in forecasting.backtest_verdict(5.0).lower()

    def test_good_band(self):
        assert "good" in forecasting.backtest_verdict(15.0).lower()

    def test_reasonable_band(self):
        assert "reasonable" in forecasting.backtest_verdict(35.0).lower()

    def test_unreliable_band(self):
        assert "unreliable" in forecasting.backtest_verdict(75.0).lower()

    def test_none_mape_handled(self):
        result = forecasting.backtest_verdict(None)
        assert isinstance(result, str)


class TestBuildBacktestChart:
    def test_returns_figure_without_error(self):
        series = _trend_series(n=150, noise=0.5, seed=5)
        result = forecasting.rolling_origin_backtest(series, "D", horizon=14, n_windows=3)
        fig = forecasting.build_backtest_chart(result, "test series")
        assert fig is not None
        assert len(fig.data) > 0
