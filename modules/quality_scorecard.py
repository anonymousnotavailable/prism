"""
Data Quality Scorecard — turns the Overview tab's 0-100 Data Health Score
(`data_engine.get_health_breakdown`) into a per-column, letter-graded
scorecard suitable for handing to someone who never opens Prism: a
manager, a data-governance reviewer, or evidence of a repeatable quality
process in a portfolio writeup.

Deliberately does no new scanning — it re-shapes the same
`get_data_quality_report()` / `get_health_breakdown()` outputs the Overview
tab already computes, so building the scorecard costs nothing extra.
"""

from __future__ import annotations

import pandas as pd

from modules.data_engine import HEALTH_COMPONENT_WEIGHTS

# (minimum score, letter) pairs, checked highest-first.
LETTER_THRESHOLDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F")]

# Per-column composite: completeness carries more weight than outlier
# cleanliness because a missing value is unusable in every downstream
# analysis, while an outlier is often a legitimate rare event.
COLUMN_COMPLETENESS_WEIGHT = 60
COLUMN_CLEANLINESS_WEIGHT = 40
OUTLIER_PCT_FOR_ZERO_CLEANLINESS = 50.0  # >=50% outlier rows -> cleanliness score bottoms out


def letter_grade(score: float) -> str:
    """Map a 0-100 score to a letter grade (A/B/C/D/F)."""
    for threshold, letter in LETTER_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def _column_grade(column: str, col_type: str, missing_pct: float, outlier_info: dict | None) -> dict:
    completeness_score = COLUMN_COMPLETENESS_WEIGHT * (1 - missing_pct / 100)
    if col_type == "numeric" and outlier_info:
        outlier_pct = outlier_info.get("pct", 0.0)
        cleanliness_score = COLUMN_CLEANLINESS_WEIGHT * max(0.0, 1 - outlier_pct / OUTLIER_PCT_FOR_ZERO_CLEANLINESS)
    else:
        # Non-numeric columns aren't outlier-scored — don't penalize them
        # for a check that doesn't apply.
        outlier_pct = None
        cleanliness_score = COLUMN_CLEANLINESS_WEIGHT

    score = round(max(0.0, min(100.0, completeness_score + cleanliness_score)), 1)
    return {
        "column": column,
        "type": col_type,
        "missing_pct": missing_pct,
        "outlier_pct": outlier_pct,
        "score": score,
        "grade": letter_grade(score),
    }


def build_scorecard(
    df: pd.DataFrame, column_types: dict[str, str], quality_report: dict, health_breakdown: dict
) -> dict:
    """Assemble the full scorecard: overall grade, per-component grades,
    every column graded individually, and the 5 worst-scoring columns
    (the ones a reviewer should look at first)."""
    columns = [
        _column_grade(
            col,
            column_types.get(col, "unknown"),
            quality_report["missing_by_column"].get(col, 0.0),
            quality_report["outliers"].get(col),
        )
        for col in df.columns
    ]

    component_grades = {
        name: letter_grade(100 * health_breakdown.get(name, 0) / weight) for name, weight in HEALTH_COMPONENT_WEIGHTS.items()
    }

    overall_score = health_breakdown["total"]
    worst_columns = sorted(columns, key=lambda c: c["score"])[:5]

    return {
        "overall_score": overall_score,
        "overall_grade": letter_grade(overall_score),
        "n_rows": quality_report["n_rows"],
        "n_cols": quality_report["n_cols"],
        "duplicate_rows": quality_report["duplicate_rows"],
        "component_scores": {name: health_breakdown.get(name, 0) for name in HEALTH_COMPONENT_WEIGHTS},
        "component_weights": HEALTH_COMPONENT_WEIGHTS,
        "component_grades": component_grades,
        "columns": columns,
        "worst_columns": worst_columns,
    }


def scorecard_to_json(scorecard: dict) -> str:
    """JSON-serializable export for programmatic use (CI gates, dashboards)."""
    import json

    return json.dumps(scorecard, indent=2, default=str)
