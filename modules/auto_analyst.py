"""
Auto Analyst — the agentic "Run Full Analysis" flow. Gemini first drafts an
ordered analysis plan (JSON: quality check -> distributions -> segments ->
correlations -> time trends if a datetime column exists -> conclusions),
then each step's pandas code is generated and run through the same
safe-execution sandbox as the AI Analyst chat tab, and finally Gemini
synthesizes the accumulated results into 5 headline findings.

Reuses modules.ai_analyst's Gemini plumbing (build_data_context, call_gemini,
ask_and_execute, parse_numbered_bullets) instead of duplicating any of it —
this module only adds the plan generation and multi-step orchestration on top.

verify_findings() closes the loop into a self-verifying agent: Gemini's prose
is fluent but not grounded, so every finding gets cross-checked against a
real scipy.stats hypothesis test (via modules.stats_lab) run on whichever
columns the finding actually names. A claim that doesn't survive its own
significance test gets flagged rather than trusted at face value — zero
extra Gemini calls, zero extra network I/O.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd

from modules import stats_lab
from modules.ai_analyst import ask_and_execute, build_data_context, call_gemini, parse_numbered_bullets

PLAN_SYSTEM_PROMPT = (
    "You are a senior data analyst planning an exploratory analysis of a pandas "
    "DataFrame called `df`. Given the dataframe's schema, a sample, and summary "
    "statistics, produce an ORDERED analysis plan as a JSON array. Each element "
    "must be an object with keys \"title\" (3-6 words) and \"question\" (a specific, "
    "self-contained analysis question that could be answered with pandas code, "
    "written the way a user would type it into a chat box).\n\n"
    "Cover, in this order, whichever are relevant to the data:\n"
    "1) a data quality check (missing values, duplicates, outliers)\n"
    "2) distributions of the key numeric/categorical columns\n"
    "3) interesting segments or groups (group-by comparisons)\n"
    "4) correlations between numeric columns\n"
    "5) time trends, ONLY if a datetime column exists\n"
    "6) a final synthesis step summarizing conclusions\n\n"
    "Return 4 to 6 steps total. Return ONLY the JSON array, no prose, no markdown "
    "code fences."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

_FINDINGS_PROMPT_TEMPLATE = (
    "You just ran the following exploratory analysis steps on a pandas DataFrame "
    "and got these results:\n\n{step_summaries}\n\n"
    "You are a senior data analyst. Based only on the results above, write exactly "
    "5 concise, business-relevant findings. Each finding MUST reference a concrete "
    "number from the results above — do not write vague statements. Format your "
    "response as exactly 5 lines, each starting with '1. ' through '5. ', with no "
    "other text before or after."
)


def _default_plan(column_types: dict[str, str]) -> list[dict]:
    """Fallback plan used when Gemini is unavailable or its JSON can't be parsed.

    Auto Analyst is a one-click feature — a plan-generation hiccup shouldn't
    block the whole run, so this always returns something runnable.
    """
    values = column_types.values()
    has_datetime = "datetime" in values
    has_categorical = "categorical" in values
    has_numeric = "numeric" in values

    plan = [
        {
            "title": "Data quality check",
            "question": "Summarize missing values, duplicate rows, and outliers in df.",
        }
    ]
    if has_numeric:
        plan.append(
            {
                "title": "Distributions",
                "question": "Describe the distribution (mean, median, std, min, max) of each numeric column in df.",
            }
        )
    if has_categorical:
        plan.append(
            {
                "title": "Segments",
                "question": (
                    "For each categorical column with a manageable number of categories, show the count "
                    "per category, and if a numeric column exists, the average of the main numeric column "
                    "per category."
                ),
            }
        )
    if has_numeric:
        plan.append(
            {
                "title": "Correlations",
                "question": "Compute the correlation matrix between numeric columns in df and identify the strongest pairwise correlation.",
            }
        )
    if has_datetime:
        plan.append(
            {
                "title": "Time trends",
                "question": "Show how the main numeric column trends over time, grouped by the datetime column at a sensible frequency.",
            }
        )
    plan.append(
        {
            "title": "Conclusions",
            "question": "Summarize the overall shape of df: row/column count, key data quality issues, and the single most notable pattern found.",
        }
    )
    return plan


def generate_analysis_plan(model, df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Ask Gemini for an ordered analysis plan.

    Always returns a usable plan — falls back to a sensible default built
    from column_types on any error, bad JSON, or empty response, since the
    whole point of this feature is a single button that "just works".
    """
    if model is None:
        return _default_plan(column_types)

    context = build_data_context(df, column_types)
    prompt = f"{PLAN_SYSTEM_PROMPT}\n\nData context:\n{context}"
    text, error = call_gemini(model, prompt)
    if error:
        return _default_plan(column_types)

    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return _default_plan(column_types)

    try:
        raw_plan = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _default_plan(column_types)

    cleaned = [
        {"title": str(step.get("title") or f"Step {i + 1}"), "question": str(step["question"])}
        for i, step in enumerate(raw_plan)
        if isinstance(step, dict) and step.get("question")
    ]
    return cleaned or _default_plan(column_types)


