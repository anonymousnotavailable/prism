"""
Data Quality Scorecard — turns the existing weighted Data Health Score
(data_engine.get_health_breakdown) into a standalone, letter-graded,
shareable artifact: per-column A-F grades, prioritized remediation
bullets, and a self-contained HTML or Markdown export.

Fully deterministic — no Gemini call anywhere in this module. Distinct
from modules/report.py's full Auto-EDA HTML export (a kitchen-sink dump
of quality + stats + charts): this is a focused, single-purpose,
portfolio-ready deliverable a candidate can hand to a stakeholder or
paste straight into a GitHub README.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

GRADE_THRESHOLDS = [(90, "A"), (80, "B"), (65, "C"), (50, "D")]

# Per-column scoring penalties (0-100 scale, same spirit as
# data_engine.HEALTH_COMPONENT_WEIGHTS but applied per-column instead of
# dataset-wide).
_TEXT_TYPE_PENALTY = 15
_OUTLIER_PENALTY_CAP = 20


def grade_for_score(score: float) -> str:
    """Map a 0-100 score to a letter grade (A-F)."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def build_column_grades(quality_report: dict, column_types: dict[str, str]) -> list[dict]:
    """Per-column quality grade, worst-first, with plain-English issues.

    Mirrors the same signals data_engine.get_health_breakdown weighs at the
    dataset level (missing data, unresolved types, outlier burden, fully-
    empty columns) but keeps a score per column so a scorecard reader can
    see exactly which columns are dragging the overall grade down.
    """
    all_null_cols = set(quality_report.get("all_null_columns", []))
    grades = []

    for col, missing_pct in quality_report["missing_by_column"].items():
        ctype = column_types.get(col, "unknown")
        issues: list[str] = []

        if col in all_null_cols:
            score = 0.0
            issues.append("entirely empty — no usable data")
        else:
            score = 100.0
            if missing_pct > 0:
                score -= missing_pct
                issues.append(f"{missing_pct}% missing")
            if ctype == "text":
                score -= _TEXT_TYPE_PENALTY
                issues.append("unresolved type (stuck as free text)")
            outlier_pct = quality_report["outliers"].get(col, {}).get("pct", 0)
            if outlier_pct:
                score -= min(outlier_pct, _OUTLIER_PENALTY_CAP)
                issues.append(f"{outlier_pct}% IQR outliers")

        score = max(0.0, min(100.0, score))
        grades.append(
            {
                "column": col,
                "type": ctype,
                "score": round(score),
                "grade": grade_for_score(score),
                "issues": issues,
            }
        )

    grades.sort(key=lambda g: g["score"])
    return grades


