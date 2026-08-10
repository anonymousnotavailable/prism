"""Tests for auto_analyst.auto_verify_hypothesis / narrate_hypothesis_verdict —
closing the suggest -> verify loop: instead of only handing the user a
suggested column pair to go test manually in Stats Lab, this actually runs
the matching scipy.stats significance test immediately and returns a
plain-English verdict, without requiring Gemini to be configured.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.auto_analyst import auto_verify_hypothesis, narrate_hypothesis_verdict


def _strong_correlation_df():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    return pd.DataFrame(
        {
            "x": x,
            "y_strong": x * 2 + rng.normal(scale=0.1, size=200),
        }
    )


def test_auto_verify_runs_the_matching_test_and_returns_a_verdict():
    df = _strong_correlation_df()
    column_types = {"x": "numeric", "y_strong": "numeric"}
    hypothesis = {"col_a": "x", "col_b": "y_strong", "reason": "strong correlation"}

    outcome = auto_verify_hypothesis(df, column_types, hypothesis)

    assert outcome["suggestion"]["test"] == "pearson"
    assert outcome["result"]["p_value"] < 0.05
    assert "Significant" in outcome["verdict"]


def test_auto_verify_numeric_categorical_runs_ttest():
    df = pd.DataFrame(
        {
            "value": [10, 11, 9, 10, 100, 101, 99, 102],
            "group": ["low"] * 4 + ["high"] * 4,
        }
    )
    column_types = {"value": "numeric", "group": "categorical"}
    hypothesis = {"col_a": "value", "col_b": "group", "reason": "groups differ"}

    outcome = auto_verify_hypothesis(df, column_types, hypothesis)

    assert outcome["suggestion"]["test"] == "ttest"
    assert outcome["result"]["p_value"] < 0.05
    assert "Significant" in outcome["verdict"]


def test_auto_verify_never_raises_when_suggestion_is_untestable():
    # Same column twice -> suggest_test still resolves types but running it
    # on degenerate input must not raise; an error dict is fine.
    df = pd.DataFrame({"a": [1, 2, 3]})
    column_types = {"a": "numeric"}
    hypothesis = {"col_a": "a", "col_b": "missing_col", "reason": "n/a"}

    outcome = auto_verify_hypothesis(df, column_types, hypothesis)

    assert "verdict" in outcome
    assert isinstance(outcome["verdict"], str)


def test_narrate_hypothesis_verdict_without_model_returns_error():
    text, error = narrate_hypothesis_verdict(None, {"reason": "x vs y"}, "Significant correlation (p=0.01).")
    assert text == ""
    assert error is not None
