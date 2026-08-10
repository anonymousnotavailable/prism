"""Tests for modules/quality_scorecard.py — letter-grade mapping, per-column
grading, and the assembled scorecard dict (reused by both the Overview UI
and the PDF/JSON exports in report_writer.py)."""

import pandas as pd
import pytest

from modules import data_engine, quality_scorecard


class TestLetterGrade:
    @pytest.mark.parametrize(
        "score,expected",
        [(100, "A"), (90, "A"), (89.9, "B"), (80, "B"), (79.9, "C"), (70, "C"), (60, "D"), (59.9, "F"), (0, "F")],
    )
    def test_thresholds(self, score, expected):
        assert quality_scorecard.letter_grade(score) == expected


class TestColumnGrade:
    def test_clean_numeric_column_is_a(self):
        graded = quality_scorecard._column_grade("age", "numeric", missing_pct=0.0, outlier_info={"count": 0, "pct": 0.0})
        assert graded["grade"] == "A"
        assert graded["score"] == 100.0

    def test_heavily_missing_column_scores_low(self):
        graded = quality_scorecard._column_grade("notes", "text", missing_pct=80.0, outlier_info=None)
        assert graded["score"] < 60
        assert graded["grade"] == "F"

    def test_non_numeric_not_penalized_for_outliers(self):
        graded = quality_scorecard._column_grade("city", "categorical", missing_pct=0.0, outlier_info=None)
        assert graded["outlier_pct"] is None
        assert graded["score"] == 100.0

    def test_heavy_outliers_reduce_score(self):
        graded = quality_scorecard._column_grade("amount", "numeric", missing_pct=0.0, outlier_info={"count": 30, "pct": 60.0})
        assert graded["score"] < 100.0


class TestBuildScorecard:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame(
            {
                "age": [25, 30, None, 40, 200],  # missing + outlier
                "city": ["Mumbai", "Delhi", "Mumbai", "Pune", "Delhi"],
                "score": [1, 2, 3, 4, 5],
            }
        )

    def test_scorecard_has_expected_shape(self, sample_df):
        column_types = data_engine.detect_column_types(sample_df)
        quality_report = data_engine.get_data_quality_report(sample_df, column_types)
        health_breakdown = data_engine.get_health_breakdown(quality_report, column_types)

        scorecard = quality_scorecard.build_scorecard(sample_df, column_types, quality_report, health_breakdown)

        assert scorecard["overall_grade"] in {"A", "B", "C", "D", "F"}
        assert scorecard["n_rows"] == 5
        assert scorecard["n_cols"] == 3
        assert len(scorecard["columns"]) == 3
        assert set(scorecard["component_grades"]) == set(data_engine.HEALTH_COMPONENT_WEIGHTS)
        assert len(scorecard["worst_columns"]) <= 5

    def test_worst_columns_sorted_ascending_by_score(self, sample_df):
        column_types = data_engine.detect_column_types(sample_df)
        quality_report = data_engine.get_data_quality_report(sample_df, column_types)
        health_breakdown = data_engine.get_health_breakdown(quality_report, column_types)
        scorecard = quality_scorecard.build_scorecard(sample_df, column_types, quality_report, health_breakdown)

        scores = [c["score"] for c in scorecard["worst_columns"]]
        assert scores == sorted(scores)

    def test_age_column_scores_lower_than_clean_score_column(self, sample_df):
        column_types = data_engine.detect_column_types(sample_df)
        quality_report = data_engine.get_data_quality_report(sample_df, column_types)
        health_breakdown = data_engine.get_health_breakdown(quality_report, column_types)
        scorecard = quality_scorecard.build_scorecard(sample_df, column_types, quality_report, health_breakdown)

        by_col = {c["column"]: c["score"] for c in scorecard["columns"]}
        assert by_col["age"] < by_col["score"]


class TestScorecardToJson:
    def test_round_trips_as_valid_json(self, sample_df=pd.DataFrame({"a": [1, 2, None], "b": ["x", "y", "z"]})):
        import json

        column_types = data_engine.detect_column_types(sample_df)
        quality_report = data_engine.get_data_quality_report(sample_df, column_types)
        health_breakdown = data_engine.get_health_breakdown(quality_report, column_types)
        scorecard = quality_scorecard.build_scorecard(sample_df, column_types, quality_report, health_breakdown)

        raw = quality_scorecard.scorecard_to_json(scorecard)
        parsed = json.loads(raw)
        assert parsed["overall_grade"] == scorecard["overall_grade"]
