"""
Unit tests for modules.hypothesis_engine — the autonomous "what should I
even be testing?" layer on top of Stats Lab.

Covers: empty/degenerate input, each of the three hypothesis kinds on
synthetic data engineered to have a known ground truth (a real effect vs.
no effect), the cardinality filter, the pre-screen -> real-test pipeline
never fabricating a verdict scipy didn't compute, ranking order, and the
deterministic (no-Gemini) narration fallback.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import hypothesis_engine as he


def _column_types(df: pd.DataFrame, categorical: list[str], numeric: list[str]) -> dict[str, str]:
    types = {}
    for col in df.columns:
        if col in categorical:
            types[col] = "categorical"
        elif col in numeric:
            types[col] = "numeric"
        else:
            types[col] = "other"
    return types


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------

def test_empty_dataframe_returns_no_hypotheses():
    df = pd.DataFrame()
    assert he.generate_hypotheses(df, {}) == []


def test_none_dataframe_returns_no_hypotheses():
    assert he.generate_hypotheses(None, {}) == []


def test_no_eligible_columns_returns_no_hypotheses():
    # A single numeric column and nothing to pair it against.
    df = pd.DataFrame({"value": [1, 2, 3, 4, 5]})
    types = {"value": "numeric"}
    assert he.generate_hypotheses(df, types) == []


def test_all_null_column_is_skipped_not_crashed():
    df = pd.DataFrame(
        {
            "value": [1, 2, 3, 4, 5, 6],
            "empty_col": [np.nan] * 6,
            "group": ["a", "b", "a", "b", "a", "b"],
        }
    )
    types = {"value": "numeric", "empty_col": "numeric", "group": "categorical"}
    # Should not raise, and should only ever reference the real columns.
    result = he.generate_hypotheses(df, types)
    for h in result:
        assert h["col_a"] != "empty_col"
        assert h["col_b"] != "empty_col"


# ---------------------------------------------------------------------------
# numeric x categorical — engineered real effect
# ---------------------------------------------------------------------------

def test_numeric_categorical_detects_real_group_difference():
    rng = np.random.RandomState(0)
    df = pd.DataFrame(
        {
            "salary": np.concatenate([rng.normal(50000, 2000, 60), rng.normal(90000, 2000, 60)]),
            "department": ["Support"] * 60 + ["Engineering"] * 60,
        }
    )
    types = _column_types(df, categorical=["department"], numeric=["salary"])

    hypotheses = he.generate_hypotheses(df, types)

    assert len(hypotheses) >= 1
    top = hypotheses[0]
    assert top["kind"] == "numeric_categorical"
    assert top["verdict"] == "supported"
    assert top["result"]["p_value"] < 0.05
    assert "salary" in top["statement"] or "department" in top["statement"]


def test_numeric_categorical_no_effect_is_not_supported():
    rng = np.random.RandomState(1)
    df = pd.DataFrame(
        {
            "score": rng.normal(50, 5, 100),
            "cohort": rng.choice(["A", "B"], 100),
        }
    )
    types = _column_types(df, categorical=["cohort"], numeric=["score"])

    hypotheses = he.generate_hypotheses(df, types)
    # Random data occasionally clears p<0.05 by chance, but the pipeline
    # must still classify honestly off the real test result either way.
    for h in hypotheses:
        expected_verdict = "supported" if h["result"]["p_value"] < 0.05 else "not supported"
        assert h["verdict"] == expected_verdict


# ---------------------------------------------------------------------------
# categorical x categorical
# ---------------------------------------------------------------------------

def test_categorical_categorical_detects_real_association():
    rng = np.random.RandomState(2)
    n = 200
    region = rng.choice(["North", "South"], n)
    # plan is strongly dependent on region
    plan = np.where(
        region == "North",
        rng.choice(["Basic", "Premium"], n, p=[0.9, 0.1]),
        rng.choice(["Basic", "Premium"], n, p=[0.1, 0.9]),
    )
    df = pd.DataFrame({"region": region, "plan": plan})
    types = _column_types(df, categorical=["region", "plan"], numeric=[])

    hypotheses = he.generate_hypotheses(df, types)
    assert len(hypotheses) == 1
    assert hypotheses[0]["kind"] == "categorical_categorical"
    assert hypotheses[0]["verdict"] == "supported"


def test_high_cardinality_categorical_is_excluded():
    df = pd.DataFrame(
        {
            "id_like": [f"id_{i}" for i in range(30)],  # 30 unique values, way over the cap
            "flag": ["yes", "no"] * 15,
        }
    )
    types = _column_types(df, categorical=["id_like", "flag"], numeric=[])
    hypotheses = he.generate_hypotheses(df, types)
    for h in hypotheses:
        assert h["col_a"] != "id_like"
        assert h["col_b"] != "id_like"


# ---------------------------------------------------------------------------
# numeric x numeric
# ---------------------------------------------------------------------------

def test_numeric_numeric_detects_real_correlation():
    rng = np.random.RandomState(3)
    x = rng.normal(0, 1, 100)
    y = x * 2 + rng.normal(0, 0.1, 100)
    df = pd.DataFrame({"x": x, "y": y})
    types = _column_types(df, categorical=[], numeric=["x", "y"])

    hypotheses = he.generate_hypotheses(df, types)
    assert len(hypotheses) == 1
    assert hypotheses[0]["kind"] == "numeric_numeric"
    assert hypotheses[0]["verdict"] == "supported"
    assert abs(hypotheses[0]["result"]["effect_size"]) > 0.9


# ---------------------------------------------------------------------------
# Ranking and caps
# ---------------------------------------------------------------------------

def test_results_are_capped_at_max_hypotheses_returned():
    rng = np.random.RandomState(4)
    n = 150
    data = {"target": rng.normal(0, 1, n)}
    # Build many categorical columns so pre-screen has plenty of candidates.
    for i in range(10):
        data[f"cat_{i}"] = rng.choice(["A", "B", "C"], n)
    df = pd.DataFrame(data)
    types = _column_types(df, categorical=[c for c in df.columns if c != "target"], numeric=["target"])

    hypotheses = he.generate_hypotheses(df, types)
    assert len(hypotheses) <= he.MAX_HYPOTHESES_RETURNED


def test_supported_hypotheses_rank_before_unsupported():
    rng = np.random.RandomState(5)
    n = 120
    df = pd.DataFrame(
        {
            "strong_signal": np.concatenate([rng.normal(0, 1, n // 2), rng.normal(10, 1, n // 2)]),
            "no_signal": rng.normal(0, 1, n),
            "group": ["a"] * (n // 2) + ["b"] * (n // 2),
        }
    )
    types = _column_types(df, categorical=["group"], numeric=["strong_signal", "no_signal"])

    hypotheses = he.generate_hypotheses(df, types)
    verdicts = [h["verdict"] for h in hypotheses]
    # Once a "not supported" appears, no "supported" should follow it.
    if "not supported" in verdicts:
        first_unsupported = verdicts.index("not supported")
        assert "supported" not in verdicts[first_unsupported:]


# ---------------------------------------------------------------------------
# Narration (deterministic fallback — must work with zero Gemini key)
# ---------------------------------------------------------------------------

def test_narrate_headline_empty():
    assert "No testable hypotheses" in he.narrate_headline([])


def test_narrate_headline_none_significant():
    hyps = [{"verdict": "not supported"}]
    msg = he.narrate_headline(hyps)
    assert "none reached statistical significance" in msg


def test_narrate_headline_with_significant_result():
    hyps = [
        {"verdict": "supported", "statement": "'x' and 'y' are linearly correlated.", "interpretation": "Significant correlation detected (p=0.0010, large effect, Pearson r=0.95)."},
        {"verdict": "not supported"},
    ]
    msg = he.narrate_headline(hyps)
    assert "1 significant" in msg
    assert "linearly correlated" in msg


def test_narrate_with_gemini_handles_empty_input_without_calling_model():
    text, error = he.narrate_with_gemini(model=None, hypotheses=[])
    assert text == ""
    assert error


def test_narrate_with_gemini_falls_back_cleanly_with_no_model_configured():
    hyps = [{"statement": "x", "interpretation": "y", "verdict": "supported"}]
    text, error = he.narrate_with_gemini(model=None, hypotheses=hyps)
    assert text == ""
    assert error  # caller falls back to narrate_headline() rather than surface a blank section
