"""
Hypothesis Engine — the agentic "what should I even be testing?" layer on
top of Stats Lab. Stats Lab is guided: it requires the user to already know
which two columns to compare. This module is autonomous: it scans every
plausible column pair in the dataset, ranks them with a cheap deterministic
pre-screen (no real test is run until a pair clears that screen — this is
what keeps a wide dataset from triggering hundreds of scipy calls), runs the
strongest candidates through modules.stats_lab's real significance tests,
and returns ranked, *tested* hypotheses — a plain-English claim, the
evidence, and a verdict — not just a chart waiting for a human to interpret it.

Deliberately mirrors modules.autocleaner's SAFE/REVIEW split in spirit: the
screening score is only ever used to pick *which* pairs are worth a real
test and to order the output — it never decides "significant" on its own.
Every verdict in the returned list comes from an actual scipy test via
stats_lab, so this module works correctly, and is fully explainable, with
zero Gemini API key configured. An optional Gemini pass (narrate_with_gemini)
can turn the ranked list into a short prose summary, but it's cosmetic —
never the source of the statistics themselves.
"""

from __future__ import annotations

import itertools
from typing import Optional

import pandas as pd

from modules import stats_lab

# Beyond this many categories a column stops being useful as a "group by"
# axis for a hypothesis (same ceiling stats_lab.suggest_test enforces).
MAX_CATEGORICAL_CARDINALITY = 10

# A pair needs at least this many non-null paired rows before it's worth
# screening at all — below this, any statistic is noise.
MIN_ROWS_FOR_SCREEN = 4

# Hard cap on how many pre-screened pairs get promoted to a real scipy test,
# so a very wide dataset (100s of columns) can't blow up runtime — this is
# a performance ceiling, not a quality judgment, and is always applied
# *after* sorting by screen score so the strongest candidates go first.
MAX_PAIRS_TESTED = 40

# How many tested hypotheses are handed back to the caller.
MAX_HYPOTHESES_RETURNED = 6

SIGNIFICANCE_ALPHA = 0.05

_NARRATION_PROMPT_TEMPLATE = (
    "You are a senior data analyst. Below are statistically tested hypotheses about a "
    "dataset, each with a p-value and effect size already computed. Write a short, "
    "confident summary (3-5 sentences, plain English, no markdown headers) of what the "
    "significant findings suggest together. Reference concrete numbers already given "
    "below — do not invent any. If none are significant, say so plainly.\n\n{findings}"
)


def _numeric_categorical_score(df: pd.DataFrame, numeric_col: str, cat_col: str) -> Optional[float]:
    """Cheap eta-squared preview: between-group variance / total variance,
    computed from group means only — the same quantity run_anova() derives
    properly, but here it's a ranking signal, not a claim.
    """
    clean = df[[numeric_col, cat_col]].dropna()
    if len(clean) < MIN_ROWS_FOR_SCREEN:
        return None
    groups = clean.groupby(cat_col, observed=True)[numeric_col]
    sizes = groups.size()
    if (sizes >= 2).sum() < 2:
        return None
    total_var = clean[numeric_col].var()
    if not total_var or pd.isna(total_var) or total_var <= 0:
        return None
    grand_mean = clean[numeric_col].mean()
    between = ((groups.mean() - grand_mean) ** 2 * sizes).sum() / sizes.sum()
    return float(between / total_var)


