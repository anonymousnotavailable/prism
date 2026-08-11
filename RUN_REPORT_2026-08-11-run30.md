# Prism Autonomous Improvement — Run 30 Report (2026-08-11)

## Summary

Shipped two features, both merged cleanly (one resolved conflict) into
`claude/adoring-meitner-7xxgfq`:

1. **Difference-in-Differences causal estimator** for the Overview tab (`modules/did.py`, new module)
2. **Survival Analysis (Kaplan-Meier + log-rank test)** for Stats Lab (`modules/survival.py`, new module)

Test suite: **611 → 669 passing, zero regressions.** App verified to
launch cleanly (HTTP 200, clean logs) after each branch and again on the
final merged branch. Pushed to `origin/claude/adoring-meitner-7xxgfq`.

## What shipped and why

### 1. Difference-in-Differences (`modules/did.py`)

`modules/causal_inference.py` already answers "what's the real effect of
a treatment" for cross-sectional data via propensity score matching —
but that method needs similar *units* to match at one point in time. A
lot of real before/after rollout data (a feature launched for one store/
region/cohort but not another, observed pre- and post-launch) doesn't
have that shape at all: it has a treated group, a control group, and two
time periods. DiD is the standard tool for exactly that case, and this
run's brief pre-committed it as a pick after three straight runs (27-29)
deferring it for capacity, not fit.

- **Core estimator** (`estimate_diff_in_differences`): fits
  `outcome = b0 + b1*treated + b2*post + b3*(treated*post)` via OLS with
  heteroskedasticity-robust (HC1) standard errors — `b3` is the DiD
  estimate. This is *mathematically identical* to the textbook 2x2
  formula `(treated_post-treated_pre) - (control_post-control_pre)`,
  which `test_naive_diff_in_means_matches_regression_estimate` verifies
  directly (not just "the number looks plausible" — the two computations
  are checked to 6 decimal places). The regression framing is what makes
  the confidence interval and covariate-adjustment path straightforward;
  the causal_inference module's own docstring calls this "the textbook,
  auditable version, not a black-box library," and `did.py` follows the
  same philosophy.
- **Parallel-trends placebo check**: when the caller supplies 2+
  pre-treatment periods, a second OLS-interaction regression restricted
  to the pre-period tests whether the treated and control groups' slopes
  already differ before treatment started — evidence *against* the
  method's core assumption if they do. This directly reflects a
  WebSearch sanity check on current econometrics literature (Roth 2022;
  Bilinski & Hatfield 2019): a non-significant pre-trend difference is
  neither necessary nor sufficient proof parallel trends holds
  afterward, since pre-trend tests are known to have low power. That
  caveat is not just mentioned in a docstring — it's a hardcoded string
  (`_PRETREND_CAVEAT`) surfaced directly in the app's UI next to the
  test result, so the panel never implies "test passed, trust the
  estimate."
- **UI** (`app.py`, Overview tab, next to the existing Causal Effect
  Estimator): pick a binary group column, a period column (2-20 distinct
  values, e.g. "before"/"after" or quarterly labels), a numeric outcome,
  and optionally extra pre-treatment periods to enable the trend check.
  Shows the DiD estimate + 95% CI + p-value, a 2x2 cell-means/n table,
  the classic DiD chart (`visualization.plot_diff_in_diff` — treated and
  control lines plus a dashed "counterfactual" line showing where the
  treated group would have ended up absent treatment, with the DiD gap
  annotated directly on the chart), and — when requested — the pre-trend
  verdict plus its own trend-line chart. Optional Gemini "Explain this"
  narration follows the exact `call_gemini()`/no-model-fallback pattern
  every other narrate_* helper in the app already uses.
- **27 new tests** in `tests/test_did.py`: true-effect recovery on
  synthetic panels within tolerance, the regression-vs-manual-formula
  identity check, every validation/failure path (missing columns,
  non-numeric outcome, non-2-group treatment, identical pre/post
  periods, thin cells, missing-value handling), pre-trend divergence
  correctly detected on a synthetic diverging-trend panel *and*
  correctly *not* flagged on a synthetic parallel-trend panel, warnings,
  narration (including a monkeypatched Gemini call asserting the prompt
  contains real result data), and both new chart functions.

### 2. Survival Analysis (`modules/survival.py`)

`modules/domains.py`'s `flag_churn()` already exists, but it's a fixed
30-day-inactivity cutoff — a fast proxy that throws away exactly the
information survival analysis is built to use: a customer who signed up
last week and hasn't churned *yet* is not the same evidence as one who
signed up two years ago and also hasn't churned. Both are
"right-censored" observations, not failures. This was Run 29's own
candidate #5, deferred twice because a from-scratch implementation
(rather than a new `lifelines` dependency) needed to be confirmed
tractable — done this run.

