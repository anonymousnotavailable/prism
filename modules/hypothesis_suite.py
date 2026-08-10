"""
Hypothesis Suite — automated multi-hypothesis testing agent.

`auto_analyst.suggest_followup_hypothesis()` suggests a single promising
column pair; Stats Lab lets a user manually pick two columns and run one
test. Neither actually sweeps the dataset. This module closes that gap:
enumerate every viable column pair, run the right test on each via
`stats_lab.suggest_test()`/`run_test()`, and correct for the multiple-
comparisons problem that sweep creates (Benjamini-Hochberg FDR) before
ranking and returning the findings that survive correction.

This is the same "run many, then verify which survive scrutiny" pattern
already used for anomaly detection (`anomaly.find_anomalies_ensemble`) and
insight generation (`auto_insights`), applied to formal hypothesis testing
— the statistical-rigor half of the agentic-EDA story: it's not enough to
p-hack across every column pair and report whatever comes back p<0.05,
so this sweep runs the correction step every real analysis of this shape
needs and reports honestly when nothing survives it.
"""

from __future__ import annotations

import hashlib
import itertools
from typing import Optional

import pandas as pd

from modules import stats_lab

# Hard caps so a wide dataset (100+ columns) can't blow up combinatorics —
# an unattended sweep must stay bounded, not just "usually fast."
MAX_NUMERIC_COLS = 12
MAX_CATEGORICAL_COLS = 8
MAX_TESTS = 40
MAX_CATEGORY_CARDINALITY = stats_lab.MAX_GROUPS_FOR_TEST  # reuse Stats Lab's own ceiling


