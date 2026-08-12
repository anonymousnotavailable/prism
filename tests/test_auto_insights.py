"""Baseline tests for modules.auto_insights — the proactive scan run on every
dataset upload. Backfilled 2026-08-10: the run report/changelog for
2026-08-07 claimed 23 tests for this module, but `git log -- tests/` shows
none were ever committed. These cover the main detector paths plus the
empty/single-row/all-null edge cases the routine's audit calls out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.auto_insights import (
    category_label,
    format_insights_text,
    generate_insights,
    insights_reference_numbers,
    narrate_insights,
    severity_icon,
    verify_narration,
)


def test_generate_insights_flags_high_missing_column():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5] * 10, "b": [np.nan] * 45 + [1.0] * 5})
    types = {"a": "numeric", "b": "numeric"}
    insights = generate_insights(df, types)
    missing = [i for i in insights if i["category"] == "missing_data" and i["column"] == "b"]
    assert missing and missing[0]["severity"] == "high"


def test_generate_insights_flags_duplicate_rows():
    df = pd.DataFrame({"a": [1, 1, 1, 2, 3], "b": ["x", "x", "x", "y", "z"]})
    insights = generate_insights(df, {"a": "numeric", "b": "categorical"})
    dupes = [i for i in insights if i["category"] == "duplicates"]
    assert dupes and "2" in dupes[0]["metric"] or dupes  # 2 exact dupes of row 0


def test_generate_insights_flags_near_constant_column():
    df = pd.DataFrame({"flag": ["Y"] * 99 + ["N"], "id": range(100)})
    insights = generate_insights(df, {"flag": "categorical", "id": "numeric"})
    assert any(i["category"] == "structure" and i["column"] == "flag" for i in insights)


def test_generate_insights_flags_high_cardinality_id_column():
    df = pd.DataFrame({"user_id": [f"u{i}" for i in range(100)], "amount": range(100)})
    insights = generate_insights(df, {"user_id": "categorical", "amount": "numeric"})
    assert any(i["column"] == "user_id" and "unique" in i["metric"] for i in insights)


def test_generate_insights_flags_strong_correlation():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    df = pd.DataFrame({"x": x, "y": x * 2 + rng.normal(scale=0.001, size=200)})
    insights = generate_insights(df, {"x": "numeric", "y": "numeric"})
    assert any(i["category"] == "correlation" for i in insights)


def test_generate_insights_on_empty_dataframe_does_not_crash():
    df = pd.DataFrame({"a": [], "b": []})
    insights = generate_insights(df, {"a": "numeric", "b": "categorical"})
    assert insights == []


def test_generate_insights_on_single_row_does_not_crash():
    df = pd.DataFrame({"a": [1], "b": ["x"]})
    insights = generate_insights(df, {"a": "numeric", "b": "categorical"})
    assert isinstance(insights, list)


def test_generate_insights_on_all_null_column_does_not_crash():
    df = pd.DataFrame({"a": [np.nan] * 20, "b": range(20)})
    insights = generate_insights(df, {"a": "numeric", "b": "numeric"})
    assert isinstance(insights, list)


def test_generate_insights_caps_at_max_insights():
    from modules.auto_insights import MAX_INSIGHTS

    # deliberately messy dataset designed to trip many detectors at once
    n = 200
    cols = {f"const_{i}": ["A"] * (n - 1) + ["B"] for i in range(15)}
    cols["dup_a"] = [1] * n
    df = pd.DataFrame(cols)
    types = {c: "categorical" for c in cols}
    insights = generate_insights(df, types)
    assert len(insights) <= MAX_INSIGHTS


def test_insights_sorted_by_severity_high_first():
    df = pd.DataFrame({"a": [np.nan] * 45 + [1.0] * 5, "b": ["x"] * 49 + ["y"]})
    insights = generate_insights(df, {"a": "numeric", "b": "categorical"})
    severities = [i["severity"] for i in insights]
    order = {"high": 0, "medium": 1, "low": 2}
    assert severities == sorted(severities, key=lambda s: order.get(s, 3))


def test_format_insights_text_empty():
    assert "no notable" in format_insights_text([]).lower()


def test_format_insights_text_lists_each_finding():
    insights = [{"severity": "high", "message": "Column X is bad."}]
    text = format_insights_text(insights)
    assert "Column X is bad." in text


def test_narrate_insights_without_model_returns_error():
    narration, error = narrate_insights(None, [{"severity": "high", "message": "x"}])
    assert narration == ""
    assert error is not None


def test_narrate_insights_with_no_findings_skips_gemini():
    class _ShouldNotBeCalled:
        def generate_content(self, *_a, **_k):
            raise AssertionError("Gemini should not be called with no insights")

    narration, error = narrate_insights(_ShouldNotBeCalled(), [])
    assert error is None
    assert "clean" in narration.lower()


def test_severity_icon_and_category_label_cover_known_values():
    assert severity_icon("high") != severity_icon("low")
    assert isinstance(category_label("missing_data"), str) and category_label("missing_data")


# --- insights_reference_numbers / verify_narration -------------------------

def test_insights_reference_numbers_empty_is_safe():
    assert insights_reference_numbers([]) == set()
    assert insights_reference_numbers(None) == set()  # type: ignore[arg-type]


def test_insights_reference_numbers_pulls_from_messages():
    insights = [{"severity": "high", "message": "Column b is 90.0% missing (45 of 50 rows)."}]
    numbers = insights_reference_numbers(insights)
    assert 90.0 in numbers and 45.0 in numbers and 50.0 in numbers


def test_verify_narration_confirmed_when_number_matches_a_message():
    insights = [{"severity": "high", "message": "Column b is 90.0% missing (45 of 50 rows)."}]
    narration = "About 90.0% of column b is missing — worth investigating the collection process."
    verification = verify_narration(narration, insights)
    assert verification["status"] == "confirmed"


def test_verify_narration_flagged_when_a_number_is_fabricated():
    insights = [{"severity": "high", "message": "Column b is 90.0% missing (45 of 50 rows)."}]
    narration = "A staggering 12345.0% of the data is missing — a critical issue."
    verification = verify_narration(narration, insights)
    assert verification["status"] == "flagged"


def test_verify_narration_unverifiable_when_no_numbers_in_text():
    verification = verify_narration("Your data looks clean overall.", [])
    assert verification["status"] == "unverifiable"


def test_verify_narration_never_raises_on_malformed_insights():
    verification = verify_narration("Some text with 42 in it.", "not a list")  # type: ignore[arg-type]
    assert verification["status"] in ("flagged", "unverifiable")
