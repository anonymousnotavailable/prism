"""Tests for modules.changepoint — CUSUM-statistic binary segmentation for
detecting mean-shift changepoints in a numeric series, the structural-break
counterpart to modules.forecasting's STL decomposition (which explains
*smooth* trend/seasonal movement, not abrupt regime changes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.changepoint import (
    build_changepoint_chart,
    changepoint_verdict,
    cusum_stat,
    detect_changepoints,
    narrate_changepoints,
)


def _step_series(n_per_segment=60, shift=10.0, noise=1.0, seed=0, n_segments=2):
    rng = np.random.default_rng(seed)
    values = []
    for i in range(n_segments):
        level = i * shift
        values.append(rng.normal(level, noise, n_per_segment))
    values = np.concatenate(values)
    index = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=index)


def _flat_series(n=150, noise=1.0, seed=1):
    rng = np.random.default_rng(seed)
    values = rng.normal(0, noise, n)
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(values, index=index)


# ─────────────────────────────────────────────────────────────────────────
# cusum_stat
# ─────────────────────────────────────────────────────────────────────────
def test_cusum_stat_finds_obvious_shift_location():
    series = _step_series(n_per_segment=50, shift=20.0, noise=0.5, seed=0)
    stat, loc = cusum_stat(series.values)
    # split point should land close to the true boundary at index 50
    assert 40 <= loc <= 60
    assert stat > 0


def test_cusum_stat_higher_for_bigger_shift():
    small = _step_series(n_per_segment=50, shift=1.0, noise=1.0, seed=0)
    big = _step_series(n_per_segment=50, shift=20.0, noise=1.0, seed=0)
    stat_small, _ = cusum_stat(small.values)
    stat_big, _ = cusum_stat(big.values)
    assert stat_big > stat_small


def test_cusum_stat_constant_series_is_zero():
    values = np.full(50, 5.0)
    stat, loc = cusum_stat(values)
    assert stat == 0.0


def test_cusum_stat_too_short_raises():
    with pytest.raises(ValueError):
        cusum_stat(np.array([1.0]))


# ─────────────────────────────────────────────────────────────────────────
# detect_changepoints
# ─────────────────────────────────────────────────────────────────────────
def test_detect_changepoints_single_shift():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    assert result["ok"]
    assert len(result["changepoints"]) == 1
    cp = result["changepoints"][0]
    assert 50 <= cp["position"] <= 70
    assert cp["p_value"] < 0.05
    assert cp["delta"] > 10  # roughly the true 15-unit shift
    assert cp["direction"] == "increase"


def test_detect_changepoints_multiple_shifts():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=3)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    assert result["ok"]
    assert len(result["changepoints"]) == 2
    positions = sorted(cp["position"] for cp in result["changepoints"])
    assert 50 <= positions[0] <= 70
    assert 110 <= positions[1] <= 130
    # segments should reconstruct the full series
    assert len(result["segments"]) == 3


def test_detect_changepoints_flat_series_finds_nothing():
    series = _flat_series(n=150, noise=1.0, seed=1)
    result = detect_changepoints(series, min_segment_size=10, seed=1)
    assert result["ok"]
    assert result["changepoints"] == []
    assert len(result["segments"]) == 1


def test_detect_changepoints_too_short_series():
    series = pd.Series([1.0, 2.0, 3.0])
    result = detect_changepoints(series, min_segment_size=10)
    assert not result["ok"]
    assert "error" in result


def test_detect_changepoints_drops_nan():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    with_nans = series.copy()
    with_nans.iloc[5] = np.nan
    with_nans.iloc[80] = np.nan
    result = detect_changepoints(with_nans, min_segment_size=10, seed=0)
    assert result["ok"]
    assert result["n"] == len(series) - 2


def test_detect_changepoints_respects_max_changepoints():
    series = _step_series(n_per_segment=25, shift=30.0, noise=0.5, seed=2, n_segments=8)
    result = detect_changepoints(series, min_segment_size=8, max_changepoints=2, seed=2)
    assert result["ok"]
    assert len(result["changepoints"]) <= 2


def test_detect_changepoints_non_numeric_series_errors():
    series = pd.Series(["a", "b", "c"] * 10)
    result = detect_changepoints(series, min_segment_size=5)
    assert not result["ok"]


def test_detect_changepoints_segments_cover_full_series_no_gaps():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    total_n = sum(seg["n"] for seg in result["segments"])
    assert total_n == result["n"]


def test_detect_changepoints_index_labels_are_original_timestamps():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    cp = result["changepoints"][0]
    assert cp["index_label"] in series.index


# ─────────────────────────────────────────────────────────────────────────
# changepoint_verdict
# ─────────────────────────────────────────────────────────────────────────
def test_verdict_no_changepoints():
    series = _flat_series(n=150, noise=1.0, seed=1)
    result = detect_changepoints(series, min_segment_size=10, seed=1)
    text = changepoint_verdict(result)
    assert "no" in text.lower()


def test_verdict_with_changepoints_mentions_count():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    text = changepoint_verdict(result)
    assert "1" in text


def test_verdict_failed_result():
    text = changepoint_verdict({"ok": False, "error": "boom"})
    assert "boom" in text


# ─────────────────────────────────────────────────────────────────────────
# build_changepoint_chart
# ─────────────────────────────────────────────────────────────────────────
def test_build_chart_returns_figure_with_shapes_for_changepoints():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    fig = build_changepoint_chart(result, "test series")
    assert fig is not None
    assert len(fig.data) >= 1
    assert len(fig.layout.shapes) == 1


def test_build_chart_no_changepoints_still_returns_figure():
    series = _flat_series(n=150, noise=1.0, seed=1)
    result = detect_changepoints(series, min_segment_size=10, seed=1)
    fig = build_changepoint_chart(result, "flat series")
    assert fig is not None
    assert len(fig.layout.shapes) == 0


# ─────────────────────────────────────────────────────────────────────────
# narrate_changepoints
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_no_model():
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)
    text, error = narrate_changepoints(None, result)
    assert text == ""
    assert error is not None


def test_narrate_failed_result():
    text, error = narrate_changepoints(object(), {"ok": False, "error": "boom"})
    assert text == ""
    assert error is not None


def test_narrate_calls_gemini_with_prompt(monkeypatch):
    series = _step_series(n_per_segment=60, shift=15.0, noise=1.0, seed=0, n_segments=2)
    result = detect_changepoints(series, min_segment_size=10, seed=0)

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_changepoints(object(), result)
    assert error is None
    assert text == "It works."
    assert "changepoint" in captured["prompt"].lower()


def test_narrate_no_changepoints_still_works(monkeypatch):
    series = _flat_series(n=150, noise=1.0, seed=1)
    result = detect_changepoints(series, min_segment_size=10, seed=1)

    def fake_call_gemini(model, prompt):
        return "No shifts found.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_changepoints(object(), result)
    assert error is None
    assert text == "No shifts found."
