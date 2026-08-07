"""Unit tests for modules.hypothesis_engine — the self-verifying hypothesis
agent. Every test here exercises the deterministic path (no Gemini call
needed): heuristic candidate generation from real correlations/variance,
Gemini JSON parsing with fallback, and the verify step that dispatches into
stats_lab and classifies CONFIRMED / NOT CONFIRMED / INCONCLUSIVE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import hypothesis_engine as he


def _correlated_df(n=200, seed=0):
    rng = np.random.RandomState(seed)
    x = rng.normal(0, 1, n)
    y = x * 3 + rng.normal(0, 0.2, n)  # strongly correlated with x
    noise = rng.normal(0, 1, n)  # uncorrelated
    group = rng.choice(["A", "B"], n)
    # numeric that clearly differs by group
    skewed = np.where(group == "A", rng.normal(10, 1, n), rng.normal(20, 1, n))
    return pd.DataFrame({"x": x, "y": y, "noise": noise, "group": group, "skewed": skewed})


COLUMN_TYPES = {"x": "numeric", "y": "numeric", "noise": "numeric", "group": "categorical", "skewed": "numeric"}


def test_heuristic_hypotheses_rank_by_correlation_strength():
    df = _correlated_df()
    hyps = he.heuristic_hypotheses(df, COLUMN_TYPES, max_hypotheses=5)
    assert hyps, "heuristic generator should always produce candidates for this data"
    # The strongly correlated x/y pair should outrank the uncorrelated noise pairs.
    pairs = [frozenset((h["col_a"], h["col_b"])) for h in hyps]
    assert frozenset(("x", "y")) in pairs
    xy_rank = pairs.index(frozenset(("x", "y")))
    if frozenset(("x", "noise")) in pairs:
        assert xy_rank < pairs.index(frozenset(("x", "noise")))


def test_heuristic_hypotheses_includes_categorical_numeric_pair():
    df = _correlated_df()
    hyps = he.heuristic_hypotheses(df, COLUMN_TYPES, max_hypotheses=10)
    pairs = [frozenset((h["col_a"], h["col_b"])) for h in hyps]
    assert frozenset(("group", "skewed")) in pairs


def test_heuristic_hypotheses_handles_no_numeric_columns():
    df = pd.DataFrame({"a": ["x", "y", "x"], "b": ["p", "q", "p"]})
    hyps = he.heuristic_hypotheses(df, {"a": "categorical", "b": "categorical"}, max_hypotheses=5)
    # chi2-eligible categorical/categorical pair should still surface
    assert any({h["col_a"], h["col_b"]} == {"a", "b"} for h in hyps)


def test_heuristic_hypotheses_empty_on_single_column():
    df = pd.DataFrame({"a": [1, 2, 3]})
    hyps = he.heuristic_hypotheses(df, {"a": "numeric"}, max_hypotheses=5)
    assert hyps == []


def test_parse_gemini_hypotheses_valid_json():
    text = (
        '```json\n[{"statement": "Revenue differs by region", "col_a": "region", '
        '"col_b": "revenue"}]\n```'
    )
    valid_cols = {"region", "revenue"}
    parsed = he._parse_gemini_hypotheses(text, valid_cols)
    assert parsed == [{"statement": "Revenue differs by region", "col_a": "region", "col_b": "revenue"}]


def test_parse_gemini_hypotheses_drops_unknown_columns():
    text = '[{"statement": "x", "col_a": "region", "col_b": "made_up_column"}]'
    parsed = he._parse_gemini_hypotheses(text, {"region", "revenue"})
    assert parsed == []


def test_parse_gemini_hypotheses_malformed_returns_none():
    assert he._parse_gemini_hypotheses("not json at all", {"a", "b"}) is None


def test_generate_hypotheses_falls_back_without_model():
    df = _correlated_df()
    result = he.generate_hypotheses(None, df, COLUMN_TYPES, max_hypotheses=3)
    assert result["source"] == "heuristic"
    assert 0 < len(result["hypotheses"]) <= 3


def test_verify_hypotheses_confirms_strong_signal():
    df = _correlated_df()
    hyps = [{"statement": "x and y move together", "col_a": "x", "col_b": "y"}]
    verified = he.verify_hypotheses(df, COLUMN_TYPES, hyps)
    assert len(verified) == 1
    v = verified[0]
    assert v["verdict"] == "CONFIRMED"
    assert v["p_value"] < 0.05
    assert "narrative" in v and v["narrative"]


def test_verify_hypotheses_rejects_noise_pair():
    df = _correlated_df(n=500)
    hyps = [{"statement": "x and noise move together", "col_a": "x", "col_b": "noise"}]
    verified = he.verify_hypotheses(df, COLUMN_TYPES, hyps)
    assert verified[0]["verdict"] == "NOT CONFIRMED"


def test_verify_hypotheses_marks_inconclusive_on_bad_columns():
    df = _correlated_df()
    hyps = [{"statement": "bogus", "col_a": "x", "col_b": "does_not_exist"}]
    verified = he.verify_hypotheses(df, COLUMN_TYPES, hyps)
    assert verified[0]["verdict"] == "INCONCLUSIVE"
    assert verified[0]["error"]


def test_run_hypothesis_engine_end_to_end_without_gemini():
    df = _correlated_df()
    report = he.run_hypothesis_engine(None, df, COLUMN_TYPES, max_hypotheses=4)
    assert report["source"] == "heuristic"
    assert len(report["results"]) > 0
    assert all(r["verdict"] in {"CONFIRMED", "NOT CONFIRMED", "INCONCLUSIVE"} for r in report["results"])


def test_run_hypothesis_engine_empty_dataframe_does_not_crash():
    df = pd.DataFrame({"a": pd.Series(dtype=float)})
    report = he.run_hypothesis_engine(None, df, {"a": "numeric"}, max_hypotheses=3)
    assert report["results"] == []
    assert report["hypotheses"] == []
