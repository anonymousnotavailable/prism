"""
Hypothesis Engine — the agentic "propose, then prove" pipeline that closes
the loop between Auto Analyst (which narrates findings) and Stats Lab
(which requires the user to hand-pick two columns before it will test
anything). This module lets Gemini nominate candidate relationships in the
data, but — mirroring the SAFE/REVIEW split already hard-coded in
modules.autocleaner — Gemini never gets to decide whether a hypothesis
actually HOLDS. It only proposes WHAT to test and WHY it might be
interesting; picking the correct test (t-test / ANOVA / chi-square /
Pearson) and running the math is 100% modules.stats_lab / scipy, exactly
as it would be if the user had picked the columns by hand.

Pipeline:
    generate_hypotheses() — Gemini reads the schema + a 3-row sample (never
        the full dataset) and proposes 4-6 plain-English hypotheses, each
        naming two real columns. If Gemini is unavailable (no key, quota
        exhausted, rate-limited), falls back to a deterministic heuristic
        generator (top correlations + top group-mean spreads) so the
        feature degrades gracefully instead of going dark.
    run_hypotheses() — each hypothesis is tested via stats_lab.run_test(),
        then ALL the resulting p-values are corrected together with a
        Benjamini-Hochberg FDR adjustment (statsmodels), because testing
        several hypotheses on the same dataset without correcting for it
        is a textbook way to manufacture false positives — the same
        p<0.05 that's meaningful for one test stops being meaningful once
        you've run five.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd
from statsmodels.stats.multitest import multipletests

from modules import stats_lab
from modules.ai_analyst import build_data_context, call_gemini, get_api_key

try:
    import google.generativeai as genai
except ImportError:  # the app should still load even if the package isn't installed yet
    genai = None

DEFAULT_MAX_HYPOTHESES = 5
FDR_ALPHA = 0.05

SYSTEM_PROMPT = (
    "You are a senior data analyst generating a shortlist of testable statistical "
    "hypotheses about a pandas DataFrame, to hand off to a rigorous stats engine. "
    "You are proposing WHAT relationship to test and WHY it might matter — never "
    "deciding HOW to test it or whether it actually holds; that runs in scipy/"
    "statsmodels afterward and can prove you wrong.\n\n"
    "Given the dataframe's schema, sample rows, and summary stats, propose specific, "
    "testable hypotheses about a relationship BETWEEN EXACTLY TWO columns each. Every "
    "hypothesis must be non-trivial (skip ID-like or near-constant columns), phrased "
    "as a plain-English claim a data analyst would say out loud, and name two "
    "DIFFERENT column names taken verbatim from the schema.\n\n"
    "Return ONLY a JSON array, no prose, no markdown code fences, shaped exactly like:\n"
    '[{"hypothesis": "<plain-English claim>", "col_a": "<exact column name>", '
    '"col_b": "<exact column name>", "rationale": "<one sentence on why this pairing '
    'is worth testing>"}]'
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def get_model(api_key: Optional[str] = None):
    """Build a configured Gemini model instance for hypothesis generation, or
    None if unavailable (no key, or the SDK failed to import).
    """
    key = api_key or get_api_key()
    if not key or genai is None:
        return None
    genai.configure(api_key=key)
    return genai.GenerativeModel(
        "gemini-flash-lite-latest", system_instruction=SYSTEM_PROMPT
    )


def _testable_columns(column_types: dict[str, str]) -> list[str]:
    return [c for c, t in column_types.items() if t in ("numeric", "categorical")]


def _parse_hypotheses(text: str, columns: list[str], column_types: dict[str, str]) -> list[dict]:
    """Extract and validate Gemini's JSON array. Drops any entry that
    hallucinates a column name, repeats a column against itself, points at
    an untestable type (datetime/text/id), or duplicates a pair already
    seen — returns [] (never raises) on anything else malformed.
    """
    match = _JSON_ARRAY_RE.search(text or "")
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    valid_cols = set(columns)
    testable = set(_testable_columns(column_types))
    seen_pairs: set[frozenset] = set()
    hypotheses = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text_claim = str(item.get("hypothesis", "")).strip()
        col_a, col_b = item.get("col_a"), item.get("col_b")
        if not text_claim or col_a not in valid_cols or col_b not in valid_cols or col_a == col_b:
            continue
        if col_a not in testable or col_b not in testable:
            continue
        pair_key = frozenset((col_a, col_b))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        hypotheses.append(
            {
                "hypothesis": text_claim,
                "col_a": col_a,
                "col_b": col_b,
                "rationale": str(item.get("rationale", "")).strip(),
                "source": "gemini",
            }
        )
    return hypotheses


def _heuristic_hypotheses(df: pd.DataFrame, column_types: dict[str, str], max_hypotheses: int) -> list[dict]:
    """Deterministic fallback when Gemini is unavailable: nominate the
    numeric pairs with the strongest absolute correlation, and the
    categorical/numeric pairs with the largest between-group mean spread
    relative to overall variance (a cheap proxy for "an ANOVA here is
    likely to find something"). No LLM call, no network — just pandas.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]
    half = max(1, (max_hypotheses + 1) // 2)

    numeric_candidates = []
    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr(numeric_only=True).abs()
        pairs = []
        for i, a in enumerate(numeric_cols):
            for b in numeric_cols[i + 1 :]:
                val = corr.loc[a, b]
                if pd.notna(val):
                    pairs.append((float(val), a, b))
        pairs.sort(reverse=True, key=lambda p: p[0])
        for val, a, b in pairs[:half]:
            numeric_candidates.append(
                {
                    "hypothesis": f"'{a}' and '{b}' are correlated.",
                    "col_a": a,
                    "col_b": b,
                    "rationale": f"Automatic correlation scan flagged this pair (|r|={val:.2f}) — Gemini was unavailable.",
                    "source": "heuristic",
                }
            )

    categorical_candidates = []
    if categorical_cols and numeric_cols:
        scored = []
        for cat in categorical_cols:
            n_groups = df[cat].dropna().nunique()
            if n_groups < 2 or n_groups > stats_lab.MAX_GROUPS_FOR_TEST:
                continue
            for num in numeric_cols:
                clean = df[[cat, num]].dropna()
                if clean.empty:
                    continue
                overall_var = clean[num].var()
                if not overall_var or pd.isna(overall_var):
                    continue
                group_spread = clean.groupby(cat)[num].mean().var()
                if pd.isna(group_spread):
                    continue
                scored.append((float(group_spread / overall_var), cat, num))
        scored.sort(reverse=True, key=lambda p: p[0])
        for score, cat, num in scored[:half]:
            categorical_candidates.append(
                {
                    "hypothesis": f"Average '{num}' differs across '{cat}' groups.",
                    "col_a": cat,
                    "col_b": num,
                    "rationale": f"Automatic group-variance scan flagged this pair (score={score:.2f}) — Gemini was unavailable.",
                    "source": "heuristic",
                }
            )

    combined = numeric_candidates + categorical_candidates
    return combined[:max_hypotheses]


def generate_hypotheses(
    model,
    df: pd.DataFrame,
    column_types: dict[str, str],
    max_hypotheses: int = DEFAULT_MAX_HYPOTHESES,
    dataset_fingerprint: Optional[dict] = None,
    pii_findings: Optional[dict] = None,
    strict_mode: bool = False,
) -> tuple[list[dict], Optional[str]]:
    """Returns (hypotheses, error). `error` is only set for a hard stop
    (not enough testable columns) — a Gemini failure degrades to the
    heuristic generator instead of erroring out, so the feature never
    goes dark just because the free-tier quota ran out.
    """
    if len(_testable_columns(column_types)) < 2:
        return [], "Need at least 2 numeric or categorical columns to generate hypotheses."

    if model is None:
        return _heuristic_hypotheses(df, column_types, max_hypotheses), None

    context = build_data_context(
        df, column_types, pii_findings=pii_findings, strict_mode=strict_mode, dataset_fingerprint=dataset_fingerprint
    )
    prompt = f"{context}\n\nPropose {max_hypotheses} testable hypotheses, following the system instructions."
    text, error = call_gemini(model, prompt)
    if error:
        return _heuristic_hypotheses(df, column_types, max_hypotheses), None

    hypotheses = _parse_hypotheses(text, list(df.columns), column_types)
    if not hypotheses:
        return _heuristic_hypotheses(df, column_types, max_hypotheses), None
    return hypotheses[:max_hypotheses], None


def run_hypotheses(df: pd.DataFrame, column_types: dict[str, str], hypotheses: list[dict]) -> list[dict]:
    """Test every hypothesis via stats_lab (Python picks the test, never
    Gemini), then apply a Benjamini-Hochberg FDR correction jointly across
    every testable hypothesis in the batch before assigning a verdict.
    Untestable pairs (too many categories, all-null overlap, etc.) get
    verdict "NOT_TESTABLE" and are excluded from the correction — they
    were never actually tested, so correcting for them would understate
    the correction the real tests need.
    """
    enriched = []
    for h in hypotheses:
        suggestion = stats_lab.suggest_test(df, column_types, h["col_a"], h["col_b"])
        if suggestion.get("error"):
            enriched.append({**h, "verdict": "NOT_TESTABLE", "reason": suggestion["error"]})
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            enriched.append({**h, "verdict": "NOT_TESTABLE", "reason": result["error"]})
            continue
        enriched.append({**h, "suggestion": suggestion, "result": result})

    testable = [h for h in enriched if "result" in h]
    if testable:
        p_values = [h["result"]["p_value"] for h in testable]
        reject_flags, adjusted_p_values, _, _ = multipletests(p_values, alpha=FDR_ALPHA, method="fdr_bh")
        for h, reject, adj_p in zip(testable, reject_flags, adjusted_p_values):
            h["adjusted_p_value"] = float(adj_p)
            h["n_tested"] = len(testable)
            h["verdict"] = "SUPPORTED" if reject else "REJECTED"
            h["narration"] = _narrate(h)

    return enriched


def _narrate(h: dict) -> str:
    verdict_label = {
        "SUPPORTED": "Likely real",
        "REJECTED": "Not significant after correction",
    }[h["verdict"]]
    detail = stats_lab.interpret_result(h["result"])
    correction_note = (
        f" Adjusted p={h['adjusted_p_value']:.4f} after Benjamini-Hochberg correction across "
        f"{h['n_tested']} simultaneous hypotheses."
        if h["n_tested"] > 1
        else ""
    )
    return f"{verdict_label} — {detail}{correction_note}"
