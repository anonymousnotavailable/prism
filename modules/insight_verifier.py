"""
Insight Verifier — the statistical verification layer for Auto Analyst.

Auto Analyst's headline findings (modules.auto_analyst.synthesize_findings)
are LLM prose written over the results of LLM-generated pandas code —
useful, but not statistically tested: a "strong link between X and Y" claim
carries no p-value or effect size.

This module closes that gap WITHOUT parsing Gemini's free-text findings to
guess which columns they mention (brittle, and wrong when the LLM paraphrases
a column name). Instead it independently re-derives the dataset's most
notable relationships straight from the dataframe — the strongest numeric
correlations, the categorical splits with the widest group-mean spread — and
routes each one through modules.stats_lab's existing test suite (t-test /
ANOVA / chi-square / Pearson), exactly the same tests a user would get by
hand-picking those columns in the Stats Lab tab.

Deliberately has no Gemini dependency at all: it's pure pandas/numpy/scipy
via stats_lab, so it costs nothing against the free-tier quota and still
works when Gemini is rate-limited or unavailable.
"""

from __future__ import annotations

import pandas as pd

from modules import stats_lab

MAX_VERIFIED_FINDINGS = 5

# How many correlation / group-split candidates to *test* before ranking and
# truncating to max_findings — wider than max_findings so a couple of
# failed/degenerate tests (e.g. all-NaN column) don't leave the final list short.
_CANDIDATE_POOL_MULTIPLIER = 2


def _top_correlation_pairs(df: pd.DataFrame, numeric_cols: list[str], top_n: int) -> list[tuple[str, str]]:
    """Numeric column pairs with the largest |Pearson r|, strongest first."""
    if len(numeric_cols) < 2:
        return []

    corr = df[numeric_cols].corr(numeric_only=True).abs()
    cols = corr.columns.tolist()
    pairs = []
    for i, col_a in enumerate(cols):
        for col_b in cols[i + 1 :]:
            value = corr.loc[col_a, col_b]
            if pd.isna(value):
                continue
            pairs.append((col_a, col_b, value))

    pairs.sort(key=lambda t: t[2], reverse=True)
    return [(a, b) for a, b, _ in pairs[:top_n]]


def _top_categorical_numeric_pairs(
    df: pd.DataFrame, column_types: dict[str, str], top_n: int
) -> list[tuple[str, str]]:
    """Categorical/numeric pairs whose group means vary the most — a cheap
    proxy (coefficient of variation of group means) for "this group split
    probably matters", run before the actual t-test/ANOVA confirms it.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]

    candidates = []
    for cat_col in categorical_cols:
        n_groups = df[cat_col].dropna().nunique()
        if n_groups < 2 or n_groups > stats_lab.MAX_GROUPS_FOR_TEST:
            continue
        for num_col in numeric_cols:
            group_means = df.groupby(cat_col)[num_col].mean().dropna()
            if len(group_means) < 2:
                continue
            center = group_means.mean()
            spread = group_means.std()
            if center == 0 or pd.isna(spread):
                continue
            candidates.append((cat_col, num_col, abs(spread / center)))

    candidates.sort(key=lambda t: t[2], reverse=True)
    return [(cat, num) for cat, num, _ in candidates[:top_n]]


def verify_relationships(
    df: pd.DataFrame, column_types: dict[str, str], max_findings: int = MAX_VERIFIED_FINDINGS
) -> list[dict]:
    """Find the dataset's most notable relationships and statistically test each one.

    Returns a list of dicts (ranked significant-first, then by effect size),
    each shaped:
        col_a, col_b       — the two columns tested
        reason             — why stats_lab picked this test (one line)
        test, test_label   — e.g. "pearson", "Pearson correlation significance"
        p_value            — from scipy.stats
        significant        — p_value < 0.05
        effect_size, effect_size_label
        verdict            — stats_lab.interpret_result(), plain English
        warnings           — stats_lab.normality_warnings(), assumption checks

    Never raises: a candidate pair that fails to test cleanly (too few rows,
    degenerate groups, etc.) is skipped rather than propagated. Returns []
    when the data has nothing testable — that's a valid outcome, not an error.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    pool_size = max_findings * _CANDIDATE_POOL_MULTIPLIER

    candidate_pairs = _top_correlation_pairs(df, numeric_cols, pool_size)
    candidate_pairs += _top_categorical_numeric_pairs(df, column_types, pool_size)

    findings = []
    for col_a, col_b in candidate_pairs:
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            continue
        findings.append(
            {
                "col_a": col_a,
                "col_b": col_b,
                "reason": suggestion["reason"],
                "test": result["test"],
                "test_label": stats_lab.TEST_LABELS[result["test"]],
                "p_value": result["p_value"],
                "significant": result["p_value"] < 0.05,
                "effect_size": result["effect_size"],
                "effect_size_label": result["effect_size_label"],
                "verdict": stats_lab.interpret_result(result),
                "warnings": stats_lab.normality_warnings(result),
            }
        )

    findings.sort(key=lambda f: (not f["significant"], -abs(f["effect_size"])))
    return findings[:max_findings]