def _categorical_categorical_score(df: pd.DataFrame, col_a: str, col_b: str) -> Optional[float]:
    """Cheap association preview: a chi-square-shaped statistic normalized
    by sample size (monotonic with, but cheaper than, Cramer's V).
    """
    clean = df[[col_a, col_b]].dropna()
    if len(clean) < MIN_ROWS_FOR_SCREEN:
        return None
    table = pd.crosstab(clean[col_a], clean[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return None
    row_sums = table.sum(axis=1).to_numpy()[:, None]
    col_sums = table.sum(axis=0).to_numpy()[None, :]
    total = table.to_numpy().sum()
    if total == 0:
        return None
    expected = row_sums @ col_sums / total
    expected = expected.astype(float)
    expected[expected == 0] = 1e-9
    chi2_like = (((table.to_numpy() - expected) ** 2) / expected).sum()
    return float(chi2_like / total)


def _numeric_numeric_score(df: pd.DataFrame, col_a: str, col_b: str) -> Optional[float]:
    clean = df[[col_a, col_b]].dropna()
    if len(clean) < MIN_ROWS_FOR_SCREEN:
        return None
    r = clean[col_a].corr(clean[col_b])
    if pd.isna(r):
        return None
    return float(abs(r))


def _hypothesis_statement(kind: str, col_a: str, col_b: str) -> str:
    if kind == "numeric_categorical":
        return f"'{col_a}' differs meaningfully across the groups of '{col_b}'."
    if kind == "categorical_categorical":
        return f"'{col_a}' and '{col_b}' are associated, not independent."
    return f"'{col_a}' and '{col_b}' are linearly correlated."


def _eligible_categorical_cols(df: pd.DataFrame, column_types: dict[str, str]) -> list[str]:
    cols = []
    for col, dtype in column_types.items():
        if dtype != "categorical":
            continue
        nunique = df[col].dropna().nunique()
        if 2 <= nunique <= MAX_CATEGORICAL_CARDINALITY:
            cols.append(col)
    return cols


def generate_hypotheses(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Scan column pairs, pre-screen cheaply, run the strongest candidates
    through Stats Lab's real tests, and return ranked, tested hypotheses.

    Returns a list of dicts (possibly empty), each with:
      statement, kind, col_a, col_b, screen_score, suggestion (stats_lab.suggest_test
      output), result (stats_lab.run_test output), verdict ("supported"/"not supported"),
      interpretation (plain English), warnings (assumption-check caveats).

    Never raises. A pair that can't actually be tested (too few rows once
    NaNs drop, degenerate groups, ...) is skipped rather than surfaced as an
    error — this function only reports hypotheses it could actually test.
    """
    if df is None or df.empty:
        return []

    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = _eligible_categorical_cols(df, column_types)

    candidates: list[tuple[float, str, str, str]] = []
    for num_col in numeric_cols:
        for cat_col in categorical_cols:
            score = _numeric_categorical_score(df, num_col, cat_col)
            if score is not None:
                candidates.append((score, "numeric_categorical", num_col, cat_col))

    for col_a, col_b in itertools.combinations(categorical_cols, 2):
        score = _categorical_categorical_score(df, col_a, col_b)
        if score is not None:
            candidates.append((score, "categorical_categorical", col_a, col_b))

    for col_a, col_b in itertools.combinations(numeric_cols, 2):
        score = _numeric_numeric_score(df, col_a, col_b)
        if score is not None:
            candidates.append((score, "numeric_numeric", col_a, col_b))

    if not candidates:
        return []

    candidates.sort(key=lambda c: c[0], reverse=True)
    candidates = candidates[:MAX_PAIRS_TESTED]

    hypotheses = []
    for score, kind, col_a, col_b in candidates:
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            continue

        verdict = "supported" if result["p_value"] < SIGNIFICANCE_ALPHA else "not supported"
        hypotheses.append(
            {
                "statement": _hypothesis_statement(kind, col_a, col_b),
                "kind": kind,
                "col_a": col_a,
                "col_b": col_b,
                "screen_score": score,
                "suggestion": suggestion,
                "result": result,
                "verdict": verdict,
                "interpretation": stats_lab.interpret_result(result),
                "warnings": stats_lab.normality_warnings(result),
            }
        )
        if len(hypotheses) >= MAX_HYPOTHESES_RETURNED:
            break

    # Strongest evidence first: significant results before non-significant
    # ones, then by p-value ascending within each group.
    hypotheses.sort(key=lambda h: (h["verdict"] != "supported", h["result"]["p_value"]))
    return hypotheses


def narrate_headline(hypotheses: list[dict]) -> str:
    """Deterministic, no-LLM-required one-liner — works with zero Gemini API
    key configured, same guarantee Auto Cleaner's narration makes.
    """
    if not hypotheses:
        return "No testable hypotheses found — not enough numeric/categorical columns with suitable cardinality."
    supported = [h for h in hypotheses if h["verdict"] == "supported"]
    if not supported:
        return f"Tested {len(hypotheses)} hypothesis(es); none reached statistical significance (p<0.05)."
    lead = supported[0]
    return (
        f"Tested {len(hypotheses)} hypothesis(es), {len(supported)} significant. "
        f"Strongest: {lead['statement']} {lead['interpretation']}"
    )


def narrate_with_gemini(model, hypotheses: list[dict]) -> tuple[str, Optional[str]]:
    """Optional prose summary via Gemini, layered on top of narrate_headline.

    Purely cosmetic — the statistics and verdicts above are already final
    before this is ever called. Reuses modules.ai_analyst.call_gemini so
    this gets the same per-session rate limiting, quota-exhaustion, and
    auth-error handling as every other Gemini call in the app for free.
    Returns (text, error); callers should fall back to narrate_headline()
    on error rather than surface a blank section.
    """
    if not hypotheses:
        return "", "No hypotheses to narrate."
    if model is None:
        return "", "No Gemini API key configured — showing the deterministic summary instead."

    from modules.ai_analyst import call_gemini  # local import: avoids a hard circular dep at module load,
    # and — as important — means calling this with an empty list never even touches google-generativeai.

    lines = []
    for h in hypotheses:
        lines.append(f"- {h['statement']} -> {h['interpretation']} [{h['verdict']}]")
    prompt = _NARRATION_PROMPT_TEMPLATE.format(findings="\n".join(lines))
    return call_gemini(model, prompt)
