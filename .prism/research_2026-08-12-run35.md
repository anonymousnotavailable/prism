# Phase 2 Research — Run 35 — 2026-08-12

Fresh WebSearch sweep, cross-checked against the actual codebase (`grep`) rather than trusting
prior runs' notes at face value — several previously-plausible "gap" ideas turned out to already
be shipped.

## Already shipped — ruled out before the table (confirmed via grep, not assumption)
- **SHAP / model explainability** — `shap==0.49.1` pinned, `modules/mllab.py::explain_with_shap()`
  / `shap_for_display()` fully wired into `app.py`. Not a gap.
- **Feature importance beyond a single model** — `modules/mllab.py::run_feature_selection()`
  already runs mutual information, L1/Lasso coefficient magnitude, and RFE side by side with a
  consensus ranking chart. Not a gap.
- **Conformal prediction / uncertainty intervals** — `run_conformal_regression()` already ships
  (Run 24-ish). Rules out plain quantile regression as a *novel* addition — it would land in
  conceptually the same territory (distributional uncertainty around a regression fit) with less
  differentiation than the two picks below.
- **SMOTE for class imbalance** — already offered in `mllab.py`'s classification baseline flow,
  confirming the *specific* "beyond SMOTE" phrasing in this run's brief as accurate rather than
  stale — SMOTE alone (no threshold tuning, no calibration) is exactly what's there today.
- **OLS regression diagnostics** — `modules/regression_diagnostics.py` (VIF, residual/QQ/scale-
  location plots) exists but is diagnostics-only: it can *tell* a user their fit is unstable
  because of a high-leverage outlier, but offers no alternative fit. Same dead-end shape as last
  run's `normality_warnings()` finding.

## Ranked candidate table

| # | Feature | Evidence | Depth | Effort | Risk | Theme |
|---|---|---|---|---|---|---|
| 1 | **Robust regression (Huber / RANSAC / Theil-Sen)** | `sklearn.linear_model.HuberRegressor` / `RANSACRegressor` / `TheilSenRegressor`, all in the already-pinned scikit-learn 1.6.1. [scikit-learn docs](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.RANSACRegressor.html), [TDS overview](https://towardsdatascience.com/dealing-with-outliers-using-three-robust-linear-regression-models-544cfbd00767/). Confirmed via grep: zero references to any of the three in the codebase; `regression_diagnostics.py`'s OLS fit is the only regression path and has no outlier-robust alternative. | 5 | M | Low | Modeling/Stats depth |
| 2 | **Decision threshold tuning + probability calibration for classification** | MachineLearningMastery ["threshold-moving"](https://machinelearningmastery.com/threshold-moving-for-imbalanced-classification/) and ["probability calibration"](https://machinelearningmastery.com/probability-calibration-for-imbalanced-classification/) guides; 2026 empirical result that threshold calibration alone matches/beats SMOTE on F1 while adding no synthetic noise ([AnalyticsVidhya 2026](https://www.analyticsvidhya.com/blog/2026/07/class-imbalance-ml/)). `sklearn.calibration.CalibratedClassifierCV` / `calibration_curve`, `sklearn.metrics.precision_recall_curve` (already imported in `mllab.py` for PR curves, so the curve data needed for optimal-threshold selection is already computed there). Confirmed via grep: zero calibration code anywhere in the repo; the only imbalance lever offered today is SMOTE. | 4 | M | Low | ML rigor / imbalanced-learning |
| 3 | Weight-of-Evidence / target encoding with leakage guard | `feature-engine`'s WoE encoder pattern; useful for categorical features in classification | 3 | M | Med (new dep, `feature-engine` not pinned; leakage-guard logic is fiddly to verify) | ML feature engineering |
| 4 | Quantile regression (`statsmodels.regression.quantile_regression.QuantReg`) | Growing use in clinical/econ literature for conditional quantiles beyond the mean | 3 | M | Low | Overlaps conformal prediction's territory — weaker differentiation |
| 5 | Data lineage / versioning / audit trail | 2026 lineage-tool roundups (Airbyte, Atlan, OvalEdge) | 3 | L | High (session-scoped single-dataset architecture has no natural "version history" concept; would need a real design, not a slice) | Governance — out of scope this run per "no architecture rewrites" guardrail |
| 6 | New agentic-EDA patterns (multi-agent supervised analysis, e.g. Snowflake CoWork-style) | 2026 "AI agents that do the analysis" trend pieces | 2 | L | Med (Atlas-adjacent, and this run should touch Atlas ≤1 time per brief; also vague, not a concrete testable feature) | Agentic — deferred |

## Selection rationale (full reasoning in routine_log.md)
Picks 1 and 2 both: zero new pip dependencies (both are stdlib-to-this-repo scikit-learn imports
already pinned at 1.6.1), M effort, low risk, non-Atlas, and both close a **specifically
confirmed** gap (not assumed from a prior run's notes) via direct grep of the actual module
files before committing to the pick. Both also compound usefully with infrastructure already in
the repo: pick 1 slots into `regression_diagnostics.py`'s existing OLS-fit UI as an outlier-
robust alternative fit shown side by side; pick 2 slots into `mllab.py`'s existing classification
baseline + PR-curve + SMOTE flow as the next natural step after "here's your imbalanced classes"
warning, closing the same kind of dead-end pattern Run 34 closed for `normality_warnings()`.
