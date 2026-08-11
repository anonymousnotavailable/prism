"""
Difference-in-Differences (DiD) — the panel-data counterpart to
modules/causal_inference.py's propensity score matching. PSM answers "what's
the effect of a treatment, matching similar units at one point in time?";
DiD answers the same causal question when the data instead has a *before*
and *after* observation for a treated group and a control group ("did the
treated group change more than the control group did, from pre to post?").

The estimator is the textbook 2x2 design generalized via regression (Angrist
& Pischke's standard approach, and what every applied-econometrics course
teaches first):

    outcome = b0 + b1*treated + b2*post + b3*(treated * post) + e

b3 — the coefficient on the treated*post interaction — is the DiD estimate:
it isolates "how much extra did the treated group change, beyond whatever
the control group's own before/after change already explains." Fit via OLS
with heteroskedasticity-robust (HC1) standard errors, since a naive DiD
comparison across groups is a classic place for non-constant variance to
distort inference. This is mathematically identical to the textbook 2x2
formula (treated_post - treated_pre) - (control_post - control_pre) — the
regression framing just makes the standard error and covariate-adjustment
extension straightforward, and is the form the confidence interval and
p-value below are computed from.

DiD's one big assumption — "parallel trends": absent treatment, the treated
group's outcome would have moved in step with the control group's. Nothing
in the 2x2 data itself can prove that; the closest thing to *evidence* for
it is checking whether the two groups were already trending together in the
periods *before* treatment started. When the caller supplies 2+ pre-
treatment periods, `estimate_diff_in_differences` runs that placebo check
(same OLS-interaction idea, restricted to pre-period data, testing whether
the groups' slopes differ) — but per current econometrics literature
(Roth 2022, Bilinski & Hatfield 2019, and the pre-trends-testing critique
more broadly), a non-significant pre-trend difference is neither necessary
nor sufficient proof that parallel trends holds afterward: it's a
diagnostic, not a proof, and the result always says so explicitly rather
than implying "test passed, trust the estimate."

100% local compute (numpy/pandas/statsmodels) — no Gemini call is required
to estimate anything. narrate_diff_in_differences() is an optional plain-
English layer on an already-computed result, same call_gemini() plumbing
and graceful no-model fallback as every other narrate_* helper in the app.
Callers are responsible for caching its result, same convention as those.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Below this many observations in any one of the four (group x period)
# cells, the DiD estimate is too noisy to trust — same spirit as
# causal_inference's _MIN_GROUP_SIZE, just applied per-cell instead of
# per-arm since DiD has four cells instead of two.
_MIN_CELL_SIZE = 5
# Below this per-cell count, flag the estimate as small-sample rather than
# silently reporting a wide-but-unqualified confidence interval.
_SMALL_SAMPLE_WARNING_THRESHOLD = 30
_PRETREND_CAVEAT = (
    "A non-significant pre-trend difference is not proof that parallel trends holds — "
    "pre-trend tests are known to have low statistical power, and passing one is neither "
    "necessary nor sufficient for the assumption to actually hold going forward. Treat this "
    "as one diagnostic, not a guarantee."
)


def _fit_ols_interaction(y: np.ndarray, group: np.ndarray, moderator: np.ndarray) -> Optional[dict]:
    """Fit y = b0 + b1*group + b2*moderator + b3*(group*moderator) via OLS
    with HC1 robust standard errors, and return the interaction term's
    coefficient/SE/CI/p-value. `moderator` is `post` for the main DiD
    estimate, or a numeric period index for the pre-trend check — same
    regression shape either way. Returns None if statsmodels isn't
    importable or the fit fails outright (e.g. a singular design matrix).
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return None

    X = np.column_stack([
        np.ones(len(y)),
        group.astype(float),
        moderator.astype(float),
        group.astype(float) * moderator.astype(float),
    ])
    try:
        fit = sm.OLS(y, X).fit(cov_type="HC1")
    except Exception:
        return None
    if not np.all(np.isfinite(fit.params)) or not np.all(np.isfinite(fit.bse)):
        return None

    ci = fit.conf_int(alpha=0.05)
    return {
        "estimate": float(fit.params[3]),
        "se": float(fit.bse[3]),
        "ci_low": float(ci[3][0]),
        "ci_high": float(ci[3][1]),
        "p_value": float(fit.pvalues[3]),
    }


