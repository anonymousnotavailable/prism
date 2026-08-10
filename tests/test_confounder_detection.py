"""Tests for modules.confounder_detection — Simpson's Paradox / confounding
variable detection. Stratifies (or partials out) candidate confounders
behind an Auto-Insights correlation finding and flags cases where the
relationship reverses sign or collapses once you control for a third
variable — the classic "correlation isn't the whole story" check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.confounder_detection import (
    auto_scan_for_confounding,
    detect_confounders,
    narrate_confounder_finding,
    partial_correlation,
    stratified_correlation,
)


def _simpsons_paradox_df() -> pd.DataFrame:
    """Textbook reversal: within each group x and y are perfectly *negatively*
    correlated (r = -1), but group B sits up-and-to-the-right of group A, so
    pooling the two groups together flips the overall correlation positive
    (r ≈ +0.49). Anyone reading only the pooled number would draw the
    opposite conclusion from what's actually happening inside each group.
    """
    group_a_x = [1, 2, 3, 4, 5]
    group_a_y = [5, 4, 3, 2, 1]
    group_b_x = [7, 8, 9, 10, 11]
    group_b_y = [9, 8, 7, 6, 5]
    return pd.DataFrame(
        {
            "x": group_a_x + group_b_x,
            "y": group_a_y + group_b_y,
            "group": ["A"] * 5 + ["B"] * 5,
        }
    )


def _robust_df() -> pd.DataFrame:
    """x and y correlate strongly and a third column carries no confounding
    information at all — the relationship should survive stratification.
    """
    rng = np.random.default_rng(0)
    x = np.arange(60, dtype=float)
    y = x * 2 + rng.normal(0, 0.5, size=60)
    noise_group = np.tile(["P", "Q", "R"], 20)
    return pd.DataFrame({"x": x, "y": y, "noise_group": noise_group})


# ─────────────────────────────────────────────────────────────────────────
# stratified_correlation
# ─────────────────────────────────────────────────────────────────────────
def test_stratified_correlation_detects_sign_flip():
    df = _simpsons_paradox_df()
    result = stratified_correlation(df, "x", "y", "group")

    assert result["overall_r"] > 0.3
    assert result["weighted_within_group_r"] < -0.9
    assert result["verdict"] == "paradox"
    assert len(result["per_group"]) == 2
    for g in result["per_group"]:
        assert g["r"] < -0.9
        assert g["n"] == 5


def test_stratified_correlation_robust_relationship():
    df = _robust_df()
    result = stratified_correlation(df, "x", "y", "noise_group")

    assert result["overall_r"] > 0.9
    assert result["weighted_within_group_r"] > 0.9
    assert result["verdict"] == "robust"


def test_stratified_correlation_flags_attenuation_without_sign_flip():
    # Overall correlation driven almost entirely by one dominant group;
    # within the other, near-zero — same sign throughout, but the
    # relationship materially weakens once stratified.
    rng = np.random.default_rng(1)
    x1 = np.arange(30, dtype=float)
    y1 = x1 * 3 + rng.normal(0, 0.5, size=30)
    x2 = np.arange(30, dtype=float)
    y2 = rng.normal(0, 5, size=30)  # no real relationship in this group
    df = pd.DataFrame(
        {"x": np.concatenate([x1, x2]), "y": np.concatenate([y1, y2]), "grp": ["A"] * 30 + ["B"] * 30}
    )
    result = stratified_correlation(df, "x", "y", "grp")
    assert result["verdict"] in ("attenuated", "paradox")


def test_stratified_correlation_ignores_undersized_groups():
    df = _simpsons_paradox_df()
    df = pd.concat([df, pd.DataFrame({"x": [3], "y": [3], "group": ["C"]})], ignore_index=True)
    result = stratified_correlation(df, "x", "y", "group", min_group_size=3)
    assert len(result["per_group"]) == 2  # group C (n=1) excluded
    assert result["excluded_small_groups"] == 1


def test_stratified_correlation_returns_none_verdict_with_too_few_groups():
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [4, 3, 2, 1], "group": ["A", "A", "A", "A"]})
    result = stratified_correlation(df, "x", "y", "group")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────
# partial_correlation
# ─────────────────────────────────────────────────────────────────────────
def test_partial_correlation_removes_shared_driver():
    # z drives both x and y; once z is partialled out, x and y should have
    # near-zero residual correlation.
    rng = np.random.default_rng(2)
    z = rng.normal(0, 1, 500)
    x = z * 2 + rng.normal(0, 0.1, 500)
    y = z * 3 + rng.normal(0, 0.1, 500)
    df = pd.DataFrame({"x": x, "y": y, "z": z})

    overall_r = df["x"].corr(df["y"])
    partial_r = partial_correlation(df, "x", "y", "z")

    assert overall_r > 0.9
    assert abs(partial_r) < 0.2


def test_partial_correlation_returns_none_on_perfect_collinearity():
    df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10], "z": [1, 2, 3, 4, 5]})
    # z == x exactly -> denominator term (1 - r_xz^2) is ~0
    assert partial_correlation(df, "x", "y", "z") is None


# ─────────────────────────────────────────────────────────────────────────
# detect_confounders — orchestration across candidate columns
# ─────────────────────────────────────────────────────────────────────────
def test_detect_confounders_flags_the_categorical_paradox_column():
    df = _simpsons_paradox_df()
    column_types = {"x": "numeric", "y": "numeric", "group": "categorical"}
    findings = detect_confounders(df, "x", "y", column_types)

    assert len(findings) == 1
    assert findings[0]["confounder"] == "group"
    assert findings[0]["type"] == "categorical"
    assert findings[0]["verdict"] == "paradox"


def test_detect_confounders_skips_robust_confounders_when_flagged_only():
    df = _robust_df()
    column_types = {"x": "numeric", "y": "numeric", "noise_group": "categorical"}
    findings = detect_confounders(df, "x", "y", column_types)
    assert all(f["verdict"] == "robust" for f in findings)


def test_detect_confounders_handles_numeric_candidate():
    rng = np.random.default_rng(3)
    z = rng.normal(0, 1, 200)
    x = z * 2 + rng.normal(0, 0.1, 200)
    y = z * 3 + rng.normal(0, 0.1, 200)
    df = pd.DataFrame({"x": x, "y": y, "z": z})
    column_types = {"x": "numeric", "y": "numeric", "z": "numeric"}

    findings = detect_confounders(df, "x", "y", column_types)
    z_finding = next(f for f in findings if f["confounder"] == "z")
    assert z_finding["type"] == "numeric"
    assert z_finding["verdict"] in ("paradox", "attenuated")


def test_detect_confounders_empty_df():
    df = pd.DataFrame({"x": [], "y": [], "g": []})
    findings = detect_confounders(df, "x", "y", {"x": "numeric", "y": "numeric", "g": "categorical"})
    assert findings == []


# ─────────────────────────────────────────────────────────────────────────
# auto_scan_for_confounding — the agentic entry point (no pair pre-selected)
# ─────────────────────────────────────────────────────────────────────────
def test_auto_scan_finds_the_paradox_without_a_hinted_pair():
    df = _simpsons_paradox_df()
    column_types = {"x": "numeric", "y": "numeric", "group": "categorical"}
    results = auto_scan_for_confounding(df, column_types)

    assert len(results) == 1
    assert {results[0]["x"], results[0]["y"]} == {"x", "y"}
    assert results[0]["findings"][0]["confounder"] == "group"


def test_auto_scan_returns_empty_when_nothing_worth_flagging():
    df = _robust_df()
    column_types = {"x": "numeric", "y": "numeric", "noise_group": "categorical"}
    results = auto_scan_for_confounding(df, column_types)
    assert results == []


def test_auto_scan_handles_too_few_numeric_columns():
    df = pd.DataFrame({"x": [1, 2, 3], "g": ["a", "b", "c"]})
    results = auto_scan_for_confounding(df, {"x": "numeric", "g": "categorical"})
    assert results == []


# ─────────────────────────────────────────────────────────────────────────
# narrate_confounder_finding
# ─────────────────────────────────────────────────────────────────────────
def test_narrate_confounder_finding_no_model():
    df = _simpsons_paradox_df()
    findings = detect_confounders(df, "x", "y", {"x": "numeric", "y": "numeric", "group": "categorical"})
    text, error = narrate_confounder_finding(None, "x", "y", findings[0])
    assert text == ""
    assert error


def test_narrate_confounder_finding_calls_gemini():
    df = _simpsons_paradox_df()
    findings = detect_confounders(df, "x", "y", {"x": "numeric", "y": "numeric", "group": "categorical"})

    class _FakeResponse:
        text = "Within each group the relationship is actually negative — the pooled positive correlation is an artifact of group differences."

    class _FakeModel:
        def generate_content(self, contents):
            assert "group" in contents.lower()
            assert "paradox" in contents.lower() or "simpson" in contents.lower()
            return _FakeResponse()

    text, error = narrate_confounder_finding(_FakeModel(), "x", "y", findings[0])
    assert error is None
    assert "negative" in text.lower()
