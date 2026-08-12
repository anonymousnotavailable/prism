"""Tests for modules.mllab's decision-threshold tuning and probability
calibration — the "beyond SMOTE" levers for imbalanced binary
classification: tune_decision_threshold(), build_threshold_chart(),
threshold_verdict(), run_probability_calibration(),
build_calibration_chart(), calibration_verdict().
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from modules.mllab import (
    build_calibration_chart,
    build_threshold_chart,
    calibration_verdict,
    run_baseline_models,
    run_probability_calibration,
    threshold_verdict,
    tune_decision_threshold,
)


def _imbalanced_binary_df(n: int = 600, seed: int = 1, positive_rate: float = 0.15) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    n_pos = max(10, int(n * positive_rate))
    target = np.zeros(n, dtype=int)
    pos_idx = rng.choice(n, size=n_pos, replace=False)
    target[pos_idx] = 1
    x1[pos_idx] += 2.2
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _regression_df(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = 3 * x1 - 2 * x2 + rng.normal(scale=1.0, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _three_class_df(n: int = 240, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    score = x1 + rng.normal(scale=0.3, size=n)
    target = pd.cut(score, bins=3, labels=["low", "mid", "high"])
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


class TestTuneDecisionThreshold:
    def test_binary_classification_returns_full_sweep(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result, model_name="Random Forest")
        assert "error" not in threshold_result
        assert len(threshold_result["thresholds"]) == len(threshold_result["f1_scores"])
        assert 0.0 <= threshold_result["best_threshold_f1"] <= 1.0
        assert threshold_result["best_f1"] >= threshold_result["default_metrics"]["f1"]

    def test_regression_task_returns_error(self):
        df = _regression_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "regression")
        threshold_result = tune_decision_threshold(result)
        assert "error" in threshold_result

    def test_multiclass_returns_error(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result)
        assert "error" in threshold_result

    def test_unknown_model_name_returns_error(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result, model_name="Nonexistent Model")
        assert "error" in threshold_result

    def test_cost_sensitive_threshold_shifts_with_cost_ratio(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        # Penalizing false negatives heavily should push the optimal
        # threshold down (favor recall) relative to a symmetric cost.
        symmetric = tune_decision_threshold(result, model_name="Random Forest", cost_fp=1.0, cost_fn=1.0)
        fn_heavy = tune_decision_threshold(result, model_name="Random Forest", cost_fp=1.0, cost_fn=10.0)
        assert fn_heavy["best_threshold_cost"] <= symmetric["best_threshold_cost"]

    def test_default_metrics_use_threshold_half(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result, model_name="Random Forest")
        assert threshold_result["default_metrics"]["threshold"] == 0.5


class TestBuildThresholdChart:
    def test_returns_figure_with_three_metric_lines(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result, model_name="Random Forest")
        fig = build_threshold_chart(threshold_result)
        assert isinstance(fig, go.Figure)
        trace_names = {trace.name for trace in fig.data}
        assert {"Precision", "Recall", "F1"}.issubset(trace_names)


class TestThresholdVerdict:
    def test_returns_nonempty_list_of_strings(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        threshold_result = tune_decision_threshold(result, model_name="Random Forest")
        verdicts = threshold_verdict(threshold_result)
        assert isinstance(verdicts, list)
        assert len(verdicts) > 0
        assert all(isinstance(v, str) for v in verdicts)


class TestRunProbabilityCalibration:
    def test_binary_classification_returns_brier_scores(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        calib_result = run_probability_calibration(result, model_name="Random Forest")
        assert "error" not in calib_result
        assert calib_result["brier_before"] >= 0
        assert calib_result["brier_after"] >= 0
        assert "reliability_uncalibrated" in calib_result
        assert "reliability_calibrated" in calib_result

    def test_regression_task_returns_error(self):
        df = _regression_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "regression")
        calib_result = run_probability_calibration(result)
        assert "error" in calib_result

    def test_multiclass_returns_error(self):
        df = _three_class_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        calib_result = run_probability_calibration(result)
        assert "error" in calib_result

    def test_too_few_minority_samples_returns_error_not_crash(self):
        df = _imbalanced_binary_df(n=40, positive_rate=0.02)  # ~1 positive row
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        calib_result = run_probability_calibration(result, model_name="Random Forest")
        # Should degrade gracefully to an error dict, never raise.
        assert isinstance(calib_result, dict)

    def test_isotonic_and_sigmoid_methods_both_run(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        for method in ["isotonic", "sigmoid"]:
            calib_result = run_probability_calibration(result, model_name="Random Forest", method=method)
            assert "error" not in calib_result
            assert calib_result["method"] == method


class TestBuildCalibrationChart:
    def test_returns_figure_with_calibrated_and_uncalibrated_traces(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        calib_result = run_probability_calibration(result, model_name="Random Forest")
        fig = build_calibration_chart(calib_result)
        assert isinstance(fig, go.Figure)
        trace_names = {trace.name for trace in fig.data}
        assert any("uncalibrated" in n.lower() for n in trace_names)
        assert any("calibrated" in n.lower() and "uncalibrated" not in n.lower() for n in trace_names)


class TestCalibrationVerdict:
    def test_returns_nonempty_list_mentioning_brier(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        calib_result = run_probability_calibration(result, model_name="Random Forest")
        verdicts = calibration_verdict(calib_result)
        assert isinstance(verdicts, list)
        assert any("brier" in v.lower() for v in verdicts)


class TestRunBaselineModelsStoresYTrain:
    def test_y_train_present_and_correct_length(self):
        df = _imbalanced_binary_df()
        result = run_baseline_models(df, ["x1", "x2"], "target", "classification")
        assert "y_train" in result
        assert len(result["y_train"]) == result["n_train"]
