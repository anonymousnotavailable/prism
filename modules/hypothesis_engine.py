"""
Hypothesis Engine — agentic hypothesis generation + real statistical
verification, on top of the existing Stats Lab.

generate_hypotheses() asks Gemini to propose N testable hypotheses about the
dataset ("X differs across groups of Y", "A and B are correlated"), each
naming two real columns and a plain-English rationale — falling back to a
rule-based generator (strongest numeric-numeric correlations + highest-spread
categorical-vs-numeric splits) when Gemini is unavailable or its JSON can't
be parsed, same fallback discipline as auto_analyst.generate_analysis_plan.

test_hypotheses() then runs every hypothesis through modules.stats_lab's
existing test-selection + execution pipeline — no Gemini in the verification
step, only in the proposal step, so a "confirmed" verdict is always backed by
a real p-value, not an LLM's opinion.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import numpy as np
import pandas as pd

from modules import stats_lab
from modules.ai_analyst import build_data_context, call_gemini

MAX_HYPOTHESES = 5
MIN_CARDINALITY_FOR_GROUPING = 2
MAX_CARDINALITY_FOR_GROUPING = 10

HYPOTHESIS_SYSTEM_PROMPT = (
    "You are a senior data analyst forming testable hypotheses about a pandas "
    "DataFrame called `df` before running any statistics. Given the dataframe's "
    "schema, a sample, and summary statistics, propose UP TO 5 specific, testable "
    "hypotheses. Each hypothesis MUST compare exactly two real columns from the "
    "schema below — never invent a column name. Return a JSON array; each element "
    "an object with keys \"statement\" (one plain-English sentence, e.g. \"Revenue "
    "differs meaningfully across regions\"), \"col_a\", \"col_b\" (exact column "
    "names), and \"rationale\" (one short sentence on why this pairing is worth "
    "testing). Return ONLY the JSON array, no prose, no markdown code fences."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _numeric_numeric_candidates(df: pd.DataFrame, numeric_cols: list[str], limit: int) -> list[dict]:
    """Strongest-|correlation| numeric pairs, as candidate hypotheses."""
    if len(numeric_cols) < 2:
        return []
    corr = df[numeric_cols].corr(numeric_only=True).abs()
    pairs = []
    seen = set()
    for col_a in numeric_cols:
        for col_b in numeric_cols:
            if col_a == col_b or (col_b, col_a) in seen:
                continue
            seen.add((col_a, col_b))
            value = corr.loc[col_a, col_b]
            if pd.isna(value):
                continue
            pairs.append((value, col_a, col_b))
    pairs.sort(key=lambda t: t[0], reverse=True)

    candidates = []
    for value, col_a, col_b in pairs[:limit]:
        candidates.append(
            {
                "statement": f"'{col_a}' and '{col_b}' are correlated.",
                "col_a": col_a,
                "col_b": col_b,
                "rationale": f"These are the two numeric columns with the strongest observed relationship (|r|~{value:.2f}).",
            }
        )
    return candidates


def _categorical_numeric_candidates(
    df: pd.DataFrame, categorical_cols: list[str], numeric_cols: list[str], limit: int
) -> list[dict]:
    """Highest-variance-of-group-means categorical-vs-numeric splits, as candidates."""
    if not categorical_cols or not numeric_cols:
        return []
    scored = []
    for cat_col in categorical_cols:
        n_unique = df[cat_col].dropna().nunique()
        if n_unique < MIN_CARDINALITY_FOR_GROUPING or n_unique > MAX_CARDINALITY_FOR_GROUPING:
            continue
        for num_col in numeric_cols:
            try:
                group_means = df.groupby(cat_col, observed=True)[num_col].mean()
            except Exception:
                continue
            spread = float(group_means.std())
            if pd.isna(spread):
                continue
            scored.append((spread, cat_col, num_col))
    scored.sort(key=lambda t: t[0], reverse=True)

    candidates = []
    for _spread, cat_col, num_col in scored[:limit]:
        candidates.append(
            {
                "statement": f"'{num_col}' differs meaningfully across groups of '{cat_col}'.",
                "col_a": num_col,
                "col_b": cat_col,
                "rationale": f"'{cat_col}' splits '{num_col}' into groups with the most spread-out means.",
            }
        )
    return candidates


def default_hypotheses(df: pd.DataFrame, column_types: dict[str, str], max_n: int = MAX_HYPOTHESES) -> list[dict]:
    """Rule-based hypothesis proposals, used when Gemini is unavailable — deterministic,
    always returns something usable as long as the dataset has 2+ testable columns.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]

    half = max(1, max_n // 2)
    candidates = _numeric_numeric_candidates(df, numeric_cols, half)
    candidates += _categorical_numeric_candidates(df, categorical_cols, numeric_cols, max_n - len(candidates))
    return candidates[:max_n]


def _validate_hypothesis(df: pd.DataFrame, hypothesis: dict) -> bool:
    col_a, col_b = hypothesis.get("col_a"), hypothesis.get("col_b")
    return (
        isinstance(col_a, str)
        and isinstance(col_b, str)
        and col_a != col_b
        and col_a in df.columns
        and col_b in df.columns
        and hypothesis.get("statement")
    )


def generate_hypotheses(model, df: pd.DataFrame, column_types: dict[str, str], max_n: int = MAX_HYPOTHESES) -> list[dict]:
    """Ask Gemini for testable hypotheses; always returns a usable, non-empty
    list (falls back to default_hypotheses on any error, bad JSON, or a
    response that names non-existent columns).
    """
    if model is None:
        return default_hypotheses(df, column_types, max_n)

    context = build_data_context(df, column_types)
    prompt = f"{HYPOTHESIS_SYSTEM_PROMPT}\n\nData context:\n{context}"
    text, error = call_gemini(model, prompt)
    if error:
        return default_hypotheses(df, column_types, max_n)

    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return default_hypotheses(df, column_types, max_n)

    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return default_hypotheses(df, column_types, max_n)

    cleaned = [h for h in raw if isinstance(h, dict) and _validate_hypothesis(df, h)][:max_n]
    return cleaned or default_hypotheses(df, column_types, max_n)


def test_hypotheses(df: pd.DataFrame, column_types: dict[str, str], hypotheses: list[dict]) -> list[dict]:
    """Run every hypothesis through stats_lab's real test-selection + execution
    pipeline. Each returned dict carries the original hypothesis fields plus
    "verdict" (one of "confirmed" / "not confirmed" / "untestable"),
    "narrative" (plain English), "warnings" (assumption-check strings), and
    the raw "result" dict from stats_lab for anything that needs the numbers.
    """
    verdicts = []
    for hypothesis in hypotheses:
        col_a, col_b = hypothesis["col_a"], hypothesis["col_b"]
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            verdicts.append(
                {**hypothesis, "verdict": "untestable", "narrative": suggestion["error"], "warnings": [], "result": None}
            )
            continue

        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            verdicts.append(
                {**hypothesis, "verdict": "untestable", "narrative": result["error"], "warnings": [], "result": None}
            )
            continue

        verdict = "confirmed" if result["p_value"] < 0.05 else "not confirmed"
        verdicts.append(
            {
                **hypothesis,
                "verdict": verdict,
                "narrative": stats_lab.interpret_result(result),
                "warnings": stats_lab.normality_warnings(result),
                "result": result,
            }
        )
    return verdicts