def _check_pre_trend(sub: pd.DataFrame, treated_mask: pd.Series, time_col: str, outcome_col: str, periods: list) -> dict:
    """Placebo test: restricted to `periods` (pre-treatment only), does the
    treated group's slope over time differ from the control group's? A
    significant treated*period_index interaction is evidence *against*
    parallel trends (the groups were already diverging before treatment
    started). Always returns a dict with "ok"; ok=False means the check
    itself couldn't run (too few periods, too little data), not that
    parallel trends was validated.
    """
    periods = [p for p in periods if p in set(sub[time_col].unique())]
    if len(periods) < 2:
        return {"ok": False, "error": "Need at least 2 pre-treatment periods to check for a trend."}

    period_rank = {p: i for i, p in enumerate(periods)}
    pre_sub = sub[sub[time_col].isin(periods)]
    if len(pre_sub) < 2 * _MIN_CELL_SIZE:
        return {"ok": False, "error": "Not enough pre-treatment observations to check for a trend."}

    pre_treated_mask = treated_mask.loc[pre_sub.index].to_numpy()
    period_idx = pre_sub[time_col].map(period_rank).to_numpy(dtype=float)
    y = pre_sub[outcome_col].to_numpy(dtype=float)

    fit = _fit_ols_interaction(y, pre_treated_mask.astype(float), period_idx)
    if fit is None:
        return {"ok": False, "error": "Could not fit a pre-trend model on these periods."}

    return {
        "ok": True,
        "slope_diff": fit["estimate"],
        "se": fit["se"],
        "p_value": fit["p_value"],
        "diverging": fit["p_value"] < 0.05,
        "periods_used": periods,
        "caveat": _PRETREND_CAVEAT,
    }


