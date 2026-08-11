"""
Power / Sample-Size Analysis — a forward-looking experiment-planning tool
built on statsmodels.stats.power, the frequentist counterpart to
modules.bayesian_ab sitting next to it in Stats Lab. Where a Bayesian
posterior can be checked at any time without inflating a false-positive
rate, a frequentist significance test needs its sample size pre-committed
before data collection starts to keep that guarantee — this module answers
the two questions that pre-commitment requires:

  - "How many samples do I need?" (solve for N, given a hypothesized or
    pilot-estimated effect size, alpha, and a target power.)
  - "What power will a planned sample size give me?" (solve for power,
    given a planned N and an effect size.)

for both two-sample mean comparisons (Cohen's d via TTestIndPower) and
two-sample proportion comparisons (NormalIndPower + proportion_effectsize).
Both are already covered by statsmodels, itself already a pinned Prism
dependency (used by modules.did, modules.regression_diagnostics,
modules.forecasting) — no new pip install.

Deliberately does NOT surface a bare "observed/post-hoc power" number
computed from the very data used to estimate the effect size. Hoenig &
Heisey's 2001 critique ("The Abuse of Power") shows post-hoc power is a
near one-to-one, deterministic function of the p-value a test already
produced — it cannot tell you anything the p-value didn't already say, and
presenting it as an independent "was my test strong enough" verdict is
widely regarded as a statistical malpractice trap. effect_size_from_means()
/ effect_size_from_proportions() are framed and labeled throughout as a
*pilot estimate to plan a future study's sample size*, never as a
retroactive validity check on the dataset they were computed from — the
"n_per_group" used in solve_power mode is always a number the caller
supplies for a hypothetical future collection, not the pilot data's own
row count.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Below this many rows in a group, an effect-size estimate from it is too
# noisy to plan a future study around — same "stay silent rather than force
# it" convention as modules.survival's _MIN_GROUP_SIZE.
_MIN_ROWS_PER_GROUP = 5
# How many points to sample along the power curve chart.
_POWER_CURVE_POINTS = 24


def required_n_means(effect_size: float, power: float = 0.8, alpha: float = 0.05, ratio: float = 1.0) -> float:
    """Required n for group 1 (group 2 = ratio * n1) to detect Cohen's d =
    `effect_size` at the given alpha with the given power, two independent
    samples, two-sided t-test. Sign of `effect_size` doesn't matter.
    """
    from statsmodels.stats.power import TTestIndPower

    n = TTestIndPower().solve_power(effect_size=abs(effect_size), power=power, alpha=alpha, ratio=ratio, nobs1=None)
    return float(np.ceil(n))


def achieved_power_means(n1: float, effect_size: float, alpha: float = 0.05, ratio: float = 1.0) -> float:
    """Power achieved with `n1` in group 1 (group 2 = ratio * n1) to detect
    Cohen's d = `effect_size` at the given alpha, two-sided t-test.
    """
    from statsmodels.stats.power import TTestIndPower

    return float(TTestIndPower().solve_power(effect_size=abs(effect_size), nobs1=n1, alpha=alpha, ratio=ratio, power=None))


def required_n_proportions(p1: float, p2: float, power: float = 0.8, alpha: float = 0.05, ratio: float = 1.0) -> float:
    """Required n for group 1 to detect a difference between proportions
    p1 and p2 at the given alpha with the given power, two-sided z-test
    (via Cohen's h effect size, `statsmodels.stats.proportion.
    proportion_effectsize`).
    """
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    es = proportion_effectsize(p1, p2)
    n = NormalIndPower().solve_power(effect_size=abs(es), power=power, alpha=alpha, ratio=ratio, nobs1=None)
    return float(np.ceil(n))


def achieved_power_proportions(n1: float, p1: float, p2: float, alpha: float = 0.05, ratio: float = 1.0) -> float:
    """Power achieved with `n1` in group 1 to detect a difference between
    proportions p1 and p2 at the given alpha, two-sided z-test.
    """
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    es = proportion_effectsize(p1, p2)
    return float(NormalIndPower().solve_power(effect_size=abs(es), nobs1=n1, alpha=alpha, ratio=ratio, power=None))


def cohens_d(mean_a: float, std_a: float, n_a: int, mean_b: float, std_b: float, n_b: int) -> float:
    """Cohen's d between two groups using the standard pooled-standard-
    deviation formula. Returns 0.0 (rather than dividing by zero) if the
    pooled standard deviation is exactly zero (both groups perfectly
    constant).
    """
    pooled_var = ((n_a - 1) * std_a ** 2 + (n_b - 1) * std_b ** 2) / (n_a + n_b - 2)
    pooled_std = np.sqrt(pooled_var)
    if pooled_std == 0:
        return 0.0
    return float((mean_b - mean_a) / pooled_std)


def effect_size_from_means(
    df: pd.DataFrame, value_col: str, group_col: str,
    group_a=None, group_b=None, min_rows: int = _MIN_ROWS_PER_GROUP,
) -> dict:
    """Estimate Cohen's d for `value_col` between two levels of
    `group_col` — a pilot estimate for planning a *future* study's sample
    size, not a validity check on this data. If `group_a`/`group_b` aren't
    given, the column must have exactly 2 levels (auto-picked, sorted).

    Returns a dict, always with an "ok" key:
      ok=False: {"ok": False, "error"}
      ok=True:  {"ok": True, "cohens_d", "group_a", "group_b",
                 "mean_a", "std_a", "n_a", "mean_b", "std_b", "n_b"}
    Never raises.
    """
    for col, label in ((value_col, "Value"), (group_col, "Group")):
        if df is None or col not in df.columns:
            return {"ok": False, "error": f"{label} column '{col}' not found in the dataset."}
    if value_col == group_col:
        return {"ok": False, "error": "value_col and group_col must be different columns."}

    sub = df[[value_col, group_col]].dropna().copy()
    sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
    sub = sub.dropna(subset=[value_col])
    if sub.empty:
        return {"ok": False, "error": "No numeric data to estimate an effect size from."}

    levels = sorted(sub[group_col].dropna().unique().tolist(), key=str)
    if group_a is not None or group_b is not None:
        if group_a not in levels or group_b not in levels:
            return {"ok": False, "error": f"group_a/group_b must both be present levels of '{group_col}' ({levels})."}
    elif len(levels) == 2:
        group_a, group_b = levels[0], levels[1]
    else:
        return {"ok": False, "error": f"'{group_col}' has {len(levels)} levels — pass group_a/group_b to pick 2."}

    vals_a = sub.loc[sub[group_col] == group_a, value_col]
    vals_b = sub.loc[sub[group_col] == group_b, value_col]
    if len(vals_a) < min_rows or len(vals_b) < min_rows:
        return {"ok": False, "error": f"Not enough rows (need >= {min_rows} per group; have {len(vals_a)} and {len(vals_b)})."}

    mean_a, std_a, n_a = float(vals_a.mean()), float(vals_a.std(ddof=1)), int(len(vals_a))
    mean_b, std_b, n_b = float(vals_b.mean()), float(vals_b.std(ddof=1)), int(len(vals_b))
    d = cohens_d(mean_a, std_a, n_a, mean_b, std_b, n_b)

    return {
        "ok": True, "cohens_d": d, "group_a": group_a, "group_b": group_b,
        "mean_a": mean_a, "std_a": std_a, "n_a": n_a,
        "mean_b": mean_b, "std_b": std_b, "n_b": n_b,
    }


def _coerce_binary(series: pd.Series) -> Optional[pd.Series]:
    """Same convention as modules.bayesian_ab._coerce_binary — coerce an
    exactly-2-valued column to 0/1, preferring an obvious "success" value.
    """
    uniques = series.dropna().unique().tolist()
    if len(uniques) != 2:
        return None
    positive_aliases = {
        1, "1", True, "true", "yes", "y", "converted", "success", "purchase",
        "purchased", "clicked", "signed_up", "won", "win",
    }
    sorted_uniques = sorted(uniques, key=str)
    positive_value = next(
        (v for v in sorted_uniques if str(v).strip().lower() in positive_aliases or v in positive_aliases),
        sorted_uniques[-1],
    )
    return (series == positive_value).astype(int)


def effect_size_from_proportions(
    df: pd.DataFrame, success_col: str, group_col: str,
    group_a=None, group_b=None, min_rows: int = _MIN_ROWS_PER_GROUP,
) -> dict:
    """Estimate two group proportions (for `proportion_effectsize`) from
    `success_col` (a binary flag) across two levels of `group_col` — same
    pilot-estimate framing as effect_size_from_means. Returns a dict,
    always with an "ok" key:
      ok=False: {"ok": False, "error"}
      ok=True:  {"ok": True, "p_a", "p_b", "group_a", "group_b", "n_a", "n_b"}
    Never raises.
    """
    for col, label in ((success_col, "Outcome"), (group_col, "Group")):
        if df is None or col not in df.columns:
            return {"ok": False, "error": f"{label} column '{col}' not found in the dataset."}
    if success_col == group_col:
        return {"ok": False, "error": "success_col and group_col must be different columns."}

    sub = df[[success_col, group_col]].dropna().copy()
    if sub.empty:
        return {"ok": False, "error": "No data to estimate proportions from."}

    binary = _coerce_binary(sub[success_col])
    if binary is None:
        n_vals = sub[success_col].nunique()
        return {"ok": False, "error": f"Outcome column '{success_col}' must have exactly 2 values (found {n_vals})."}
    sub = sub.assign(_success=binary)

    levels = sorted(sub[group_col].dropna().unique().tolist(), key=str)
    if group_a is not None or group_b is not None:
        if group_a not in levels or group_b not in levels:
            return {"ok": False, "error": f"group_a/group_b must both be present levels of '{group_col}' ({levels})."}
    elif len(levels) == 2:
        group_a, group_b = levels[0], levels[1]
    else:
        return {"ok": False, "error": f"'{group_col}' has {len(levels)} levels — pass group_a/group_b to pick 2."}

    sub_a = sub.loc[sub[group_col] == group_a]
    sub_b = sub.loc[sub[group_col] == group_b]
    if len(sub_a) < min_rows or len(sub_b) < min_rows:
        return {"ok": False, "error": f"Not enough rows (need >= {min_rows} per group; have {len(sub_a)} and {len(sub_b)})."}

    return {
        "ok": True,
        "p_a": float(sub_a["_success"].mean()), "n_a": int(len(sub_a)), "group_a": group_a,
        "p_b": float(sub_b["_success"].mean()), "n_b": int(len(sub_b)), "group_b": group_b,
    }


def _build_power_curve(achieved_power_fn, required_n: float, n_points: int = _POWER_CURVE_POINTS) -> list[dict]:
    """Sweep n from a small floor up to ~2x the required n, computing
    achieved power at each point, for the power-curve chart.
    """
    ceiling = max(required_n * 2, required_n + 10)
    floor = max(2, required_n * 0.1)
    ns = sorted(set(int(round(x)) for x in np.linspace(floor, ceiling, n_points) if x >= 2))
    return [{"n": n, "power": achieved_power_fn(n)} for n in ns]


def auto_select_inputs(df: pd.DataFrame, column_types: dict[str, str]) -> Optional[dict]:
    """Best-guess pilot-data inputs for a zero-configuration invocation —
    e.g. Atlas's voice/typed "run a power analysis" command, which has no
    metric-type/column pickers to fall back on. Mirrors the Stats Lab UI's
    own column-eligibility rules (a numeric column + a 2-8-level group
    column for means; a 2-level outcome column + a 2-8-level group column
    for proportions), resolved to a single deterministic pick: means are
    preferred when both are available (matching the UI's own default
    "Means" radio selection), falling back to proportions.

    Returns a dict shaped either
    {"metric_type": "mean", "value_col": ..., "group_col": ...} or
    {"metric_type": "proportion", "success_col": ..., "group_col": ...},
    or None (never raises) when neither pairing exists — the caller should
    fall back to "navigate there and let the user configure it" rather
    than guess further. Pure function of `df`/`column_types`.
    """
    if df is None or df.empty or not column_types:
        return None
    group_candidates = [
        c for c in df.columns
        if column_types.get(c) in ("categorical", "text", "boolean") and 2 <= df[c].nunique(dropna=True) <= 8
    ]
    if not group_candidates:
        return None

    numeric_candidates = [c for c in df.columns if column_types.get(c) == "numeric"]
    for group_col in group_candidates:
        value_candidates = [c for c in numeric_candidates if c != group_col]
        if value_candidates:
            return {"metric_type": "mean", "value_col": value_candidates[0], "group_col": group_col}

    binary_candidates = [
        c for c in df.columns
        if column_types.get(c) in ("categorical", "text", "boolean") and df[c].nunique(dropna=True) == 2
    ]
    for group_col in group_candidates:
        success_candidates = [c for c in binary_candidates if c != group_col]
        if success_candidates:
            return {"metric_type": "proportion", "success_col": success_candidates[0], "group_col": group_col}

    return None


def _validate_common(alpha: float, mode: str) -> Optional[str]:
    if mode not in ("solve_n", "solve_power"):
        return f"mode must be 'solve_n' or 'solve_power' (got '{mode}')."
    if not (0 < alpha < 1):
        return "alpha must be between 0 and 1."
    return None


def plan_power_means(
    mode: str,
    effect_size_source: str = "manual",
    effect_size: Optional[float] = None,
    df: Optional[pd.DataFrame] = None,
    value_col: Optional[str] = None,
    group_col: Optional[str] = None,
    group_a=None, group_b=None,
    alpha: float = 0.05,
    target_power: float = 0.8,
    n_per_group: Optional[int] = None,
    ratio: float = 1.0,
) -> dict:
    """App-facing entry point for two-sample mean comparisons.
    `mode="solve_n"` computes the required n/group for `target_power`;
    `mode="solve_power"` computes achieved power at `n_per_group`.
    `effect_size_source="manual"` uses `effect_size` (Cohen's d) directly;
    `"data"` estimates it from `df`/`value_col`/`group_col` via
    effect_size_from_means() first (a pilot-data estimate).

    Returns a dict, always with an "ok" key. Never raises. ok=True adds
    (mode-dependent) "required_n_per_group"/"power_curve" or
    "achieved_power", plus "metric_type": "mean", "effect_size",
    "effect_size_source", and (if from data) a "pilot" sub-dict.
    """
    err = _validate_common(alpha, mode)
    if err:
        return {"ok": False, "error": err}
    if ratio <= 0:
        return {"ok": False, "error": "ratio must be positive."}

    pilot = None
    if effect_size_source == "data":
        if df is None or value_col is None or group_col is None:
            return {"ok": False, "error": "effect_size_source='data' needs df, value_col, and group_col."}
        pilot = effect_size_from_means(df, value_col, group_col, group_a, group_b)
        if not pilot["ok"]:
            return {"ok": False, "error": pilot["error"]}
        effect_size = pilot["cohens_d"]
    elif effect_size_source == "manual":
        if effect_size is None:
            return {"ok": False, "error": "effect_size_source='manual' needs an explicit effect_size (Cohen's d)."}
    else:
        return {"ok": False, "error": "effect_size_source must be 'manual' or 'data'."}

    if effect_size == 0:
        return {"ok": False, "error": "Effect size is 0 — no achievable sample size can detect a null effect."}

    result = {
        "ok": True, "metric_type": "mean", "mode": mode,
        "effect_size": float(effect_size), "effect_size_source": effect_size_source,
        "alpha": alpha, "ratio": ratio, "pilot": pilot,
    }

    if mode == "solve_n":
        if not (0 < target_power < 1):
            return {"ok": False, "error": "target_power must be between 0 and 1."}
        required_n = required_n_means(effect_size, target_power, alpha, ratio)
        result["target_power"] = target_power
        result["required_n_per_group"] = required_n
        result["required_n_total"] = int(np.ceil(required_n * (1 + ratio)))
        result["power_curve"] = _build_power_curve(lambda n: achieved_power_means(n, effect_size, alpha, ratio), required_n)
    else:
        if not n_per_group or n_per_group <= 1:
            return {"ok": False, "error": "solve_power mode needs n_per_group (an integer > 1)."}
        result["n_per_group"] = int(n_per_group)
        result["achieved_power"] = achieved_power_means(n_per_group, effect_size, alpha, ratio)
        result["power_curve"] = _build_power_curve(lambda n: achieved_power_means(n, effect_size, alpha, ratio), n_per_group)

    return result


def plan_power_proportions(
    mode: str,
    effect_size_source: str = "manual",
    p1: Optional[float] = None, p2: Optional[float] = None,
    df: Optional[pd.DataFrame] = None,
    success_col: Optional[str] = None,
    group_col: Optional[str] = None,
    group_a=None, group_b=None,
    alpha: float = 0.05,
    target_power: float = 0.8,
    n_per_group: Optional[int] = None,
    ratio: float = 1.0,
) -> dict:
    """App-facing entry point for two-sample proportion comparisons. Same
    mode/effect_size_source contract as plan_power_means(), but the effect
    size is a pair of proportions (p1, p2) instead of a Cohen's d. Returns
    a dict, always with an "ok" key; ok=True includes "metric_type":
    "proportion" plus the same mode-dependent fields as plan_power_means().
    Never raises.
    """
    err = _validate_common(alpha, mode)
    if err:
        return {"ok": False, "error": err}
    if ratio <= 0:
        return {"ok": False, "error": "ratio must be positive."}

    pilot = None
    if effect_size_source == "data":
        if df is None or success_col is None or group_col is None:
            return {"ok": False, "error": "effect_size_source='data' needs df, success_col, and group_col."}
        pilot = effect_size_from_proportions(df, success_col, group_col, group_a, group_b)
        if not pilot["ok"]:
            return {"ok": False, "error": pilot["error"]}
        p1, p2 = pilot["p_a"], pilot["p_b"]
    elif effect_size_source == "manual":
        if p1 is None or p2 is None:
            return {"ok": False, "error": "effect_size_source='manual' needs explicit p1 and p2."}
    else:
        return {"ok": False, "error": "effect_size_source must be 'manual' or 'data'."}

    if not (0 <= p1 <= 1) or not (0 <= p2 <= 1):
        return {"ok": False, "error": "p1 and p2 must both be between 0 and 1."}
    if p1 == p2:
        return {"ok": False, "error": "p1 and p2 are identical — no achievable sample size can detect a null effect."}

    result = {
        "ok": True, "metric_type": "proportion", "mode": mode,
        "p1": float(p1), "p2": float(p2), "effect_size_source": effect_size_source,
        "alpha": alpha, "ratio": ratio, "pilot": pilot,
    }

    if mode == "solve_n":
        if not (0 < target_power < 1):
            return {"ok": False, "error": "target_power must be between 0 and 1."}
        required_n = required_n_proportions(p1, p2, target_power, alpha, ratio)
        result["target_power"] = target_power
        result["required_n_per_group"] = required_n
        result["required_n_total"] = int(np.ceil(required_n * (1 + ratio)))
        result["power_curve"] = _build_power_curve(lambda n: achieved_power_proportions(n, p1, p2, alpha, ratio), required_n)
    else:
        if not n_per_group or n_per_group <= 1:
            return {"ok": False, "error": "solve_power mode needs n_per_group (an integer > 1)."}
        result["n_per_group"] = int(n_per_group)
        result["achieved_power"] = achieved_power_proportions(n_per_group, p1, p2, alpha, ratio)
        result["power_curve"] = _build_power_curve(lambda n: achieved_power_proportions(n, p1, p2, alpha, ratio), n_per_group)

    return result


def narrate_power_analysis(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one plan_power_means()/plan_power_proportions()
    result in plain English. Returns (narration, error) — never raises.
    Callers should cache the result rather than re-calling this on every
    rerun, same convention as every other narrate_* helper in the app.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    if result["metric_type"] == "mean":
        effect_txt = f"Cohen's d = {result['effect_size']:.3f}"
    else:
        effect_txt = f"proportions {result['p1']:.2%} vs {result['p2']:.2%}"

    if result["mode"] == "solve_n":
        outcome_txt = (
            f"Required sample size: {result['required_n_per_group']:.0f} per group "
            f"(target power {result['target_power']:.0%}, alpha {result['alpha']:.2f})."
        )
    else:
        outcome_txt = (
            f"With {result['n_per_group']} per group, achieved power = {result['achieved_power']:.1%} "
            f"(alpha {result['alpha']:.2f})."
        )

    prompt = (
        f"A statistical power/sample-size planning calculation was run for a {result['metric_type']} "
        f"comparison ({effect_txt}). {outcome_txt}\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what this number means "
        "for planning an experiment (why underpowering risks missing a real effect, why overpowering "
        "wastes data-collection time/cost) and how to use it. Do not repeat the raw numbers verbatim — "
        "focus on the practical planning decision. If asked to comment on whether an *already-collected* "
        "sample was 'strong enough', note briefly that power is a forward-looking planning tool, not a "
        "retroactive grade on a finished test."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
