"""
Hypothesis Engine — automatic multi-column hypothesis scanning built on top
of Stats Lab. Stats Lab tests exactly the two columns a user manually picks;
this module enumerates every valid testable column pair (capped to keep
runtime bounded and the multiple-comparisons correction meaningful), runs
stats_lab's existing suggest_test()/run_test() pipeline on each pair, and
applies a Benjamini-Hochberg false-discovery-rate correction across the
whole batch of p-values — the same guard a careful analyst applies before
trusting any single p-value out of a dozen tests run back to back. Testing
20 column pairs at p<0.05 raw would produce roughly one false positive by
chance alone even in pure noise; FDR correction is what keeps "Auto-Scan"
honest instead of just being a p-value fishing expedition.

Gemini narration is optional and additive: narrate_findings() turns the
corrected-significant results into plain-English bullets, with a fully
offline templated fallback (built from stats_lab.interpret_result()) when
no model/key is available or the call fails — the scan's numbers stand on
their own either way.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from statsmodels.stats.multitest import multipletests

from modules import stats_lab
from modules.ai_analyst import call_gemini, parse_numbered_bullets

# C(12, 2) = 66 pairs — enough breadth to find real relationships in a
# typical dataset while keeping the scan instant and the correction batch
# a size where FDR still means something (correcting over 1000s of pairs
# from very wide datasets would bury everything under the correction).
MAX_COLUMNS = 12
MAX_NARRATED = 5
ALPHA = 0.05

_NARRATION_PROMPT_TEMPLATE = (
    "You are a senior data analyst. An automated hypothesis scan tested {n_tests} "
    "column-pair relationships in a dataset and applied a Benjamini-Hochberg "
    "false-discovery-rate correction to guard against false positives from testing "
    "many pairs at once. These relationships stayed significant after correction, "
    "ranked strongest first:\n\n{summaries}\n\n"
    "Write up to {top_n} concise, business-relevant findings, one per line, each "
    "starting with '1. ' through '{top_n}. '. Each finding MUST name both columns "
    "and reference the effect size or p-value given above. Do not invent numbers "
    "not present in the data above."
)


def _select_columns(column_types: dict[str, str], max_columns: int = MAX_COLUMNS) -> tuple[list[str], int]:
    """Testable columns (numeric/categorical only), capped at max_columns.

    Order follows column_types' insertion order (i.e. the dataframe's own
    column order) so which columns get dropped on a wide dataset is at
    least predictable, not arbitrary.
    """
    testable = [c for c, t in column_types.items() if t in ("numeric", "categorical")]
    return testable[:max_columns], len(testable)


def _candidate_pairs(columns: list[str]) -> list[tuple[str, str]]:
    return [(columns[i], columns[j]) for i in range(len(columns)) for j in range(i + 1, len(columns))]


def scan_hypotheses(df: pd.DataFrame, column_types: dict[str, str], max_columns: int = MAX_COLUMNS, alpha: float = ALPHA) -> dict:
    """Run every valid pairwise test across up to max_columns testable columns.

    Returns {"results": [...], "columns_scanned", "columns_available",
    "pairs_tested", "truncated"}. Each entry in "results" extends a
    stats_lab.run_test() result dict with "col_a", "col_b", "test_label",
    "p_value_corrected", "significant_raw", "significant_corrected", sorted
    with corrected-significant, stronger-effect results first.

    A pair with no valid test (suggest_test error — e.g. too many
    categories — or a run_test error — e.g. too few paired values) is
    silently skipped: that's an incompatible pair, not a failed hypothesis.
    An empty "results" list is a valid outcome (not enough testable columns,
    or every pair was incompatible), never an error — callers should render
    it as "nothing conclusive found", not surface an exception.
    """
    columns, available = _select_columns(column_types, max_columns)
    pairs = _candidate_pairs(columns)

    raw_results = []
    for col_a, col_b in pairs:
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            continue
        result["col_a"] = col_a
        result["col_b"] = col_b
        result["test_label"] = stats_lab.TEST_LABELS[result["test"]]
        raw_results.append(result)

    if raw_results:
        p_values = [r["p_value"] for r in raw_results]
        _, corrected_p, _, _ = multipletests(p_values, alpha=alpha, method="fdr_bh")
        for result, q in zip(raw_results, corrected_p):
            result["p_value_corrected"] = float(q)
            result["significant_raw"] = bool(result["p_value"] < alpha)
            result["significant_corrected"] = bool(q < alpha)

        raw_results.sort(key=lambda r: (not r["significant_corrected"], r["p_value_corrected"], -abs(r["effect_size"])))

    return {
        "results": raw_results,
        "columns_scanned": len(columns),
        "columns_available": available,
        "pairs_tested": len(pairs),
        "truncated": available > max_columns,
    }


def _fallback_bullets(significant: list[dict], top_n: int) -> list[str]:
    """Templated, Gemini-free summary — used when no model is configured
    and as the safety net if a Gemini call fails."""
    return [
        f"'{r['col_a']}' and '{r['col_b']}': {stats_lab.interpret_result(r)} "
        f"(FDR-corrected p={r['p_value_corrected']:.4f})."
        for r in significant[:top_n]
    ]


def narrate_findings(model, scan: dict, top_n: int = MAX_NARRATED) -> tuple[list[str], Optional[str]]:
    """Plain-English bullets for the corrected-significant results in `scan`.

    Returns (bullets, error). "No significant relationships survived
    correction" is a valid, non-error outcome (empty bullets, error=None) —
    it's itself a finding worth showing, not a failure. A Gemini error
    degrades quietly to the templated fallback rather than surfacing to the
    user, since the numeric scan result already stands on its own.
    """
    significant = [r for r in scan.get("results", []) if r.get("significant_corrected")]
    if not significant:
        return [], None

    if model is None:
        return _fallback_bullets(significant, top_n), None

    summaries = "\n".join(
        f"- {r['col_a']} vs {r['col_b']} ({r['test_label']}): {stats_lab.interpret_result(r)}, "
        f"FDR-corrected p={r['p_value_corrected']:.4f}"
        for r in significant[:top_n]
    )
    n_narrated = min(top_n, len(significant))
    prompt = _NARRATION_PROMPT_TEMPLATE.format(n_tests=len(scan["results"]), summaries=summaries, top_n=n_narrated)
    text, error = call_gemini(model, prompt)
    if error:
        return _fallback_bullets(significant, top_n), None

    bullets = parse_numbered_bullets(text)
    return (bullets or _fallback_bullets(significant, top_n)), None
