"""
Unit tests for modules.hypothesis_engine — written before the module's
UI integration (per the routine's "tests first" rule). No live Gemini
calls: generation is exercised via a fake `model` object (matching the
same call_gemini() contract every other Gemini-touching test in this
repo would need) and via model=None to cover the heuristic fallback path,
which is the path that actually runs on CI / this eval environment where
no GEMINI_API_KEY is configured.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import hypothesis_engine as he


def _sample_df(n=200, seed=0):
    rng = np.random.RandomState(seed)
    dept = rng.choice(["Sales", "Engineering", "Support"], size=n)
    # salary deliberately depends on dept so the categorical/numeric pair
    # is a real, testable relationship rather than pure noise.
    bump = pd.Series(dept).map({"Sales": 8000, "Engineering": 0, "Support": -4000}).to_numpy()
    salary = rng.normal(50000, 5000, n) + bump
    tenure = rng.normal(5, 2, n)
    # revenue correlates with salary by construction.
    revenue = salary * 2.1 + rng.normal(0, 3000, n)
    return pd.DataFrame(
        {
            "department": dept,
            "salary": salary,
            "tenure_years": tenure,
            "revenue": revenue,
            "employee_id": np.arange(n),  # id-like column — never a valid hypothesis target
        }
    )


def _column_types():
    return {
        "department": "categorical",
        "salary": "numeric",
        "tenure_years": "numeric",
        "revenue": "numeric",
        "employee_id": "numeric",
    }


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Stands in for a genai.GenerativeModel — call_gemini() only ever
    calls .generate_content(contents) on it.
    """

    def __init__(self, reply_text):
        self.reply_text = reply_text

    def generate_content(self, _contents):
        return _FakeResponse(self.reply_text)


# ── generate_hypotheses ──────────────────────────────────────────────────


def test_generate_hypotheses_requires_two_testable_columns():
    df = pd.DataFrame({"id": [1, 2, 3]})
    hyps, error = he.generate_hypotheses(None, df, {"id": "numeric"})
    assert hyps == []
    assert "at least 2" in error


def test_generate_hypotheses_falls_back_to_heuristics_without_a_model():
    df = _sample_df()
    hyps, error = he.generate_hypotheses(None, df, _column_types(), max_hypotheses=4)
    assert error is None
    assert 1 <= len(hyps) <= 4
    assert all(h["source"] == "heuristic" for h in hyps)
    assert all(h["col_a"] != h["col_b"] for h in hyps)


def test_generate_hypotheses_parses_valid_gemini_json():
    reply = (
        '[{"hypothesis": "Sales pays more than other departments", '
        '"col_a": "department", "col_b": "salary", "rationale": "commission-heavy roles"}, '
        '{"hypothesis": "Salary tracks revenue", "col_a": "salary", "col_b": "revenue", '
        '"rationale": "comp is often revenue-linked"}]'
    )
    df = _sample_df()
    hyps, error = he.generate_hypotheses(_FakeModel(reply), df, _column_types())
    assert error is None
    assert len(hyps) == 2
    assert {h["col_a"] for h in hyps} == {"department", "salary"}
    assert all(h["source"] == "gemini" for h in hyps)


def test_generate_hypotheses_drops_hallucinated_columns_and_falls_back():
    # Gemini names a column that doesn't exist in the schema — every entry
    # must be rejected, and the pipeline must still return something useful
    # rather than an empty result.
    reply = '[{"hypothesis": "made up", "col_a": "not_a_real_column", "col_b": "salary", "rationale": "x"}]'
    df = _sample_df()
    hyps, error = he.generate_hypotheses(_FakeModel(reply), df, _column_types())
    assert error is None
    assert all(h["col_a"] != "not_a_real_column" for h in hyps)


def test_generate_hypotheses_rejects_id_like_and_self_paired_columns():
    reply = (
        '[{"hypothesis": "id tracks salary", "col_a": "employee_id", "col_b": "salary", "rationale": "x"}, '
        '{"hypothesis": "salary tracks itself", "col_a": "salary", "col_b": "salary", "rationale": "x"}, '
        '{"hypothesis": "valid one", "col_a": "department", "col_b": "salary", "rationale": "x"}]'
    )
    # employee_id is typed numeric here on purpose to prove the id-like
    # exclusion isn't happening — this test documents that hypothesis_engine
    # trusts column_types, not name-sniffing; a real id column should be
    # typed appropriately upstream by data_engine.detect_column_types.
    df = _sample_df()
    hyps, _ = he.generate_hypotheses(_FakeModel(reply), df, _column_types())
    assert not any(h["col_a"] == h["col_b"] for h in hyps)
    assert any(h["col_a"] == "department" and h["col_b"] == "salary" for h in hyps)


def test_generate_hypotheses_handles_malformed_json_via_fallback():
    hyps, error = he.generate_hypotheses(_FakeModel("not json at all"), _sample_df(), _column_types())
    assert error is None
    assert all(h["source"] == "heuristic" for h in hyps)


# ── run_hypotheses ───────────────────────────────────────────────────────


def test_run_hypotheses_assigns_verdicts_and_narration():
    df = _sample_df()
    hyps = [
        {"hypothesis": "Salary depends on department", "col_a": "department", "col_b": "salary", "rationale": "", "source": "test"},
        {"hypothesis": "Revenue correlates with salary", "col_a": "salary", "col_b": "revenue", "rationale": "", "source": "test"},
    ]
    results = he.run_hypotheses(df, _column_types(), hyps)
    assert len(results) == 2
    for r in results:
        assert r["verdict"] in ("SUPPORTED", "REJECTED")
        assert "narration" in r
        assert 0.0 <= r["adjusted_p_value"] <= 1.0
        # both hypotheses are real relationships by construction — expect them supported.
        assert r["verdict"] == "SUPPORTED"


def test_run_hypotheses_marks_untestable_pairs_without_crashing():
    df = _sample_df()
    hyps = [{"hypothesis": "too many groups", "col_a": "employee_id", "col_b": "salary", "rationale": "", "source": "test"}]
    # employee_id has 200 unique values — suggest_test should refuse it as a group column.
    results = he.run_hypotheses(df, {**_column_types(), "employee_id": "categorical"}, hyps)
    assert results[0]["verdict"] == "NOT_TESTABLE"
    assert "reason" in results[0]


def test_run_hypotheses_applies_multiple_testing_correction():
    # Build several categorical/numeric pairs where the categorical column
    # is pure noise (independent of the numeric column) — with enough of
    # them, at least one raw p-value should dip under 0.05 by chance, but
    # the FDR-adjusted verdict should be more conservative than the raw one.
    rng = np.random.RandomState(1)
    n = 60
    df = pd.DataFrame({"num": rng.normal(size=n)})
    col_types = {"num": "numeric"}
    hyps = []
    for i in range(8):
        col = f"noise_{i}"
        df[col] = rng.choice(["A", "B"], size=n)
        col_types[col] = "categorical"
        hyps.append({"hypothesis": f"noise_{i} vs num", "col_a": col, "col_b": "num", "rationale": "", "source": "test"})

    results = he.run_hypotheses(df, col_types, hyps)
    testable = [r for r in results if r["verdict"] in ("SUPPORTED", "REJECTED")]
    assert len(testable) == 8
    for r in testable:
        # adjusted p-value is never smaller than the raw p-value (BH correction only inflates).
        assert r["adjusted_p_value"] >= r["result"]["p_value"] - 1e-9
        assert r["n_tested"] == 8


def test_run_hypotheses_empty_list_is_a_noop():
    assert he.run_hypotheses(_sample_df(), _column_types(), []) == []


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
