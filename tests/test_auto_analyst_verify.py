"""Tests for the Auto Analyst statistical verification layer
(modules.auto_analyst.verify_findings / _find_mentioned_columns).

This is the "self-verifying agent" pass: Gemini's prose findings get
cross-checked against a real scipy.stats hypothesis test on whatever
columns the finding actually names, so a plausible-sounding but
statistically empty claim gets flagged instead of trusted at face value.
Deliberately has zero Gemini/network dependency — it's pure pandas/scipy,
so it's fast and deterministic in CI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.auto_analyst import _find_mentioned_columns, verify_findings


@pytest.fixture
def correlated_df():
    rng = np.random.RandomState(0)
    x = rng.normal(size=200)
    # y strongly, linearly dependent on x -> Pearson test should be significant.
    y = 3 * x + rng.normal(scale=0.1, size=200)
    noise = rng.normal(size=200)  # unrelated to x -> should NOT be significant
    category = rng.choice(["A", "B"], size=200)
    return pd.DataFrame({"revenue": x, "cost": y, "unrelated_score": noise, "segment": category})


@pytest.fixture
def column_types():
    return {
        "revenue": "numeric",
        "cost": "numeric",
        "unrelated_score": "numeric",
        "segment": "categorical",
    }


# --- _find_mentioned_columns -------------------------------------------------

def test_find_mentioned_columns_matches_word_boundary():
    cols = ["age", "revenue"]
    found = _find_mentioned_columns("The average revenue rose sharply.", cols)
    # "age" must NOT match inside "average" — only "revenue" is really mentioned.
    assert found == ["revenue"]


def test_find_mentioned_columns_handles_underscored_names():
    cols = ["unit_price", "segment"]
    found = _find_mentioned_columns("Unit price varies a lot by segment.", cols)
    assert found == ["unit_price", "segment"]


def test_find_mentioned_columns_orders_by_first_appearance():
    cols = ["cost", "revenue"]
    found = _find_mentioned_columns("Revenue correlates strongly with cost.", cols)
    assert found == ["revenue", "cost"]


def test_find_mentioned_columns_no_match_returns_empty():
    assert _find_mentioned_columns("Nothing about columns here.", ["revenue", "cost"]) == []


# --- verify_findings ----------------------------------------------------------

def test_verify_findings_marks_real_correlation_as_verified(correlated_df, column_types):
    findings = ["Revenue and cost are strongly correlated."]
    result = verify_findings(correlated_df, column_types, findings)
    assert len(result) == 1
    assert result[0]["status"] == "verified"
    assert result[0]["p_value"] < 0.05
    assert set(result[0]["columns"]) == {"revenue", "cost"}


def test_verify_findings_flags_unsupported_claim_as_not_significant(correlated_df, column_types):
    findings = ["Revenue is correlated with the unrelated score."]
    result = verify_findings(correlated_df, column_types, findings)
    assert result[0]["status"] == "not_significant"
    assert result[0]["p_value"] >= 0.05


def test_verify_findings_single_column_mention_is_not_testable(correlated_df, column_types):
    findings = ["Revenue has a wide spread of values."]
    result = verify_findings(correlated_df, column_types, findings)
    assert result[0]["status"] == "not_testable"
    assert result[0]["p_value"] is None


def test_verify_findings_no_column_mention_is_not_testable(correlated_df, column_types):
    findings = ["Overall, the dataset looks clean and ready for modeling."]
    result = verify_findings(correlated_df, column_types, findings)
    assert result[0]["status"] == "not_testable"


def test_verify_findings_numeric_categorical_pair_runs_group_test(correlated_df, column_types):
    findings = ["Revenue differs notably across segment groups."]
    result = verify_findings(correlated_df, column_types, findings)
    assert result[0]["status"] in ("verified", "not_significant")
    assert result[0]["test"] in ("Independent t-test", "One-way ANOVA")


def test_verify_findings_preserves_order_and_count(correlated_df, column_types):
    findings = [
        "Revenue and cost are strongly correlated.",
        "The dataset has no obvious issues.",
        "Revenue differs across segment.",
    ]
    result = verify_findings(correlated_df, column_types, findings)
    assert len(result) == 3
    assert result[1]["status"] == "not_testable"


def test_verify_findings_empty_list_returns_empty():
    assert verify_findings(pd.DataFrame({"a": [1, 2]}), {"a": "numeric"}, []) == []
