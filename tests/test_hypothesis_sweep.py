"""Tests for modules.hypothesis_sweep — automated pairwise hypothesis
testing across a dataset with Benjamini-Hochberg FDR correction."""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

from modules.hypothesis_sweep import (
    DEFAULT_ALPHA,
    build_sweep_chart,
    cross_check_confounders,
    fingerprint_sweep,
    narrate_sweep,
    sweep_hypotheses,
    sweep_reference_numbers,
    verify_narration,
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


# --- sweep_reference_numbers / verify_narration --------------------------
# Fact-checks narrate_sweep()'s Gemini prose against the sweep's own
# already-computed test statistics (Run 17) — the same "plausible but
# wrong number" safety net insight_verifier applies to Auto Analyst
# findings, but backed by exact numbers the sweep already produced rather
# than a DataFrame recomputation.

def test_sweep_reference_numbers_includes_top_level_counts():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    numbers = sweep_reference_numbers(result)
    assert float(result["n_tests_run"]) in numbers
    assert float(result["n_significant"]) in numbers


def test_sweep_reference_numbers_includes_per_test_statistics():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    numbers = sweep_reference_numbers(result)
    row = result["tested"][0]
    assert round(float(row["effect_size"]), 2) in numbers
    assert round(float(row["n"]), 2) in numbers


def test_sweep_reference_numbers_empty_result_is_safe():
    assert sweep_reference_numbers(None) == set()
    assert sweep_reference_numbers({"tested": []}) == {0.0}


def test_verify_narration_confirmed_when_numbers_match():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    n_sig = result["n_significant"]
    narration = f"{n_sig} relationship(s) survived FDR correction — worth a closer look."
    verification = verify_narration(narration, result)
    assert verification["status"] == "confirmed"


def test_verify_narration_flagged_when_a_number_is_fabricated():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    narration = "A whopping 987654 relationships were significant — an extraordinary result."
    verification = verify_narration(narration, result)
    assert verification["status"] == "flagged"


def test_verify_narration_unverifiable_when_no_numbers_in_text():
    result = {"tested": [], "n_tests_run": 0, "n_significant": 0}
    verification = verify_narration("Nothing to report here.", result)
    assert verification["status"] == "unverifiable"


def test_verify_narration_never_raises_on_malformed_result():
    # A malformed "tested" value must degrade gracefully (no exception) —
    # the narration's number won't match the resulting near-empty
    # reference set, which correctly reads as "flagged", not a crash.
    verification = verify_narration("Some text with 42 in it.", {"tested": "not a list"})
    assert verification["status"] in ("flagged", "unverifiable")


# --- build_sweep_chart --------------------------------------------------------

def test_build_sweep_chart_returns_none_when_nothing_significant():
    result = {"tested": [{"col_a": "a", "col_b": "b", "significant": False, "effect_size": 0.01}]}
    assert build_sweep_chart(result) is None


def test_build_sweep_chart_returns_figure_for_significant_findings():
    df = _correlated_df()
    result = sweep_hypotheses(df, _column_types(df))
    fig = build_sweep_chart(result)
    assert fig is not None


# --- cross_check_confounders ---------------------------------------------
# Agentic follow-up to the sweep itself: does a significant pearson pair
# hold up once you control for a third variable? Reuses
# modules.confounder_detection.auto_scan_for_confounding — same paradox
# shape as test_confounder_detection's _simpsons_paradox_df, scaled up so
# the pooled pair also clears FDR significance inside a real sweep.

def _sweep_paradox_df(n_per_group: int = 60, seed: int = 1) -> pd.DataFrame:
    """Within each of two groups, x and y are strongly *negatively*
    correlated, but group B sits far up-and-to-the-right of group A, so the
    pooled correlation comes out strongly *positive* instead — classic
    Simpson's Paradox, scaled up so the pooled x/y pair is itself a
    significant sweep finding (not just a paradox in isolation)."""
    rng = np.random.default_rng(seed)
    x_a = np.linspace(1, 20, n_per_group)
    y_a = 20 - x_a + rng.normal(scale=0.3, size=n_per_group)
    x_b = np.linspace(30, 49, n_per_group)
    y_b = 70 - x_b + rng.normal(scale=0.3, size=n_per_group)
    return pd.DataFrame(
        {
            "x": np.concatenate([x_a, x_b]),
            "y": np.concatenate([y_a, y_b]),
            "group": ["A"] * n_per_group + ["B"] * n_per_group,
        }
    )


def test_cross_check_confounders_flags_planted_paradox():
    df = _sweep_paradox_df()
    result = sweep_hypotheses(df, _column_types(df))
    xy = next(r for r in result["tested"] if {r["col_a"], r["col_b"]} == {"x", "y"})
    assert xy["test"] == "pearson" and xy["significant"] is True  # sanity: the sweep itself found it

    cross = cross_check_confounders(df, _column_types(df), result)
    assert cross
    scan = next(s for s in cross if {s["x"], s["y"]} == {"x", "y"})
    verdicts = {f["confounder"]: f["verdict"] for f in scan["findings"]}
    assert verdicts.get("group") == "paradox"


def test_cross_check_confounders_empty_when_nothing_significant():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"a": rng.normal(size=50), "b": rng.normal(size=50)})
    result = sweep_hypotheses(df, _column_types(df))
    assert cross_check_confounders(df, _column_types(df), result) == []


def test_cross_check_confounders_skips_when_no_significant_pearson_pair():
    df = _correlated_df()
    # Only the categorical/categorical pair is significant, no pearson pair.
    fake_result = {
        "tested": [
            {"col_a": "group", "col_b": "tier", "test": "chi2", "significant": True, "effect_size": 0.9},
            {"col_a": "x", "col_b": "z", "test": "pearson", "significant": False, "effect_size": 0.01},
        ]
    }
    assert cross_check_confounders(df, _column_types(df), fake_result) == []


def test_cross_check_confounders_handles_missing_or_malformed_result_safely():
    df = _correlated_df()
    types = _column_types(df)
    assert cross_check_confounders(df, types, None) == []
    assert cross_check_confounders(df, types, {"tested": "not a list"}) == []