def enumerate_candidate_pairs(
    df: pd.DataFrame, column_types: dict[str, str]
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """All numeric/numeric, numeric/categorical, categorical/categorical
    pairs worth testing, plus a `truncation` dict noting anything dropped
    for being over the caps — a bounded sweep should say what it skipped,
    not silently drop it.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric" and c in df.columns]
    categorical_cols = [
        c
        for c, t in column_types.items()
        if t == "categorical" and c in df.columns and 2 <= df[c].nunique(dropna=True) <= MAX_CATEGORY_CARDINALITY
    ]

    truncation: dict[str, int] = {}
    if len(numeric_cols) > MAX_NUMERIC_COLS:
        truncation["numeric"] = len(numeric_cols) - MAX_NUMERIC_COLS
        numeric_cols = numeric_cols[:MAX_NUMERIC_COLS]
    if len(categorical_cols) > MAX_CATEGORICAL_COLS:
        truncation["categorical"] = len(categorical_cols) - MAX_CATEGORICAL_COLS
        categorical_cols = categorical_cols[:MAX_CATEGORICAL_COLS]

    pairs = list(itertools.combinations(numeric_cols, 2))
    pairs += list(itertools.product(numeric_cols, categorical_cols))
    pairs += list(itertools.combinations(categorical_cols, 2))

    if len(pairs) > MAX_TESTS:
        truncation["pairs"] = len(pairs) - MAX_TESTS
        pairs = pairs[:MAX_TESTS]

    return pairs, truncation


def _benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR correction. Returns a same-order list of
    booleans: True where a p-value survives correction at the given alpha.

    Running M independent significance tests and reporting every raw p<0.05
    hit is the textbook false-discovery-rate inflation problem — with
    enough column pairs, some will look "significant" by chance alone. BH
    finds the largest rank k (p-values sorted ascending) where
    p(k) <= (k/M)*alpha, and every test at or below that rank survives.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    threshold_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / m) * alpha:
            threshold_rank = rank
    survives = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= threshold_rank:
            survives[idx] = True
    return survives


def run_hypothesis_suite(df: pd.DataFrame, column_types: dict[str, str], alpha: float = 0.05) -> dict:
    """Run suggest_test()+run_test() over every viable column pair, apply
    BH-FDR correction across all p-values obtained, and return findings
    ranked by (survives correction, |effect size|) descending.

    Returns {"findings": [...], "n_tested": int, "n_significant_raw": int,
    "n_significant_corrected": int, "truncation": dict}. Never raises — any
    pair that a lower-level function rejects (suggest_test/run_test error)
    is skipped, not fatal to the batch; a data quirk in one column pair
    shouldn't kill the whole sweep.
    """
    pairs, truncation = enumerate_candidate_pairs(df, column_types)

    raw_results = []
    for col_a, col_b in pairs:
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            continue
        raw_results.append({**result, "col_a": col_a, "col_b": col_b, "reason": suggestion["reason"]})

    p_values = [r["p_value"] for r in raw_results]
    survives = _benjamini_hochberg(p_values, alpha)

    findings = []
    for result, sig in zip(raw_results, survives):
        finding = dict(result)
        finding["significant_raw"] = finding["p_value"] < alpha
        finding["significant_corrected"] = sig
        finding["interpretation"] = stats_lab.interpret_result(finding)
        # Drop bulky nested detail (per-group normality checks, full
        # contingency table) — kept lean for the ranked summary; the exact
        # same pair is one click away in Stats Lab for the full breakdown.
        finding.pop("normality", None)
        finding.pop("contingency_table", None)
        findings.append(finding)

    findings.sort(key=lambda f: (not f["significant_corrected"], -abs(f["effect_size"])))

    return {
        "findings": findings,
        "n_tested": len(raw_results),
        "n_significant_raw": sum(1 for f in findings if f["significant_raw"]),
        "n_significant_corrected": sum(1 for f in findings if f["significant_corrected"]),
        "truncation": truncation,
    }


def fingerprint_suite(result: Optional[dict]) -> str:
    """A short, stable hash of a `run_hypothesis_suite()` result — used to
    cache the AI narration below so re-viewing the same result (e.g. after
    switching tabs) doesn't re-spend a Gemini call.
    """
    if not result or not result.get("findings"):
        return "empty"
    parts = sorted(
        f"{f['col_a']}|{f['col_b']}|{f['test']}|{f['p_value']:.6f}|{f['significant_corrected']}"
        for f in result["findings"]
    )
    key = f"{result.get('n_tested', 0)}|" + "|".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data analyst who just ran an automated hypothesis-testing sweep "
    "across {n_tested} column-pair test(s) (t-tests / ANOVA / chi-square / correlation), "
    "correcting for multiple comparisons with Benjamini-Hochberg FDR. {n_sig} pair(s) "
    "remained significant after correction. Here are the top surviving findings:\n\n"
    "{findings_text}\n\n"
    "In 3-4 sentences: summarize what these findings suggest about the dataset's "
    "underlying structure, and recommend ONE concrete next analysis step. Do not simply "
    "restate the numbers back."
)


def narrate_hypothesis_suite(model, result: Optional[dict]) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn a `run_hypothesis_suite()` result into a short
    plain-English summary + suggested next step, covering only the findings
    that survived multiple-comparisons correction.

    Returns (narration, error). Callers should cache the result keyed by
    `fingerprint_suite(result)`, same convention as the rest of the app's
    narration helpers (this function itself always calls Gemini when given
    a model and at least one surviving finding).
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result or not result.get("findings"):
        return "No testable column pairs were found — nothing to narrate.", None

    significant = [f for f in result["findings"] if f["significant_corrected"]]
    if not significant:
        return (
            "None of the tested hypotheses survived correction for multiple comparisons — "
            "no statistically reliable relationships found in this sweep.",
            None,
        )

    from modules.ai_analyst import call_gemini

    findings_text = "\n".join(f"- {f['col_a']} vs {f['col_b']} ({f['test']}): {f['interpretation']}" for f in significant[:8])
    prompt = _NARRATION_PROMPT.format(
        n_tested=result["n_tested"], n_sig=len(significant), findings_text=findings_text
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
