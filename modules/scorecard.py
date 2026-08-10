"""
Data Quality Scorecard — turns the existing 0-100 Data Health Score
(`data_engine.get_health_breakdown()`) into a shareable, exportable report:
a letter grade, a ranked list of issues with concrete recommendations, and
optional Gemini-written executive summary. Deliberately does not recompute
any quality signal itself — every number here traces back to the same
health-score components already shown in the Overview tab, so the export
can never disagree with what the app displays.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

import pandas as pd

from modules.data_engine import HEALTH_COMPONENT_WEIGHTS

# Standard US-style letter grading, same bands most data-quality tooling
# (and most portfolios' "test coverage" badges) already use — familiar to
# a reviewing panel without needing a legend.
_GRADE_BANDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F")]

_COMPONENT_LABELS = {
    "completeness": "Completeness",
    "consistency": "Consistency",
    "uniqueness": "Uniqueness",
    "validity": "Validity",
    "outlier_burden": "Outlier Burden",
}

# One rule-based recommendation per weak component, each pointing at the
# specific Prism tab/tool that addresses it — keeps the scorecard actionable
# instead of just a diagnosis.
_RECOMMENDATIONS = {
    "completeness": "Missing values are dragging the score down — use the Data Processing "
    "panel or Auto Clean to impute or drop sparse columns.",
    "consistency": "Several columns are still stuck as free text instead of a proper type — "
    "run type coercion (or Hell Mode for messy real-world formats) to fix this.",
    "uniqueness": "Duplicate rows were found — review and drop them from the Clean tab "
    "before running any statistics that assume independent observations.",
    "validity": "Unmasked PII or fully-empty columns were found — check the PII Shield and "
    "drop any all-null columns before sharing this dataset externally.",
    "outlier_burden": "A high share of numeric values fall outside the IQR fences — run "
    "Anomaly Detection (ensemble mode recommended) before trusting summary statistics.",
}


def grade_for_score(score: float) -> str:
    """Map a 0-100 health score to a letter grade (A/B/C/D/F)."""
    for threshold, grade in _GRADE_BANDS:
        if score >= threshold:
            return grade
    return "F"  # unreachable given the 0-threshold band, kept for clarity


def build_scorecard(
    df: pd.DataFrame,
    column_types: dict[str, str],
    quality_report: dict,
    health_breakdown: dict,
    dataset_name: str = "Untitled dataset",
) -> dict:
    """Assemble the full scorecard dict from already-computed quality data.

    `health_breakdown` is `data_engine.get_health_breakdown()`'s output —
    this function synthesizes it into components/issues/recommendations,
    it does not touch the dataframe for scoring (only for shape/dtypes
    already implied by column_types, kept as a parameter for the report
    header and to keep the signature symmetric with the detectors it
    reports on).
    """
    overall_score = health_breakdown["total"]
    components = [
        {
            "key": key,
            "label": _COMPONENT_LABELS[key],
            "score": health_breakdown[key],
            "max": weight,
            "pct": round(100 * health_breakdown[key] / weight, 1) if weight else 100.0,
        }
        for key, weight in HEALTH_COMPONENT_WEIGHTS.items()
    ]

    # A component under 70% of its own max weight is "weak enough to flag" —
    # independent of the other components, so a dataset can have several
    # issues even with a passable overall score.
    issues = [
        {
            "component": c["key"],
            "label": c["label"],
            "score": c["score"],
            "max": c["max"],
            "pct": c["pct"],
        }
        for c in components
        if c["pct"] < 70
    ]
    issues.sort(key=lambda i: i["pct"])

    recommendations = [
        {"component": issue["component"], "text": _RECOMMENDATIONS[issue["component"]]} for issue in issues
    ]

    return {
        "dataset_name": dataset_name,
        "shape": tuple(df.shape),
        "overall_score": overall_score,
        "grade": grade_for_score(overall_score),
        "components": components,
        "issues": issues,
        "recommendations": recommendations,
        "duplicate_rows": quality_report.get("duplicate_rows", 0),
        "total_missing_pct": quality_report.get("total_missing_pct", 0.0),
    }


def render_markdown_scorecard(card: dict) -> str:
    """Render a scorecard dict as a standalone Markdown report — suitable
    for a download button or pasting into a PR/README as evidence of a
    data-quality pass.
    """
    lines = [
        f"# Data Quality Scorecard — {card['dataset_name']}",
        "",
        f"**Overall Score: {card['overall_score']} / 100 (Grade {card['grade']})**",
        "",
        f"- Rows x Columns: {card['shape'][0]:,} x {card['shape'][1]}",
        f"- Missing cells: {card['total_missing_pct']}%",
        f"- Duplicate rows: {card['duplicate_rows']:,}",
        "",
        "## Component Breakdown",
        "",
        "| Component | Score | Max | % |",
        "|---|---|---|---|",
    ]
    for c in card["components"]:
        lines.append(f"| {c['label']} | {c['score']} | {c['max']} | {c['pct']}% |")

    lines += ["", "## Issues Found"]
    if not card["issues"]:
        lines.append("")
        lines.append("No components scored below the 70% flag threshold — clean bill of health.")
    else:
        lines.append("")
        for issue in card["issues"]:
            lines.append(f"- **{issue['label']}** — {issue['score']}/{issue['max']} ({issue['pct']}%)")

    lines += ["", "## Recommendations"]
    if not card["recommendations"]:
        lines.append("")
        lines.append("No action needed.")
    else:
        lines.append("")
        for rec in card["recommendations"]:
            lines.append(f"- {rec['text']}")

    return "\n".join(lines) + "\n"


def render_json_scorecard(card: dict) -> str:
    """Render a scorecard dict as pretty-printed JSON — for programmatic
    consumption (CI gates, dashboards) rather than human reading.
    """
    exportable = dict(card)
    exportable["shape"] = list(card["shape"])  # tuples aren't valid JSON
    return json.dumps(exportable, indent=2)


def fingerprint_scorecard(card: dict) -> str:
    """A short, stable hash of a scorecard — used to cache the AI executive
    summary below so re-viewing the same scorecard doesn't re-spend a
    Gemini call. Changes whenever the score or any issue changes.
    """
    key = f"{card['dataset_name']}|{card['overall_score']}|" + "|".join(
        f"{i['component']}:{i['score']}" for i in card["issues"]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data analyst writing a 3-4 sentence executive summary of a data "
    "quality scorecard for a stakeholder who isn't technical. Overall score: {score}/100 "
    "(Grade {grade}). Issues found:\n\n{issues_text}\n\n"
    "Explain in plain English whether this dataset is ready to analyze as-is, what the "
    "biggest risk is if it's used without cleanup, and one concrete next step. "
    "Do not simply restate the numbers back."
)


def narrate_scorecard(model, card: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn a scorecard into a short executive summary.

    Returns (narration, error). Callers should cache the result keyed by
    `fingerprint_scorecard(card)`, same caching pattern as
    `anomaly.narrate_anomalies()` / `auto_insights.narrate_insights()`.
    """
    if model is None:
        return "", "No Gemini model available for narration."

    if card["issues"]:
        issues_text = "\n".join(f"- {i['label']}: {i['score']}/{i['max']} ({i['pct']}%)" for i in card["issues"])
    else:
        issues_text = "None — every component scored above the flag threshold."

    prompt = _NARRATION_PROMPT.format(score=card["overall_score"], grade=card["grade"], issues_text=issues_text)

    from modules.ai_analyst import call_gemini

    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
