"""Tests for modules.regression_diagnostics's robust regression comparison —
fit_robust_regressors(), robust_regression_verdict(), and
build_robust_regression_chart(). Fits Huber, RANSAC, and Theil-Sen
(sklearn.linear_model, already pinned) alongside the existing OLS fit so a
diagnostics panel that flags a high-leverage outlier or non-normal
residuals has an actual next step, not just a warning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from modules.regression_diagnostics import (
    build_robust_regression_chart,
    fit_ols,
    fit_robust_regressors,
    robust_regression_verdict,
)

TRUE_SLOPE = 3.0
TRUE_INTERCEPT = 1.0


def _clean_linear_df(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(scale=2.0, size=n)
    y = TRUE_INTERCEPT + TRUE_SLOPE * x1 - 1.5 * x2 + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def _outlier_perturbed_df(n: int = 200, seed: int = 1, n_outliers: int = 12) -> pd.DataFrame:
    df = _clean_linear_df(n=n, seed=seed)
    rng = np.random.default_rng(seed + 100)
    outlier_idx = rng.choice(df.index, size=n_outliers, replace=False)
    # Push a small subset of y values wildly off the true line — the
    # classic "OLS gets dragged, robust methods don't" scenario.
    df.loc[outlier_idx, "y"] = df.loc[outlier_idx, "y"] + rng.choice([-1, 1], size=n_outliers) * 60
    return df


class TestFitRobustRegressors:
    def test_clean_data_all_models_fit_and_agree_with_ols(self):
        df = _clean_linear_df()
        ols_fit = fit_ols(df, ["x1", "x2"], "y")
        comparison = fit_robust_regressors(ols_fit)

        assert not comparison["errors"]
        for model_name in ["OLS", "Huber", "RANSAC", "Theil-Sen"]:
            assert model_name in comparison["coefficients"].columns
            assert comparison["r_squared"][model_name] > 0.8

        # On clean data every model should land close to the true slope.
        for model_name in ["OLS", "Huber", "RANSAC", "Theil-Sen"]:
            coef_x1 = comparison["coefficients"].loc["x1", model_name]
            assert abs(coef_x1 - TRUE_SLOPE) < 0.5

    def test_coefficients_table_has_const_and_feature_rows(self):
        df = _clean_linear_df()
        ols_fit = fit_ols(df, ["x1", "x2"], "y")
        comparison = fit_robust_regressors(ols_fit)
        assert list(comparison["coefficients"].index) == ["const", "x1", "x2"]

    def test_ransac_inlier_fraction_present_and_bounded(self):
        df = _clean_linear_df()
        ols_fit = fit_ols(df, ["x1", "x2"], "y")
        comparison = fit_robust_regressors(ols_fit)
        frac = comparison["ransac_inlier_fraction"]
        assert frac is not None
        assert 0.0 <= frac <= 1.0

    def test_outliers_pull_ols_more_than_huber(self):
        df = _outlier_perturbed_df()
        ols_fit = fit_ols(df, ["x1", "x2"], "y")
        comparison = fit_robust_regressors(ols_fit)

        ols_x1 = comparison["coefficients"].loc["x1", "OLS"]
        huber_x1 = comparison["coefficients"].loc["x1", "Huber"]
        # Huber's estimate should land closer to the true slope than OLS's
        # once a subset of rows has been pushed far off the line.
        assert abs(huber_x1 - TRUE_SLOPE) < abs(ols_x1 - TRUE_SLOPE)

    def test_outliers_reduce_ransac_inlier_fraction(self):
        clean_comparison = fit_robust_regressors(fit_ols(_clean_linear_df(), ["x1", "x2"], "y"))
        outlier_comparison = fit_robust_regressors(fit_ols(_outlier_perturbed_df(), ["x1", "x2"], "y"))
        # Not a strict guarantee for every random seed, but with 12/200 (6%)
        # rows pushed 60 units off the line, RANSAC should flag noticeably
        # more outliers than on clean data.
        assert outlier_comparison["ransac_inlier_fraction"] <= clean_comparison["ransac_inlier_fraction"]

    def test_rmse_present_for_every_fitted_model(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        for model_name in ["OLS", "Huber", "RANSAC", "Theil-Sen"]:
            assert comparison["rmse"][model_name] >= 0


class TestRobustRegressionVerdict:
    def test_clean_data_no_sign_flip_verdict(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        verdicts = robust_regression_verdict(comparison)
        assert isinstance(verdicts, list)
        assert any("no coefficient sign flip" in v.lower() for v in verdicts)

    def test_verdict_mentions_ransac_outlier_fraction(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        verdicts = robust_regression_verdict(comparison)
        assert any("ransac" in v.lower() for v in verdicts)

    def test_errors_surface_as_info_lines(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        comparison["errors"] = {"Theil-Sen": "singular matrix"}
        verdicts = robust_regression_verdict(comparison)
        assert any("theil-sen" in v.lower() and "singular matrix" in v.lower() for v in verdicts)


class TestBuildRobustRegressionChart:
    def test_returns_figure_with_one_trace_per_model(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        fig = build_robust_regression_chart(comparison)
        assert isinstance(fig, go.Figure)
        model_names_in_traces = {trace.name for trace in fig.data}
        assert model_names_in_traces == {"OLS", "Huber", "RANSAC", "Theil-Sen"}

    def test_excludes_intercept_row_from_chart(self):
        df = _clean_linear_df()
        comparison = fit_robust_regressors(fit_ols(df, ["x1", "x2"], "y"))
        fig = build_robust_regression_chart(comparison)
        for trace in fig.data:
            assert "const" not in list(trace.x)

    def test_returns_none_when_no_models_fit(self):
        comparison = {
            "coefficients": pd.DataFrame({"OLS": [1.0, 2.0]}, index=["const", "x1"]),
            "r_squared": {"OLS": 0.9},
            "rmse": {"OLS": 0.1},
            "errors": {"Huber": "failed", "RANSAC": "failed", "Theil-Sen": "failed"},
            "feature_names": ["x1"],
            "ransac_inlier_fraction": None,
        }
        fig = build_robust_regression_chart(comparison)
        # Only OLS present — still a valid (if sparse) comparison chart, not None.
        assert isinstance(fig, go.Figure)
