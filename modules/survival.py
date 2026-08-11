"""
Survival Analysis — Kaplan-Meier curves and the log-rank test, the standard
toolkit for "time until an event" questions (time until a customer churns,
a machine fails, a loan defaults) that every other statistical surface in
Prism sidesteps by throwing away *when* something didn't happen yet.

modules/domains.py's flag_churn() answers "has this user gone quiet by a
fixed cutoff?" — a fast proxy, but a hard yes/no that discards the single
piece of information survival analysis exists to use: a customer who
signed up last week and hasn't churned *yet* is not the same evidence as
one who signed up two years ago and also hasn't churned. Both are
"right-censored" — the event (churn, failure, default) simply hasn't
happened by the time the data was pulled, not evidence it never will.
Kaplan-Meier is the product-limit estimator built specifically to use
partial (censored) observations instead of dropping them; the log-rank
test is the standard way to ask "do two (or more) groups' survival curves
actually differ, or could that gap be noise?"

This is the textbook, auditable version (product-limit estimator with
Greenwood's variance, log-rank via the standard observed-vs-expected
chi-square construction) — not a black-box survival ML library. No new
dependency: everything here is numpy/pandas/scipy, same footprint
philosophy as modules/causal_inference.py and modules/market_basket.py.

100% local compute — no Gemini call is required to estimate anything.
narrate_survival() is an optional plain-English layer on an already-
computed result, same call_gemini() plumbing and graceful no-model
fallback as every other narrate_* helper in the app. Callers are
responsible for caching its result, same convention as those.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Below this many total (non-missing) rows, a Kaplan-Meier curve is too
# noisy to be worth showing.
_MIN_ROWS = 10
# A group with fewer than this many rows can't support its own curve /
# contribution to the log-rank test.
_MIN_GROUP_SIZE = 5
# More levels than this and the curve becomes unreadable and the log-rank
# test's degrees of freedom balloon past what's interpretable in one chart.
_MAX_GROUP_LEVELS = 8
# Tractability cap, same "sample down rather than hang" convention as
# market_basket.MAX_BASKETS — the O(n_event_times * n) log-rank/KM loop
# would get slow well before this on a genuinely huge upload.
_MAX_ROWS = 20_000


def _km_from_arrays(durations: np.ndarray, events: np.ndarray) -> dict:
    """The product-limit (Kaplan-Meier) estimator plus Greenwood's variance,
    over one homogeneous group of (duration, event) pairs. Never raises.
    Returns {"ok": False, "error"} or {"ok": True, "curve", "median_survival",
    "n", "n_events", "n_censored"}. `curve` is a list of dicts (one row per
    *event* time, the standard KM convention — censoring-only times don't
    get their own row, but do shrink the risk set for every later row).
    """
    if len(durations) == 0:
        return {"ok": False, "error": "No data to analyze."}

    n = len(durations)
    n_events_total = int(events.sum())
    n_censored_total = n - n_events_total
    event_times = sorted(set(durations[events == 1].tolist()))

    curve = []
    survival = 1.0
    var_sum = 0.0  # cumulative Greenwood sum: sum(d_i / (n_i * (n_i - d_i)))
    median_survival = None
    for t in event_times:
        at_risk_mask = durations >= t
        n_i = int(at_risk_mask.sum())
        d_i = int(((durations == t) & (events == 1)).sum())
        if n_i == 0:
            continue
        survival *= (1 - d_i / n_i)
        if n_i - d_i > 0:
            var_sum += d_i / (n_i * (n_i - d_i))
            se = float(survival * np.sqrt(var_sum))
        else:
            se = 0.0
        ci_low = max(0.0, survival - 1.96 * se)
        ci_high = min(1.0, survival + 1.96 * se)
        curve.append({
            "time": t, "n_at_risk": n_i, "n_events": d_i,
            "survival": float(survival), "se": se, "ci_low": ci_low, "ci_high": ci_high,
        })
        if median_survival is None and survival <= 0.5:
            median_survival = t

    return {
        "ok": True,
        "curve": curve,
        "median_survival": median_survival,
        "n": n,
        "n_events": n_events_total,
        "n_censored": n_censored_total,
    }


def compute_kaplan_meier(durations, events) -> dict:
    """Public entry point for a single Kaplan-Meier curve. `durations` and
    `events` are array-likes (event: 1 = event observed, 0 = censored).
    See _km_from_arrays for the return shape. Never raises.
    """
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    if len(durations) != len(events):
        return {"ok": False, "error": "Durations and events must be the same length."}
    return _km_from_arrays(durations, events)


def log_rank_test(durations, events, groups) -> dict:
    """Log-rank test across 2+ groups: at every observed event time, compare
    each group's actual event count against the count it would be expected
    to contribute if the hazard were identical across groups (proportional
    to how many of that group are still at risk). Summed across all event
    times and standardized by the pooled hypergeometric variance, this is
    the standard chi-square test of "do these survival curves actually
    differ" (Mantel-Haenszel / Klein & Moeschberger's construction).

    Returns a dict, always with an "ok" key:
      ok=False: {"ok": False, "error": "<why>"}
      ok=True:  {"ok": True, "statistic", "df", "p_value",
                 "groups": [{"group", "observed", "expected"}, ...]}

    Never raises — degenerate inputs (fewer than 2 groups, zero events, a
    singular covariance matrix) are reported as ok=False.
    """
    from scipy import stats as scipy_stats

    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    groups = np.asarray(groups)
    if len(durations) != len(events) or len(durations) != len(groups):
        return {"ok": False, "error": "Durations, events, and groups must be the same length."}

    labels = sorted(set(groups.tolist()), key=str)
    k = len(labels)
    if k < 2:
        return {"ok": False, "error": "Need at least 2 groups to compare survival curves."}
    if events.sum() == 0:
        return {"ok": False, "error": "No events observed in this data — nothing to compare."}

    event_times = sorted(set(durations[events == 1].tolist()))
    if not event_times:
        return {"ok": False, "error": "No events observed in this data — nothing to compare."}

    observed = np.zeros(k)
    expected = np.zeros(k)
    V = np.zeros((k, k))
    group_idx = {label: i for i, label in enumerate(labels)}

    for t in event_times:
        at_risk_mask = durations >= t
        n_i = int(at_risk_mask.sum())
        d_i = int(((durations == t) & (events == 1)).sum())
        if n_i <= 1 or d_i == 0:
            continue
        n_ig = np.array([int((at_risk_mask & (groups == g)).sum()) for g in labels])
        d_ig = np.array([int(((durations == t) & (events == 1) & (groups == g)).sum()) for g in labels])
        e_ig = n_ig * d_i / n_i
        observed += d_ig
        expected += e_ig

        factor = d_i * (n_i - d_i) / (n_i - 1) if n_i > 1 else 0.0
        for a in range(k):
            for b in range(k):
                if a == b:
                    V[a, b] += factor * n_ig[a] * (n_i - n_ig[a]) / (n_i ** 2)
                else:
                    V[a, b] += -factor * n_ig[a] * n_ig[b] / (n_i ** 2)

    oe = observed - expected
    # V is singular by construction (rows/cols sum to 0) — drop the last
    # group and invert the (k-1)x(k-1) submatrix, standard log-rank practice.
    oe_reduced = oe[:-1]
    V_reduced = V[:-1, :-1]
    try:
        statistic = float(oe_reduced @ np.linalg.solve(V_reduced, oe_reduced))
    except np.linalg.LinAlgError:
        return {"ok": False, "error": "Could not compute the log-rank test — degenerate risk sets in this data."}
    if not np.isfinite(statistic) or statistic < 0:
        return {"ok": False, "error": "Could not compute the log-rank test — degenerate risk sets in this data."}

    df = k - 1
    p_value = float(scipy_stats.chi2.sf(statistic, df))
    return {
        "ok": True,
        "statistic": statistic,
        "df": df,
        "p_value": p_value,
        "groups": [{"group": labels[i], "observed": float(observed[i]), "expected": float(expected[i])} for i in range(k)],
    }


def survival_analysis(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    group_col: Optional[str] = None,
    min_rows: int = _MIN_ROWS,
    min_group_size: int = _MIN_GROUP_SIZE,
    max_group_levels: int = _MAX_GROUP_LEVELS,
    max_rows: int = _MAX_ROWS,
    random_state: int = 42,
) -> dict:
    """App-facing entry point: validates `duration_col` (numeric, >= 0) and
    `event_col` (binary — accepts 0/1, True/False, Yes/No, or any exactly-
    2-valued column), computes an overall Kaplan-Meier curve, and — if
    `group_col` is given — a per-group curve plus a log-rank test comparing
    them.

    Returns a dict, always with an "ok" key:
      ok=False: {"ok": False, "error": "<why>"}
      ok=True:  {"ok": True, "duration_col", "event_col", "group_col",
                 "overall": <compute_kaplan_meier result, plus "label">,
                 "groups": None or {level: <compute_kaplan_meier result>, ...},
                 "log_rank": None or <log_rank_test result>,
                 "warnings": [str, ...]}

    Never raises — missing columns, a non-numeric/negative duration column,
    a non-binary event column, too little data, or a group column with too
    many levels are all reported as ok=False with a plain-English reason.
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    for col, label in ((duration_col, "Duration"), (event_col, "Event")):
        if col not in df.columns:
            return {"ok": False, "error": f"{label} column '{col}' not found in the dataset."}
    if group_col is not None and group_col not in df.columns:
        return {"ok": False, "error": f"Group column '{group_col}' not found in the dataset."}

    cols = [duration_col, event_col] + ([group_col] if group_col else [])
    sub = df[cols].dropna().copy()

    if not pd.api.types.is_numeric_dtype(sub[duration_col]):
        sub[duration_col] = pd.to_numeric(sub[duration_col], errors="coerce")
        sub = sub.dropna(subset=[duration_col])
    if not pd.api.types.is_numeric_dtype(sub[duration_col]):
        return {"ok": False, "error": f"Duration column '{duration_col}' must be numeric."}
    if (sub[duration_col] < 0).any():
        return {"ok": False, "error": f"Duration column '{duration_col}' has negative values — durations must be >= 0."}

    event_uniques = sub[event_col].dropna().unique().tolist()
    if len(event_uniques) != 2:
        return {"ok": False, "error": f"Event column '{event_col}' must have exactly 2 values (found {len(event_uniques)})."}
    # Coerce to 0/1: prefer an obvious "event happened" value (1, True, "Yes", "yes")
    # if present among the two, otherwise fall back to treating the second
    # sorted value as the event (arbitrary but deterministic).
    positive_aliases = {1, "1", True, "true", "yes", "y", "churned", "died", "failed", "default", "defaulted"}
    sorted_uniques = sorted(event_uniques, key=str)
    positive_value = next(
        (v for v in sorted_uniques if str(v).strip().lower() in positive_aliases or v in positive_aliases),
        sorted_uniques[-1],
    )
    sub["_event_bin"] = (sub[event_col] == positive_value).astype(int)

    if len(sub) < min_rows:
        return {"ok": False, "error": f"Not enough data after dropping missing values: {len(sub)} rows (need >= {min_rows})."}

    warnings = []
    if len(sub) > max_rows:
        sub = sub.sample(n=max_rows, random_state=random_state)
        warnings.append(f"Dataset sampled down to {max_rows:,} rows for tractability.")

    overall = compute_kaplan_meier(sub[duration_col].to_numpy(), sub["_event_bin"].to_numpy())
    if not overall["ok"]:
        return {"ok": False, "error": overall["error"]}

    groups_result = None
    log_rank = None
    if group_col:
        levels = sorted(sub[group_col].dropna().unique().tolist(), key=str)
        if len(levels) < 2:
            return {"ok": False, "error": f"Group column '{group_col}' needs at least 2 levels to compare."}
        if len(levels) > max_group_levels:
            return {
                "ok": False,
                "error": f"Group column '{group_col}' has {len(levels)} levels — pick one with <= {max_group_levels}.",
            }
        thin = [lv for lv in levels if (sub[group_col] == lv).sum() < min_group_size]
        if thin:
            return {
                "ok": False,
                "error": f"Not enough rows in group(s) {', '.join(str(t) for t in thin)} (need >= {min_group_size} each).",
            }

        groups_result = {}
        for level in levels:
            level_df = sub[sub[group_col] == level]
            groups_result[level] = compute_kaplan_meier(level_df[duration_col].to_numpy(), level_df["_event_bin"].to_numpy())

        log_rank = log_rank_test(sub[duration_col].to_numpy(), sub["_event_bin"].to_numpy(), sub[group_col].to_numpy())

    return {
        "ok": True,
        "duration_col": duration_col,
        "event_col": event_col,
        "group_col": group_col,
        "overall": overall,
        "groups": groups_result,
        "log_rank": log_rank,
        "warnings": warnings,
    }


