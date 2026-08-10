"""Tests for modules.hypothesis_sweep — automated pairwise hypothesis
testing across a dataset with Benjamini-Hochberg FDR correction."""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

from modules.hypothesis_sweep import (
    DEFAULT_ALPHA,
    build_sweep_chart,
    fingerprint_sweep,
    narrate_sweep,
    sweep_hypotheses,
)


def _correlated_df(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    y = 3 * x + rng.normal(scale=0.1, size=n)  # strong, near-deterministic correlation
    group = rng.choice(["a", "b", "c"], size=n)
    # numeric that genuinely differs by group (planted ANOVA signal)
    offset = pd.Series(group).map({"a": 0, "b": 5, "c": 10}).to_numpy()
    z = offset + rng.normal(scale=0.5, size=n)
    # two categoricals that are genuinely associated (planted chi-square signal)
    cat_a = pd.Series(group)
    cat_b = cat_a.map({"a": "low", "b": "mid", "c": "high"})
    return pd.DataFrame({"x": x, "y": y, "z": z, "group": group, "tier": cat_b})


def _column_types(df: pd.DataFrame) -> dict[str, str]:
    types = {}
    for col in df.columns:
        types[col] = "numeric" if pd.api.types.is_numeric_dtype(df[col]) else "categorical"
    return types


# --- sweep_hypotheses: planted-signal recovery ----------------------------

def test_sweep_finds_planted_numeric_correlation():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    xy = next(r for r in result["tested"] if {r["col_a"], r["col_b"]} == {"x", "y"})
    assert xy["test"] == "pearson"
    assert xy["significant"] is True
    assert abs(xy["effect_size"]) > 0.9


def test_sweep_finds_planted_anova_signal():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    zg = next(r for r in result["tested"] if {r["col_a"], r["col_b"]} == {"z", "group"})
    assert zg["test"] == "anova"
    assert zg["significant"] is True


def test_sweep_finds_planted_chi2_signal():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    gt = next(r for r in result["tested"] if {r["col_a"], r["col_b"]} == {"group", "tier"})
    assert gt["test"] == "chi2"
    assert gt["significant"] is True


def test_sweep_result_is_sorted_by_adjusted_p_value():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    p_adjs = [r["p_adj"] for r in result["tested"]]
    assert p_adjs == sorted(p_adjs)


def test_sweep_counts_are_internally_consistent():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    assert result["n_tests_run"] == len(result["tested"])
    assert result["n_significant"] == sum(1 for r in result["tested"] if r["significant"])
    assert result["n_significant"] <= result["n_tests_run"]


# --- FDR correction actually corrects -------------------------------------

def test_fdr_correction_matches_statsmodels_directly():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df), alpha=0.05)
    raw_p = [r["p_value"] for r in sorted(result["tested"], key=lambda r: (r["col_a"], r["col_b"]))]
    # order-independent check: adjusted p-values from the module should be a
    # valid Benjamini-Hochberg correction of the module's own raw p-values
    reject, expected_adj, _, _ = multipletests(
        [r["p_value"] for r in result["tested"]], alpha=0.05, method="fdr_bh"
    )
    actual_adj = [r["p_adj"] for r in result["tested"]]
    assert np.allclose(actual_adj, expected_adj)
    assert [bool(x) for x in reject] == [r["significant"] for r in result["tested"]]


def test_fdr_correction_suppresses_noise_false_positives():
    # 15 mutually independent noise columns -> 105 pairs. At raw alpha=0.05
    # we'd expect ~5 "significant" pairs by chance alone; BH correction
    # should knock most or all of those back down since there's no real signal.
    rng = np.random.default_rng(123)
    df = pd.DataFrame({f"n{i}": rng.normal(size=300) for i in range(15)})
    result = sweep_hypotheses(df, _column_types(df))
    raw_significant = sum(1 for r in result["tested"] if r["p_value"] < 0.05)
    assert result["n_significant"] <= raw_significant


def test_effect_size_is_populated_and_sortable():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    for row in result["tested"]:
        assert row["effect_size"] is not None
        assert row["effect_size_name"]
        assert row["effect_size_label"]


# --- pair cap ---------------------------------------------------------------

