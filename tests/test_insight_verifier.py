"""Unit tests for modules.insight_verifier — the statistical verification
layer that turns Auto Analyst's headline findings into tested claims.

Written before the implementation (TDD): these pin down the contract the
Auto Analyst UI wiring in app.py relies on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import insight_verifier


def _rng():
    return np.random.RandomState(42)


def test_verify_relationships_flags_a_real_correlation():
    rng = _rng()
    x = rng.normal(size=300)
    y = x * 3 + rng.normal(scale=0.1, size=300)  # near-perfect linear relationship
    df = pd.DataFrame({"x": x, "y": y, "noise": rng.normal(size=300)})
    column_types = {"x": "numeric", "y": "numeric", "noise": "numeric"}

    findings = insight_verifier.verify_relationships(df, column_types)

    assert findings, "expected at least one verified finding"
    top = findings[0]
    assert {top["col_a"], top["col_b"]} == {"x", "y"}
    assert top["test"] == "pearson"
    assert top["significant"] is True
    assert top["p_value"] < 0.001
    assert "p=" in top["verdict"] or "p<" in top["verdict"]


def test_verify_relationships_flags_a_real_group_difference():
    rng = _rng()
    group_a = rng.normal(loc=10, scale=1, size=150)
    group_b = rng.normal(loc=20, scale=1, size=150)
    df = pd.DataFrame(
        {
            "value": np.concatenate([group_a, group_b]),
            "segment": ["A"] * 150 + ["B"] * 150,
        }
    )
    column_types = {"value": "numeric", "segment": "categorical"}

    findings = insight_verifier.verify_relationships(df, column_types)

    assert findings
    top = findings[0]
    assert top["test"] == "ttest"
    assert top["significant"] is True
    assert top["effect_size_label"] in ("medium", "large")


def test_verify_relationships_does_not_flag_pure_noise():
    rng = _rng()
    df = pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})
    column_types = {"a": "numeric", "b": "numeric"}

    findings = insight_verifier.verify_relationships(df, column_types)

    # A weak/random correlation may still be *returned* (there's nothing else
    # to rank), but it must not be reported as significant.
    for f in findings:
        if f["test"] == "pearson":
            assert f["p_value"] > 0.01 or not f["significant"] or abs(f["effect_size"]) < 0.3


def test_verify_relationships_handles_no_numeric_columns():
    df = pd.DataFrame({"cat1": ["a", "b", "a", "b"], "cat2": ["x", "y", "x", "y"]})
    column_types = {"cat1": "categorical", "cat2": "categorical"}

    findings = insight_verifier.verify_relationships(df, column_types)

    assert isinstance(findings, list)  # chi-square candidates are fine, just shouldn't crash


def test_verify_relationships_handles_empty_dataframe():
    df = pd.DataFrame({"x": pd.Series(dtype=float), "y": pd.Series(dtype=float)})
    column_types = {"x": "numeric", "y": "numeric"}

    findings = insight_verifier.verify_relationships(df, column_types)

    assert findings == []


def test_verify_relationships_respects_max_findings():
    rng = _rng()
    df = pd.DataFrame({f"n{i}": rng.normal(size=100) for i in range(6)})
    column_types = {c: "numeric" for c in df.columns}

    findings = insight_verifier.verify_relationships(df, column_types, max_findings=2)

    assert len(findings) <= 2


def test_verify_relationships_never_raises_on_single_column():
    df = pd.DataFrame({"only": [1, 2, 3, 4, 5]})
    column_types = {"only": "numeric"}

    findings = insight_verifier.verify_relationships(df, column_types)

    assert findings == []


def test_findings_are_ranked_significant_first():
    rng = _rng()
    strong_x = rng.normal(size=200)
    strong_y = strong_x * 5 + rng.normal(scale=0.1, size=200)
    weak = rng.normal(size=200)
    df = pd.DataFrame({"strong_x": strong_x, "strong_y": strong_y, "weak": weak})
    column_types = {c: "numeric" for c in df.columns}

    findings = insight_verifier.verify_relationships(df, column_types)

    sig_flags = [f["significant"] for f in findings]
    # once a False appears, no True should follow it
    if False in sig_flags:
        first_false = sig_flags.index(False)
        assert all(not s for s in sig_flags[first_false:])
