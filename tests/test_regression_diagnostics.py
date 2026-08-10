"""Tests for modules.regression_diagnostics — statsmodels OLS diagnostic battery.

Ported from eval/regression_diagnostics_eval.py (see .prism/audit_2026-08-10.md
for why this port happened — Run 2 claimed these as pytest coverage but they
were never actually collected by pytest).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

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


def _make_data():
    rng = np.random.default_rng(42)
    n = 300
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    x3 = x1 * 0.9 + rng.normal(0, 0.1, n)  # collinear with x1
    noise = rng.normal(0, 1, n)
    y = 3 * x1 + 2 * x2 + 5 + noise
    clean_df = pd.DataFrame({"x1": x1, "x2": x2, "y": y, "category": rng.choice(["A", "B"], n)})
    collinear_df = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "y": y})
    return clean_df, collinear_df, n


def test_fit_ols_recovers_known_coefficients():
    clean_df, _, n = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    assert "error" not in fit1
    assert abs(fit1["model"].params["x1"] - 3) < 0.5
    assert abs(fit1["model"].params["x2"] - 2) < 0.5
    assert fit1["n_obs"] == n


def test_fit_ols_drops_categorical_columns_instead_of_crashing():
    clean_df, _, _ = _make_data()
    fit_mixed = fit_ols(clean_df, ["x1", "x2", "category"], "y")
    assert "dropped_categorical" in fit_mixed
    assert "category" in fit_mixed.get("dropped_categorical", [])


def test_fit_ols_errors_on_too_few_rows():
    clean_df, _, _ = _make_data()
    tiny_df = clean_df.head(MIN_ROWS_REQUIRED - 1)
    fit_tiny = fit_ols(tiny_df, ["x1", "x2"], "y")
    assert "error" in fit_tiny


def test_fit_ols_drops_zero_variance_columns():
    clean_df, _, _ = _make_data()
    const_df = clean_df.copy()
    const_df["const_col"] = 5.0
    fit_const = fit_ols(const_df, ["x1", "x2", "const_col"], "y")
    assert "dropped_zero_variance" in fit_const


def test_fit_ols_errors_when_no_numeric_features():
    clean_df, _, _ = _make_data()
    fit_none = fit_ols(clean_df, ["category"], "y")
    assert "error" in fit_none


def test_summarize_fit():
    clean_df, _, n = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    summary = summarize_fit(fit1)
    assert summary["r_squared"] > 0.7
    assert summary["adj_r_squared"] <= summary["r_squared"]
    assert summary["n_obs"] == n
    assert np.isfinite(summary["aic"]) and np.isfinite(summary["bic"])


def test_coefficient_table_shape_and_columns():
    clean_df, _, _ = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    coef_table = coefficient_table(fit1)
    assert len(coef_table) == 3  # intercept + 2 features
    assert {"coefficient", "std_error", "t_stat", "p_value"}.issubset(coef_table.columns)


def test_compute_vif_flags_multicollinearity():
    clean_df, collinear_df, _ = _make_data()
    fit_collinear = fit_ols(collinear_df, ["x1", "x2", "x3"], "y")
    vif_collinear = compute_vif(fit_collinear)
    assert len(vif_collinear) == 3
    x1_vif = vif_collinear[vif_collinear["feature"] == "x1"]["vif"].iloc[0]
    assert x1_vif > 5

    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    vif_clean = compute_vif(fit1)
    assert (vif_clean["vif"] < 5).all()

    single_feature_fit = fit_ols(clean_df, ["x1"], "y")
    vif_single = compute_vif(single_feature_fit)
    assert vif_single.empty  # VIF undefined for a single predictor


def test_run_diagnostics_on_well_behaved_residuals():
    clean_df, _, _ = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    diag = run_diagnostics(fit1)
    assert 1.5 < diag["durbin_watson"] < 2.5  # i.i.d. noise -> no autocorrelation
    assert 0 <= diag["shapiro_p"] <= 1
    assert 0 <= diag["breusch_pagan_p"] <= 1
    assert diag["residuals_normal"] is True
    assert isinstance(diag["homoscedastic"], bool)


def test_diagnostics_verdict_produces_readable_output():
    clean_df, _, _ = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    diag = run_diagnostics(fit1)
    vif_clean = compute_vif(fit1)
    verdicts = diagnostics_verdict(diag, vif_clean)
    assert len(verdicts) >= 3
    assert all(v.startswith(("✅", "⚠️")) for v in verdicts)


def test_heteroscedastic_data_flagged_by_breusch_pagan():
    rng = np.random.default_rng(42)
    x_hetero = rng.uniform(1, 10, 300)
    y_hetero = 2 * x_hetero + rng.normal(0, x_hetero, 300)  # variance grows with x
    hetero_df = pd.DataFrame({"x": x_hetero, "y": y_hetero})
    fit_hetero = fit_ols(hetero_df, ["x"], "y")
    diag_hetero = run_diagnostics(fit_hetero)
    assert diag_hetero["breusch_pagan_p"] < 0.05
    assert diag_hetero["homoscedastic"] is False


def test_plot_functions_return_figures_without_crashing():
    clean_df, collinear_df, _ = _make_data()
    fit1 = fit_ols(clean_df, ["x1", "x2"], "y")
    diag = run_diagnostics(fit1)
    fit_collinear = fit_ols(collinear_df, ["x1", "x2", "x3"], "y")
    vif_collinear = compute_vif(fit_collinear)
    single_feature_fit = fit_ols(clean_df, ["x1"], "y")
    vif_single = compute_vif(single_feature_fit)

    assert plot_residuals_vs_fitted(diag) is not None
    assert plot_qq(diag) is not None
    assert plot_scale_location(diag) is not None
    assert plot_vif_chart(vif_collinear) is not None
    assert plot_vif_chart(vif_single) is None  # empty VIF table -> no chart
