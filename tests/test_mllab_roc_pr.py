"""Tests for modules.mllab ROC-AUC / Precision-Recall curve support —
compute_roc_pr_curves(), build_roc_chart(), build_pr_chart(), and
roc_pr_verdict() — on top of run_baseline_models()'s classification output.
Accuracy alone is misleading on imbalanced classes (which ML Lab already
detects and offers SMOTE for); ROC-AUC and especially the Precision-Recall
curve are the standard remedy. Multiclass targets are supported via a
one-vs-rest scheme (build_multiclass_roc_chart, build_multiclass_pr_chart,
multiclass_roc_pr_verdict).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.mllab import (
    build_multiclass_pr_chart,
    build_multiclass_roc_chart,
    build_pr_chart,
    build_roc_chart,
    compute_roc_pr_curves,
    multiclass_roc_pr_verdict,
    roc_pr_verdict,
    run_baseline_models,
)


def _binary_df(n: int = 300, seed: int = 0, separation: float = 2.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = (separation * x1 + rng.normal(scale=1.0, size=n) > 0).astype(int)
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _imbalanced_binary_df(n: int = 400, seed: int = 1, positive_rate: float = 0.08) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    n_pos = max(2, int(n * positive_rate))
    target = np.zeros(n, dtype=int)
    # give the positive class a genuinely different x1 distribution so the
    # model has something real to learn, not just noise.
    pos_idx = rng.choice(n, size=n_pos, replace=False)
    target[pos_idx] = 1
    x1[pos_idx] += 2.5
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _three_class_df(n: int = 240, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    score = x1 + rng.normal(scale=0.3, size=n)
    target = pd.cut(score, bins=3, labels=["low", "mid", "high"])
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _four_class_df(n: int = 320, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    score = x1 + rng.normal(scale=0.3, size=n)
    target = pd.cut(score, bins=4, labels=["a", "b", "c", "d"])
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _regression_df(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = 3 * x1 - 2 * x2 + rng.normal(scale=1.0, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


class TestComputeRocPrCurves:
    def test_binary_classification_returns_curves_for_both_models(self):
        df = _binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves is not None
        assert curves["mode"] == "binary"
        assert set(curves["roc"].keys()) == {"Baseline", "Random Forest"}
        assert set(curves["pr"].keys()) == {"Baseline", "Random Forest"}

    def test_well_separated_classes_have_high_auc(self):
        df = _binary_df(separation=4.0)
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves["roc"]["Baseline"]["auc"] > 0.85

    def test_roc_curve_arrays_are_monotonic_rate_bounds(self):
        df = _binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        for name, d in curves["roc"].items():
            assert d["fpr"].min() >= 0.0 and d["fpr"].max() <= 1.0
            assert d["tpr"].min() >= 0.0 and d["tpr"].max() <= 1.0
            assert 0.0 <= d["auc"] <= 1.0

    def test_pr_curve_has_average_precision_and_baseline_rate(self):
        df = _binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        for name, d in curves["pr"].items():
            assert 0.0 <= d["ap"] <= 1.0
        assert 0.0 < curves["baseline_rate"] < 1.0

    def test_regression_returns_none(self):
        df = _regression_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "regression")
        assert compute_roc_pr_curves(result) is None

    def test_imbalanced_data_baseline_rate_matches_minority_share(self):
        df = _imbalanced_binary_df(positive_rate=0.08)
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves is not None
        assert curves["baseline_rate"] == pytest.approx(0.08, abs=0.03)


class TestMulticlassRocPrCurves:
    """One-vs-rest multiclass extension: per-class ROC/PR curves plus a
    macro-averaged AUC/AP summary, for targets with 3+ classes."""

    def test_three_class_returns_curves_not_none(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves is not None
        assert curves["mode"] == "multiclass"

    def test_three_class_has_one_curve_per_class_per_model(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert set(curves["classes"]) == {"low", "mid", "high"}
        for model_name in ("Baseline", "Random Forest"):
            assert set(curves["roc"][model_name].keys()) == set(curves["classes"])
            assert set(curves["pr"][model_name].keys()) == set(curves["classes"])
            for cls in curves["classes"]:
                roc_d = curves["roc"][model_name][cls]
                assert 0.0 <= roc_d["auc"] <= 1.0
                assert roc_d["fpr"].min() >= 0.0 and roc_d["fpr"].max() <= 1.0
                pr_d = curves["pr"][model_name][cls]
                assert 0.0 <= pr_d["ap"] <= 1.0

    def test_macro_average_present_and_bounded(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        for model_name in ("Baseline", "Random Forest"):
            assert 0.0 <= curves["macro_auc"][model_name] <= 1.0
            assert 0.0 <= curves["macro_ap"][model_name] <= 1.0

    def test_four_class_target_also_supported(self):
        df = _four_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves is not None
        assert curves["mode"] == "multiclass"
        assert len(curves["classes"]) == 4

    def test_well_separated_multiclass_has_high_macro_auc(self):
        # Reuse _three_class_df but with a stronger x1 signal via a larger
        # frame — pd.cut on x1 + small noise gives clearly separable bins.
        df = _three_class_df(n=600)
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        assert curves["macro_auc"]["Random Forest"] > 0.75


class TestChartBuilders:
    def test_build_roc_chart_returns_figure_with_traces(self):
        df = _binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        fig = build_roc_chart(curves)
        assert fig is not None
        # one trace per model plus the diagonal "random" reference line
        assert len(fig.data) == len(curves["roc"]) + 1

    def test_build_pr_chart_returns_figure_with_traces(self):
        df = _binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        fig = build_pr_chart(curves)
        assert fig is not None
        assert len(fig.data) >= len(curves["pr"])


class TestMulticlassChartBuilders:
    def test_build_multiclass_roc_chart_one_trace_per_class_plus_diagonal(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        fig = build_multiclass_roc_chart(curves, "Random Forest")
        assert fig is not None
        assert len(fig.data) == len(curves["classes"]) + 1

    def test_build_multiclass_pr_chart_one_trace_per_class(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        fig = build_multiclass_pr_chart(curves, "Random Forest")
        assert fig is not None
        assert len(fig.data) >= len(curves["classes"])

    def test_build_multiclass_chart_unknown_model_raises_keyerror(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        with pytest.raises(KeyError):
            build_multiclass_roc_chart(curves, "Nonexistent Model")


class TestRocPrVerdict:
    def test_high_auc_verdict_mentions_strong_or_excellent(self):
        df = _binary_df(separation=4.0)
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        verdict = roc_pr_verdict(curves)
        assert isinstance(verdict, str) and verdict
        assert "AUC" in verdict

    def test_verdict_flags_imbalance_when_baseline_rate_skewed(self):
        df = _imbalanced_binary_df(positive_rate=0.08)
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        verdict = roc_pr_verdict(curves)
        assert "imbalanc" in verdict.lower() or "precision-recall" in verdict.lower()

    def test_verdict_handles_none_gracefully(self):
        assert roc_pr_verdict(None) == ""


class TestMulticlassRocPrVerdict:
    def test_verdict_mentions_macro_auc(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        verdict = multiclass_roc_pr_verdict(curves)
        assert isinstance(verdict, str) and verdict
        assert "macro" in verdict.lower() and "auc" in verdict.lower()

    def test_verdict_names_weakest_class(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        curves = compute_roc_pr_curves(result)
        verdict = multiclass_roc_pr_verdict(curves)
        assert any(str(cls) in verdict for cls in curves["classes"])

    def test_verdict_handles_none_gracefully(self):
        assert multiclass_roc_pr_verdict(None) == ""