def narrate_survival(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one survival_analysis() result in plain
    English. Returns (narration, error) — never raises. Callers should
    cache the result rather than re-calling this on every rerun, same
    convention as causal_inference.narrate_causal_effect.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    overall = result["overall"]
    lines = [
        f"Overall: n={overall['n']}, events={overall['n_events']}, censored={overall['n_censored']}, "
        f"median survival time: {overall['median_survival'] if overall['median_survival'] is not None else 'not reached'} "
        f"(in units of '{result['duration_col']}')."
    ]
    if result.get("groups"):
        for level, g in result["groups"].items():
            median = g["median_survival"] if g["median_survival"] is not None else "not reached"
            lines.append(f"  - {result['group_col']} = {level}: n={g['n']}, events={g['n_events']}, median survival: {median}.")
    lr_block = ""
    lr = result.get("log_rank")
    if lr and lr.get("ok"):
        lr_block = f"\nLog-rank test across groups: p={lr['p_value']:.3g} (df={lr['df']})."

    prompt = (
        f"A Kaplan-Meier survival analysis was run on '{result['duration_col']}' (time until "
        f"'{result['event_col']}').\n" + "\n".join(lines) + lr_block + "\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what the median "
        "survival time(s) mean, whether groups (if any) differ meaningfully, and what 'not reached' "
        "means if it comes up (it means most subjects hadn't experienced the event by the end of the "
        "observation window, not that they never will). Do not repeat the raw numbers verbatim — "
        "focus on practical interpretation."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
