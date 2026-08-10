"""Tests for modules/hypothesis_suite.py — the automated multi-hypothesis
testing sweep: enumerate every viable column pair, run the right test on
each via Stats Lab, and correct for the multiple-comparisons problem that
creates with Benjamini-Hochberg FDR before ranking findings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.hypothesis_suite import (
    _benjamini_hochberg,
    enumerate_candidate_pairs,
    fingerprint_suite,
    narrate_hypothesis_suite,
    run_hypothesis_suite,
)

# --- enumerate_candidate_pairs --------------------------------------------


def test_enumerates_all_pair_types():
    df = pd.DataFrame(
        {
            "n1": range(10),
            "n2": range(10),
            "cat1": ["a", "b"] * 5,
            "cat2": ["x", "y"] * 5,
        }
    )
    column_types = {"n1": "numeric", "n2": "numeric", "cat1": "categorical", "cat2": "categorical"}
    pairs, truncation = enumerate_candidate_pairs(df, column_types)
    pair_set = {frozenset(p) for p in pairs}
    assert frozenset({"n1", "n2"}) in pair_set
    assert frozenset({"n1", "cat1"}) in pair_set
    assert frozenset({"cat1", "cat2"}) in pair_set
    assert truncation == {}


def test_drops_high_cardinality_categorical_columns():
    df = pd.DataFrame({"n1": range(20), "id_like": [f"id_{i}" for i in range(20)]})
    column_types = {"n1": "numeric", "id_like": "categorical"}
    pairs, _ = enumerate_candidate_pairs(df, column_types)
    assert pairs == []  # id_like has 20 unique values, way over the cardinality cap


def test_caps_wide_datasets_and_reports_truncation():
    n_numeric = 20
    data = {f"n{i}": np.arange(30) + i for i in range(n_numeric)}
    df = pd.DataFrame(data)
    column_types = {c: "numeric" for c in df.columns}
    pairs, truncation = enumerate_candidate_pairs(df, column_types)
    assert truncation.get("numeric") == n_numeric - 12  # MAX_NUMERIC_COLS
    assert len(pairs) <= 40  # MAX_TESTS


# --- _benjamini_hochberg ---------------------------------------------------


def test_bh_correction_known_example():
    # 5 p-values, alpha=0.05. BH critical values: rank/5*0.05 = .01,.02,.03,.04,.05
    p_values = [0.01, 0.02, 0.03, 0.04, 0.10]
    survives = _benjamini_hochberg(p_values, alpha=0.05)
    # sorted (already ascending): rank1 .01<=.01 pass, rank2 .02<=.02 pass,
    # rank3 .03<=.03 pass, rank4 .04<=.04 pass, rank5 .10<=.05 fail
    # largest passing rank is 4 -> first four survive, the last doesn't
    assert survives == [True, True, True, True, False]


def test_bh_correction_empty_input():
    assert _benjamini_hochberg([]) == []


def test_bh_correction_all_pass_when_all_highly_significant():
    p_values = [0.0001, 0.0002, 0.0003]
    assert all(_benjamini_hochberg(p_values, alpha=0.05))


# --- run_hypothesis_suite --------------------------------------------------


def _df_with_strong_relationship(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    x = rng.normal(size=n)
    return pd.DataFrame(
        {
            "x": x,
            "y_strong": x * 3 + rng.normal(scale=0.1, size=n),
            "noise1": rng.normal(size=n),
            "noise2": rng.normal(size=n),
        }
    )


def test_run_suite_finds_strong_relationship():
    df = _df_with_strong_relationship()
    column_types = {c: "numeric" for c in df.columns}
    result = run_hypothesis_suite(df, column_types)
    assert result["n_tested"] > 0
    top = result["findings"][0]
    assert {top["col_a"], top["col_b"]} == {"x", "y_strong"}
    assert top["significant_corrected"] is True


def test_run_suite_sorted_by_significance_then_effect_size():
    df = _df_with_strong_relationship()
    column_types = {c: "numeric" for c in df.columns}
    result = run_hypothesis_suite(df, column_types)
    sig_flags = [f["significant_corrected"] for f in result["findings"]]
    # all True entries must come before all False entries
    assert sig_flags == sorted(sig_flags, key=lambda s: not s)


def test_run_suite_on_no_viable_pairs_returns_empty_findings():
    df = pd.DataFrame({"n1": range(5)})
    column_types = {"n1": "numeric"}
    result = run_hypothesis_suite(df, column_types)
    assert result["findings"] == []
    assert result["n_tested"] == 0


def test_run_suite_counts_are_consistent():
    df = _df_with_strong_relationship()
    column_types = {c: "numeric" for c in df.columns}
    result = run_hypothesis_suite(df, column_types)
    assert result["n_significant_corrected"] <= result["n_significant_raw"] <= result["n_tested"]
    assert result["n_significant_corrected"] == sum(f["significant_corrected"] for f in result["findings"])


# --- fingerprint_suite -----------------------------------------------------


def test_fingerprint_stable_for_same_result():
    df = _df_with_strong_relationship()
    column_types = {c: "numeric" for c in df.columns}
    result = run_hypothesis_suite(df, column_types)
    assert fingerprint_suite(result) == fingerprint_suite(result)


def test_fingerprint_empty_for_no_findings():
    assert fingerprint_suite({"findings": [], "n_tested": 0}) == "empty"
    assert fingerprint_suite(None) == "empty"


# --- narrate_hypothesis_suite -----------------------------------------------


def test_narrate_without_model_returns_error():
    narration, error = narrate_hypothesis_suite(None, {"findings": [], "n_tested": 0})
    assert narration == ""
    assert error is not None


def test_narrate_with_no_findings_skips_gemini():
    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called with no findings")

    narration, error = narrate_hypothesis_suite(_ShouldNotBeCalled(), {"findings": [], "n_tested": 0})
    assert error is None
    assert "no testable" in narration.lower()


def test_narrate_with_no_survivors_skips_gemini():
    df = pd.DataFrame({"n1": np.random.default_rng(1).normal(size=50), "n2": np.random.default_rng(2).normal(size=50)})
    column_types = {"n1": "numeric", "n2": "numeric"}
    result = run_hypothesis_suite(df, column_types)

    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called when nothing survives correction")

    # Force the no-survivor path regardless of the random draw's actual p-value.
    for f in result["findings"]:
        f["significant_corrected"] = False

    narration, error = narrate_hypothesis_suite(_ShouldNotBeCalled(), result)
    assert error is None
    assert "multiple comparisons" in narration.lower() or "no statistically" in narration.lower()


def test_narrate_calls_gemini_with_significant_findings():
    df = _df_with_strong_relationship()
    column_types = {c: "numeric" for c in df.columns}
    result = run_hypothesis_suite(df, column_types)

    class _FakeResponse:
        text = "The x/y relationship is the dominant structure here. Investigate its driver next."

    class _FakeModel:
        def generate_content(self, contents):
            assert "hypothesis" in contents.lower() or "multiple comparisons" in contents.lower()
            return _FakeResponse()

    narration, error = narrate_hypothesis_suite(_FakeModel(), result)
    assert error is None
    assert "investigate" in narration.lower()
