"""
Hypothesis Engine + Anomaly Tuning Eval Harness — deterministic test cases
for modules.hypothesis_engine and the new configurable-sensitivity /
narration additions to modules.anomaly. Writes
eval/hypothesis_engine_eval_results.md with a pass/fail breakdown.

No Gemini API key needed: generate_hypotheses()/narrate_anomalies() are only
exercised via their model=None fallback paths here (default_hypotheses(),
_default_narration()) — the LLM-proposal step is the one part of each
feature that genuinely needs Gemini, and it degrades to a deterministic
rule-based path by design, which is exactly what's scored below. The
*verification* step (test_hypotheses) never touches Gemini at all, by
construction, and is scored the same way regardless.

Run with:  python eval/hypothesis_engine_eval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import anomaly, data_engine, hypothesis_engine  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVAL_DIR / "hypothesis_engine_eval_results.md"


def _correlated_df(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    x = rng.normal(50, 10, n)
    y = x * 2 + rng.normal(0, 1, n)  # near-perfectly correlated with x
    noise = rng.normal(0, 10, n)  # uncorrelated with everything
    group = rng.choice(["A", "B"], n, p=[0.5, 0.5])
    # group B's target is shifted hard so the group split is genuinely significant
    target = np.where(group == "A", rng.normal(10, 2, n), rng.normal(40, 2, n))
    return pd.DataFrame({"x": x, "y": y, "noise": noise, "group": group, "target": target})


def _case_default_hypotheses_reference_real_columns() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    hyps = hypothesis_engine.default_hypotheses(df, column_types)
    if not hyps:
        return False, "default_hypotheses() returned an empty list on a dataset with valid pairs."
    bad = [h for h in hyps if h["col_a"] not in df.columns or h["col_b"] not in df.columns]
    if bad:
        return False, f"{len(bad)} hypothesis(es) reference non-existent columns."
    return True, f"{len(hyps)} hypothesis(es) generated, all referencing real columns."


def _case_default_hypotheses_finds_strong_correlation() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    hyps = hypothesis_engine.default_hypotheses(df, column_types)
    pairs = {frozenset((h["col_a"], h["col_b"])) for h in hyps}
    if frozenset({"x", "y"}) not in pairs:
        return False, f"Expected the strong x/y correlation to surface; got pairs {pairs}."
    return True, "The strongly correlated ('x', 'y') pair was proposed as a hypothesis."

def _case_test_hypotheses_confirms_real_effect() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    hyps = [{"statement": "target differs by group", "col_a": "target", "col_b": "group", "rationale": "test"}]
    results = hypothesis_engine.test_hypotheses(df, column_types, hyps)
    if len(results) != 1:
        return False, f"Expected 1 result, got {len(results)}."
    r = results[0]
    if r["verdict"] != "confirmed":
        return False, f"Expected 'confirmed' for a strongly group-separated column, got {r['verdict']!r} ({r['narrative']})."
    if r["result"] is None or r["result"]["p_value"] >= 0.05:
        return False, "Expected p < 0.05 backing the confirmed verdict."
    return True, f"Correctly confirmed with p={r['result']['p_value']:.2e}."


def _case_test_hypotheses_rejects_noise() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    hyps = [{"statement": "x and noise are correlated", "col_a": "x", "col_b": "noise", "rationale": "test"}]
    results = hypothesis_engine.test_hypotheses(df, column_types, hyps)
    r = results[0]
    if r["verdict"] != "not confirmed":
        return False, f"Expected 'not confirmed' for two independent columns, got {r['verdict']!r}."
    return True, "Correctly did not confirm a hypothesis over independently generated columns."


def _case_test_hypotheses_handles_untestable() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    # 'target' is numeric with >10 distinct values used as a fake grouping column against itself-shaped data
    hyps = [{"statement": "bad pairing", "col_a": "x", "col_b": "x", "rationale": "test"}]
    results = hypothesis_engine.test_hypotheses(df, column_types, hyps)
    r = results[0]
    if r["verdict"] != "untestable":
        return False, f"Expected 'untestable' for a column tested against itself, got {r['verdict']!r}."
    if r["result"] is not None:
        return False, "Expected result=None for an untestable hypothesis."
    return True, "Correctly marked an invalid pairing as untestable rather than crashing."


def _case_generate_hypotheses_falls_back_without_model() -> tuple[bool, str]:
    df = _correlated_df()
    column_types = data_engine.detect_column_types(df)
    hyps = hypothesis_engine.generate_hypotheses(None, df, column_types)
    if not hyps:
        return False, "generate_hypotheses(model=None, ...) returned an empty list."
    return True, f"model=None correctly fell back to {len(hyps)} rule-based hypothesis(es)."


def _case_anomaly_contamination_is_clamped() -> tuple[bool, str]:
    rng = np.random.RandomState(1)
    df = pd.DataFrame({"a": rng.normal(0, 1, 100), "b": rng.normal(0, 1, 100)})
    column_types = data_engine.detect_column_types(df)
    flagged, error = anomaly.find_anomalies(df, column_types, contamination=0.9)  # way out of range
    if error:
        return False, f"Unexpected error with an out-of-range contamination value: {error}"
    frac = len(flagged) / len(df)
    if frac > anomaly.MAX_CONTAMINATION + 0.05:
        return False, f"contamination=0.9 flagged {frac:.0%} of rows — clamp doesn't appear to be applied."
    return True, f"contamination=0.9 was clamped; {frac:.0%} of rows flagged (max allowed ~{anomaly.MAX_CONTAMINATION:.0%})."


def _case_anomaly_narration_fallback_no_model() -> tuple[bool, str]:
    rng = np.random.RandomState(2)
    normal = rng.normal(0, 1, (95, 2))
    outliers = rng.normal(20, 1, (5, 2))
    df = pd.DataFrame(np.vstack([normal, outliers]), columns=["a", "b"])
    column_types = data_engine.detect_column_types(df)
    flagged, error = anomaly.find_anomalies(df, column_types, contamination=0.1)
    if error or flagged is None or len(flagged) == 0:
        return False, f"Expected some flagged rows on an obvious-outlier dataset; error={error}."
    narration, narr_error = anomaly.narrate_anomalies(None, flagged, len(df))
    if narr_error is not None:
        return False, f"Expected no error from the model=None fallback path, got {narr_error!r}."
    if not narration or len(narration) < 10:
        return False, f"Fallback narration looks too short/empty: {narration!r}."
    return True, f"Fallback narration produced without Gemini: {narration[:80]!r}..."


def _case_anomaly_narration_empty_flagged() -> tuple[bool, str]:
    flagged = pd.DataFrame(columns=["a", "b", "anomaly_reason"])
    narration, error = anomaly.narrate_anomalies(None, flagged, 100)
    if error is not None:
        return False, f"Expected no error for an empty flagged set, got {error!r}."
    if "No rows" not in narration:
        return False, f"Expected the 'no anomalies' fallback message, got {narration!r}."
    return True, "Correctly handled the zero-flagged-rows case without calling Gemini."


CASES = [
    {"id": 1, "name": "default_hypotheses references real columns", "fn": _case_default_hypotheses_reference_real_columns},
    {"id": 2, "name": "default_hypotheses surfaces strong correlation", "fn": _case_default_hypotheses_finds_strong_correlation},
    {"id": 3, "name": "test_hypotheses confirms a real group effect", "fn": _case_test_hypotheses_confirms_real_effect},
    {"id": 4, "name": "test_hypotheses rejects independent columns", "fn": _case_test_hypotheses_rejects_noise},
    {"id": 5, "name": "test_hypotheses handles an untestable pairing", "fn": _case_test_hypotheses_handles_untestable},
    {"id": 6, "name": "generate_hypotheses falls back with model=None", "fn": _case_generate_hypotheses_falls_back_without_model},
    {"id": 7, "name": "anomaly contamination is clamped to a sane range", "fn": _case_anomaly_contamination_is_clamped},
    {"id": 8, "name": "anomaly narration fallback (no Gemini)", "fn": _case_anomaly_narration_fallback_no_model},
    {"id": 9, "name": "anomaly narration handles zero flagged rows", "fn": _case_anomaly_narration_empty_flagged},
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
        "# Prism — Hypothesis Engine + Anomaly Tuning Eval Results",
        "",
        f"**Accuracy: {evaluation['accuracy']}%** ({evaluation['n_passed']}/{evaluation['n_total']} test cases passed)",
        "",
        "Runs `modules.hypothesis_engine`'s rule-based fallback + real statistical "
        "verification pipeline, and `modules.anomaly`'s new configurable-sensitivity "
        "and narration-fallback paths, against synthetic datasets with known ground "
        "truth (a strong correlation, a strong group effect, pure noise). No Gemini "
        "API key required — every scored path is the deterministic fallback.",
        "",
        "| # | Case | Result |",
        "|---|------|--------|",
    ]
    status_labels = {"pass": "PASS", "fail": "FAIL"}
    for r in evaluation["results"]:
        detail = r["detail"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['name']} | **{status_labels[r['status']]}** — {detail} |")

    lines.append("")
    lines.append("## Failures in detail")
    failures = [r for r in evaluation["results"] if r["status"] == "fail"]
    if not failures:
        lines.append("None — every test case passed.")
    else:
        for r in failures:
            lines.append(f"### #{r['id']} — {r['name']}")
            lines.append(f"- {r['detail']}")
            lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    evaluation = run_eval()
    write_report(evaluation)
    print(f"Accuracy: {evaluation['accuracy']}% ({evaluation['n_passed']}/{evaluation['n_total']} passed) — see {RESULTS_PATH}")
