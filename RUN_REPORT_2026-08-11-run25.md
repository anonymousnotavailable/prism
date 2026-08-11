# Prism Autonomous Improvement — Run 25 (2026-08-11)

## Summary

Run 24 closed the last well-scoped, non-cosmetic backlog item (large
Excel ingestion) and explicitly recommended a fresh Phase 2 web research
sweep for Run 25, since 16 consecutive prior runs had been reusing an
earlier sweep. This run did that sweep, selected two features, and
shipped both:

1. **Conformal Prediction Intervals** — distribution-free uncertainty
   quantification for ML Lab regression baselines.
2. **K-Fold Cross-Validation** — replaces ML Lab's single 80/20-split
   model evaluation with proper mean ± std cross-validated metrics.

Both are pure local scikit-learn compute (no Gemini calls at all — zero
free-tier rate-limit exposure by construction). Full test suite: 454
green before this run → 479 green after (25 new tests, zero
regressions). Merged to `claude/adoring-meitner-7xxgfq` and pushed.

## Why these two, and why not the agentic-AI theme

The Phase 2 sweep (`.prism/research_2026-08-11-run25.md`) covered DA/DS
job-posting requirements, Hex/Deepnote/Julius AI/ChatGPT ADA/Databricks
Assistant feature comparisons, the polars/DuckDB/PyGWalker ecosystem,
agentic-EDA research (DeepAnalyze, LongDA), Pandera/Great Expectations
data-quality practice, and the conformal-prediction + SHAP explainability/
uncertainty-quantification convergence specifically flagged as a current
(2026) XAI trend.

Before ranking, the codebase was read directly to check what's already
shipped — Prism's statistical toolkit turned out to be unusually deep
for an "auto-EDA tool" after 24 runs: SHAP explainability, FDR-corrected
multi-hypothesis sweeps, parametric forecast confidence intervals (ETS/
SARIMAX), propensity-score causal inference with bootstrap CIs, and full
OLS regression diagnostics (VIF, Breusch-Pagan, Durbin-Watson,
Shapiro-Wilk) were all already there. Several first-instinct research
candidates (schema-contract validation vs. the existing `drift.py`,
silhouette-score cluster validation) were down-ranked or deferred once
that overlap was confirmed by reading the modules, not just searching
the web.

Two gaps were verifiably open and technically deep: `grep -rn
"cross_val\|KFold\|silhouette" modules/*.py` returned zero hits, and
`grep -rln "from modules import mllab" tests/*.py` confirmed
`run_baseline_models()` — ML Lab's core model comparison — had **zero**
direct unit tests before this run. An ML baseline runner with SHAP
explainability and OLS diagnostics but no cross-validation and no
prediction uncertainty is exactly the kind of methodology weak spot a
hiring-panel-caliber reviewer flags first, which is why both beat every
other ranked candidate on this run's "technical depth over cosmetic
polish" filter.

Runs 22 (Anomaly Drivers narration) and 23 (Explore Mode click-through)
shipped in the agentic-AI theme in the two runs immediately preceding
this one — per the run brief's own exception clause, this run leaned
toward the stronger statistical/ML-rigor candidates the research sweep
actually surfaced instead of forcing a third consecutive agentic-theme
feature. Neither shipped feature touches the Atlas/JARVIS copilot track.

## What shipped

### 1. Conformal Prediction Intervals (`modules/mllab.py`)

Split-conformal prediction (Lei et al.): fits a Random Forest on a 60%
train split, computes absolute-residual nonconformity scores on a
held-out 20% calibration split, and widens Random-Forest point
predictions on the remaining 20% test split by the finite-sample-
corrected (1-α) quantile of those scores. No normality assumption —
unlike the OLS diagnostics elsewhere in ML Lab — with a genuine marginal
coverage guarantee instead.

New functions: `run_conformal_regression()`, `build_conformal_chart()`,
`conformal_verdict()`. New UI section "Prediction Intervals (Conformal
Prediction)" under ML Lab's regression results — a target-coverage
slider (50-99%), a Compute button, target-vs-empirical coverage metrics,
mean interval width, a shaded-band chart (predicted line + interval band
+ actual points, sorted by predicted value), and a plain-English
verdict.

Live-verified against `samples/sales_data.csv` (region/product →
quantity): targeting 90% coverage, empirical coverage came out 93.8% on
a real dataset — closely matching target, as expected.

### 2. K-Fold Cross-Validation (`modules/mllab.py`)

`run_cross_validation()` runs the same Baseline (Logistic/Linear
Regression) and Random Forest models `run_baseline_models()` compares
through StratifiedKFold (classification) or KFold (regression), via a
single sklearn `Pipeline` passed to `cross_validate()` so preprocessing
is refit inside every fold — no leakage between folds. Reports mean ±
std per metric (accuracy/f1 for classification, rmse/r2 for regression)
instead of one single-split point estimate. k auto-reduces (flagged)
when it exceeds the rarest class's member count, since
`StratifiedKFold` requires `n_splits <= min_class_count`.

New functions: `run_cross_validation()`, `build_cv_score_chart()`,
`cv_verdict()`. New UI section "Cross-Validation" under ML Lab's
baseline metrics (applies to both classification and regression, unlike
the conformal feature) — a fold-count slider (2-10, default 5), per-
model mean±std metric cards, a per-fold score box plot, and a
plain-English verdict.

Live-verified against `samples/sales_data.csv`: 5-fold CV correctly
returned per-fold RMSE/R² scores for both models with sensible mean/std
(and correctly showed both models performing near-chance on
region/product → quantity, an intentionally weak predictor pairing —
the honest result cross-validation is supposed to surface instead of an
optimistic single-split number).

