"""Tests for modules.quality_scorecard — deterministic, no Gemini involved.

Turns the existing weighted Data Health Score (data_engine.get_health_breakdown)
into a standalone, letter-graded, exportable scorecard.
"""
from __future__ import annotations

import pandas as pd

from modules import data_engine
from modules.quality_scorecard import (
    build_column_grades,
    build_scorecard,
    grade_for_score,
    render_scorecard_html,
    render_scorecard_markdown,
)


def _clean_df():
    return pd.DataFrame(
        {
            "amount": [10.0 + 0.1 * i for i in range(50)],
            "label": ["x", "y"] * 25,
        }
    )


def _messy_df():
    return pd.DataFrame(
        {
            "amount": [10.0, None, None, None, 5000.0] * 10,  # missing + outlier
            "empty_col": [None] * 50,
            "free_text": [f"note {i}" for i in range(50)],  # stays 'text'
        }
    )


def test_grade_for_score_boundaries():
    assert grade_for_score(95) == "A"
    assert grade_for_score(90) == "A"
    assert grade_for_score(89.9) == "B"
    assert grade_for_score(80) == "B"
    assert grade_for_score(65) == "C"
    assert grade_for_score(50) == "D"
    assert grade_for_score(49.9) == "F"
    assert grade_for_score(0) == "F"


def test_build_column_grades_clean_column_scores_well():
    df = _clean_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    grades = build_column_grades(quality, ct)
    by_col = {g["column"]: g for g in grades}
    assert by_col["amount"]["grade"] in ("A", "B")
    assert by_col["amount"]["issues"] == [] or by_col["amount"]["score"] >= 80


def test_build_column_grades_flags_empty_and_missing_and_text_columns():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    grades = build_column_grades(quality, ct)
    by_col = {g["column"]: g for g in grades}

    assert by_col["empty_col"]["grade"] == "F"
    assert any("empty" in issue for issue in by_col["empty_col"]["issues"])

    assert by_col["amount"]["score"] < 100
    assert any("missing" in issue for issue in by_col["amount"]["issues"])

    assert by_col["free_text"]["grade"] != "A"  # unresolved type dinged


def test_build_column_grades_sorted_worst_first():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    grades = build_column_grades(quality, ct)
    scores = [g["score"] for g in grades]
    assert scores == sorted(scores)


def test_build_scorecard_matches_overall_health_score():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    breakdown = data_engine.get_health_breakdown(quality, ct)
    scorecard = build_scorecard(df, quality, breakdown, ct)
    assert scorecard["overall_score"] == breakdown["total"]
    assert scorecard["overall_grade"] == grade_for_score(breakdown["total"])
    assert len(scorecard["column_grades"]) == quality["n_cols"]


def test_build_scorecard_remediation_present_for_messy_data():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    breakdown = data_engine.get_health_breakdown(quality, ct)
    scorecard = build_scorecard(df, quality, breakdown, ct)
    assert len(scorecard["remediation"]) > 0


def test_build_scorecard_no_remediation_for_clean_data():
    df = _clean_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    breakdown = data_engine.get_health_breakdown(quality, ct)
    scorecard = build_scorecard(df, quality, breakdown, ct)
    assert scorecard["remediation"] == []


def test_render_scorecard_html_contains_score_and_columns():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    breakdown = data_engine.get_health_breakdown(quality, ct)
    scorecard = build_scorecard(df, quality, breakdown, ct)
    html = render_scorecard_html(scorecard)
    assert "<html" in html.lower()
    assert str(scorecard["overall_score"]) in html
    for g in scorecard["column_grades"]:
        assert g["column"] in html


def test_render_scorecard_markdown_has_table_and_no_html_tags():
    df = _messy_df()
    ct = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, ct)
    breakdown = data_engine.get_health_breakdown(quality, ct)
    scorecard = build_scorecard(df, quality, breakdown, ct)
    md = render_scorecard_markdown(scorecard)
    assert "| Column | Grade" in md
    assert "<html" not in md.lower()
    assert "<div" not in md.lower()
