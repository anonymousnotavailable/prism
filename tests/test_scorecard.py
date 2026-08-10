"""Tests for modules.scorecard — the exportable Data Quality Scorecard.

Builds on top of data_engine.get_data_quality_report()/get_health_breakdown()
(the existing 0-100 Data Health Score) rather than recomputing quality
signals — this module's job is synthesis, grading, and export, not detection.
"""
from __future__ import annotations

import json

import pandas as pd

from modules import data_engine
from modules.scorecard import (
    build_scorecard,
    fingerprint_scorecard,
    grade_for_score,
    narrate_scorecard,
    render_json_scorecard,
    render_markdown_scorecard,
)


def _clean_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": range(1, 51),
            "amount": [100.0 + i for i in range(50)],
            "category": (["a", "b", "c"] * 17)[:50],
        }
    )


def _messy_df() -> pd.DataFrame:
    # 25 unique ids repeated twice with a constant 'notes' and fully-missing
    # 'amount' -> 25 exact duplicate rows (50%) and 33% missing cells overall,
    # enough to push both uniqueness and completeness below the 70% flag line.
    ids = list(range(1, 26)) * 2
    return pd.DataFrame({"id": ids, "amount": [None] * 50, "notes": ["same note"] * 50})


def _quality_and_health(df: pd.DataFrame):
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    health = data_engine.get_health_breakdown(quality, column_types, None)
    return column_types, quality, health


# --- grade_for_score -------------------------------------------------------

def test_grade_boundaries():
    assert grade_for_score(95) == "A"
    assert grade_for_score(90) == "A"
    assert grade_for_score(89) == "B"
    assert grade_for_score(80) == "B"
    assert grade_for_score(79) == "C"
    assert grade_for_score(70) == "C"
    assert grade_for_score(69) == "D"
    assert grade_for_score(60) == "D"
    assert grade_for_score(59) == "F"
    assert grade_for_score(0) == "F"


# --- build_scorecard ---------------------------------------------------

def test_build_scorecard_on_clean_data_scores_well_with_few_issues():
    df = _clean_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="clean.csv")

    assert card["dataset_name"] == "clean.csv"
    assert card["overall_score"] == health["total"]
    assert card["grade"] == grade_for_score(health["total"])
    assert card["shape"] == (50, 3)
    assert isinstance(card["issues"], list)
    assert isinstance(card["recommendations"], list)
    # a clean dataset shouldn't trip every possible issue
    assert len(card["issues"]) < 4


def test_build_scorecard_on_messy_data_flags_completeness_and_uniqueness():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")

    issue_components = {issue["component"] for issue in card["issues"]}
    assert "completeness" in issue_components
    assert "uniqueness" in issue_components
    assert card["overall_score"] < 90
    # every issue should carry an actionable recommendation
    assert len(card["recommendations"]) >= len(card["issues"])


def test_build_scorecard_components_sum_matches_total():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")
    component_sum = sum(c["score"] for c in card["components"])
    assert component_sum == card["overall_score"]


# --- render_markdown_scorecard / render_json_scorecard ---------------------

def test_render_markdown_contains_grade_and_score():
    df = _clean_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="clean.csv")
    md = render_markdown_scorecard(card)
    assert "clean.csv" in md
    assert card["grade"] in md
    assert str(card["overall_score"]) in md


def test_render_json_scorecard_round_trips():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")
    raw = render_json_scorecard(card)
    parsed = json.loads(raw)
    assert parsed["overall_score"] == card["overall_score"]
    assert parsed["grade"] == card["grade"]
    assert parsed["dataset_name"] == "messy.csv"


def test_render_markdown_lists_every_recommendation():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")
    md = render_markdown_scorecard(card)
    for rec in card["recommendations"]:
        assert rec["text"] in md


# --- fingerprint_scorecard / narrate_scorecard ------------------------------

def test_fingerprint_stable_for_the_same_card():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")
    assert fingerprint_scorecard(card) == fingerprint_scorecard(card)


def test_fingerprint_changes_when_score_changes():
    df1, df2 = _clean_df(), _messy_df()
    ct1, q1, h1 = _quality_and_health(df1)
    ct2, q2, h2 = _quality_and_health(df2)
    card1 = build_scorecard(df1, ct1, q1, h1, dataset_name="a.csv")
    card2 = build_scorecard(df2, ct2, q2, h2, dataset_name="a.csv")
    assert fingerprint_scorecard(card1) != fingerprint_scorecard(card2)


def test_narrate_scorecard_without_model_returns_error():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")
    narration, error = narrate_scorecard(None, card)
    assert narration == ""
    assert error is not None


def test_narrate_scorecard_calls_gemini_with_score_and_grade():
    df = _messy_df()
    column_types, quality, health = _quality_and_health(df)
    card = build_scorecard(df, column_types, quality, health, dataset_name="messy.csv")

    class _FakeResponse:
        text = "This dataset needs attention on completeness and duplicates before analysis."

    class _FakeModel:
        def generate_content(self, contents):
            assert str(card["overall_score"]) in contents
            assert card["grade"] in contents
            return _FakeResponse()

    narration, error = narrate_scorecard(_FakeModel(), card)
    assert error is None
    assert "attention" in narration.lower()