def build_scorecard(
    df: pd.DataFrame, quality_report: dict, health_breakdown: dict, column_types: dict[str, str]
) -> dict:
    """Assemble the full scorecard data (no HTML/Markdown here — see the
    render_* functions below for that), ready to hand to either export.
    """
    column_grades = build_column_grades(quality_report, column_types)

    remediation = []
    for g in column_grades:
        if g["grade"] in ("D", "F") and g["issues"]:
            remediation.append(f"**{g['column']}** ({g['grade']}): {'; '.join(g['issues'])}")
    if quality_report.get("duplicate_rows", 0) > 0:
        remediation.append(
            f"{quality_report['duplicate_rows']} duplicate row(s) found — consider deduplicating before analysis."
        )

    return {
        "overall_score": health_breakdown["total"],
        "overall_grade": grade_for_score(health_breakdown["total"]),
        "component_breakdown": {
            k: v for k, v in health_breakdown.items() if k != "total"
        },
        "n_rows": quality_report["n_rows"],
        "n_cols": quality_report["n_cols"],
        "duplicate_rows": quality_report.get("duplicate_rows", 0),
        "column_grades": column_grades,
        "remediation": remediation,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


_SCORECARD_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  body { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; background: linear-gradient(180deg, #0A0C10 0%, #0D1016 100%);
    color: #F1F5F9; padding: 2.5rem; max-width: 900px; margin: 0 auto; }
  h1 { font-weight: 800; letter-spacing: -0.02em; border-bottom: 2px solid #22D3EE; padding-bottom: 0.6rem; }
  h2 { color: #22D3EE; font-weight: 700; margin-top: 2.25rem; }
  p { color: #8A97A8; }
  .score-badge { display: inline-flex; align-items: center; gap: 0.75rem; background: #12151B; border: 1px solid #232833;
    border-radius: 16px; padding: 1.25rem 2rem; margin: 1rem 0; }
  .score-badge .grade { font-size: 3rem; font-weight: 800; color: #22D3EE; }
  .score-badge .num { font-size: 1.1rem; color: #8A97A8; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; border-radius: 10px; overflow: hidden; }
  th, td { border: 1px solid #232833; padding: 8px 12px; text-align: left; font-size: 0.9rem; }
  th { background: #12151B; color: #22D3EE; font-weight: 600; }
  tr:nth-child(even) { background: #12151B; }
  .grade-A { color: #4ADE80; font-weight: 700; } .grade-B { color: #86EFAC; font-weight: 700; }
  .grade-C { color: #FBBF24; font-weight: 700; } .grade-D { color: #FB923C; font-weight: 700; }
  .grade-F { color: #F87171; font-weight: 700; }
  ul { color: #F1F5F9; } li { margin: 0.4rem 0; }
  .footer { margin-top: 3rem; color: #8A97A8; font-size: 0.8rem; border-top: 1px solid #232833; padding-top: 1.25rem; }
</style>
"""


def render_scorecard_html(scorecard: dict) -> str:
    """Standalone, self-contained HTML scorecard — download-and-share ready."""
    rows_html = "".join(
        f"<tr><td>{g['column']}</td><td class='grade-{g['grade']}'>{g['grade']}</td>"
        f"<td>{g['score']}/100</td><td>{g['type']}</td>"
        f"<td>{'; '.join(g['issues']) if g['issues'] else '—'}</td></tr>"
        for g in scorecard["column_grades"]
    )
    component_rows = "".join(
        f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v}</td></tr>"
        for k, v in scorecard["component_breakdown"].items()
    )
    remediation_html = (
        "<ul>" + "".join(f"<li>{r}</li>" for r in scorecard["remediation"]) + "</ul>"
        if scorecard["remediation"]
        else "<p>No remediation items — every column scores at or above a 'D' threshold.</p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Prism — Data Quality Scorecard</title>
  {_SCORECARD_CSS}
</head>
<body>
  <h1>Data Quality Scorecard</h1>
  <p>Generated {scorecard['generated_at']} &middot; {scorecard['n_rows']:,} rows &times; {scorecard['n_cols']} columns</p>
  <div class="score-badge">
    <span class="grade grade-{scorecard['overall_grade']}">{scorecard['overall_grade']}</span>
    <span class="num">{scorecard['overall_score']} / 100 overall</span>
  </div>
  <h2>Score Breakdown</h2>
  <table><tr><th>Component</th><th>Points</th></tr>{component_rows}</table>
  <h2>Per-Column Grades</h2>
  <table><tr><th>Column</th><th>Grade</th><th>Score</th><th>Type</th><th>Issues</th></tr>{rows_html}</table>
  <h2>Remediation</h2>
  {remediation_html}
  <div class="footer">Generated by Prism — an Auto-EDA tool with an AI analyst layer.</div>
</body>
</html>"""


def render_scorecard_markdown(scorecard: dict) -> str:
    """Portfolio-ready Markdown export — pastes cleanly into a GitHub README
    or PR description, no HTML dependency.
    """
    lines = [
        "# Data Quality Scorecard",
        "",
        f"Generated {scorecard['generated_at']} · {scorecard['n_rows']:,} rows × {scorecard['n_cols']} columns",
        "",
        f"## Overall: {scorecard['overall_grade']} ({scorecard['overall_score']} / 100)",
        "",
        "| Component | Points |",
        "|---|---|",
    ]
    for k, v in scorecard["component_breakdown"].items():
        lines.append(f"| {k.replace('_', ' ').title()} | {v} |")

    lines += ["", "## Per-Column Grades", "", "| Column | Grade | Score | Type | Issues |", "|---|---|---|---|---|"]
    for g in scorecard["column_grades"]:
        issues = "; ".join(g["issues"]) if g["issues"] else "—"
        lines.append(f"| {g['column']} | {g['grade']} | {g['score']}/100 | {g['type']} | {issues} |")

    lines += ["", "## Remediation", ""]
    if scorecard["remediation"]:
        lines += [f"- {r}" for r in scorecard["remediation"]]
    else:
        lines.append("No remediation items — every column scores at or above a 'D' threshold.")

    return "\n".join(lines)
