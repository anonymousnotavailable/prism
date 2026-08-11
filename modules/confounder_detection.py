"""
Confounder / Simpson's Paradox Detection — automatically stress-tests the
strong correlations Auto-Insights already found by stratifying (categorical
confounders) or partialling out (numeric confounders) every other column in
the dataset, and flags when the relationship reverses sign or collapses
once you control for a third variable.

Why this exists: a pooled Pearson correlation can be actively misleading —
the textbook case is Simpson's Paradox, where a relationship that's
negative within every subgroup looks positive once the subgroups are
pooled together (or vice versa), because the subgroups differ on some
other variable that's driving both x and y. Auto-Insights (modules/
auto_insights.py) already surfaces "these two columns correlate" as a
finding; this module is the agentic follow-up question a careful analyst
asks next — "...but does that hold up once I control for group?" — run
automatically, not on request.

Everything here is deterministic (pandas/numpy correlation arithmetic) —
no Gemini call is required to detect a paradox. narrate_confounder_finding()
is an optional plain-English interpretation layer on top, following the
same call_gemini() plumbing (and graceful no-model fallback) as every other
narration helper in the app; callers are responsible for caching its result
per finding, same convention as modules.anomaly's narrate_* functions.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# "Worth reporting" thresholds. Kept as module constants (not buried magic
# numbers) since three different call paths reuse them and a future run
# tuning sensitivity should only need to touch one place.
_SIGN_FLIP_MIN_ADJUSTED_R = 0.2   # the adjusted relationship must itself be non-trivial to call it a "paradox"
_SIGN_FLIP_MIN_OVERALL_R = 0.05   # ...and the pooled number must be a real (non-noise) correlation too
_ATTENUATION_MIN_OVERALL_R = 0.3  # only worth flagging attenuation if the pooled correlation looked meaningful
_ATTENUATION_RATIO = 0.5          # adjusted_r shrinking below this fraction of overall_r counts as "attenuated"
_HETEROGENEITY_R_RANGE = 0.5      # per-group correlations spanning more than this counts as "attenuated" even if the weighted average looks stable


def _verdict_from_r_pair(overall_r: float, adjusted_r: float) -> str:
    """Shared paradox/attenuation/robust classification given a pooled
    correlation and its confounder-adjusted counterpart (weighted
    within-group correlation, or a partial correlation)."""
    if overall_r is None or adjusted_r is None or pd.isna(overall_r) or pd.isna(adjusted_r):
        return "robust"
    sign_flip = (overall_r > 0 > adjusted_r) or (overall_r < 0 < adjusted_r)
    if sign_flip and abs(adjusted_r) >= _SIGN_FLIP_MIN_ADJUSTED_R and abs(overall_r) >= _SIGN_FLIP_MIN_OVERALL_R:
        return "paradox"
    if abs(overall_r) >= _ATTENUATION_MIN_OVERALL_R and abs(adjusted_r) < _ATTENUATION_RATIO * abs(overall_r):
        return "attenuated"
    return "robust"


def stratified_correlation(
    df: pd.DataFrame, x: str, y: str, group_col: str, min_group_size: int = 3
) -> Optional[dict]:
    """Pearson correlation of (x, y) computed separately within each level
    of `group_col`, plus the n-weighted pooled-within-group average, and a
    verdict comparing that to the plain overall correlation.

    Returns None when there aren't at least two groups with >= min_group_size
    non-null, non-constant (x, y) pairs to compare — nothing to stratify.
    """
    sub = df[[x, y, group_col]].dropna()
    if sub.empty:
        return None

    per_group = []
    excluded = 0
    for name, gdf in sub.groupby(group_col, observed=True):
        if len(gdf) < min_group_size or gdf[x].std(ddof=0) == 0 or gdf[y].std(ddof=0) == 0:
            excluded += 1
            continue
        r = gdf[x].corr(gdf[y])
        if pd.isna(r):
            excluded += 1
            continue
        per_group.append({"group": name, "r": float(r), "n": int(len(gdf))})

    if len(per_group) < 2:
        return None

    total_n = sum(g["n"] for g in per_group)
    weighted_r = sum(g["r"] * g["n"] for g in per_group) / total_n
    overall_r = sub[x].corr(sub[y])
    if pd.isna(overall_r):
        return None

    r_range = max(g["r"] for g in per_group) - min(g["r"] for g in per_group)
    verdict = _verdict_from_r_pair(overall_r, weighted_r)
    if verdict == "robust" and r_range >= _HETEROGENEITY_R_RANGE:
        # Same sign, similar pooled magnitude, but the subgroups don't agree
        # with each other — the pooled number is an average of genuinely
        # different relationships, which is its own kind of misleading.
        verdict = "attenuated"

    return {
        "overall_r": float(overall_r),
        "weighted_within_group_r": float(weighted_r),
        "per_group": sorted(per_group, key=lambda g: -g["n"]),
        "verdict": verdict,
        "excluded_small_groups": excluded,
    }


def partial_correlation(df: pd.DataFrame, x: str, y: str, control: str) -> Optional[float]:
    """First-order partial correlation of x and y controlling for a third
    numeric column, via the standard closed-form:

        r_xy.z = (r_xy - r_xz * r_yz) / sqrt((1 - r_xz^2) * (1 - r_yz^2))

    Returns None when there's too little data, or x/control (or y/control)
    are collinear enough that the denominator is ~0 (the partial correlation
    is undefined — controlling for something that IS x, or a perfect linear
    function of it, leaves no independent variation to correlate with y).
    """
    sub = df[[x, y, control]].dropna()
    if len(sub) < 4:
        return None
    r_xy = sub[x].corr(sub[y])
    r_xz = sub[x].corr(sub[control])
    r_yz = sub[y].corr(sub[control])
    if any(pd.isna(v) for v in (r_xy, r_xz, r_yz)):
        return None
    denom = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))
    if not np.isfinite(denom) or denom < 1e-6:
        return None
    partial = (r_xy - r_xz * r_yz) / denom
    return float(np.clip(partial, -1.0, 1.0))


def detect_confounders(
    df: pd.DataFrame,
    x: str,
    y: str,
    column_types: dict,
    candidates: Optional[list] = None,
    min_group_size: int = 3,
    max_categorical_groups: int = 15,
    min_numeric_rows: int = 10,
) -> list[dict]:
    """Check every other column in the dataset as a candidate confounder for
    the (x, y) relationship — stratification for categorical/text/boolean
    columns, partial correlation for numeric ones. Returns a list of finding
    dicts (possibly empty), ranked worst-first: paradox > attenuated >
    robust, and within a tier by how much the adjustment moved the number.

    Each finding: {confounder, type ("categorical"|"numeric"), overall_r,
    adjusted_r, verdict, detail}. `detail` is the per-group breakdown for
    categorical confounders, or {"n": ...} for numeric ones.
    """
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        return []

    if candidates is None:
        candidates = [c for c in df.columns if c not in (x, y)]

    findings = []
    for col in candidates:
        if col not in df.columns or col not in column_types:
            continue
        ctype = column_types[col]
        if ctype in ("categorical", "text", "boolean"):
            nunique = df[col].nunique(dropna=True)
            if nunique < 2 or nunique > max_categorical_groups:
                continue
            result = stratified_correlation(df, x, y, col, min_group_size=min_group_size)
            if result is None:
                continue
            findings.append(
                {
                    "confounder": col,
                    "type": "categorical",
                    "overall_r": result["overall_r"],
                    "adjusted_r": result["weighted_within_group_r"],
                    "verdict": result["verdict"],
                    "detail": result["per_group"],
                }
            )
        elif ctype == "numeric":
            sub = df[[x, y, col]].dropna()
            if len(sub) < min_numeric_rows:
                continue
            overall_r = sub[x].corr(sub[y])
            if pd.isna(overall_r):
                continue
            partial_r = partial_correlation(sub, x, y, col)
            if partial_r is None:
                continue
            findings.append(
                {
                    "confounder": col,
                    "type": "numeric",
                    "overall_r": float(overall_r),
                    "adjusted_r": partial_r,
                    "verdict": _verdict_from_r_pair(overall_r, partial_r),
                    "detail": {"n": int(len(sub))},
                }
            )

    severity = {"paradox": 0, "attenuated": 1, "robust": 2}
    findings.sort(key=lambda f: (severity.get(f["verdict"], 3), -abs(f["overall_r"] - f["adjusted_r"])))
    return findings


def auto_scan_for_confounding(
    df: pd.DataFrame,
    column_types: dict,
    correlation_pairs: Optional[list] = None,
    top_k_pairs: int = 3,
    min_abs_r: float = 0.3,
    min_rows: int = 6,
) -> list[dict]:
    """The agentic entry point — no pair needs to be hinted. Picks the
    strongest numeric/numeric correlation pairs in the dataset (or reuses
    ones a caller already computed, e.g. Auto-Insights' correlation
    findings, via `correlation_pairs=[(a, b, r), ...]`) and runs
    detect_confounders on each, keeping only pairs where at least one
    candidate confounder came back non-"robust".

    Returns [{x, y, overall_r, findings: [...]}] — empty when nothing in
    the dataset is worth a second look, which is the common/healthy case.
    """
    if df is None or df.empty:
        return []
    numeric_cols = [c for c, t in column_types.items() if t == "numeric" and c in df.columns]
    if len(numeric_cols) < 2:
        return []

    if correlation_pairs is None:
        corr = df[numeric_cols].corr(numeric_only=True)
        pairs = []
        for i, a in enumerate(numeric_cols):
            for b in numeric_cols[i + 1 :]:
                r = corr.loc[a, b]
                if pd.isna(r) or abs(r) < min_abs_r:
                    continue
                pairs.append((a, b, float(r)))
        pairs.sort(key=lambda p: -abs(p[2]))
        correlation_pairs = pairs[:top_k_pairs]
    else:
        correlation_pairs = list(correlation_pairs)[:top_k_pairs]

    results = []
    for a, b, r in correlation_pairs:
        if a not in df.columns or b not in df.columns:
            continue
        sub = df[[a, b]].dropna()
        if len(sub) < min_rows:
            continue
        findings = [f for f in detect_confounders(df, a, b, column_types) if f["verdict"] != "robust"][:2]
        if findings:
            results.append({"x": a, "y": b, "overall_r": float(r), "findings": findings})
    return results


_VERDICT_LABELS = {
    "paradox": "a possible Simpson's Paradox",
    "attenuated": "a weakened or confounded relationship",
}


def narrate_confounder_finding(model, x: str, y: str, finding: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one detect_confounders() finding in plain
    English. Returns (narration, error) — never raises. Callers should
    cache the result (e.g. keyed by (x, y, finding['confounder'])) rather
    than re-calling this on every rerun, same convention as the app's other
    narrate_* helpers.
    """
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    verdict_label = _VERDICT_LABELS.get(finding["verdict"], "a checked relationship")
    if finding["type"] == "categorical":
        detail_lines = "\n".join(f"- {g['group']}: r = {g['r']:.2f} (n={g['n']})" for g in finding["detail"])
        detail_block = f"Within-group correlations when split by '{finding['confounder']}':\n{detail_lines}"
    else:
        detail_block = f"Partial correlation of '{x}' and '{y}' controlling for '{finding['confounder']}': {finding['adjusted_r']:.2f}"

    prompt = (
        f"A data analysis tool found {verdict_label} between '{x}' and '{y}'.\n"
        f"Overall (pooled) correlation: {finding['overall_r']:.2f}\n"
        f"{detail_block}\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what this means "
        "and why the pooled correlation alone would be misleading here. Do not repeat raw numbers "
        "verbatim — focus on the practical interpretation and what to check next."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