def run_plan_step(model, df: pd.DataFrame, column_types: dict[str, str], step: dict, chat_history: list[dict]) -> dict:
    """Execute one plan step through the existing self-healing chat pipeline.

    Returns the same dict shape as ai_analyst.ask_and_execute (code, result,
    error, ask_error, retried, original_error) plus "title" and "question"
    for display in the progress panel.
    """
    outcome = ask_and_execute(model, df, column_types, step["question"], chat_history)
    outcome["title"] = step["title"]
    outcome["question"] = step["question"]
    return outcome


def _summarize_result(result) -> str:
    """Stringify a step's result compactly enough to fit in a follow-up prompt."""
    if result is None:
        return "(no result)"
    if isinstance(result, (pd.DataFrame, pd.Series)):
        return result.head(10).to_string()
    return str(result)


def synthesize_findings(model, step_outcomes: list[dict]) -> tuple[list[str], Optional[str]]:
    """Ask Gemini to turn the accumulated step results into 5 headline findings.

    Returns (bullets, error). Steps that failed or errored are excluded from
    the summary prompt so a single bad step doesn't sink the whole synthesis.
    """
    if model is None:
        return [], "No Gemini model available."

    summaries = [
        f"- {outcome['title']}: {_summarize_result(outcome.get('result'))}"
        for outcome in step_outcomes
        if not outcome.get("error") and not outcome.get("ask_error")
    ]
    if not summaries:
        return [], "No successful analysis steps to summarize."

    prompt = _FINDINGS_PROMPT_TEMPLATE.format(step_summaries="\n\n".join(summaries))
    text, error = call_gemini(model, prompt)
    if error:
        return [], error
    return parse_numbered_bullets(text), None


def _find_mentioned_columns(text: str, columns: list[str]) -> list[str]:
    """Which of `columns` are actually named in `text`, in order of first
    appearance. Matches on word boundaries (so a column called "age" doesn't
    false-positive inside "average") against both the raw column name and an
    underscore/dash-to-space variant (so "unit_price" also matches the prose
    "unit price", which is how a model or a human would actually write it).
    """
    lower_text = text.lower()
    hits: list[tuple[int, str]] = []
    for col in columns:
        variants = {col.lower(), col.lower().replace("_", " ").replace("-", " ")}
        earliest: Optional[int] = None
        for variant in variants:
            if not variant.strip():
                continue
            match = re.search(r"\b" + re.escape(variant) + r"\b", lower_text)
            if match and (earliest is None or match.start() < earliest):
                earliest = match.start()
        if earliest is not None:
            hits.append((earliest, col))
    hits.sort(key=lambda pair: pair[0])
    return [col for _, col in hits]


def verify_findings(df: pd.DataFrame, column_types: dict[str, str], findings: list[str]) -> list[dict]:
    """Cross-check each headline finding against a real statistical test.

    For every finding, name-match it against the dataframe's columns and, if
    two testable (numeric/categorical) columns are mentioned, run the same
    suggest_test()/run_test() pipeline Stats Lab uses on them. Returns one
    dict per finding, same order, each with a "status":
      - "verified"       — a hypothesis test ran and came back significant (p<0.05)
      - "not_significant" — a test ran but did NOT support the claim (p>=0.05)
      - "not_testable"    — fewer than 2 matching columns, or the test couldn't run

    This never calls Gemini and never touches the network — it's a pure
    pandas/scipy pass, so it's cheap enough to run on every Auto Analyst run.
    """
    testable_types = {"numeric", "categorical"}
    columns = list(column_types.keys())
    results: list[dict] = []

    for text in findings:
        mentioned = [c for c in _find_mentioned_columns(text, columns) if column_types.get(c) in testable_types]
        # dedupe while preserving order (a column matched via two variants shouldn't count twice)
        seen: set[str] = set()
        mentioned = [c for c in mentioned if not (c in seen or seen.add(c))]

        if len(mentioned) < 2:
            results.append({
                "status": "not_testable",
                "detail": "No two matching columns named in this finding to run a hypothesis test against.",
                "test": None, "p_value": None, "columns": mentioned,
            })
            continue

        col_a, col_b = mentioned[0], mentioned[1]
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            results.append({
                "status": "not_testable", "detail": suggestion["error"],
                "test": None, "p_value": None, "columns": [col_a, col_b],
            })
            continue

        result = stats_lab.run_test(df, suggestion)
        if result.get("error"):
            results.append({
                "status": "not_testable", "detail": result["error"],
                "test": suggestion.get("test"), "p_value": None, "columns": [col_a, col_b],
            })
            continue

        significant = result["p_value"] < 0.05
        results.append({
            "status": "verified" if significant else "not_significant",
            "detail": stats_lab.interpret_result(result),
            "test": stats_lab.TEST_LABELS[result["test"]],
            "p_value": result["p_value"],
            "columns": [col_a, col_b],
        })

    return results