def estimate_diff_in_differences(
    df: pd.DataFrame,
    group_col: str,
    treated_value,
    time_col: str,
    pre_period,
    post_period,
    outcome_col: str,
    pre_trend_periods: Optional[list] = None,
    min_cell_size: int = _MIN_CELL_SIZE,
) -> dict:
    """Estimate the Difference-in-Differences effect of `group_col ==
    treated_value` on `outcome_col`, comparing the change from `pre_period`
    to `post_period` (both values of `time_col`) against the same change in
    the control group.

    Returns a dict, always with an "ok" key:
      ok=False: {"ok": False, "error": "<why>"}
      ok=True:  {"ok": True, "did_estimate", "se", "ci_low", "ci_high",
                 "p_value", "group_col", "treated_value", "control_value",
                 "time_col", "pre_period", "post_period", "outcome_col",
                 "cell_means": {"treated_pre", "treated_post", "control_pre",
                 "control_post"}, "cell_ns": {...same 4 keys...},
                 "pre_trend_check": None or a dict (see _check_pre_trend),
                 "warnings": [str, ...]}

    Never raises — every failure path (missing columns, non-2-group
    treatment, non-numeric outcome, invalid period values, an empty or
    under-powered cell, a degenerate regression fit) is reported as
    ok=False with a plain-English reason instead.
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    for col, label in ((group_col, "Group"), (time_col, "Time"), (outcome_col, "Outcome")):
        if col not in df.columns:
            return {"ok": False, "error": f"{label} column '{col}' not found in the dataset."}
    if not pd.api.types.is_numeric_dtype(df[outcome_col]):
        return {"ok": False, "error": f"Outcome column '{outcome_col}' must be numeric."}
    if pre_period == post_period:
        return {"ok": False, "error": "Pre-period and post-period must be different values."}

    group_uniques = df[group_col].dropna().unique().tolist()
    if len(group_uniques) != 2:
        return {"ok": False, "error": f"Group column '{group_col}' must have exactly 2 groups (found {len(group_uniques)})."}
    if treated_value not in group_uniques:
        return {"ok": False, "error": f"'{treated_value}' is not a value of '{group_col}'."}
    control_value = next(v for v in group_uniques if v != treated_value)

    time_uniques = df[time_col].dropna().unique().tolist()
    if pre_period not in time_uniques:
        return {"ok": False, "error": f"Pre-period '{pre_period}' is not a value of '{time_col}'."}
    if post_period not in time_uniques:
        return {"ok": False, "error": f"Post-period '{post_period}' is not a value of '{time_col}'."}

    sub = df[[group_col, time_col, outcome_col]].dropna().copy()
    sub = sub[sub[group_col].isin([treated_value, control_value]) & sub[time_col].isin([pre_period, post_period])]

    treated_mask_full = sub[group_col] == treated_value
    post_mask_full = sub[time_col] == post_period

    cell_ns = {
        "treated_pre": int(((treated_mask_full) & (~post_mask_full)).sum()),
        "treated_post": int(((treated_mask_full) & (post_mask_full)).sum()),
        "control_pre": int(((~treated_mask_full) & (~post_mask_full)).sum()),
        "control_post": int(((~treated_mask_full) & (post_mask_full)).sum()),
    }
    if min(cell_ns.values()) < min_cell_size:
        thin = ", ".join(f"{k}={v}" for k, v in cell_ns.items() if v < min_cell_size)
        return {
            "ok": False,
            "error": f"Not enough data in every group/period cell (need >= {min_cell_size} each): {thin}.",
        }

    y = sub[outcome_col].to_numpy(dtype=float)
    fit = _fit_ols_interaction(y, treated_mask_full.to_numpy(), post_mask_full.to_numpy())
    if fit is None:
        return {"ok": False, "error": "Could not fit the difference-in-differences regression on this data."}

    cell_means = {
        "treated_pre": float(sub.loc[(treated_mask_full) & (~post_mask_full), outcome_col].mean()),
        "treated_post": float(sub.loc[(treated_mask_full) & (post_mask_full), outcome_col].mean()),
        "control_pre": float(sub.loc[(~treated_mask_full) & (~post_mask_full), outcome_col].mean()),
        "control_post": float(sub.loc[(~treated_mask_full) & (post_mask_full), outcome_col].mean()),
    }

    pre_trend_check = None
    if pre_trend_periods:
        # `pre_trend_periods` is the full chronologically-ordered window to
        # test (typically includes `pre_period` itself as the most recent
        # pre-treatment point) — passed through as-is, not modified here,
        # so the caller controls exactly what's compared.
        trend_sub = df[[group_col, time_col, outcome_col]].dropna().copy()
        trend_sub = trend_sub[trend_sub[group_col].isin([treated_value, control_value])]
        trend_treated_mask = trend_sub[group_col] == treated_value
        pre_trend_check = _check_pre_trend(trend_sub, trend_treated_mask, time_col, outcome_col, list(pre_trend_periods))

    warnings = []
    if min(cell_ns.values()) < _SMALL_SAMPLE_WARNING_THRESHOLD:
        warnings.append(
            f"Small sample in at least one cell (smallest n={min(cell_ns.values())}) — "
            "the confidence interval below will be wide/unstable."
        )
    if pre_trend_check is not None and pre_trend_check.get("ok") and pre_trend_check.get("diverging"):
        warnings.append(
            "The pre-treatment trend check found a statistically significant difference in slopes — "
            "parallel trends looks questionable for this pair of groups."
        )

    return {
        "ok": True,
        "did_estimate": fit["estimate"],
        "se": fit["se"],
        "ci_low": fit["ci_low"],
        "ci_high": fit["ci_high"],
        "p_value": fit["p_value"],
        "group_col": group_col,
        "treated_value": treated_value,
        "control_value": control_value,
        "time_col": time_col,
        "pre_period": pre_period,
        "post_period": post_period,
        "outcome_col": outcome_col,
        "cell_means": cell_means,
        "cell_ns": cell_ns,
        "pre_trend_check": pre_trend_check,
        "warnings": warnings,
    }


def narrate_diff_in_differences(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one estimate_diff_in_differences() result in
    plain English. Returns (narration, error) — never raises. Callers
    should cache the result rather than re-calling this on every rerun,
    same convention as causal_inference.narrate_causal_effect.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    m = result["cell_means"]
    pretrend_block = ""
    pt = result.get("pre_trend_check")
    if pt and pt.get("ok"):
        pretrend_block = (
            f"\nPre-treatment trend check across {', '.join(str(p) for p in pt['periods_used'])}: "
            f"slope difference {pt['slope_diff']:.3g} (p={pt['p_value']:.3g}), "
            f"{'diverging' if pt['diverging'] else 'no significant divergence'}."
        )
    warn_block = ("\nCaveats: " + "; ".join(result["warnings"])) if result["warnings"] else ""

    prompt = (
        f"A difference-in-differences analysis estimated the effect of "
        f"'{result['group_col']} = {result['treated_value']}' (vs. '{result['control_value']}') "
        f"on '{result['outcome_col']}', comparing '{result['time_col']}' = {result['pre_period']} "
        f"(pre) to {result['post_period']} (post).\n"
        f"DiD estimate: {result['did_estimate']:.3g}, 95% CI [{result['ci_low']:.3g}, {result['ci_high']:.3g}], "
        f"p={result['p_value']:.3g}.\n"
        f"Group means — treated: {m['treated_pre']:.3g} -> {m['treated_post']:.3g}; "
        f"control: {m['control_pre']:.3g} -> {m['control_post']:.3g}."
        f"{pretrend_block}{warn_block}\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what this estimate means, "
        "whether the confidence interval suggests the effect is real, and any caveat that matters (including "
        "the parallel-trends assumption this method relies on). Do not repeat the raw numbers verbatim — "
        "focus on practical interpretation."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
