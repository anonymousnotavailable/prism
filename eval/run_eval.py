"""
Code-Gen Eval Harness — runs modules.ai_analyst's question -> pandas code ->
execution pipeline against eval/questions.json (20 fixed Q&A pairs over the
bundled sample datasets, after the same Smart Type Coercion cleanup a user
would apply) and scores each answer against a fixed ground truth. Writes
eval_results.md with the overall accuracy and a per-question breakdown.

Run with:  python eval/run_eval.py
Needs a working GEMINI_API_KEY (.env or environment) — this exercises the
real AI pipeline, not a mock.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import ai_analyst, data_engine, type_coercion  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = EVAL_DIR.parent / "samples"
HELL_SAMPLES_DIR = SAMPLES_DIR / "hell"
QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_PATH = EVAL_DIR / "eval_results.md"


def _prep_dataset(filename: str) -> tuple[pd.DataFrame, dict]:
    """Load a sample CSV (checking samples/ then samples/hell/) and
    auto-apply Smart Type Coercion, mirroring how a user would clean it
    before asking questions in the AI Analyst tab.
    """
    path = SAMPLES_DIR / filename
    if not path.exists():
        path = HELL_SAMPLES_DIR / filename
    with open(path, "rb") as f:
        df, error, _warnings = data_engine.load_data(f)
    if error:
        raise RuntimeError(f"Failed to load {filename}: {error}")

    column_types = data_engine.detect_column_types(df)
    for candidate in type_coercion.detect_numeric_candidates(df, column_types):
        df, _ = type_coercion.convert_column(df, candidate["column"])
    column_types = data_engine.detect_column_types(df)
    return df, column_types


def _extract_scalar(result):
    """Pull a single numeric value out of a pandas result, or None if it
    isn't scalar-shaped (a multi-row/column answer can't be scored numerically).
    """
    if isinstance(result, (int, float, np.integer, np.floating)):
        return float(result)
    if isinstance(result, pd.Series) and len(result) == 1:
        return float(result.iloc[0])
    if isinstance(result, pd.DataFrame) and result.shape == (1, 1):
        return float(result.iloc[0, 0])
    return None


def check_answer(result, check: dict) -> tuple[bool, str]:
    """Grade one result against its ground-truth check. Returns (passed, detail)."""
    if result is None:
        return False, "No result produced."

    check_type = check["type"]
    if check_type == "numeric":
        value = _extract_scalar(result)
        if value is None:
            return False, f"Could not extract a numeric scalar from a {type(result).__name__} result."
        expected = check["expected"]
        tolerance = max(abs(expected) * check.get("tolerance_pct", 2.0) / 100, check.get("abs_tolerance", 0))
        passed = abs(value - expected) <= tolerance
        return passed, f"Got {value:.2f}, expected {expected} (tolerance +/- {tolerance:.2f})."

    if check_type == "contains_text":
        text = str(result).lower()
        expected_substr = str(check["expected"]).lower()
        passed = expected_substr in text
        return passed, f"Expected to find '{check['expected']}' in the result."

    return False, f"Unknown check type '{check_type}'."


def run_eval() -> dict:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    model = ai_analyst.get_model()
    if model is None:
        raise RuntimeError("No Gemini API key found (GEMINI_API_KEY) — set it in .env to run the eval harness.")

    dataset_cache: dict[str, tuple[pd.DataFrame, dict]] = {}
    results = []
    quota_hit = False

    for q in questions:
        if quota_hit:
            results.append({**q, "status": "not_run", "detail": "Skipped — Gemini free-tier quota already exhausted this run.", "code": None})
            continue

        dataset_name = q["dataset"]
        if dataset_name not in dataset_cache:
            dataset_cache[dataset_name] = _prep_dataset(dataset_name)
        df, column_types = dataset_cache[dataset_name]

        outcome = ai_analyst.ask_and_execute(model, df, column_types, q["question"], [])

        if outcome["ask_error"]:
            if "quota" in outcome["ask_error"].lower():
                quota_hit = True
                results.append({**q, "status": "not_run", "detail": "Gemini free-tier quota exceeded.", "code": None})
            else:
                results.append({**q, "status": "fail", "detail": f"Gemini request failed: {outcome['ask_error']}", "code": None})
            continue
        if outcome["error"]:
            results.append({**q, "status": "fail", "detail": f"Execution failed: {outcome['error']}", "code": outcome["code"]})
            continue

        passed, detail = check_answer(outcome["result"], q["check"])
        results.append({**q, "status": "pass" if passed else "fail", "detail": detail, "code": outcome["code"]})

    n_passed = sum(r["status"] == "pass" for r in results)
    n_evaluated = sum(r["status"] != "not_run" for r in results)
    n_not_run = sum(r["status"] == "not_run" for r in results)
    accuracy = round(100 * n_passed / n_evaluated, 1) if n_evaluated else 0.0
    return {
        "results": results, "n_passed": n_passed, "n_evaluated": n_evaluated,
        "n_not_run": n_not_run, "n_total": len(results), "accuracy": accuracy,
    }


def write_report(evaluation: dict) -> None:
    partial_note = ""
    if evaluation["n_not_run"]:
        partial_note = (
            f"\n> **Partial run:** {evaluation['n_not_run']} question(s) were skipped after hitting the Gemini "
            "free-tier daily quota mid-run — they count toward neither passes nor failures. Re-run "
            "`python eval/run_eval.py` once the quota resets (or with a fresh API key) for a full score.\n"
        )

    lines = [
        "# Prism — Code-Gen Eval Results",
        "",
        f"**Accuracy: {evaluation['accuracy']}%** ({evaluation['n_passed']}/{evaluation['n_evaluated']} evaluated questions passed)",
        partial_note,
        "Runs each question in `questions.json` through the real AI Analyst pipeline "
        "(`modules.ai_analyst.ask_and_execute` — Gemini-generated pandas code, run in the "
        "safe-execution sandbox) against the bundled sample datasets, after the same Smart "
        "Type Coercion cleanup a user would apply in the app, and checks the result against "
        "a fixed ground truth.",
        "",
        "| # | Dataset | Question | Result |",
        "|---|---------|----------|--------|",
    ]
    status_labels = {"pass": "PASS", "fail": "FAIL", "not_run": "NOT RUN"}
    for r in evaluation["results"]:
        detail = r["detail"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['dataset']} | {r['question']} | **{status_labels[r['status']]}** — {detail} |")

    lines.append("")
    lines.append("## Failures in detail")
    failures = [r for r in evaluation["results"] if r["status"] == "fail"]
    if not failures:
        lines.append("None — every evaluated question passed.")
    else:
        for r in failures:
            lines.append(f"### #{r['id']} — {r['question']}")
            lines.append(f"- Dataset: {r['dataset']}")
            lines.append(f"- {r['detail']}")
            if r.get("code"):
                lines.append("- Generated code:")
                lines.append("```python")
                lines.append(r["code"])
                lines.append("```")
            lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    evaluation = run_eval()
    write_report(evaluation)
    print(
        f"Accuracy: {evaluation['accuracy']}% ({evaluation['n_passed']}/{evaluation['n_evaluated']} evaluated, "
        f"{evaluation['n_not_run']} not run) — see {RESULTS_PATH}"
    )
