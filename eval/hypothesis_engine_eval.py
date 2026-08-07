"""
Hypothesis Engine Eval Harness — runs modules.hypothesis_engine's
scan_hypotheses()/narrate_findings() against fixed synthetic datasets with
known-planted relationships (and known non-relationships), and asserts the
scan finds what it should while the Benjamini-Hochberg correction actually
suppresses the false positives a naive "test everything at p<0.05" scan
would report. Writes eval/hypothesis_engine_eval_results.md.

Fully deterministic (fixed numpy seeds) and needs NO Gemini API key —
narrate_findings() is only exercised in its model=None (templated fallback)
path here, same reasoning as autocleaner_eval.py.

Run with:  python eval/hypothesis_engine_eval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import data_engine, hypothesis_engine  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVAL_DIR / "hypothesis_engine_eval_results.md"


def _types_for(df: pd.DataFrame) -> dict:
    return data_engine.detect_column_types(df)


def _case_finds_planted_correlation() -> tuple[bool, str]:
    rng = np.random.RandomState(0)
    x = rng.normal(100, 15, 300)
    df = pd.DataFrame({
        "revenue": x,
        "marketing_spend": x * 2.5 + rng.normal(0, 5, 300),  # strongly correlated by construction
        "region": rng.choice(["North", "South", "East", "West"], 300),
    })
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types)
    hit = next(
        (r for r in scan["results"] if {r["col_a"], r["col_b"]} == {"revenue", "marketing_spend"}),
        None,
    )
    if hit is None:
        return False, "No result for the planted revenue/marketing_spend correlation."
    if hit["test"] != "pearson":
        return False, f"Expected a pearson test, got {hit['test']!r}."
    if not hit["significant_corrected"]:
        return False, f"Planted strong correlation did not survive FDR correction (q={hit['p_value_corrected']:.4g})."
    if hit["effect_size"] < 0.8:
        return False, f"Expected a large Pearson r for a 2.5x-scaled relationship, got r={hit['effect_size']:.2f}."
    return True, f"revenue/marketing_spend flagged significant after correction (r={hit['effect_size']:.2f}, q={hit['p_value_corrected']:.4g})."


def _case_finds_planted_group_difference() -> tuple[bool, str]:
    rng = np.random.RandomState(1)
    control = rng.normal(50, 8, 150)
    treatment = rng.normal(65, 8, 150)  # clearly higher mean by construction
    df = pd.DataFrame({
        "conversion_score": np.concatenate([control, treatment]),
        "variant": ["control"] * 150 + ["treatment"] * 150,
        "noise_col": rng.normal(0, 1, 300),
    })
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types)
    hit = next(
        (r for r in scan["results"] if {r["col_a"], r["col_b"]} == {"conversion_score", "variant"}),
        None,
    )
    if hit is None:
        return False, "No result for the planted conversion_score/variant group difference."
    if hit["test"] != "ttest":
        return False, f"Expected a ttest, got {hit['test']!r}."
    if not hit["significant_corrected"]:
        return False, f"Planted group difference did not survive FDR correction (q={hit['p_value_corrected']:.4g})."
    return True, f"conversion_score/variant flagged significant after correction (Cohen's d={hit['effect_size']:.2f})."


def _case_fdr_correction_suppresses_noise() -> tuple[bool, str]:
    # 12 fully independent random numeric columns -> 66 pairwise Pearson
    # tests where the null hypothesis (no correlation) is always true. At
    # raw p<0.05 that's ~3 false positives expected by chance; FDR
    # correction should knock most/all of them back out.
    rng = np.random.RandomState(42)
    df = pd.DataFrame({f"noise_{i}": rng.normal(0, 1, 200) for i in range(12)})
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types)

    n_raw_significant = sum(1 for r in scan["results"] if r["significant_raw"])
    n_corrected_significant = sum(1 for r in scan["results"] if r["significant_corrected"])

    if scan["pairs_tested"] != 66:
        return False, f"Expected 66 pairs tested for 12 columns, got {scan['pairs_tested']}."
    if n_corrected_significant > n_raw_significant:
        return False, "Corrected significant count exceeds raw significant count — correction is not shrinking, it's growing."
    if n_corrected_significant > 2:
        return False, f"FDR correction let {n_corrected_significant} pure-noise pairs through as significant, expected <=2."
    return True, f"{n_raw_significant} raw-significant -> {n_corrected_significant} after FDR correction, out of 66 pure-noise pairs."


def _case_too_few_columns_returns_empty() -> tuple[bool, str]:
    df = pd.DataFrame({"only_numeric_col": [1.0, 2.0, 3.0, 4.0, 5.0]})
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types)
    if scan["results"] != []:
        return False, f"Expected no results with a single testable column, got {len(scan['results'])}."
    if scan["pairs_tested"] != 0:
        return False, f"Expected 0 pairs tested, got {scan['pairs_tested']}."
    return True, "Single-column dataset scanned to an empty (not crashed) result."


def _case_truncates_wide_datasets() -> tuple[bool, str]:
    rng = np.random.RandomState(2)
    df = pd.DataFrame({f"col_{i}": rng.normal(0, 1, 50) for i in range(20)})
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types, max_columns=12)
    if not scan["truncated"]:
        return False, "Expected truncated=True for a 20-column dataset scanned with max_columns=12."
    if scan["columns_scanned"] != 12 or scan["columns_available"] != 20:
        return False, f"Expected columns_scanned=12/columns_available=20, got {scan['columns_scanned']}/{scan['columns_available']}."
    return True, "20-column dataset correctly capped to 12 scanned columns with truncated=True."


def _case_narrate_findings_fallback_without_model() -> tuple[bool, str]:
    rng = np.random.RandomState(0)
    x = rng.normal(100, 15, 300)
    df = pd.DataFrame({"revenue": x, "marketing_spend": x * 2.5 + rng.normal(0, 5, 300)})
    column_types = _types_for(df)
    scan = hypothesis_engine.scan_hypotheses(df, column_types)

    bullets, error = hypothesis_engine.narrate_findings(None, scan)
    if error is not None:
        return False, f"Expected no error in the model=None fallback path, got {error!r}."
    if not bullets:
        return False, "Expected at least one templated fallback bullet for a significant scan."
    if "revenue" not in bullets[0] or "marketing_spend" not in bullets[0]:
        return False, f"Fallback bullet doesn't name both columns: {bullets[0]!r}"
    return True, f"Templated fallback produced {len(bullets)} bullet(s) without calling Gemini."


def _case_narrate_findings_no_significant_results() -> tuple[bool, str]:
    empty_scan = {"results": [], "columns_scanned": 0, "columns_available": 0, "pairs_tested": 0, "truncated": False}
    bullets, error = hypothesis_engine.narrate_findings(None, empty_scan)
    if error is not None:
        return False, f"Expected no error for an empty scan, got {error!r}."
    if bullets != []:
        return False, f"Expected no bullets for an empty scan, got {bullets}."
    return True, "Empty scan narrates to zero bullets, no error raised."


CASES = [
    {"id": 1, "name": "finds a planted strong correlation", "dataset": "(synthetic)", "fn": _case_finds_planted_correlation},
    {"id": 2, "name": "finds a planted group difference", "dataset": "(synthetic)", "fn": _case_finds_planted_group_difference},
    {"id": 3, "name": "FDR correction suppresses noise false-positives", "dataset": "(synthetic)", "fn": _case_fdr_correction_suppresses_noise},
    {"id": 4, "name": "single testable column -> empty result, no crash", "dataset": "(synthetic)", "fn": _case_too_few_columns_returns_empty},
    {"id": 5, "name": "wide dataset truncates to max_columns", "dataset": "(synthetic)", "fn": _case_truncates_wide_datasets},
    {"id": 6, "name": "narrate_findings templated fallback (no model)", "dataset": "(synthetic)", "fn": _case_narrate_findings_fallback_without_model},
    {"id": 7, "name": "narrate_findings on an empty scan", "dataset": "(synthetic)", "fn": _case_narrate_findings_no_significant_results},
]


def run_eval() -> dict:
    results = []
    for case in CASES:
        try:
            passed, detail = case["fn"]()
        except Exception as exc:  # noqa: BLE001 — surface any failure as a scored result, not a crash
            passed, detail = False, f"Raised {type(exc).__name__}: {exc}"
        results.append({**case, "status": "pass" if passed else "fail", "detail": detail})

    n_passed = sum(r["status"] == "pass" for r in results)
    accuracy = round(100 * n_passed / len(results), 1) if results else 0.0
    return {"results": results, "n_passed": n_passed, "n_total": len(results), "accuracy": accuracy}


def write_report(evaluation: dict) -> None:
    lines = [
        "# Prism — Hypothesis Engine Eval Results",
        "",
        f"**Accuracy: {evaluation['accuracy']}%** ({evaluation['n_passed']}/{evaluation['n_total']} test cases passed)",
        "",
        "Runs `modules.hypothesis_engine`'s scan_hypotheses()/narrate_findings() directly against "
        "fixed synthetic datasets with planted relationships (and planted non-relationships). No "
        "Gemini API key required — the scan itself is fully deterministic scipy/statsmodels, and "
        "narrate_findings() is only exercised in its model=None templated-fallback path here.",
        "",
        "| # | Case | Dataset | Result |",
        "|---|------|---------|--------|",
    ]
    status_labels = {"pass": "PASS", "fail": "FAIL"}
    for r in evaluation["results"]:
        detail = r["detail"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['name']} | {r['dataset']} | **{status_labels[r['status']]}** — {detail} |")

    lines.append("")
    lines.append("## Failures in detail")
    failures = [r for r in evaluation["results"] if r["status"] == "fail"]
    if not failures:
        lines.append("None — every test case passed.")
    else:
        for r in failures:
            lines.append(f"### #{r['id']} — {r['name']}")
            lines.append(f"- Dataset: {r['dataset']}")
            lines.append(f"- {r['detail']}")
            lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    evaluation = run_eval()
    write_report(evaluation)
    print(f"Accuracy: {evaluation['accuracy']}% ({evaluation['n_passed']}/{evaluation['n_total']} passed) — see {RESULTS_PATH}")
