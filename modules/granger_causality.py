"""
Granger Causality — does one time series' *past* help predict another
series' *future*, beyond what the second series' own past already
explains? The time-series-precedence sibling of modules/causal_inference.py
(cross-sectional propensity-score matching) and modules/did.py (before/
after panel comparison): those answer "what happened *because of* a
one-time treatment"; this answers "does X's history carry information
about where Y is headed" for two ongoing numeric series over time.

The single most-repeated caveat in the Granger-causality literature is that
this tests *predictability, not causality* — "Granger causality" is a
statistics-community name for a specific predictive-precedence test, not a
guarantee of a true causal mechanism (a confound that itself drives both
series with a lag would also pass this test). Every result and verdict
below says so explicitly, same "state the assumption, don't imply more than
the test can show" convention as causal_inference.py and did.py already
follow for their own methods.

Pipeline (each step is current textbook best practice, not a shortcut):

  1. Align the two chosen numeric columns on a shared, regularly-spaced
     datetime axis (prepare_pair() — same regularization idea as
     modules.forecasting.prepare_series, just for a pair of columns).
  2. Test each series for stationarity via the Augmented Dickey-Fuller test
     and difference (up to `max_diff` times) until it passes, or the cap is
     hit (difference_until_stationary()). Both series are then differenced
     by whichever order was larger, so they stay aligned and directly
     comparable — testing Granger causality on non-stationary series can
     produce spurious "significant" results driven purely by shared trends,
     not real predictive information.
  3. Pick the lag order via `statsmodels.tsa.api.VAR.select_order()`'s
     AIC-minimizing choice on the two-variable system, rather than
     guessing a lag or trying every lag until one looks significant
     (multiple-testing p-hacking) — lag order is itself a real modeling
     choice with real consequences (too few lags misses genuine delayed
     effects, too many overfits and burns degrees of freedom).
  4. Run `statsmodels.tsa.stattools.grangercausalitytests` at that lag in
     BOTH directions — X->Y and Y->X — since Granger causality is not
     symmetric, and a "feedback loop" (both directions significant) is
     itself a genuinely informative, distinct finding from a one-way
     relationship.

100% local compute (numpy/pandas/statsmodels, already a pinned dependency —
zero new installs). narrate_granger_causality() is an optional plain-
English layer on an already-computed result, same call_gemini() plumbing
and graceful no-model fallback as every other narrate_* helper in the app.
Callers are responsible for caching its result, same convention as those.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

# Below this many aligned observations, lag selection + a VAR fit + a
# Granger test are all too unstable to trust — need enough headroom for
# several lags' worth of degrees of freedom even after any differencing.
MIN_HISTORY_POINTS = 30
DEFAULT_MAX_LAG = 10
DEFAULT_MAX_DIFF = 2
DEFAULT_SIGNIFICANCE = 0.05


def prepare_pair(df: pd.DataFrame, datetime_col: str, cause_col: str, effect_col: str) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
    """Build a clean, regularly-spaced two-column time series ready for a
    Granger causality test. Returns (aligned_df, freq, error); aligned_df
    has exactly [cause_col, effect_col] as columns, sorted, evenly spaced,
    duplicate timestamps averaged, gaps linearly interpolated — same
    regularization approach as modules.forecasting.prepare_series, applied
    to a pair of columns at once so both stay index-aligned.
    """
    clean = df[[datetime_col, cause_col, effect_col]].dropna()
    if clean.empty:
        return None, None, "No non-null paired values in the selected columns."

    aligned = clean.groupby(datetime_col)[[cause_col, effect_col]].mean().sort_index()
    if len(aligned) < MIN_HISTORY_POINTS:
        return None, None, (
            f"Only {len(aligned)} distinct timestamps with both columns present — "
            f"need at least {MIN_HISTORY_POINTS} to fit a Granger causality test."
        )

    freq = pd.infer_freq(aligned.index)
    if freq is None:
        median_gap = aligned.index.to_series().diff().dropna().median()
        if median_gap <= pd.Timedelta(days=1):
            freq = "D"
        elif median_gap <= pd.Timedelta(days=8):
            freq = "W"
        elif median_gap <= pd.Timedelta(days=32):
            freq = "MS"
        else:
            freq = "QS"

    aligned = aligned.asfreq(freq).interpolate(limit_direction="both")
    return aligned, freq, None


def difference_until_stationary(series: pd.Series, max_diff: int = DEFAULT_MAX_DIFF, alpha: float = 0.05) -> tuple[pd.Series, int, float, float]:
    """Difference `series` (via .diff(), dropping the resulting leading NaN
    each time) until an Augmented Dickey-Fuller test says it's stationary
    (p < alpha) or `max_diff` differences have been applied, whichever
    comes first.

    Returns (result_series, d, p_value_before, p_value_after) — d is how
    many times it was differenced; p_value_before/after are the ADF
    p-value on the original series and on the (possibly differenced)
    result, so callers can report both.
    """
    current = series.reset_index(drop=True)
    try:
        p_before = float(adfuller(current, autolag="AIC")[1])
    except Exception:
        p_before = float("nan")

    p_current = p_before
    d = 0
    while (np.isnan(p_current) or p_current >= alpha) and d < max_diff:
        current = current.diff().dropna().reset_index(drop=True)
        d += 1
        if len(current) < 8:  # too short to even run ADF meaningfully
            break
        try:
            p_current = float(adfuller(current, autolag="AIC")[1])
        except Exception:
            p_current = float("nan")

    return current, d, p_before, p_current


def run_granger_causality(
    df: pd.DataFrame,
    datetime_col: str,
    cause_col: str,
    effect_col: str,
    max_lag: Optional[int] = None,
    significance: float = DEFAULT_SIGNIFICANCE,
    max_diff: int = DEFAULT_MAX_DIFF,
) -> dict:
    """Test whether `cause_col`'s past helps predict `effect_col`'s future
    (and vice versa, for the reverse-direction context), over the datetime
    axis given by `datetime_col`.

    Returns a dict:
      ok: bool
      error: str (only when ok is False)
      cause_col / effect_col: str
      n_obs: int (aligned observations actually used, after differencing)
      selected_lag: int (AIC-chosen VAR lag order)
      differencing: {cause_d, effect_d, applied_d, cause_adf_pvalue_before/
          after, effect_adf_pvalue_before/after}
      forward: {f_stat, p_value, df_num, df_denom, significant} — does
          cause_col Granger-cause effect_col
      reverse: {...} — does effect_col Granger-cause cause_col
      feedback: bool — both directions significant
    """
    if cause_col == effect_col:
        return {"ok": False, "error": "Pick two different columns — a series can't Granger-cause itself."}

    aligned, freq, prep_error = prepare_pair(df, datetime_col, cause_col, effect_col)
    if prep_error:
        return {"ok": False, "error": prep_error}

    cause_series = aligned[cause_col]
    effect_series = aligned[effect_col]

    if cause_series.std(ddof=0) == 0.0 or effect_series.std(ddof=0) == 0.0:
        return {"ok": False, "error": "One of the selected columns is constant over this range — nothing to test."}

    _, cause_d, cause_p_before, cause_p_after = difference_until_stationary(cause_series, max_diff=max_diff)
    _, effect_d, effect_p_before, effect_p_after = difference_until_stationary(effect_series, max_diff=max_diff)
    applied_d = max(cause_d, effect_d)

    if applied_d > 0:
        cause_final = cause_series.diff(applied_d).dropna()
        effect_final = effect_series.diff(applied_d).dropna()
    else:
        cause_final = cause_series
        effect_final = effect_series

    data = pd.DataFrame({cause_col: cause_final, effect_col: effect_final}).dropna().reset_index(drop=True)
    n = len(data)
    if n < MIN_HISTORY_POINTS:
        return {
            "ok": False,
            "error": f"Only {n} usable observations after aligning and differencing — "
                     f"need at least {MIN_HISTORY_POINTS} to fit a reliable Granger causality test.",
        }

    lag_cap = max(1, min(max_lag or DEFAULT_MAX_LAG, n // 5 - 1))

    try:
        from statsmodels.tsa.api import VAR
        var_model = VAR(data[[effect_col, cause_col]])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            selection = var_model.select_order(maxlags=lag_cap)
        selected_lag = int(selection.aic) if selection.aic else 1
        selected_lag = max(1, min(selected_lag, lag_cap))
    except Exception as e:
        return {"ok": False, "error": f"Couldn't select a lag order: {e}"}

    def _run(y_col: str, x_col: str) -> dict:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = grangercausalitytests(data[[y_col, x_col]].values, maxlag=[selected_lag], verbose=False)
        f_stat, p_value, df_denom, df_num = res[selected_lag][0]["ssr_ftest"]
        return {
            "f_stat": float(f_stat),
            "p_value": float(p_value),
            "df_num": int(df_num),
            "df_denom": float(df_denom),
            "significant": bool(p_value < significance),
        }

    try:
        forward = _run(effect_col, cause_col)  # does cause_col Granger-cause effect_col
        reverse = _run(cause_col, effect_col)  # does effect_col Granger-cause cause_col
    except Exception as e:
        return {"ok": False, "error": f"Granger causality test failed: {e}"}

    return {
        "ok": True,
        "cause_col": cause_col,
        "effect_col": effect_col,
        "n_obs": n,
        "selected_lag": selected_lag,
        "differencing": {
            "cause_d": cause_d,
            "effect_d": effect_d,
            "applied_d": applied_d,
            "cause_adf_pvalue_before": cause_p_before,
            "cause_adf_pvalue_after": cause_p_after,
            "effect_adf_pvalue_before": effect_p_before,
            "effect_adf_pvalue_after": effect_p_after,
        },
        "forward": forward,
        "reverse": reverse,
        "feedback": bool(forward["significant"] and reverse["significant"]),
    }


def granger_verdict(result: dict) -> str:
    """Plain-text one-line summary of a run_granger_causality() result."""
    if not result.get("ok"):
        return f"Couldn't run the Granger causality test: {result.get('error', 'unknown error')}"

    cause, effect = result["cause_col"], result["effect_col"]
    fwd, rev = result["forward"], result["reverse"]

    if result["feedback"]:
        return (
            f"Feedback loop: '{cause}' helps predict '{effect}' (p={fwd['p_value']:.3g}) AND "
            f"'{effect}' helps predict '{cause}' (p={rev['p_value']:.3g}) — each carries information "
            f"about the other's future, not just a one-way relationship."
        )
    if fwd["significant"]:
        return f"'{cause}''s past helps predict '{effect}''s future (p={fwd['p_value']:.3g}) — no evidence it runs the other way."
    if rev["significant"]:
        return f"'{effect}''s past helps predict '{cause}''s future (p={rev['p_value']:.3g}) — the reverse of what was tested for."
    return f"No significant Granger-causal relationship found between '{cause}' and '{effect}' in either direction."


def build_granger_chart(result: dict) -> Optional[go.Figure]:
    """Grouped bar chart comparing the forward and reverse tests' p-values
    against the significance threshold, so which direction (if either) is
    significant is visible at a glance."""
    if not result.get("ok"):
        return None

    fwd, rev = result["forward"], result["reverse"]
    labels = [f"{result['cause_col']} → {result['effect_col']}", f"{result['effect_col']} → {result['cause_col']}"]
    p_values = [fwd["p_value"], rev["p_value"]]
    colors = ["#16a34a" if p < 0.05 else "#9ca3af" for p in p_values]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=p_values, marker_color=colors, name="p-value"))
    fig.add_hline(y=0.05, line_dash="dash", line_color="#dc2626", annotation_text="p = 0.05")
    fig.update_layout(title="Granger causality — p-value by direction", yaxis_title="p-value", showlegend=False)
    return fig


def narrate_granger_causality(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one run_granger_causality() result in plain
    English. Returns (narration, error) — never raises. Callers should
    cache the result rather than re-calling this on every rerun, same
    convention as modules.did.narrate_diff_in_differences.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    cause, effect = result["cause_col"], result["effect_col"]
    fwd, rev = result["forward"], result["reverse"]
    d_note = (
        f"Both series were differenced {result['differencing']['applied_d']}x before testing (they weren't stationary)."
        if result["differencing"]["applied_d"] > 0 else "Both series were already stationary — no differencing needed."
    )

    prompt = (
        f"A Granger causality test (lag={result['selected_lag']}) between '{cause}' and '{effect}':\n"
        f"Does {cause}'s past help predict {effect}'s future? F={fwd['f_stat']:.3g}, p={fwd['p_value']:.3g} "
        f"({'significant' if fwd['significant'] else 'not significant'}).\n"
        f"Does {effect}'s past help predict {cause}'s future? F={rev['f_stat']:.3g}, p={rev['p_value']:.3g} "
        f"({'significant' if rev['significant'] else 'not significant'}).\n"
        f"{d_note}\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what this means. Be explicit "
        "that Granger causality tests predictive precedence, not proof of a true causal mechanism — a shared "
        "underlying driver could produce the same pattern. Do not repeat the raw numbers verbatim."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
