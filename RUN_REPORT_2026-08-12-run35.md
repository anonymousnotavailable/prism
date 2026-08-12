# Run 35 Report — 2026-08-12

## Summary

Shipped 2 features + 1 housekeeping cleanup on `claude/adoring-meitner-7xxgfq`. Test suite
904 → 932 (28 new tests). Zero regressions, zero merge conflicts, both features verified live
with real Playwright screenshots (desktop + mobile-PWA, dark + light) against real sample
datasets and real trained models — not mocked data.

## What shipped

### 0. Housekeeping: removed dead `voice_input.py` (Phase 1 audit finding)
Run 34 replaced `modules/voice_input.py`'s streamlit-mic-recorder path with
`modules/web_speech.py` but left the old module in place. Confirmed via grep this run: zero
remaining call sites anywhere in `app.py` or any module, and zero test coverage — its removal
didn't change the pass count. Removed the module, the now-unused `streamlit-mic-recorder==0.0.8`
pip dependency, and fixed a stale README module-tree entry (also added the `web_speech.py` entry
Run 34 never added).

### 1. Robust Regression comparison
**What:** `modules/regression_diagnostics.py` gained `fit_robust_regressors()`,
`robust_regression_verdict()`, and `build_robust_regression_chart()`, fitting Huber, RANSAC, and
Theil-Sen regressors (`sklearn.linear_model`, already pinned at scikit-learn 1.6.1 — zero new
dependencies) alongside the existing OLS diagnostics fit. New "Robust Regression" sub-panel in
the ML Lab's Regression Diagnostics section, gated behind a "Compare to Robust Regressors" button.

**Why:** Phase 1 audit found `regression_diagnostics.py`'s OLS diagnostics (VIF, residual/QQ/
scale-location plots) can *detect* a high-leverage outlier or non-normal residuals but offered no
alternative fit — the same "diagnose but no next step" dead end Run 34 found and closed for
`normality_warnings()` in Stats Lab. Phase 2 research confirmed via grep this was a genuine
zero-hit gap (no RANSAC/Huber/TheilSen reference anywhere in the codebase) and that it's a
concrete, well-scoped feature 2026 data-science hiring panels specifically probe for (robust
regression is standard "how do you handle outliers in a linear model" territory).

**Technical depth:** RANSAC's `inlier_mask_` surfaces exactly what fraction of the data it
excluded as outliers to reach consensus — a genuinely informative number, not just a coefficient
table. The verdict logic checks for coefficient *sign flips* between OLS and Huber specifically
(directional instability under outlier influence), a stronger and more specific claim than "the
numbers are different."

**STAR:** *Situation* — the Regression Diagnostics panel could warn about outlier influence but
gave the user no way to act on that warning. *Task* — close the dead end without adding a new
pip dependency or rearchitecting the panel. *Action* — reused the same OLS `fit_result` dict
already in session state, fit three scikit-learn robust regressors on the identical
features/target, and built a coefficient-comparison verdict that specifically flags sign flips
(not just magnitude differences) as the actionable signal. *Result* — 12 new tests (clean vs.
outlier-perturbed synthetic data, RANSAC inlier bookkeeping, chart construction including the
zero-robust-models-fit edge case), verified live against the Stocks sample dataset (`close`
regressed on `open`/`high`/`low`/`volume`) at 3 viewport/theme combinations with zero console
errors.

### 2. Decision threshold tuning + probability calibration
**What:** `modules/mllab.py` gained `tune_decision_threshold()`, `build_threshold_chart()`,
`threshold_verdict()`, `run_probability_calibration()`, `build_calibration_chart()`, and
`calibration_verdict()`. New "Decision Threshold Tuning & Probability Calibration" panel in ML
Lab, directly below the existing binary ROC/PR curves. `run_baseline_models()` now also returns
`y_train` (previously only `X_train_transformed` was kept), needed for calibration's internal
cross-validation.

**Why:** Phase 2 research (fresh WebSearch sweep) confirmed the brief's own hunch: SMOTE
(already offered in ML Lab) is the *only* imbalance lever in the app, and 2026 empirical results
show decision-threshold tuning alone matches or beats SMOTE on F1 while adding no synthetic
noise — "start at the decision level because it's the cheapest experiment" is the recommended
order of operations, and Prism had skipped straight to resampling.

**Technical depth:** Threshold tuning supports an explicit cost matrix (cost per false positive
vs. false negative), not just F1-maximization — the cost-optimal threshold is a materially
different (and more business-relevant) number than the F1-optimal one whenever misses and false
alarms aren't equally expensive. Calibration is done correctly: `CalibratedClassifierCV` is fit
on a *fresh clone* of the model via its own internal cross-validation on the training set, not
the already-fitted instance (which would leak test-adjacent information into the calibration
curve) — this distinction is exactly the kind of thing a data-science interviewer checks for.

