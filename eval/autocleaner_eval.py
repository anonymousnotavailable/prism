"""
Auto Cleaner Eval Harness — runs modules.autocleaner's scan -> plan ->
execute pipeline against 5 fixed test cases over the bundled Hell Mode
sample datasets, and asserts specific fixes get planned/applied. Writes
eval/autocleaner_eval_results.md with a pass/fail breakdown.

Unlike run_eval.py, this needs NO Gemini API key: Auto Cleaner's scan,
plan, and execution are fully deterministic — only the one-line narration
touches Gemini, and this eval never calls narrate_plan().

Run with:  python eval/autocleaner_eval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import autocleaner, data_engine  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
HELL_SAMPLES_DIR = EVAL_DIR.parent / "samples" / "hell"
RESULTS_PATH = EVAL_DIR / "autocleaner_eval_results.md"


def _load(filename: str) -> tuple[pd.DataFrame, dict, dict]:
    df = pd.read_csv(HELL_SAMPLES_DIR / filename)
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    return df, column_types, quality


def _case_parse_indian_number() -> tuple[bool, str]:
    df, column_types, quality = _load("indian_startup_funding_messy.csv")
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "parse_indian_number" and a["column"] == "funding_amount"), None)
    if action is None:
        return False, "No 'parse_indian_number' plan action for 'funding_amount'."
    if action["risk"] != "SAFE":
        return False, f"Expected SAFE risk, got {action['risk']}."
    new_df, new_types, _log, applied = autocleaner.execute_safe_actions(df, column_types, plan)
    if new_types.get("funding_amount") != "numeric":
        return False, f"'funding_amount' is {new_types.get('funding_amount')!r} after execution, expected 'numeric'."
    if not pd.api.types.is_numeric_dtype(new_df["funding_amount"]):
        return False, "'funding_amount' column dtype is not numeric after execution."
    return True, f"'funding_amount' parsed to numeric ({applied} SAFE action(s) applied)."


def _case_remove_exact_duplicates() -> tuple[bool, str]:
    df, column_types, quality = _load("product_events_messy.csv")
    before_dupes = int(df.duplicated().sum())
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "remove_exact_duplicates"), None)
    if action is None:
        return False, f"No 'remove_exact_duplicates' plan action (dataset has {before_dupes} exact duplicate row(s))."
    new_df, _new_types, _log, _applied = autocleaner.execute_safe_actions(df, column_types, plan)
    after_dupes = int(new_df.duplicated().sum())
    if after_dupes != 0:
        return False, f"{after_dupes} duplicate row(s) remain after execution (started with {before_dupes})."
    return True, f"{before_dupes} exact duplicate row(s) removed, 0 remain."


def _case_convert_disguised_nulls() -> tuple[bool, str]:
    df, column_types, quality = _load("product_events_messy.csv")
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "convert_disguised_nulls" and a["column"] == "device_type"), None)
    if action is None:
        return False, "No 'convert_disguised_nulls' plan action for 'device_type'."
    before_nulls = int(df["device_type"].isna().sum())
    new_df, _new_types, _log, _applied = autocleaner.execute_safe_actions(df, column_types, plan)
    after_nulls = int(new_df["device_type"].isna().sum())
    if after_nulls <= before_nulls:
        return False, f"Missing count in 'device_type' did not increase ({before_nulls} -> {after_nulls})."
    return True, f"'device_type' missing count rose from {before_nulls} to {after_nulls} (disguised nulls converted)."


def _case_normalize_units() -> tuple[bool, str]:
    df, column_types, quality = _load("product_events_messy.csv")
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "normalize_units" and a["column"] == "session_duration"), None)
    if action is None:
        return False, "No 'normalize_units' plan action for 'session_duration'."
    if action["risk"] != "REVIEW":
        return False, f"Expected REVIEW risk (target unit is a judgment call), got {action['risk']}."
    new_df, new_types, _desc, _code = autocleaner.apply_action(df, column_types, action)
    if new_types.get("session_duration") != "numeric":
        return False, f"'session_duration' is {new_types.get('session_duration')!r} after execution, expected 'numeric'."
    if not pd.api.types.is_numeric_dtype(new_df["session_duration"]):
        return False, "'session_duration' column dtype is not numeric after execution."
    return True, f"'session_duration' normalized to a single unit ({action['params']['target_unit']})."


def _case_already_clean_dataset() -> tuple[bool, str]:
    df = pd.DataFrame({
        "id": range(1, 21),
        "score": [round(50 + i * 1.3, 1) for i in range(20)],
        "category": (["alpha", "beta", "gamma"] * 7)[:20],
    })
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    if plan:
        offenders = ", ".join(f"{a['action']}({a['column']})" for a in plan)
        return False, f"Expected an empty plan for already-clean data, got {len(plan)} action(s): {offenders}."
    narration = autocleaner.narrate_plan(None, plan, health_score=96)
    if narration != "Scan complete. Nothing to fix — health score 96.":
        return False, f"Unexpected narration for empty plan: {narration!r}"
    return True, "Empty plan for already-clean data; narration matches expected template."


def _case_meaningful_na() -> tuple[bool, str]:
    # House Prices-style: PoolQC is NA for ~99% of houses because they simply
    # have no pool, not because the value is unknown.
    df = pd.DataFrame({
        "PoolQC": [None] * 99 + ["Gd"],
        "SalePrice": list(range(100, 200)),
    })
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "impute_missing" and a["column"] == "PoolQC"), None)
    if action is None:
        return False, "No 'impute_missing' plan action for 'PoolQC'."
    if action["params"].get("strategy") != "constant":
        return False, f"Expected the meaningful-NA path (strategy='constant'), got {action['params'].get('strategy')!r}."
    new_df, _new_types, _desc, _code = autocleaner.apply_action(df, column_types, action)
    if new_df["PoolQC"].isna().any():
        return False, "'PoolQC' still has NaN after applying the meaningful-NA fill."
    filled_count = (new_df["PoolQC"] == "Not Applicable").sum()
    if filled_count != 99:
        return False, f"Expected 99 rows marked 'Not Applicable', got {filled_count}."
    return True, "99% missing 'PoolQC' correctly filled with an explicit 'Not Applicable' category, not the mode."


def _case_zero_sentinel() -> tuple[bool, str]:
    # Pima Diabetes-style: Glucose=0 is biologically impossible, a disguised null.
    import numpy as np
    rng = np.random.default_rng(0)
    glucose = rng.normal(120, 20, 100)
    glucose[:5] = 0
    df = pd.DataFrame({"Glucose": glucose, "Outcome": rng.integers(0, 2, 100)})
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "convert_zero_sentinel" and a["column"] == "Glucose"), None)
    if action is None:
        return False, "No 'convert_zero_sentinel' plan action for 'Glucose'."
    if action["risk"] != "REVIEW":
        return False, f"Expected REVIEW risk (domain-knowledge call), got {action['risk']}."
    if any(a["action"] == "convert_zero_sentinel" and a["column"] == "Outcome" for a in plan):
        return False, "False positive: 'Outcome' (a legitimate 0/1 flag) was flagged as a zero sentinel."
    new_df, _new_types, _desc, _code = autocleaner.apply_action(df, column_types, action)
    if (new_df["Glucose"] == 0).any():
        return False, "'Glucose' still has zero values after applying the fix."
    if new_df["Glucose"].isna().sum() != 5:
        return False, f"Expected 5 NaN in 'Glucose', got {new_df['Glucose'].isna().sum()}."
    return True, "5 placeholder zeros in 'Glucose' converted to missing; legitimate 0/1 'Outcome' column left alone."


def _case_multi_value_split() -> tuple[bool, str]:
    # Netflix-style: 'listed_in' packs multiple comma-separated genres per cell.
    df = pd.DataFrame({
        "listed_in": ["Action, Adventure, Sci-Fi", "Comedy, Drama", "Documentaries", "Horror, Thriller", "Comedy"] * 20,
        "title": [f"Movie {i}" for i in range(100)],
    })
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    scan_results = autocleaner.scan(df, column_types, quality)
    plan = autocleaner.build_plan(df, column_types, scan_results)
    action = next((a for a in plan if a["action"] == "split_multi_value" and a["column"] == "listed_in"), None)
    if action is None:
        return False, "No 'split_multi_value' plan action for 'listed_in'."
    new_df, _new_types, _desc, _code = autocleaner.apply_action(df, column_types, action)
    if "listed_in_count" not in new_df.columns or "listed_in_primary" not in new_df.columns:
        return False, "Expected 'listed_in_count' and 'listed_in_primary' columns after applying the split."
    if new_df.loc[0, "listed_in_count"] != 3 or new_df.loc[0, "listed_in_primary"] != "Action":
        return False, f"Row 0 expected count=3/primary='Action', got count={new_df.loc[0, 'listed_in_count']}/primary={new_df.loc[0, 'listed_in_primary']!r}."
    return True, "Multi-value 'listed_in' column correctly surfaced as count + primary-value columns."


CASES = [
    {"id": 1, "name": "parse_indian_number (funding_amount)", "dataset": "indian_startup_funding_messy.csv", "fn": _case_parse_indian_number},
    {"id": 2, "name": "remove_exact_duplicates", "dataset": "product_events_messy.csv", "fn": _case_remove_exact_duplicates},
    {"id": 3, "name": "convert_disguised_nulls (device_type)", "dataset": "product_events_messy.csv", "fn": _case_convert_disguised_nulls},
    {"id": 4, "name": "normalize_units (session_duration)", "dataset": "product_events_messy.csv", "fn": _case_normalize_units},
    {"id": 5, "name": "already-clean dataset -> empty plan", "dataset": "(synthetic)", "fn": _case_already_clean_dataset},
    {"id": 6, "name": "meaningful NA (PoolQC, House Prices-style)", "dataset": "(synthetic)", "fn": _case_meaningful_na},
    {"id": 7, "name": "zero sentinel (Glucose, Pima Diabetes-style)", "dataset": "(synthetic)", "fn": _case_zero_sentinel},
    {"id": 8, "name": "multi-value split (listed_in, Netflix-style)", "dataset": "(synthetic)", "fn": _case_multi_value_split},
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
        "# Prism — Auto Cleaner Eval Results",
        "",
        f"**Accuracy: {evaluation['accuracy']}%** ({evaluation['n_passed']}/{evaluation['n_total']} test cases passed)",
        "",
        "Runs `modules.autocleaner`'s scan -> plan -> execute pipeline directly against the bundled "
        "Hell Mode sample datasets and asserts specific fixes get planned and applied. No Gemini API "
        "key required — the plan and its execution are fully deterministic; only the optional one-line "
        "narration touches Gemini, and this eval never calls it in the scored path.",
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