- **Kaplan-Meier estimator** (`compute_kaplan_meier` /
  `_km_from_arrays`): the product-limit estimator with Greenwood's
  variance for confidence bands and a median-survival-time readout
  (explicitly reported as `None`/"not reached" rather than a misleading
  number when survival never crosses 0.5 within the observation window —
  a common and meaningful real-world outcome, not an edge case to hide).
  `test_km_hand_verified_values` checks the curve against a textbook
  6-subject example (Klein & Moeschberger style) computed by hand, not
  just checked for "looks monotonic."
- **Log-rank test** (`log_rank_test`): the standard observed-vs-expected
  chi-square construction (Mantel-Haenszel), generalized to 2-8 groups
  via the usual approach of dropping one group and inverting the
  (k-1)x(k-1) covariance submatrix (the full k x k matrix is singular by
  construction). `test_log_rank_p_value_is_calibrated_under_null`
  verifies statistical correctness the way a single-seed check can't:
  under a true null (identical hazards), the log-rank p-value should be
  ~uniform(0,1), so its *mean* across 30 independent synthetic draws
  should land near 0.5 — a much stronger correctness signal than "wasn't
  significant on one lucky seed."
- **UI** (`app.py`, Stats Lab tab, after Hypothesis Sweep): pick a
  non-negative numeric duration column, a binary event column (coerced
  from Yes/No/True/False/1/0 variants automatically), and an optional
  2-8-level group column. Shows the classic step-function KM chart
  (`visualization.plot_kaplan_meier`, one line per group when comparing),
  a per-group median-survival/events/censored table, and the log-rank
  test's p-value with a plain-English significance verdict. Optional
  Gemini narration follows the same convention as every other
  narrate_* helper.
- **Explicit bad-input/scale handling**: negative durations rejected
  with a clear error; non-binary event columns rejected; thin groups
  (<5 rows) rejected by name rather than silently distorting the curve;
  datasets over 20,000 rows are sampled down with a warning surfaced in
  the UI, same tractability-cap convention `market_basket.py` already
  established for pathological input sizes.
- **31 new tests** in `tests/test_survival.py`: the hand-verified KM
  curve, censoring correctly shrinking the risk set without a false
  survival drop, median-survival edge cases (reached vs. never reached),
  Greenwood CI bounds, the log-rank calibration check plus a
  true-hazard-difference detection check (p < 0.01 on a synthetic 3x
  hazard-ratio panel) and a 3-group degrees-of-freedom check, every
  `survival_analysis()` validation path (missing columns, negative
  durations, non-binary event column, too-few-rows, too-many-group-
  levels, missing-value dropping, the >20k-row sampling cap), narration,
  and both new chart-rendering tests.

## Verification

Playwright/Chromium **not retried** — 5th consecutive run confirmed-
blocked by sandbox egress policy per this run's own brief instruction
not to keep re-litigating it. Used the documented fallback, plus one
addition beyond prior runs' standard method:

1. **Full pytest suite** at every stage — 611 baseline, 638 after
   `feature/diff-in-diff`, 642 after `feature/survival-analysis`, 669
   after both merged. Zero regressions at any point.
2. **Live `streamlit run` smoke test** (HTTP 200, clean startup logs, no
   exceptions) — once per feature branch and once on the final merged
   branch.
3. **`streamlit.testing.v1.AppTest` driving the actual `app.py` render
   path** with synthetic data injected directly into session state (not
   just unit-testing the standalone `did.py`/`survival.py` modules in
   isolation) — this is a strictly stronger integration check than
   function-level testing alone, since it exercises the real
   `app.py` session-state wiring, column-type gating logic, and
   `st.plotly_chart`/`st.dataframe` rendering calls, which unit tests of
   the modules themselves never touch. For DiD: loaded a synthetic panel
   with a known true effect (4.0), clicked the actual "Estimate DiD
   effect" button through AppTest's widget simulation, and separately
   pre-set a computed result to exercise the full chart/cell-table/
   pre-trend-check render path — zero exceptions, on-page metric read
   4.06. For Survival Analysis: loaded a synthetic two-group churn
   dataset with a known 2.5x hazard ratio, exercised the full chart/
   table/log-rank UI — zero exceptions, on-page log-rank p-value
   correctly read 8.9e-06 (significant, matching the synthetic design).
   Re-ran both checks again on the final merged branch in isolated
   single-run `AppTest` sessions to confirm the merge conflict
   resolution (see below) didn't break either panel.
