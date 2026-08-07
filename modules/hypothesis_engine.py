"""
Hypothesis Engine — a self-verifying analysis agent, not a chatty one.

Two-stage design deliberately kept independent enough to unit-test without
Gemini or a browser:

    generate_hypotheses() proposes candidate, falsifiable statements about
    the active dataset — via Gemini when a model + quota are available,
    always falling back to heuristic_hypotheses(), a deterministic ranking
    by |Pearson r| (numeric/numeric) and between-group variance (categorical/
    numeric) that needs no API key at all.

    verify_hypotheses() never trusts either source's claim at face value —
    every hypothesis is dispatched straight into Stats Lab's suggest_test()/
    run_test() (the same scipy.stats machinery the Stats Lab tab uses) and
    classified CONFIRMED / NOT CONFIRMED purely from the p-value that comes
    back, or INCONCLUSIVE if the columns don't support a real test. Gemini
    only ever proposes *what* to check; a real statistical test decides the
    verdict.

run_hypothesis_engine() wires both stages together for the UI.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd

from modules import stats_lab
from modules.ai_analyst import build_data_context, call_gemini

# Mirror Stats Lab's own cardinality ceiling so a categorical column that
# Stats Lab would refuse never gets proposed as a hypothesis in the first place.
MAX_GROUPS = stats_lab.MAX_GROUPS_FOR_TEST
SIGNIFICANCE_ALPHA = 0.05

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

_GENERATION_PROMPT = (
    "You are a senior data analyst proposing testable hypotheses about a pandas "
    "DataFrame `df`, given its schema, a sample, and summary statistics below. "
    "Propose up to {n} specific, falsifiable hypotheses, each comparing or "
    "relating EXACTLY TWO existing columns — never invent a column name that "
    "isn't in the schema. Return ONLY a JSON array, no prose, no markdown code "
    "fences. Each element is an object with keys \"statement\" (one plain-"
    "English sentence a data analyst would say aloud, e.g. \"Revenue differs "
    "meaningfully by region\"), \"col_a\", and \"col_b\" (must exactly match "
    "column names from the schema, case-sensitive)."
)


def heuristic_hypotheses(df: pd.DataFrame, column_types: dict[str, str], max_hypotheses: int = 5) -> list[dict]:
    """Deterministic candidate ranking, used whenever Gemini isn't available
    or its output can't be parsed into real column references.

    Ranks numeric/numeric pairs by |Pearson r| and categorical/numeric pairs
    by a quick between-group mean spread (relative to the column's overall
    std) — cheap proxies for "worth testing", not a test result themselves.
    verify_hypotheses() runs the actual significance test afterward; this
    function only decides what order to test things in, so it can't leak a
    p-value into its own ranking.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric" and c in df.columns]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical" and c in df.columns]

    candidates: list[tuple[float, str, str, str]] = []

    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1 :]:
            paired = df[[col_a, col_b]].dropna()
            if len(paired) < 3:
                continue
            corr = paired[col_a].corr(paired[col_b])
            if pd.isna(corr):
                continue
            candidates.append((abs(corr), f"'{col_a}' and '{col_b}' are correlated", col_a, col_b))

    for cat in categorical_cols:
        n_groups = df[cat].dropna().nunique()
        if n_groups < 2 or n_groups > MAX_GROUPS:
            continue
        for num in numeric_cols:
            paired = df[[cat, num]].dropna()
            if paired.empty:
                continue
            group_means = paired.groupby(cat)[num].mean()
            overall_std = paired[num].std()
            if not overall_std or pd.isna(overall_std):
                continue
            spread = (group_means.max() - group_means.min()) / overall_std
            candidates.append((float(spread), f"'{num}' differs across '{cat}' groups", cat, num))

    for i, col_a in enumerate(categorical_cols):
        for col_b in categorical_cols[i + 1 :]:
            n_a, n_b = df[col_a].dropna().nunique(), df[col_b].dropna().nunique()
            if 2 <= n_a <= MAX_GROUPS and 2 <= n_b <= MAX_GROUPS:
                candidates.append((0.0, f"'{col_a}' and '{col_b}' are related", col_a, col_b))

    candidates.sort(key=lambda c: c[0], reverse=True)

    seen: set = set()
    hypotheses = []
    for _, statement, col_a, col_b in candidates:
        key = frozenset((col_a, col_b))
        if key in seen:
            continue
        seen.add(key)
        hypotheses.append({"statement": statement, "col_a": col_a, "col_b": col_b})
        if len(hypotheses) >= max_hypotheses:
            break
    return hypotheses