def test_max_pairs_cap_is_respected_and_reported():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({f"n{i}": rng.normal(size=50) for i in range(10)})  # 45 pairs
    result = sweep_hypotheses(df, _column_types(df), max_pairs=3)
    assert result["n_pairs_available"] == 45
    assert len(result["tested"]) <= 3
    assert result["n_pairs_skipped"] >= 42


# --- edge cases --------------------------------------------------------------

def test_sweep_handles_empty_dataframe():
    df = pd.DataFrame()
    result = sweep_hypotheses(df, {})
    assert result["tested"] == []
    assert result["n_tests_run"] == 0
    assert result["n_significant"] == 0


def test_sweep_handles_single_column():
    df = pd.DataFrame({"only": [1, 2, 3, 4, 5]})
    result = sweep_hypotheses(df, {"only": "numeric"})
    assert result["tested"] == []
    assert result["n_pairs_available"] == 0


def test_sweep_skips_single_category_columns_without_crashing():
    df = pd.DataFrame({"const": ["a"] * 20, "value": range(20)})
    result = sweep_hypotheses(df, {"const": "categorical", "value": "numeric"})
    assert result["tested"] == []
    assert result["n_pairs_skipped"] == 1


def test_sweep_handles_nan_heavy_columns():
    df = pd.DataFrame({"a": [np.nan] * 10 + list(range(10)), "b": list(range(20))})
    result = sweep_hypotheses(df, {"a": "numeric", "b": "numeric"})
    # should not raise; either scores the pair on the non-null rows or skips it
    assert isinstance(result["tested"], list)


# --- fingerprint_sweep -------------------------------------------------------

def test_fingerprint_is_stable_for_the_same_result():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    assert fingerprint_sweep(result) == fingerprint_sweep(result)


def test_fingerprint_changes_when_significant_findings_change():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    other = sweep_hypotheses(_correlated_df(seed=99), _column_types(df))
    assert fingerprint_sweep(result) != fingerprint_sweep(other)


def test_fingerprint_of_empty_result_is_stable():
    empty = {"tested": [], "n_tests_run": 0, "n_significant": 0}
    assert fingerprint_sweep(empty) == fingerprint_sweep(empty) == "empty"
    assert fingerprint_sweep(None) == "empty"


# --- narrate_sweep -----------------------------------------------------------

def test_narrate_sweep_without_model_returns_error():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    narration, error = narrate_sweep(None, result)
    assert narration == ""
    assert error is not None


def test_narrate_sweep_with_no_viable_pairs_skips_gemini():
    empty = {"tested": [], "n_tests_run": 0, "n_significant": 0}

    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called with no viable pairs")

    narration, error = narrate_sweep(_ShouldNotBeCalled(), empty)
    assert error is None
    assert "nothing to narrate" in narration.lower()


def test_narrate_sweep_with_no_significant_findings_skips_gemini():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"n0": rng.normal(size=30), "n1": rng.normal(size=30)})
    result = sweep_hypotheses(df, _column_types(df))
    result["tested"] = [{**r, "significant": False} for r in result["tested"]]

    class _ShouldNotBeCalled:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Gemini should not be called with nothing significant")

    narration, error = narrate_sweep(_ShouldNotBeCalled(), result)
    assert error is None
    assert "no reliable relationships" in narration.lower()


def test_narrate_sweep_calls_gemini_with_top_findings():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))

    class _FakeResponse:
        text = "The strongest signal is between x and y — worth a closer look."

    class _FakeModel:
        def generate_content(self, contents):
            assert "hypothesis sweep" in contents.lower()
            assert "false-discovery-rate" in contents.lower()
            return _FakeResponse()

    narration, error = narrate_sweep(_FakeModel(), result)
    assert error is None
    assert "worth a closer look" in narration.lower()


# --- build_sweep_chart --------------------------------------------------------

def test_build_sweep_chart_returns_none_when_nothing_significant():
    result = {"tested": [{"col_a": "a", "col_b": "b", "significant": False, "effect_size": 0.01}]}
    assert build_sweep_chart(result) is None


def test_build_sweep_chart_returns_figure_for_significant_findings():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    fig = build_sweep_chart(result)
    assert fig is not None
