"""
Regression Diagnostics Panel — pytest suite (ported from
eval/regression_diagnostics_eval.py; see test_auto_insights.py's module
docstring for why this port happened).
"""

import numpy as np
import pandas as pd
import pytest

from modules.regression_diagnostics import (
    MIN_ROWS_REQUIRED,
    coefficient_table,
    compute_vif,
    diagnostics_verdict,
    fit_ols,
    plot_qq,
    plot_residuals_vs_fitted,
    plot_scale_location,
    plot_vif_chart,
    run_diagnostics,
    summarize_fit,
)


@pytest.fixture(scope="module")
def data():
    np.random.seed(42)
    n = 300
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    x3 = x1 * 0.9 + np.random.normal(0, 0.1, n)
    noise = np.random.normal(0, 1, n)
    y = 3 * x1 + 2 * x2 + 5 + noise
    clean_df = pd.DataFrame({"x1": x1, "x2": x2, "y": y, "category": np.random.choice(["A", "B"], n)})
    collinear_df = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "y": y})
    return {"n": n, "clean_df": clean_df, "collinear_df": collinear_df}


@pytest.fixture(scope="module")
def fit1(data):
    return fit_ols(data["clean_df"], ["x1", "x2"], "y")


def test_fit_ols_recovers_known_coefficients(data, fit1):
    assert "error" not in fit1
    assert abs(fit1["model"].params["x1"] - 3) < 0.5
    assert abs(fit1["model"].params["x2"] - 2) < 0.5
    assert fit1["n_obs"] == data["n"]


def test_fit_ols_drops_categorical_columns(data):
    fit_mixed = fit_ols(data["clean_df"], ["x1", "x2", "category"], "y")
    assert "dropped_categorical" in fit_mixed
    assert "category" in fit_mixed["dropped_categorical"]


def test_fit_ols_rejects_too_few_rows(data):
    tiny_df = data["clean_df"].head(MIN_ROWS_REQUIRED - 1)
    assert "error" in fit_ols(tiny_df, ["x1", "x2"], "y")


def test_fit_ols_drops_zero_variance_columns(data):
    const_df = data["clean_df"].copy()
    const_df["const_col"] = 5.0
    fit_const = fit_ols(const_df, ["x1", "x2", "const_col"], "y")
    assert "dropped_zero_variance" in fit_const


def test_fit_ols_rejects_no_numeric_features(data):
    assert "error" in fit_ols(data["clean_df"], ["category"], "y")


def test_summarize_fit(data, fit1):
    summary = summarize_fit(fit1)
    assert summary["r_squared"] > 0.7
    assert summary["adj_r_squared"] <= summary["r_squared"]
    assert summary["n_obs"] == data["n"]
    assert np.isfinite(summary["aic"]) and np.isfinite(summary["bic"])


def test_coefficient_table(fit1):
    coef_table = coefficient_table(fit1)
    assert len(coef_table) == 3
    assert {"coefficient", "std_error", "t_stat", "p_value"}.issubset(coef_table.columns)


def test_vif_detects_multicollinearity(data, fit1):
    fit_collinear = fit_ols(data["collinear_df"], ["x1", "x2", "x3"], "y")
    vif_collinear = compute_vif(fit_collinear)
    assert len(vif_collinear) == 3
    x1_vif = vif_collinear[vif_collinear["feature"] == "x1"]["vif"].iloc[0]
    assert x1_vif > 5

    vif_clean = compute_vif(fit1)
    assert (vif_clean["vif"] < 5).all()

    single_feature_fit = fit_ols(data["clean_df"], ["x1"], "y")
    assert compute_vif(single_feature_fit).empty


def test_run_diagnostics_on_clean_fit(fit1):
    diag = run_diagnostics(fit1)
    assert 1.5 < diag["durbin_watson"] < 2.5
    assert 0 <= diag["shapiro_p"] <= 1
    assert 0 <= diag["breusch_pagan_p"] <= 1
    assert diag["residuals_normal"] is True
    assert isinstance(diag["homoscedastic"], bool)


def test_diagnostics_verdict_readable(fit1):
    diag = run_diagnostics(fit1)
    vif_clean = compute_vif(fit1)
    verdicts = diagnostics_verdict(diag, vif_clean)
    assert len(verdicts) >= 3
    assert all(v.startswith(("✅", "⚠️")) for v in verdicts)


def test_heteroscedastic_data_flagged():
    np.random.seed(42)
    x_hetero = np.random.uniform(1, 10, 300)
    y_hetero = 2 * x_hetero + np.random.normal(0, x_hetero, 300)
    hetero_df = pd.DataFrame({"x": x_hetero, "y": y_hetero})
    fit_hetero = fit_ols(hetero_df, ["x"], "y")
    diag_hetero = run_diagnostics(fit_hetero)
    assert diag_hetero["breusch_pagan_p"] < 0.05
    assert diag_hetero["homoscedastic"] is False


def test_plot_functions_return_figures(data, fit1):
    fit_collinear = fit_ols(data["collinear_df"], ["x1", "x2", "x3"], "y")
    vif_collinear = compute_vif(fit_collinear)
    single_feature_fit = fit_ols(data["clean_df"], ["x1"], "y")
    vif_single = compute_vif(single_feature_fit)

    diag = run_diagnostics(fit1)
    assert plot_residuals_vs_fitted(diag) is not None
    assert plot_qq(diag) is not None
    assert plot_scale_location(diag) is not None
    assert plot_vif_chart(vif_collinear) is not None
    assert plot_vif_chart(vif_single) is None