def _parse_gemini_hypotheses(text: str, valid_columns: set) -> Optional[list[dict]]:
    """Parse Gemini's JSON array response, dropping any hypothesis that
    references a column name it hallucinated. Returns None (not []) when
    the response isn't parseable JSON at all, so the caller can tell "Gemini
    said nothing usable" apart from "Gemini's hypotheses all referenced bad
    columns" — both fall back to the heuristic, but the distinction matters
    for testing this function in isolation.
    """
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return None
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list):
        return None

    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        statement, col_a, col_b = item.get("statement"), item.get("col_a"), item.get("col_b")
        if not statement or not col_a or not col_b or col_a == col_b:
            continue
        if col_a not in valid_columns or col_b not in valid_columns:
            continue
        cleaned.append({"statement": str(statement), "col_a": str(col_a), "col_b": str(col_b)})
    return cleaned


def generate_hypotheses(model, df: pd.DataFrame, column_types: dict[str, str], max_hypotheses: int = 5) -> dict:
    """Propose candidate hypotheses. Always returns a usable list — Gemini
    is an enhancement, never a hard dependency, matching every other
    agentic flow in this app (Auto Analyst, Atlas).

    Returns {"hypotheses": [...], "source": "gemini"|"heuristic", "error": Optional[str]}.
    "error" is only ever a surfaced-for-display Gemini error (e.g. rate limit);
    it is never set just because the heuristic path was used by design.
    """
    heuristic = heuristic_hypotheses(df, column_types, max_hypotheses)
    if model is None or not heuristic:
        return {"hypotheses": heuristic, "source": "heuristic", "error": None}

    context = build_data_context(df, column_types)
    prompt = _GENERATION_PROMPT.format(n=max_hypotheses) + f"\n\nData context:\n{context}"
    text, error = call_gemini(model, prompt)
    if error:
        return {"hypotheses": heuristic, "source": "heuristic", "error": error}

    valid_columns = set(column_types.keys()) & set(df.columns)
    parsed = _parse_gemini_hypotheses(text, valid_columns)
    if not parsed:
        return {"hypotheses": heuristic, "source": "heuristic", "error": None}
    return {"hypotheses": parsed[:max_hypotheses], "source": "gemini", "error": None}


def verify_hypotheses(df: pd.DataFrame, column_types: dict[str, str], hypotheses: list[dict]) -> list[dict]:
    """Statistically verify each hypothesis via Stats Lab's own test
    machinery. Never marks anything CONFIRMED off a model's say-so — only
    off a real p-value this function computed.
    """
    results = []
    for hyp in hypotheses:
        col_a, col_b = hyp.get("col_a"), hyp.get("col_b")
        base = {"statement": hyp.get("statement", ""), "col_a": col_a, "col_b": col_b}

        if col_a not in df.columns or col_b not in df.columns:
            results.append({**base, "verdict": "INCONCLUSIVE", "error": "Column not found in the active dataset.", "p_value": None})
            continue

        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            results.append({**base, "verdict": "INCONCLUSIVE", "error": suggestion["error"], "p_value": None})
            continue

        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            results.append({**base, "verdict": "INCONCLUSIVE", "error": result["error"], "p_value": None})
            continue

        p_value = result["p_value"]
        verdict = "CONFIRMED" if p_value < SIGNIFICANCE_ALPHA else "NOT CONFIRMED"
        results.append(
            {
                **base,
                "verdict": verdict,
                "error": None,
                "test": result["test"],
                "test_label": stats_lab.TEST_LABELS.get(result["test"], result["test"]),
                "p_value": p_value,
                "effect_size": result.get("effect_size"),
                "effect_size_name": result.get("effect_size_name"),
                "effect_size_label": result.get("effect_size_label"),
                "narrative": stats_lab.interpret_result(result),
                "warnings": stats_lab.normality_warnings(result),
            }
        )
    return results


def run_hypothesis_engine(model, df: pd.DataFrame, column_types: dict[str, str], max_hypotheses: int = 5) -> dict:
    """Generate then verify in one call — what the UI button triggers.

    Returns {"hypotheses": [...], "source": ..., "generation_error": ...,
    "results": [...]} — "results" is the verify_hypotheses() output, ready
    to render as CONFIRMED/NOT CONFIRMED/INCONCLUSIVE cards.
    """
    generated = generate_hypotheses(model, df, column_types, max_hypotheses)
    results = verify_hypotheses(df, column_types, generated["hypotheses"]) if generated["hypotheses"] else []
    return {
        "hypotheses": generated["hypotheses"],
        "source": generated["source"],
        "generation_error": generated["error"],
        "results": results,
    }