**STAR:** *Situation* — ML Lab's only answer to class imbalance was SMOTE, a data-level fix.
*Task* — add the cheaper, better-evidenced output-level fixes without a new pip dependency or
touching Atlas. *Action* — reused the PR-curve infrastructure already computed for ROC/PR
(`compute_roc_pr_curves`'s binary mode), swept 99 candidate thresholds scoring precision/recall/
F1/cost at each, and implemented calibration via `sklearn.base.clone()` + `CalibratedClassifierCV`
specifically to avoid the leakage a naive "wrap the fitted model directly" approach would cause.
*Result* — 16 new tests (binary sweep correctness, 3 error paths, cost-ratio shifting the optimal
threshold in the expected direction, both calibration methods, a too-few-minority-samples
graceful-degradation case), verified live against the HR sample dataset's real 16%-imbalanced
`attrition` target — real Brier scores (0.1425 → 0.1314), a real reliability diagram, at 4
viewport/theme combinations with zero console errors.

## Verification
- Full pytest suite green at every stage: 904 (start) → 916 (after robust regression) → 932
  (after threshold/calibration). Zero regressions, zero flaky failures.
- Live `streamlit run app.py` smoke test after the cleanup commit and after the final merge —
  HTTP 200, clean log, no tracebacks, on `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`-
  driven headless Chromium per Run 34's confirmed-working recipe (never `playwright install`).
- Real Playwright screenshots, saved to `.prism/runs/2026-08-12-run35/`: robust regression at
  desktop dark, desktop light, and mobile-PWA dark; threshold tuning + calibration at desktop
  dark, desktop light, and mobile-PWA dark. All against real fitted models on real sample
  datasets (Stocks, HR), not mocked/stubbed results. Checked for: readable contrast in both
  themes, no overflow/clipping on mobile, glass-panel visual consistency, chart legends legible,
  zero JS console/page errors throughout every click sequence.
- No merge conflicts — cleanup merged first, then robust-regression (touches
  `regression_diagnostics.py` only), then threshold-calibration (touches `mllab.py` only); each
  branched off the already-merged base per Run 33/34's established no-conflict sequencing.

## Backlog not built this run
From the Phase 2 research table (`.prism/research_2026-08-12-run35.md`):
- **Weight-of-Evidence / target encoding with leakage guard** — needs a new pip dependency
  (`feature-engine`, not pinned) and fiddly leakage-guard logic to verify correctly; deferred as
  a candidate for a run with more time budget to get the leakage guard right.
- **Quantile regression** (`statsmodels.QuantReg`) — ruled out this run as too close in spirit to
  the already-shipped conformal prediction (both are about distributional uncertainty around a
  regression fit); would need a sharper differentiation angle before it's worth building.
- **Data lineage / versioning / audit trail** — explicitly out of scope: Prism's session-scoped
  single-active-dataset architecture has no version-history concept to extend, and building one
  would be an architecture change, not a feature slice, violating this run's "no rewrites"
  guardrail. Worth a dedicated design discussion in a future run if the toolkit's roadmap wants
  it, not a drop-in addition.
- **New agentic-EDA/multi-agent patterns** (Snowflake CoWork-style supervised multi-agent
  analysis) — vague as a concrete testable feature, and Atlas-adjacent; Atlas was substantively
  extended just last run (Run 34's Web Speech voice input), so this run intentionally left it
  alone per the "at most 1 feature may touch Atlas, likely skip" guidance, and the vagueness
  alone would have disqualified it from a 2-feature slice anyway.

## Run 36 recommendation
The toolkit is now unusually deep (Robust Regression and Threshold/Calibration bring the running
total past 20 statistical/ML/agentic features shipped since Run 22). A genuinely fresh Phase 2
sweep is still finding real gaps each run, but they're getting narrower and more specialized —
worth explicitly time-boxing the research sweep to 20-30 minutes before settling on a pick, since
the "obvious" gaps are thinning out. Two credible starting points already surfaced by this run's
research and not yet built: (1) Weight-of-Evidence / target encoding with a real leakage guard —
worth it if a run has the time budget to get the leakage-guard test coverage genuinely airtight,
since that's the part reviewers scrutinize hardest; (2) a fresh look at whether Atlas's intent
router (untouched substantively since Run 32/34's voice work) has any narrow, well-scoped gaps
now that voice input and non-parametric stats give it more to route to — but only if a concrete,
testable slice presents itself, not a vague "improve Atlas" mandate.
