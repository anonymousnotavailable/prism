"""Tests for modules/data_quality.py — the exportable Data Quality
Scorecard + AI narration shipped in the 2026-08-10 Run 4 routine pass.
Closes a backlog item flagged, unbuilt, across three prior runs.
"""

import json

import pandas as pd

from modules import data_engine
from modules.data_quality import (
    build_scorecard,
    fingerprint_breakdown,
    narrate_health_score,
    scorecard_json_bytes,
)


def _quality_and_breakdown(df: pd.DataFrame):
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    breakdown = data_engine.get_health_breakdown(quality, column_types)
    return quality, breakdown


# --- fingerprint_breakdown -------------------------------------------------

def test_fingerprint_breakdown_stable_for_same_input():
    breakdown = {"completeness": 30, "consistency": 25, "uniqueness": 15, "validity": 15, "outlier_burden": 15, "total": 100}
    assert fingerprint_breakdown(breakdown) == fingerprint_breakdown(dict(breakdown))


def test_fingerprint_breakdown_changes_with_component_even_if_total_ties():
    # Two different failure profiles that happen to sum to the same total
    # must NOT collide — the narration should differ.
    a = {"completeness": 20, "consistency": 25, "uniqueness": 15, "validity": 15, "outlier_burden": 15, "total": 90}
    b = {"completeness": 30, "consistency": 15, "uniqueness": 15, "validity": 15, "outlier_burden": 15, "total": 90}
    assert fingerprint_breakdown(a) != fingerprint_breakdown(b)


# --- build_scorecard / scorecard_json_bytes --------------------------------

def test_build_scorecard_perfect_dataset():
    df = pd.DataFrame({"a": range(20), "b": [f"x{i}" for i in range(20)]})
    quality, breakdown = _quality_and_breakdown(df)
    card = build_scorecard(quality, breakdown, dataset_name="clean.csv")

    assert card["dataset_name"] == "clean.csv"
    assert card["rows"] == 20
    assert card["columns"] == 2
    assert card["total_score"] == breakdown["total"]
    assert card["max_score"] == 100
    assert set(card["components"]) == set(data_engine.HEALTH_COMPONENT_WEIGHTS)
    for name, weight in data_engine.HEALTH_COMPONENT_WEIGHTS.items():
        assert card["components"][name]["max"] == weight
        assert card["components"][name]["score"] == breakdown[name]
    assert card["summary_stats"]["duplicate_rows"] == 0


def test_build_scorecard_messy_dataset_flags_summary_stats():
    df = pd.DataFrame({
        "a": [1, 1, None, None, 100000],  # missing + an IQR outlier
        "b": [1, 1, 1, 1, 1],  # duplicate rows once combined with a repeats
    })
    quality, breakdown = _quality_and_breakdown(df)
    card = build_scorecard(quality, breakdown)

    assert card["dataset_name"] == "unnamed dataset"  # default when not given
    assert card["summary_stats"]["missing_cells_pct"] > 0
    assert card["total_score"] < 100


def test_build_scorecard_is_json_serializable_and_roundtrips():
    df = pd.DataFrame({"a": [1, 2, 3, None], "b": ["x", "y", "y", "z"]})
    quality, breakdown = _quality_and_breakdown(df)
    card = build_scorecard(quality, breakdown, dataset_name="sample.csv")

    raw = scorecard_json_bytes(card)
    assert isinstance(raw, bytes)
    reloaded = json.loads(raw.decode("utf-8"))
    assert reloaded == card


# --- narrate_health_score ---------------------------------------------------

def test_narrate_health_score_without_model_returns_error():
    breakdown = {"completeness": 30, "consistency": 25, "uniqueness": 15, "validity": 15, "outlier_burden": 15, "total": 100}
    narration, error = narrate_health_score(None, breakdown)
    assert narration == ""
    assert error is not None


def test_narrate_health_score_missing_total_key_returns_error():
    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called for a malformed breakdown")

    narration, error = narrate_health_score(_ShouldNotBeCalled(), {"completeness": 30})
    assert narration == ""
    assert error is not None


def test_narrate_health_score_calls_gemini_with_component_breakdown():
    breakdown = {"completeness": 10, "consistency": 25, "uniqueness": 15, "validity": 15, "outlier_burden": 15, "total": 80}

    class _FakeResponse:
        text = "Completeness is the weakest link here. Consider imputing or dropping sparse columns."

    class _FakeModel:
        def generate_content(self, contents):
            assert "completeness: 10/30" in contents
            assert "80" in contents
            return _FakeResponse()

    narration, error = narrate_health_score(_FakeModel(), breakdown)
    assert error is None
    assert "completeness" in narration.lower()