4. **Direct function-level correctness checks** beyond plausibility:
   the DiD regression estimate proven identical to the textbook 2x2
   diff-of-diffs formula to 6 decimal places; the Kaplan-Meier curve
   checked against a hand-computed textbook example; the log-rank test's
   p-value shown to be empirically well-calibrated (mean ~0.5 across 30
   independent null-hypothesis draws, not just "not significant on one
   seed").

**Noted, not fixed (out of scope):** `streamlit.testing.v1.AppTest`'s own
widget-state serializer throws a `ValueError` on a *second* `.run()` call
after switching `active_section` — reproduced on an untouched base
branch with an unrelated sample CSV (`hr_data.csv`), confirming it's a
pre-existing AppTest harness quirk unrelated to this run's changes, not
a Prism bug. Worked around by using one fresh `AppTest` instance per
section under test rather than reusing one instance across a section
switch. Worth a note for whichever future run next reaches for AppTest.

## Merge conflict

`feature/diff-in-diff` and `feature/survival-analysis` both added a new
chart function to `modules/visualization.py` at the same location
(immediately after `plot_cate_by_subgroup`, before `auto_generate_charts`
— the established insertion point for causal/statistical chart helpers).
Resolved by keeping both additions in full (`plot_diff_in_diff` +
`plot_did_pre_trend` from the first branch, `plot_kaplan_meier` from the
second) — no logic overlap, purely an insertion-point collision. Re-ran
`ast.parse` and the full test suite (669 passed) before committing the
merge to confirm the resolution was clean, not just syntactically valid.

## Backlog not built this run

From `.prism/research_2026-08-11-run30.md`'s gap sweep (grep-confirmed
zero coverage in `modules/*.py`):

- **Bayesian A/B testing** (beta-binomial posterior + credible intervals)
  — natural fit for Stats Lab next to the existing frequentist t-test/
  chi-square/ANOVA suite, pure `scipy.stats`, no new dependency.
- **Power / sample-size analysis** (minimum detectable effect
  calculator) — pure scipy/numpy normal-approximation formulas, no new
  dependency; slightly different in kind from Prism's "analyze the data
  you uploaded" pattern (pre-experiment planning vs. post-hoc analysis)
  but can seed its inputs from an uploaded dataset's own baseline
  rate/variance.
- **DiD with a linear pre-trend adjustment** (Bilinski & Hatfield 2019's
  recommended default) as a documented enhancement to the already-shipped
  `modules/did.py` — not a blocker, the current placebo-check-only
  version is a legitimate, textbook-standard implementation on its own.
- Sentiment/NLP analytics remains an open, larger-scope gap (needs either
  a new lightweight dependency or a heavier from-scratch tokenizer) —
  bigger than a single run slot.

## STAR bullets

**Difference-in-Differences causal estimator**
- **Situation:** Prism's Causal Effect Estimator only handled
  cross-sectional data (propensity score matching needs similar units to
  match at one point in time); a large class of real rollout/before-
  after data has no such shape.
- **Task:** Add a second causal-inference method for panel data, deferred
  three prior runs for scheduling capacity, not fit — this run's brief
  pre-committed it.
- **Action:** Implemented the standard OLS-interaction DiD estimator with
  HC1-robust SEs (proven identical to the textbook 2x2 formula by test),
  plus an optional parallel-trends placebo check whose result is
  presented with an explicit "not proof, a diagnostic" caveat sourced
  from a live WebSearch sanity check against 2025-2026 econometrics
  literature (Roth 2022; Bilinski & Hatfield 2019) rather than an
  assumed-safe green checkmark.
- **Result:** 27 new tests, zero regressions, verified end-to-end via
  AppTest driving the real UI (not just the standalone module) — on-page
  estimate (4.06) matched a synthetic true effect (4.0) within noise.

**Survival Analysis (Kaplan-Meier + log-rank test)**
- **Situation:** The only "time until churn" tool in Prism
  (`domains.flag_churn`) was a fixed-cutoff proxy that discards
  right-censoring information — the exact case survival analysis exists
  to handle correctly.
- **Task:** Ship Kaplan-Meier + log-rank from scratch (no `lifelines`
  dependency), a gap deferred twice pending confirmation that from-
  scratch was tractable in one run's budget.
- **Action:** Implemented the product-limit estimator with Greenwood's
  variance and a general k-group log-rank test (Mantel-Haenszel
  construction, reduced (k-1)x(k-1) covariance solve), validated against
  a hand-computed textbook example and an empirical calibration check
  (mean p-value ~0.5 across 30 independent null-hypothesis draws) rather
  than a single-seed plausibility check.
- **Result:** 31 new tests, zero regressions, verified end-to-end via
  AppTest — on-page log-rank p-value (8.9e-06) correctly flagged a
  synthetic 2.5x hazard-ratio difference as significant.

## Run 31 recommendation

Bayesian A/B testing (beta-binomial posterior, credible intervals for
two-proportion comparisons) is the strongest next pick: zero coverage
today, pure `scipy.stats`, no new dependency, slots naturally into Stats
Lab next to the existing frequentist test suite as "the Bayesian
alternative view" on the same kind of two-group comparison Stats Lab
already runs — genuinely different statistical machinery (posterior
distributions and credible intervals, not p-values and confidence
intervals) rather than another metric bolted onto an existing panel.
Power/sample-size analysis is the second-strongest option if Bayesian
A/B testing turns out to overlap too much with it in a single run
(they're often presented together in practice) — pick whichever of the
two isn't picked this run for the one after.
