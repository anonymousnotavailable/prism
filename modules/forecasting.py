"""
Forecasting — pick a datetime + numeric column, get a statsmodels forecast
with confidence bands. Tries ETS (statsmodels' ExponentialSmoothing/Holt-
Winters implementation) first since it natively supports trend + seasonality;
falls back to SARIMAX if ETS can't fit the series (e.g. too little data for
the seasonal component it picked).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from statsmodels.tsa.exponential_smoothing.ets import ETSModel
from statsmodels.tsa.statespace.sarimax import SARIMAX

MIN_HISTORY_POINTS = 8

# Roughly-standard seasonal cycle length per inferred pandas frequency code.
_SEASONAL_PERIODS_BY_FREQ = {
    "D": 7, "B": 5, "W": 52, "M": 12, "MS": 12, "Q": 4, "QS": 4, "A": 1, "Y": 1, "H": 24,
}


def _infer_seasonal_periods(freq: str) -> int:
    base = (freq or "D").split("-")[0]
    return _SEASONAL_PERIODS_BY_FREQ.get(base, 0)


def prepare_series(df: pd.DataFrame, datetime_col: str, numeric_col: str) -> tuple[Optional[pd.Series], Optional[str], Optional[str]]:
    """Build a clean, regularly-spaced time series ready for forecasting.

    Returns (series, freq, error). Duplicate timestamps are averaged; gaps
    introduced by resampling to a regular frequency are linearly interpolated
    (statsmodels' forecasting models require an evenly-spaced index).
    """
    clean = df[[datetime_col, numeric_col]].dropna()
    if clean.empty:
        return None, None, "No non-null paired values in the selected columns."

    series = clean.groupby(datetime_col)[numeric_col].mean().sort_index()
    if len(series) < MIN_HISTORY_POINTS:
        return None, None, f"Only {len(series)} distinct timestamps found — need at least {MIN_HISTORY_POINTS} to forecast."

    freq = pd.infer_freq(series.index)
    if freq is None:
        median_gap = series.index.to_series().diff().dropna().median()
        if median_gap <= pd.Timedelta(days=1):
            freq = "D"
        elif median_gap <= pd.Timedelta(days=8):
            freq = "W"
        elif median_gap <= pd.Timedelta(days=32):
            freq = "MS"
        else:
            freq = "QS"

    series = series.asfreq(freq).interpolate(limit_direction="both")
    return series, freq, None


def run_forecast(series: pd.Series, periods: int, freq: str) -> dict:
    """Fit a forecast model and project `periods` steps ahead with a 95%
    confidence band. Returns a dict with "model_used", "forecast" (a
    DataFrame indexed by future dates with forecast/lower/upper columns),
    "history" (the input series), and "warning" (set if ETS failed over to
    SARIMAX) — or "error" if both models failed.
    """
    seasonal_periods = _infer_seasonal_periods(freq)
    use_seasonal = seasonal_periods >= 2 and len(series) >= 2 * seasonal_periods

    model_used = None
    forecast_df = None
    warning = None

    try:
        if use_seasonal:
            model = ETSModel(series, trend="add", seasonal="add", seasonal_periods=seasonal_periods, freq=freq)
        else:
            model = ETSModel(series, trend="add", freq=freq)
        fit = model.fit(disp=False)
        pred = fit.get_prediction(start=len(series), end=len(series) + periods - 1)
        summary = pred.summary_frame(alpha=0.05)
        model_used = "Exponential Smoothing (ETS)" + (" with seasonality" if use_seasonal else "")
        forecast_df = pd.DataFrame(
            {"forecast": summary["mean"], "lower": summary["pi_lower"], "upper": summary["pi_upper"]}
        )
    except Exception as e:
        warning = f"Exponential smoothing failed ({e}); fell back to a SARIMAX model."

    if forecast_df is None:
        try:
            seasonal_order = (1, 1, 1, seasonal_periods) if use_seasonal else (0, 0, 0, 0)
            model = SARIMAX(
                series, order=(1, 1, 1), seasonal_order=seasonal_order,
                enforce_stationarity=False, enforce_invertibility=False,
            )
            fit = model.fit(disp=False)
            pred = fit.get_forecast(steps=periods)
            ci = pred.conf_int(alpha=0.05)
            model_used = "SARIMAX(1,1,1)" + (f"x(1,1,1,{seasonal_periods})" if use_seasonal else "")
            forecast_df = pd.DataFrame(
                {"forecast": pred.predicted_mean, "lower": ci.iloc[:, 0], "upper": ci.iloc[:, 1]}
            )
        except Exception as e:
            return {"error": f"Forecasting failed with both Exponential Smoothing and SARIMAX: {e}"}

    forecast_df.index.name = series.index.name or "date"
    return {"model_used": model_used, "forecast": forecast_df, "history": series, "warning": warning}


def forecast_caveat(n_history: int, periods: int, model_used: str) -> str:
    """Plain-English reliability caveat, scaled to how far out the forecast reaches."""
    ratio = periods / n_history if n_history else 1.0
    if ratio > 0.5:
        confidence = "low"
    elif ratio > 0.2:
        confidence = "moderate"
    else:
        confidence = "reasonable"

    risk_note = (
        "Forecasting this far relative to the amount of history available carries real risk of error — "
        "treat it as directional, not precise. "
        if confidence != "reasonable"
        else ""
    )
    return (
        f"Fit on {n_history} historical observations to project {periods} periods ahead using {model_used}. "
        f"Confidence in this forecast is **{confidence}**. {risk_note}"
        "Forecasts assume future patterns resemble the past and cannot anticipate one-off events (promotions, "
        "holidays, external shocks) — widening bands further out reflect growing uncertainty, not a return to old values."
    )


def build_forecast_chart(history: pd.Series, forecast_df: pd.DataFrame, title: str) -> go.Figure:
    """History as a solid line, forecast as a dashed line, with a shaded 95% confidence band."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history.index, y=history.values, mode="lines", name="History"))
    fig.add_trace(
        go.Scatter(x=forecast_df.index, y=forecast_df["forecast"], mode="lines", name="Forecast", line=dict(dash="dash"))
    )
    fig.add_trace(
        go.Scatter(
            x=list(forecast_df.index) + list(forecast_df.index[::-1]),
            y=list(forecast_df["upper"]) + list(forecast_df["lower"][::-1]),
            fill="toself", fillcolor="rgba(0, 200, 200, 0.15)", line=dict(width=0),
            name="95% confidence", hoverinfo="skip",
        )
    )
    fig.update_layout(title=title, margin=dict(t=50, b=10, l=10, r=10))
    return fig