## Verification

- Full test suite: 454 → 479 passing, zero regressions (`python3 -m
  pytest -q`).
- 25 new tests across `tests/test_mllab_conformal.py` (13) and
  `tests/test_mllab_cross_validation.py` (12), covering unit-level
  statistical correctness (coverage guarantees, alpha/noise sensitivity,
  informative-vs-noise feature scoring) and edge cases (too few rows,
  invalid targets/alphas, single-class targets, k reduction, NaN rows)
  for both features.
- App launches cleanly post-merge (`streamlit run app.py`, HTTP 200, no
  traceback in server logs) and via Streamlit's headless `AppTest`
  harness (`streamlit.testing.v1.AppTest`, zero top-level exceptions).
- Both new functions were also exercised directly against a real sample
  dataset (`samples/sales_data.csv`) end-to-end, not just synthetic test
  data.

### Screenshot verification not performed this run

Playwright's Chromium download (`cdn.playwright.dev`) and the bundled
`playwright-browser-automation` skill were blocked by this session's
egress policy (`connect_rejected`/403 via the agent proxy — a policy
denial, confirmed via `curl $HTTPS_PROXY/__agentproxy/status`, not a
cert or setup issue). No browser automation was available this run, so
the usual desktop/mobile × dark/light screenshot matrix wasn't captured.

This is a lower-risk gap than usual: both new UI sections are standard
Streamlit widgets (`st.slider`, `st.button`, `st.metric`, `st.plotly_chart`,
`st.info`/`st.success`/`st.warning`) placed inside ML Lab's existing
regression-diagnostics/baseline-results containers, reusing exactly the
patterns (metric columns, dividers, verdict callouts) already used
throughout that tab — no new CSS, no new glass-panel components, no
custom layout. Verification instead relied on Streamlit's built-in
`AppTest` headless harness plus a live server smoke test (`streamlit run
app.py`, HTTP 200, clean logs) and direct function-level runs against a
real sample CSV. If a future run has Playwright access again, capturing
this tab in both themes would still be worth doing as routine polish,
but it is not flagged as an open risk.

## Backlog not built this run

- Silhouette-score cluster validation (research candidate #3) — smaller
  and lower-priority than the two shipped features; deferred, not
  rejected.
- Pandera-style schema/data-contract validation (research candidate #4)
  — meaningful overlap with the existing `drift.py` new/missing-category
  detection; would need a clearer differentiation before it's worth
  building as a separate feature.
- Polars/DuckDB backend adoption (research candidate #5) — explicitly
  out of scope per this run's "no architecture rewrites" guardrail;
  flagged as a proposal only, not built.
- PyGWalker-style drag-and-drop chart builder — largely covered already
  by Prism's Explore Mode + Manual Builder (shipped Run 23); lower
  priority per this run's technical-depth-over-cosmetic filter.
- Light-theme repaint lag, mobile-viewport Playwright gap, Atlas/HUD
  maturity, live-Gemini verification — unchanged from prior runs'
  backlog notes; still cosmetic/out-of-scope/structural, not touched.

## STAR-style interview bullets

**Conformal Prediction Intervals:**
> Identified that Prism's ML Lab shipped SHAP explainability and full
> OLS regression diagnostics but no uncertainty quantification on its
> own Random Forest predictions — a gap that current (2026) XAI
> literature specifically flags as an emerging best practice (SHAP +
> conformal prediction convergence). Implemented split-conformal
> prediction from scratch (train/calibration/test split, finite-sample-
> corrected residual quantile) rather than adding a new heavy
> dependency, verified the marginal coverage guarantee empirically
> against synthetic data across varying alpha and noise levels, and
> shipped it as a self-contained ML Lab section with 13 new tests and
> zero regressions to the existing 454-test suite.

**K-Fold Cross-Validation:**
> Found via direct code/test-suite inspection (not just intuition) that
> ML Lab's core baseline-model comparison function had zero cross-
> validation and zero direct unit test coverage after 24 prior
> improvement runs — a methodology gap a technical interviewer would
> flag immediately. Built a leakage-safe k-fold harness (StratifiedKFold/
> KFold over a single sklearn Pipeline, so preprocessing refits inside
> every fold) with automatic, flagged k-reduction for imbalanced
> classification targets, replacing a single noisy 80/20-split estimate
> with a proper mean ± std readout, backed by 12 new tests including a
> statistical correctness check (informative features must outscore
> pure noise on cross-validated R²).

## Recommendation for Run 26

The backlog is thin again after this run: silhouette-score cluster
validation and the Pandera-overlap question are the only two open,
non-cosmetic candidates from this run's research sweep, both smaller in
scope than what shipped this run. Recommend either:

1. Build silhouette-score cluster validation (small, clean, closes a
   real unsupervised-learning rigor gap in `clustering.py`), **or**
2. Run another fresh Phase 2 sweep if that's judged too small on its
   own — this run's sweep surfaced enough genuinely new candidates
   (schema contracts, polars/DuckDB, DeepAnalyze-style agentic reports)
   that a full re-sweep isn't yet necessary, but Run 26 should make that
   call explicitly rather than defaulting to backlog reuse past the
   point this routine's own rule says to stop.

Also worth a note for whichever run has Playwright access again: this
run's two new ML Lab sections have never been visually verified in
either theme or the mobile-PWA viewport — not flagged as a defect (they
reuse existing, already-verified widget patterns), but worth a quick
screenshot pass as routine housekeeping once browser automation is
available again in this sandbox.
