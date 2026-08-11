# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-11 (Run 33)

### Fixed
- **Stats Lab: Text Analytics panel unreachable when `testable_cols < 2`**
  — the whole Stats Lab section (including Text Analytics, Bayesian A/B,
  Power Analysis, and Survival Analysis) was nested inside a top-level
  `if len(testable_cols) < 2: <empty state>` gate. Text Analytics reads a
  free-text column via NLP, not numeric/categorical values, so a dataset
  with 1 testable column plus a good text column could never reach it.
  Moved Text Analytics to its own independent
  `text_analytics.eligible_text_columns()`-gated block at the section
  level; left Bayesian A/B / Power Analysis / Survival Analysis inside the
  gate since they legitimately need numeric/categorical columns. Found
  during this run's Phase 1 audit (flagged as a backlog item by Run 32).

### Added
- **Changepoint Detection** (`modules/changepoint.py`, new module) — added
  to the Forecasting tab after STL Decomposition, reusing the existing
  datetime/numeric column pickers. Binary segmentation over a normalized
  CUSUM statistic (no `ruptures` dependency — pure numpy, the
  tractable-to-verify textbook sibling of PELT), with each candidate split
  confirmed via a permutation test and a Bonferroni-style correction across
  the recursion tree to control the compounding false-positive rate binary
  segmentation is otherwise prone to. Detects mean-shift level changes (a
  pricing change, an outage, a policy switch) with a chart (series +
  segment means + vertical changepoint markers), a results table, and a
  cached "✨ Explain this" Gemini narration. 22 new tests.
- **Granger Causality** (`modules/granger_causality.py`, new module) —
  added to the Forecasting tab after Changepoint Detection, with its own
  "Potential cause (X)" / "Effect (Y)" column pickers (gated on 2+ numeric
  columns). Auto-checks both series for stationarity via Augmented
  Dickey-Fuller and auto-differences (capped at 2) if needed, picks the lag
  order via `statsmodels.tsa.api.VAR.select_order()`'s AIC-minimizing
  choice, then runs `grangercausalitytests` in both directions (X→Y and
  Y→X — Granger causality isn't symmetric, and a detected feedback loop is
  itself informative). Explicitly frames every result as predictive
  precedence, not proof of true causation, same convention as
  `causal_inference.py` and `did.py`. Zero new pip dependencies —
  statsmodels already pinned. 21 new tests.

### Verification
- Full pytest suite: 788 -> 831, zero regressions (22 changepoint + 21
  Granger causality tests; the Text Analytics bugfix is pure UI
  restructuring with no new test path of its own, confirmed via AppTest
  instead).
- Playwright/Chromium not retried (8th consecutive confirmed-blocked run,
  sandbox egress policy). Verified instead via: full pytest suite at every
  stage; a live `streamlit run` smoke test (HTTP 200, clean logs) on each
  feature branch and the final merged branch; and
  `streamlit.testing.v1.AppTest` driving the real `app.py` end-to-end (one
  fresh instance per scenario, exactly one `.run()` call each, working
  around the confirmed "second real `.run()` throws on an unrelated
  multiselect widget" harness quirk by pre-seeding session state with a
  precomputed result instead of chaining multiple `.run()` calls) — 3
  Changepoint Detection scenarios, 3 Granger Causality scenarios, and 1
  scenario confirming the Text Analytics bugfix reaches the panel with
  only 1 numeric column present, all zero exceptions.

## 2026-08-11 (Run 32)

### Added
- **Atlas: Bayesian A/B Test + Power Analysis voice/typed commands** — the
  intent router (`modules/atlas.py`) now has four new `APP_COMMAND`
  actions, extending Run 17's zero-Gemini keyword fast path: `run_bayesian_ab`
  / `run_power_analysis` navigate to Stats Lab and auto-run the panel using
  a deterministic best-guess column pairing (two new pure functions —
  `bayesian_ab.auto_select_columns()` / `power_analysis.auto_select_inputs()`
  — mirroring each panel's own selectbox eligibility rules), falling back to
  "navigate there and let the user configure it" when no obvious pairing
  exists rather than guessing further; `explain_bayesian_ab` /
  `explain_power_analysis` are voice/typed counterparts to each panel's
  existing "✨ Explain this" button. Read-only compute — no confirmation
  guard needed. 14 new tests.
- **Text Analytics** (`modules/text_analytics.py`, new module) — added to
  Stats Lab after Power Analysis, gated on the dataset having a column that
  reads as actual prose (average >= 3 words/cell, not just any
  high-cardinality "text"-typed column). Three pieces: a lexicon-based
  sentiment scorer (~90-word hand-curated polarity list, -3..+3, with
  token-window negation flipping and intensifier/diminisher scaling —
  documented as a heuristic first read, not a trained classifier), TF-IDF
  keyword extraction ranked by summed corpus weight, and NMF topic modeling
  (topic count auto-clipped to what the corpus can support). Pure
  numpy/pandas/scikit-learn — no new pip dependency. Three new charts
  (sentiment distribution, top terms, topic shares) and a cached "✨
  Explain this" Gemini narration, same layout convention as the panels
  beside it. 36 new tests.

### Verification
- Full pytest suite: 738 -> 788, zero regressions.
- Playwright/Chromium not retried (7th consecutive confirmed-blocked run,
  sandbox egress policy). Verified instead via: full pytest suite at every
  stage; a live `streamlit run` smoke test (HTTP 200, clean logs) on each
  feature branch and the final merged branch; and
  `streamlit.testing.v1.AppTest` driving the real `app.py` end-to-end,
  worked around the confirmed "second real `.run()` throws on an unrelated
  multiselect widget" harness quirk by monkeypatching `st.chat_input`/
  `st.button` to fire exactly once within a single `.run()` call — 7 Atlas
  scenarios and 2 Text Analytics scenarios, all zero exceptions, including
  a recovered 50/50 sentiment split exactly matching a synthetic corpus's
  known construction.

## 2026-08-11 (Run 31)

### Added
- **Bayesian A/B Testing** (`modules/bayesian_ab.py`, new module) — added
  to Stats Lab as a new panel after Survival Analysis. Beta-binomial
  conjugate posterior per variant (closed-form update, configurable prior,
  defaults to uninformative Beta(1,1)), 95% credible intervals, and
  P(treatment beats control) computed via Evan Miller's exact closed-form
  summation (falls back to Monte Carlo sampling for large posterior
  counts, verified to agree with the exact method to within 1%). Also
  reports expected loss per decision (the average regret of picking a
  variant if it turns out to be the worse one) and the absolute/relative
  lift distribution — a risk-based complement to a bare probability
  threshold. Unlike a fixed-N frequentist significance test, a Bayesian
  posterior can be checked at any time without a "peeking" penalty. New
  chart: overlaid posterior density curves for the two variants. 31 new
  tests.
- **Power / Sample-Size Planning** (`modules/power_analysis.py`, new
  module) — added to Stats Lab as a new panel, the frequentist
  counterpart to Bayesian A/B Testing sitting next to it: pre-committing
  to a sample size is exactly how a frequentist test earns the guarantee
  a Bayesian posterior gets for free. Wraps `statsmodels.stats.power`
  (`TTestIndPower` for two-sample means via Cohen's d, `NormalIndPower` +
  `proportion_effectsize` for two-sample proportions) to solve either
  direction: required sample size for a target power, or achieved power
  for a planned sample size. Effect size can be typed directly or
  estimated from a pilot slice of the loaded dataset. Deliberately does
  not surface a bare "observed/post-hoc power" number computed from the
  same data used to estimate the effect size — framed throughout as a
  forward-looking planning tool, per Hoenig & Heisey's 2001 critique that
  post-hoc power is a near-deterministic function of a p-value already
  obtained, not an independent validity check. New chart: power-vs-
  sample-size curve with the solved-for point marked. 38 new tests,
  including two regression tests for a same-column-selection crash found
  and fixed during development (`df[[col, col]]` producing a
  duplicate-column DataFrame instead of a Series, breaking downstream
  `.unique()` calls) — the same latent bug was also caught and fixed in
  the new `bayesian_ab.py` module before it shipped.

## 2026-08-11 (Run 30)

### Added
- **Difference-in-Differences causal estimator** (`modules/did.py`, new
  module) — added alongside the existing propensity-score-matching Causal
  Effect Estimator in the Overview tab. For before/after panel data
  (a treated group + a control group, each observed at a "pre" and a
  "post" period), estimates the DiD effect via OLS with a treated*post
  interaction term and heteroskedasticity-robust (HC1) standard errors —
  mathematically identical to the textbook (treated_post-treated_pre) -
  (control_post-control_pre) formula, verified by test. When 2+
  pre-treatment periods are available, runs an optional parallel-trends
  placebo check (does the treated group's pre-period slope already differ
  from the control group's?) with an explicit caveat, per current
  econometrics literature (Roth 2022; Bilinski & Hatfield 2019), that a
  non-significant pre-trend is neither necessary nor sufficient proof the
  parallel-trends assumption holds going forward — a diagnostic, not a
  guarantee. New chart: the classic DiD plot with a dashed counterfactual
  line showing where the treated group would have ended up absent
  treatment. 27 new tests.
- **Survival Analysis** (`modules/survival.py`, new module) — added to
  Stats Lab as a new panel after Hypothesis Sweep. Kaplan-Meier
  product-limit estimator (with Greenwood's-variance confidence bands and
  median survival time) plus a log-rank test for comparing survival
  curves across 2-8 groups — the standard "time until an event" toolkit
  (customer tenure until churn, time until failure/default) that properly
  uses right-censored observations (rows where the event hasn't happened
  *yet*) instead of discarding that information the way a fixed-cutoff
  proxy like `domains.flag_churn()` has to. New classic step-function KM
  chart (`visualization.plot_kaplan_meier`). Handles bad/huge input
  explicitly: negative durations rejected, event columns coerced from
  Yes/No/True/False/1/0 variants, >20k rows sampled down with a warning
  (same tractability-cap convention as `market_basket.py`), thin groups
  rejected with a plain-English reason. 31 new tests, including a
  hand-verified Kaplan-Meier curve against a textbook 6-subject example
  and a log-rank calibration check (p-value averages ~0.5 across 30
  independent null-hypothesis draws).

Both features are 100% local compute (numpy/pandas/scipy/statsmodels,
zero new pip dependency) with an optional Gemini narration layer
following the app's existing call_gemini()/no-model-fallback convention.
Full suite: 611 -> 669 tests, zero regressions.

## 2026-08-11 (Run 29)

### Added
- **DBSCAN + Agglomerative Hierarchical clustering** (`modules/clustering.py`)
  — the Clustering tab now has an algorithm picker alongside the existing
  KMeans option. DBSCAN finds arbitrary-shaped, density-based clusters and
  explicitly labels points that don't belong to any dense region as
  "Noise" instead of forcing every point into a cluster; its `eps`
  parameter is suggested via a k-distance-plot elbow heuristic the user
  can inspect (mirroring the existing KMeans elbow/silhouette-chart
  pattern). Agglomerative Hierarchical clustering (ward/complete/average/
  single linkage) needs no upfront shape assumption and comes with an
  inspectable dendrogram (via `plotly.figure_factory.create_dendrogram`,
  no new dependency). Both share the existing PCA scatter, silhouette
  verdict, cluster-stats table, and "Name Segments with AI" UI through a
  new shared renderer. 19 new tests.
- **Market Basket Analysis** (`modules/market_basket.py`, new module) —
  a new section under Domain Lens → Product Analytics mines frequent
  itemsets and association rules ("customers who buy X also buy Y") from
  a (Basket ID, Item) column pair via a from-scratch Apriori
  implementation (join-and-prune, itemsets up to size 3) — no new pip
  dependency. Rules are scored by support/confidence/lift and shown as a
  top-rules-by-lift bar chart plus a sortable table; a raw frequent-
  itemsets table is available in an expander. Tractability caps (item-
  vocabulary size, basket sampling) protect against pathological inputs
  and are reported back in the UI when triggered. 28 new tests, including
  exact recovery of known co-purchase structure in synthetic transaction
  data.

## 2026-08-11 (Run 28)

### Added
- **Multiclass ROC/PR curves** (`modules/mllab.py`) — `compute_roc_pr_curves()`
  now supports classification targets with 3+ classes via a one-vs-rest
  (OvR) scheme, extending its prior binary-only restriction. Each class
  gets its own ROC and Precision-Recall curve plus a macro-averaged
  AUC/AP summary (the standard multiclass extension per scikit-learn's
  own documented approach). The ML Lab tab shows a model selector and the
  per-class curves side by side, with a plain-English verdict naming the
  single weakest-performing class (the one most likely being confused
  with the others — worth checking in the confusion matrix first). 22
  tests (was 9) in `tests/test_mllab_roc_pr.py`.
- **"Export as Python Script" for ML Lab** (`modules/mllab.py`) — a new
  `export_baseline_script()` generates a standalone, runnable .py file
  reproducing the exact ColumnTransformer preprocessing pipeline, 80/20
  train/test split, optional SMOTE resampling, and both baseline models
  (Logistic/Linear Regression + Random Forest) for the current ML Lab
  run — mirroring the existing `cleaning.export_script()` pattern
  (cited as a top DA/DS industry priority — "analyses that can be re-run
  as data updates") but scoped specifically to the ML Lab baseline-model
  pipeline. Available as a download button next to the feature-importance
  chart. 11 new tests, including subprocess round-trip tests that
  actually execute the generated script against a real CSV and confirm
  it runs clean with matching metric output.

## 2026-08-11 (Run 27)

### Added
- **Population Stability Index (PSI)** (`modules/drift.py`) — the Drift tab
  now computes PSI for every shared numeric column, alongside the existing
  ad-hoc mean-shift/TVD scores. PSI bins the comparison dataset onto the
  baseline dataset's own quantile edges and measures how much probability
  mass moved between bins — the industry-standard drift metric in credit-
  risk/model-monitoring practice, with universally-cited thresholds
  (< 0.10 stable, 0.10-0.25 moderate shift, > 0.25 significant shift
  warranting a model/segment review). Shown in the drift summary table and
  as a plain-English verdict in each column's detail expander. Handles
  constant/near-constant baselines, empty series, NaNs, and empty-bin
  edge cases (an epsilon floor avoids log(0)/divide-by-zero when one
  dataset has no points at all in a tail bin) without raising. 17 new
  tests.
- **Rolling-Origin Forecast Backtesting** (`modules/forecasting.py`) — the
  Forecasting tab can now validate a forecast before you trust it: fits
  the same ETS/SARIMAX model on progressively earlier cutoffs (an
  expanding training window that only ever slides forward in time, never
  shuffled), forecasts the held-out horizon from each cutoff, and scores
  the forecast against what actually happened — Hyndman & Athanasopoulos'
  "time series cross-validation," the standard way to check real forecast
  accuracy instead of trusting a single full-history fit with a parametric
  CI band and no held-out check at all (which is what `run_forecast()` did
  previously). Reports mean MAE/RMSE/MAPE across the backtest windows plus
  a plain-English verdict using Lewis (1982)'s widely-cited MAPE bands
  (excellent/good/reasonable/unreliable), and a window-by-window actual-
  vs-predicted chart. 16 new tests, including a mathematical invariant
  check (RMSE >= MAE), safe-MAPE handling when actuals are near zero, and
  confirming the backtest never mutates the input series.

### Notes
- Playwright/Chromium remained blocked by this session's sandbox egress
  policy for a 3rd consecutive run (`cdn.playwright.dev` → 403 "CONNECT
  tunnel failed", confirmed directly via `curl`) — no UI screenshots this
  run either. Verified instead via the full pytest suite (510 → 543
  green, zero regressions), a live `streamlit run` smoke test (HTTP 200,
  clean logs), and direct function-level runs against real sample data
  (`samples/stock_data.csv` for both PSI and rolling-origin backtesting).

## 2026-08-11 (Run 26)

### Added
- **Silhouette-Score Cluster Validation** (`modules/clustering.py`) — the
  Clustering tab's K suggestion is now a hybrid elbow + silhouette-score
  method instead of elbow alone: the elbow method (inertia drop-off)
  narrows to a small candidate window, then the silhouette score — which
  actually measures how well-separated the resulting clusters are, not
  just how tight they are — picks the winner within that window. This is
  the standard practice recommendation confirmed by current sources,
  since inertia decreases monotonically with K by construction and can't
  by itself tell a genuinely good K from an arbitrary one. Also shown:
  a silhouette-score-by-K bar chart alongside the existing elbow chart,
  and a plain-English verdict on the chosen clustering's silhouette score
  (using the standard Kaufman & Rousseeuw interpretation bands: strong/
  reasonable/weak/no real structure). 19 new tests — the first direct
  test coverage for `modules/clustering.py` — verify true-K recovery on
  synthetic separable blobs and score-band verdict text.
- **ROC-AUC / Precision-Recall Curves** (`modules/mllab.py`) — ML Lab's
  baseline model runner now reports threshold-independent classification
  quality for binary targets, not just accuracy/F1/confusion matrix.
  Accuracy alone is misleading on imbalanced classes — exactly the case
  ML Lab's own class-imbalance detector and SMOTE option already handle
  — since a model can score high accuracy just by favoring the majority
  class. Shows ROC curve + AUC and Precision-Recall curve + average
  precision for both the Baseline and Random Forest models, plus a
  verdict that explicitly flags when the positive class is skewed enough
  that the PR curve should be weighted over ROC-AUC alone (current
  guidance for imbalanced classification). Deliberately binary-only —
  multiclass targets get a graceful explanatory note instead of a
  fabricated one-vs-rest chart, since that needs its own UI decision.
  12 new tests, including a real-data check via `samples/hr_data.csv`
  (attrition prediction) where accuracy alone showed 84.75% but ROC-AUC
  revealed the model was performing worse than random guessing — the
  exact failure mode this feature exists to catch.

## 2026-08-11 (Run 25)

### Added
- **Conformal Prediction Intervals** (`modules/mllab.py`) — ML Lab's
  regression baseline now offers distribution-free uncertainty
  quantification alongside its point predictions, closing a real gap:
  the app already had SHAP explainability and OLS regression diagnostics
  but no interval estimate on the Random Forest's own predictions.
  Split-conformal: fits a Random Forest on a 60% train split, scores
  absolute residuals on a held-out 20% calibration split, and widens
  predictions on the remaining 20% test split by the finite-sample-
  corrected (1-alpha) quantile of those residuals — a genuine marginal
  coverage guarantee with no normality assumption, unlike the parametric
  confidence bands elsewhere in the app. New "Prediction Intervals"
  section under ML Lab's regression results: a target-coverage slider,
  target-vs-empirical coverage readout, mean interval width, a shaded-
  band chart, and a plain-English verdict. 13 new tests, including
  empirical coverage landing near target on synthetic data and explicit
  edge cases (too few rows, non-numeric/all-null target, invalid alpha).
- **K-Fold Cross-Validation** (`modules/mllab.py`) — ML Lab's baseline
  model comparison previously ran off exactly one 80/20 train/test split
  (confirmed zero cross-validation anywhere in the codebase, and zero
  direct unit test coverage on `run_baseline_models` itself before this
  run). `run_cross_validation()` runs the same Baseline and Random
  Forest models through StratifiedKFold (classification) or KFold
  (regression) via a single sklearn Pipeline passed to
  `cross_validate()` — preprocessing refit inside every fold, no
  leakage — reporting mean ± std per metric instead of one noisy point
  estimate. k auto-reduces (and flags) when it exceeds the rarest
  class's member count. New "Cross-Validation" section under ML Lab's
  baseline results (both classification and regression): a fold-count
  slider, per-model mean±std metrics, a per-fold score box plot, and a
  plain-English verdict. 12 new tests, including informative features
  scoring measurably higher than noise and edge cases (too few rows,
  single-class target, empty feature list, k<2, NaN rows).

Both features are pure local scikit-learn/statsmodels compute — no
Gemini calls, no free-tier rate-limit exposure. Full suite 454 → 479
green, zero regressions. Selected via a fresh Phase 2 web research
sweep (`.prism/research_2026-08-11-run25.md`) after 16 consecutive prior
runs reused an earlier sweep; both close verified, non-cosmetic ML-
methodology gaps rather than duplicating the agentic-AI-theme work
Runs 22-23 already shipped (Anomaly Drivers narration, Explore Mode
click-through) — see `.prism/routine_log.md` for the full selection
rationale.

## 2026-08-11 (Run 24)

### Added
- **Streaming out-of-core Excel ingestion** (`modules/data_engine.py`) —
  closes the oldest open backlog item (4 runs, since Run 20). Large
  `.xlsx` uploads previously went through a bare `pd.read_excel()` with
  no row cap threaded through — unlike the CSV path's DuckDB out-of-core
  reader, a genuinely large workbook fully materialized in memory before
  any truncation logic ran (pandas' own `OpenpyxlReader.get_sheet_data()`
  appends every row to a Python list regardless, even though it opens
  the workbook via openpyxl's `read_only=True` mode). New
  `_stream_sample_excel()` opens `.xlsx` files via openpyxl's row
  iterator directly and reservoir-samples in a single pass — a genuine
  random sample across the whole sheet, not just the first N rows —
  while never holding more than `max_rows` rows in memory. Gated behind
  a 15 MB threshold (`LARGE_EXCEL_THRESHOLD_BYTES`), `.xlsx`-only, with
  a streaming-mode equivalent of the existing banner-row/blank-line
  header recovery. Falls back silently to the existing `pd.read_excel()`
  path on any failure (corrupt workbook, missing sheet, empty sheet),
  same fail-safe design as the DuckDB CSV path. 19 new tests, full suite
  435 → 454 green. Live-verified against a genuine 400,000-row / 16.8 MB
  `.xlsx` through the running app: correctly counted all 400,000 rows,
  triggered Smart Sampling, completed the full upload → sample → profile
  flow with no traceback.

## 2026-08-11 (Run 23)

### Added
- **Explore Mode: "Load into Manual Builder" click-through**
  (`modules/visualization.py`, `app.py`) — closes the standing backlog
  item open since Run 20 (3 runs). Explore Mode's auto-suggested chart
  encodings rendered as static info cards with no way to act on them; a
  new "📥 Load into Manual Builder" button under each suggestion now
  preloads the Manual Chart Builder's X-axis/Y-axis/Chart type/Color
  widgets with that suggestion's encoding and renders the matching chart
  immediately, no extra "Build Chart" click required. New
  `suggestion_to_builder_state()` is a pure, Streamlit-free translation
  of a `suggest_encodings()` suggestion into the exact widget
  `session_state` keys/values the builder reads, including the
  `"(none)"` sentinel the optional selectboxes use and a deliberate
  reset of the Facet/Aggregation channels to their defaults (a stale
  facet pick can otherwise collide with the newly-loaded x/y/color and
  raise a Streamlit "value not in options" error, since facet options
  dynamically exclude the current x/y/color). Zero extra Gemini calls,
  fully deterministic. 7 new tests, full suite 428 → 435/435 green.

## 2026-08-11 (Run 22)

### Added
- **Anomaly Drivers** (`modules/anomaly.py`, `app.py`) — IsolationForest
  (and the LOF/DBSCAN ensemble) flag *which* rows are unusual but never
  say *why*. `find_anomaly_drivers()` answers that: it splits the dataset
  into flagged-vs-normal and tests every other column for a real
  difference between the two groups — Welch's t-test (Cohen's d) for
  numeric columns, a chi-square test of independence (Cramer's V) for
  categorical/boolean ones — reusing `stats_lab.run_ttest()`/`run_chi2()`
  directly so the effect sizes and small/medium/large labels always match
  what Stats Lab would report for the same columns. Only statistically
  significant drivers (p < 0.05) surface, ranked by effect size. A new
  "🔬 What makes these rows anomalous?" panel renders under the Anomaly
  Detection results (both single-method and ensemble mode) with an
  optional "✨ Explain these drivers with AI" Gemini narration, cached by
  fingerprint and fact-checked against the drivers' own numbers via the
  same `insight_verifier`-backed safety net the rest of the app uses.
  Zero extra Gemini calls unless the user asks for the narration. 24 new
  tests (44 total in `test_anomaly.py`), full suite 428/428 green.

## 2026-08-11 (Run 21)

### Added
- **Hypothesis Sweep: group-difference confounder cross-check**
  (`modules/confounder_detection.py`, `modules/hypothesis_sweep.py`,
  `app.py`) — Run 19's confounder cross-check only covered significant
  Pearson (numeric/numeric) sweep pairs; Simpson's Paradox applies just as
  much to a group difference (a significant Welch's t-test) as it does to
  a correlation — the classic version is a treatment effect that reverses
  once you control for patient severity. New `stratified_mean_difference()`
  computes Cohen's d per stratum of a candidate confounder and compares it
  to the pooled effect (same paradox/attenuation verdict logic as the
  existing correlation check); `detect_group_diff_confounders()` and
  `auto_scan_for_group_diff_confounding()` are the group-diff analogs of
  `detect_confounders()`/`auto_scan_for_confounding()`.
  `cross_check_confounders()` now scans the sweep's significant t-test
  rows through this new path alongside its existing Pearson-pair scan,
  tagging each result `"relationship": "correlation"` or `"group_diff"`.
  The existing "🕵️ Confounder cross-check" panel renders group-diff
  findings (pooled vs. adjusted Cohen's d, per-stratum mean-diff table)
  with the same expander/badge/"Explain this" UI as the correlation
  findings — no new styling. Categorical confounders only (a numeric
  confounder would need binning first); requires the categorical side to
  have exactly 2 groups, matching `stats_lab.run_ttest()`'s own scope. Zero
  extra Gemini calls, fully deterministic. 23 new tests, full suite
  390 → 413/413 green.

## 2026-08-11 (Run 20)

### Added
- **Explore Mode: auto-suggested chart encodings** (`modules/
  visualization.py`, `app.py`) — closes the oldest standing backlog item
  (first logged Run 13, unbuilt through Run 19). `suggest_encodings()`
  ranks candidate charts by deterministic signal strength: |correlation|
  for numeric x numeric pairs (Scatter), an ANOVA eta-squared effect size
  for categorical x numeric (Bar, gated to 2-15 distinct categories so
  constant/near-unique columns don't clutter the ranking), |trend
  correlation| for datetime x numeric (Line), and |skew| for single
  numeric columns (Histogram). Zero extra Gemini calls — entirely
  offline/deterministic, so it works even when the API is rate-limited.
  New "🧭 Explore Mode" panel in the Visualize tab, between Auto-Generated
  Charts and the Manual Chart Builder, rendering the top-ranked
  suggestions with a plain-English reason and score, built via the
  existing `build_manual_chart()` so every suggestion is guaranteed
  renderable. 9 new tests, full suite 386 → 395/395 green.

## 2026-08-11 (Run 19)

### Added
- **Hypothesis Sweep confounder cross-check** (`modules/hypothesis_sweep.py`,
  `app.py`) — the sweep's own agentic follow-up question: a pair surviving
  Benjamini-Hochberg FDR correction across dozens of automated tests still
  isn't guaranteed to be causally clean, so `cross_check_confounders()`
  now runs the sweep's top significant Pearson pairs through
  `confounder_detection.auto_scan_for_confounding()` — the same Simpson's-
  Paradox / attenuation check Auto-Insights' correlations already get,
  reusing that module's `correlation_pairs=` hook instead of recomputing
  anything. Deterministic, zero extra Gemini calls. New "🕵️ Confounder
  cross-check" panel under Hypothesis Sweep's results table, matching
  Overview's existing Confounder Check UI (paradox/attenuated badges,
  per-group table, cached AI explanation button). 4 new tests (33 total in
  `test_hypothesis_sweep.py`), full suite 382 → 386/386 green.

## 2026-08-11 (Run 18)

### Added
- **Narration fact-check completion** (`modules/anomaly.py`,
  `modules/auto_insights.py`, `modules/insight_orchestrator.py`) — extends
  the insight_verifier-style "plausible but wrong number" safety net to
  every remaining `narrate_*` helper in the app: `narrate_anomalies()` and
  `narrate_ensemble_disagreement()` (Anomaly Detection panel),
  `narrate_insights()` (Auto-Insights executive summary), and
  `narrate_orchestration()` (Agent Summary panel). Each gets its own
  `*_reference_numbers()` builder — anomaly's from the flagged
  DataFrame/methods_summary the narration was built from, auto_insights'
  and the orchestrator's from the source insight messages / ranked
  headlines (already deterministic, non-LLM text) — plus a
  `verify_narration()` wrapper reusing `insight_verifier.verify_finding()`.
  All four wired into `app.py` with the same cached-verification +
  `build_verification_caption()` pattern Runs 15-17 established for
  Report Writer, Story Mode, Demo Mode, and Hypothesis Sweep. Closes Run
  17's exact logged backlog item — every Gemini-narrated surface in Prism
  is now fact-checked against its own real numbers, with zero extra
  Gemini calls. 22 new tests.

## 2026-08-11 (Run 17)

### Added
- **Hypothesis Sweep narration fact-check** (`modules/hypothesis_sweep.py`)
  — extends the insight_verifier-style "plausible but wrong number" safety
  net (already covering Auto Analyst, AI Analyst, Report Writer, Story
  Mode, and Demo Mode's `generate_key_insights()` call sites) to Stats
  Lab's automated FDR-corrected Hypothesis Sweep, whose Gemini narration
  cites p-values, effect sizes, and significant-pair counts but had zero
  fact-checking. New `sweep_reference_numbers()` reads the sweep's own
  already-computed statistics directly (no DataFrame recomputation
  needed, unlike `insight_verifier.compute_reference_numbers()`); new
  `verify_narration()` reuses `insight_verifier.verify_finding()` for the
  actual number-matching. The narration panel now shows the same
  confirmed/unconfirmed fact-check caption every other verified insight
  surface in the app has. Zero extra Gemini calls. 9 new tests.
- **Atlas keyword fast path** (`modules/atlas.py`) — `classify_intent_fast()`
  matches a small, deliberately conservative set of context-free commands
  (navigate to a tab, start demo/story mode, next/previous, cancel)
  without a Gemini API round-trip, wired ahead of `classify_intent()` in
  `handle_utterance()`. Anything context-sensitive — including the
  router's own documented "go"/"do it"/"start" overlap between "confirm"
  and "execute_plan" — is deliberately excluded and still falls through to
  the full Gemini classifier. Cuts latency/quota for the handful of
  commands used every session and makes them exercisable without a live
  `GEMINI_API_KEY` (closes the gap Run 16's routine log flagged: "every
  command, however literal, requires a live API call to route"). 19 new
  tests.

## 2026-08-11 (Run 16)

### Added
- **Fact-check badges for Story Mode and Demo Mode** (`modules/story_mode.py`)
  — the fourth and fifth `ai_analyst.generate_key_insights()` call sites
  (alongside Auto Analyst's Run Full Analysis, verified since Run 10; the AI
  Analyst tab's Generate Key Insights, verified since Run 14; and Report
  Writer's HTML/PDF export, verified since Run 15), and until this run the
  only two with zero fact-checking of their own. New shared, `st`-free
  `_generate_and_verify_insights()` helper runs `insight_verifier` over
  every insight both paths generate. Story Mode shows the confirmed/
  unconfirmed badge next to each slide's "Finding N of M" label; Demo Mode
  switched its hand-duplicated card markup over to `modules.ui`'s shared
  `build_insight_cards_html()`/`build_verification_caption()` so its
  post-narration summary gets the same badges and fact-check caption every
  other insight list in the app has. Zero extra Gemini calls. 5 new tests
  in `tests/test_story_mode.py` (new file — this module had none before).

## 2026-08-11 (Run 15)

### Added
- **Fact-check badges for the Report Writer's HTML/PDF exports**
  (`modules/report_writer.py`) — `build_report_content()` calls
  `ai_analyst.generate_key_insights()` directly, the third independent
  Gemini call site sharing that function's "quote a number straight from
  the data" findings shape (alongside Auto Analyst's Run Full Analysis,
  verified since Run 10, and the AI Analyst tab's Generate Key Insights,
  verified since Run 14) — and the only one whose output leaves the app as
  a downloadable artifact a user might hand to someone else, which made it
  the most consequential of the three to still have zero fact-checking.
  `build_report_content()` now runs `insight_verifier.verify_findings()`
  over the generated findings and attaches the result as
  `findings_verification`. `generate_html_report()` badges each finding
  VERIFIED/UNCONFIRMED (self-contained CSS — the export has no Streamlit
  theme loaded) plus a one-line fact-check caption; `generate_pdf_report()`
  tags each finding with a plain-ASCII `[VERIFIED]` /
  `[UNCONFIRMED - verify before citing]` suffix (fpdf2's core Helvetica
  font can't render the checkmark glyphs the HTML badges use) plus the
  same caption in italic. Both renderers degrade gracefully when
  verification is absent. Zero extra Gemini calls. 12 new tests in
  `tests/test_report_writer.py` (new file — this module had none before).
- **Facet Row (dual-axis small multiples) for the Manual Chart Builder**
  (`modules/visualization.py`, Visualize tab) — continues Run 13/14's
  grammar-of-graphics slice (Color, Aggregation, Facet columns) with the
  second facet dimension Run 14's own report recommended next: a true
  row x column small-multiples grid instead of a single wrapped strip.
  `build_manual_chart()` and `plot_scatter()` gain an optional `facet_row`
  parameter using Plotly Express's native `facet_row`, validated the same
  way `facet` already is. New `MAX_FACET_ROW_CATEGORIES` (4, tighter than
  the column facet's 6 since the two dimensions multiply), capped
  independently via a generalized `_cap_facet_categories(df, facet,
  max_categories)` so each dimension's own frequency ranking is respected.
  Still selectbox-based, no drag-and-drop/custom JS component — same
  no-architecture-rewrite-risk approach as the prior two runs. New "Facet
  rows by (optional)" selectbox in `app.py`. 14 new tests.

## 2026-08-11 (Run 14)

### Added
- **Fact-check badges for "Generate Key Insights"**
  (`modules/ui.build_insight_cards_html`, `modules/ui.build_verification_caption`,
  `app.py`) — extends the confirmed/unconfirmed badge pattern Run 10 wired
  into Auto Analyst's "Run Full Analysis" findings to the AI Analyst tab's
  separate "Generate Key Insights" button. That button makes its own
  independent Gemini call (`ai_analyst.generate_key_insights`, also shared
  by Story Mode and the Report Writer's PDF/HTML export) that quotes
  numbers straight from the data, and until this run had no fact-check of
  its own — the same "plausible but wrong number" risk Run 10 addressed
  only at the other call site. The shared "insight-card + badge" HTML and
  the fact-check caption are now factored into two pure, testable
  functions in `modules/ui.py`, used by both render sites instead of each
  duplicating the badge markup. Zero extra Gemini calls (same static,
  local recomputation `insight_verifier` already does). 11 new tests.
- **Facet (small-multiples) encoding channel for the Manual Chart Builder**
  (`modules/visualization.build_manual_chart`, Visualize tab) — continues
  Run 13's grammar-of-graphics slice (Color + Aggregation) with the next
  encoding channel Run 13's own report recommended: an optional "Facet by"
  column that splits a chart into a grid of small-multiple subplots (one
  per category) instead of overlaying groups in one plot. Available on
  Histogram, Box, Bar, Scatter, and Line (same set as Color; Pie has no
  facet concept of its own). Capped to the 6 most frequent categories by
  frequency (`MAX_FACET_CATEGORIES`) so a high-cardinality column can't
  blow up into an unreadable subplot grid — same top-N capping convention
  Bar/Pie already use for their own axis categories. Still an ordinary
  selectbox, no custom drag-and-drop component. 14 new tests.

### Notes
- Audited the standing "DuckDB/polars-backed Auto Cleaner path for large
  datasets" backlog item and found it already effectively closed: Run 8's
  DuckDB out-of-core ingestion path reservoir-samples any large CSV down
  to `MAX_ROWS` before the DataFrame ever reaches `autocleaner.py`, so Auto
  Cleaner never actually operates on an unbounded dataset. The real
  remaining gap is narrower — large Excel uploads have no equivalent
  out-of-core reader — logged as a new, more precisely scoped backlog
  candidate instead of re-building something already shipped.

## 2026-08-11 (Run 13)

### Added
- **Tier-2 proactive Atlas alert for lone confounder paradoxes**
  (`modules/insight_orchestrator.proactive_alert_text_tier2`, `app.py`) —
  a second, narrower JARVIS-copilot slice alongside the existing
  cross-detector agreement/contradiction alert. Confounder detection runs
  silently on every dataset upload (same as Auto-Insights) but, unlike
  Auto-Insights, had no proactive announcement of its own — a freshly
  detected Simpson's-paradox-style confounder could sit unannounced in
  the Overview tab's collapsed panel. Now Atlas speaks up unprompted the
  moment a lone high-severity confounder paradox is the top-ranked
  finding, even at the plain two-detector baseline (no third detector
  needed, unlike tier 1). Detectors that already actively surface their
  own findings inline when computed (Auto-Insights, Causal Effect
  Estimator, Anomaly Detection, Drift, Hypothesis Sweep, the Auto Analyst
  verifier) are deliberately excluded to avoid double-speaking the same
  information. Zero extra Gemini calls. 7 new tests.
- **Manual Chart Builder: Color + Aggregation encoding**
  (`modules/visualization.build_manual_chart`, Visualize tab) — a
  grammar-of-graphics-style slice toward the long-standing PyGWalker-style
  chart builder backlog item. The existing X/Y/type builder gains an
  optional Color channel (splits/groups marks on Histogram, Box, Bar,
  Scatter, and Line charts) and, for Bar charts, a choice of aggregation
  function (mean/sum/median/min/max) instead of always averaging. Both
  controls only appear for chart types that support them. No custom
  drag-and-drop component — encoding channels are exposed as ordinary
  selectboxes, staying inside Streamlit's native widget set. 19 new tests
  (this module had no dedicated test file before this run).

### Fixed
- Sandbox environment gap: a fresh `pip install` sometimes leaves
  `_cffi_backend` missing, which breaks every test that imports the
  Gemini client chain via `cryptography` with a `pyo3_runtime.PanicException`
  at collection time. `pip install --force-reinstall --no-cache-dir cffi`
  resolves it — logged again here (Run 12 first hit this) so it's
  immediately recognized as environment, not regression, if it recurs.

## 2026-08-11 (Run 12)

### Added
- **Hypothesis Sweep wired into the Agentic Insight Orchestrator**
  (`modules/insight_orchestrator._adapt_hypothesis_sweep`, `app.py`) —
  Stats Lab's automated, Benjamini-Hochberg FDR-corrected pairwise
  hypothesis sweep now feeds the same cross-detector "Agent Summary"
  synthesis every other detector (Auto-Insights, Confounder Check, Causal
  Effect Estimator, Anomaly Detection, Drift) already goes through. Only
  pairs that survive FDR correction (`significant=True`) become claims —
  a pre-correction p<0.05 out of a batch sweep is implicit p-hacking, not
  a reportable finding, so the adapter deliberately drops anything that
  didn't survive it. Severity is derived from the sweep's own small/
  medium/large Cohen's-convention effect-size label, matching the
  severity vocabulary every other detector's claims already use. This
  closes a real gap: a formally-tested, multiple-comparisons-corrected
  relationship (hypothesis_sweep) and a raw correlation-scan flag
  (auto_insights) covering the same column pair previously rendered as
  two disconnected panels; they now collapse into one grouped topic with
  an "agreement" bonus, and — as a side effect of Run 11's proactive Atlas
  alert reading from the same orchestration result — Atlas can now also
  speak up unprompted the moment a hypothesis-sweep-confirmed relationship
  becomes the top cross-detector finding. No new UI surface (same 🧠 Agent
  Summary panel, same proactive-alert convention); zero extra Gemini
  calls. 6 new tests (FDR-filtering, effect-size-to-severity mapping,
  empty/None safety, cross-detector agreement grouping), full suite
  259/259 green. Verified live (Playwright, desktop 1440px, dark theme,
  `samples/stock_data.csv`): ran Hypothesis Sweep (6 pairs survived FDR
  correction out of 15 tested), confirmed the Overview tab's Agent
  Summary now reads "3 detectors" and correctly ranks the `open`/`high`
  pair, and confirmed Atlas's proactive side-panel alert fired for it —
  no traceback, no regression to the existing verifier/causal/confounder
  agreement paths.
- **Environment fix**: the sandbox's `cryptography` install was missing
  its `_cffi_backend` native module, causing every test that imports the
  Gemini client chain to fail with a Rust panic unrelated to any Prism
  code (`pyo3_runtime.PanicException` in `cryptography.exceptions`).
  Reinstalling `cffi` resolves it — a fresh sandbox per run means this
  may recur; noted here so a future run recognizes it as an environment
  gap (fix: `pip install --force-reinstall cffi`) rather than a logic
  regression if it resurfaces.

## 2026-08-11 (Run 11)

### Added
- **Atlas proactively surfaces new Agent Summary findings — JARVIS-copilot
  slice** (`modules/insight_orchestrator.proactive_alert_text()`,
  `app.py`) — previously the orchestration layer's "what matters most"
  synthesis (cross-detector agreement, contradiction flags) only appeared
  if the user opened the Overview tab and clicked "Generate Executive
  Summary." Atlas now speaks up unprompted, in the persistent side panel,
  the moment a *new* top-ranked agreement or contradiction appears —
  no click, no tab visit required. Deliberately narrow by design: only
  the #1 ranked finding, only when it's genuinely the orchestrator's own
  signal (cross-detector agreement/contradiction, not a lone severity
  claim a single detector's panel already shows), only once per distinct
  result (a plain rerun doesn't re-speak the same finding), and silent at
  the baseline two-detector state every upload produces automatically
  (auto_insights + confounder_scan) — that's already covered by the
  existing ambient-upload announcement, so only a genuinely new *third*
  detector firing (Causal Effect Estimator, Anomaly Detection, Drift, or
  Auto Analyst's verifier) counts as news. Zero extra Gemini calls (plain
  synthesis over already-computed detector output, same as the rest of
  the orchestrator). To make this fire regardless of which tab is active
  (e.g. running the Causal Effect Estimator on its own tab, without ever
  visiting Overview), the orchestration computation itself moved from
  inside the Overview tab's render block to run once per rerun at the top
  level — the Overview tab now reuses that same value instead of
  recomputing it. 8 new tests for the pure decision logic in
  `proactive_alert_text()`; full suite 255/255 green. Verified live
  (Playwright, desktop 1440px dark + light, mobile 390px dark): loaded
  `samples/stock_data.csv`, ran the Causal Effect Estimator, and confirmed
  Atlas's side panel spoke up automatically — "Quick flag — 2 independent
  checks now agree on high, open. See the Agent Summary panel for
  details." — with the Agent Summary panel itself rendering the same
  confirmed-by-2-detectors finding beneath it, no traceback.

## 2026-08-11 (Run 10)

### Added
- **Agentic Insight Orchestrator now cross-checks Auto Analyst's own
  fact-checker** (`modules/insight_orchestrator.py`) — Run 9 shipped the
  orchestrator over the six Overview-tab detectors but deliberately left
  out `insight_verifier` (Auto Analyst's static, non-LLM safety net that
  recomputes every quoted number in a Gemini-synthesized finding against
  the real DataFrame) because its findings live on a different tab. This
  run wires it in: a new `verifier` adapter reads Auto Analyst's
  synthesized findings plus `insight_verifier.verify_findings()`'s
  parallel per-finding results, and turns every **"flagged"** finding (a
  quoted number that didn't match anything recomputable — "confirmed" and
  "unverifiable" findings are already badged in-tab and would just be
  noise here) into a `Claim`. Free-text findings have no structured
  per-column field like the other detectors, so subjects are extracted by
  matching the dataset's own column names against the finding text
  (whole-word, case-insensitive) — this lets a flagged Auto Analyst claim
  join the same subject-based grouping as every other detector, so a
  flagged number about a column another detector already flagged now
  surfaces as agreement/contradiction context in one place instead of
  staying siloed on a separate tab the user has to remember to check.
  5 new tests (`tests/test_insight_orchestrator.py`) cover the adapter's
  flagged-only filter, subject extraction, empty/None safety, and that a
  verifier claim participates in cross-detector grouping exactly like the
  other six. Full suite: 247/247 passing (242 baseline + 5 new). No new UI
  surface — reuses the existing "🧠 Agent Summary" panel and its silent-
  below-threshold convention; verified live (Playwright, desktop + mobile,
  `samples/stock_data.csv`) that the panel still renders cleanly with the
  new detector wired in and silently at zero when Auto Analyst hasn't run.

## 2026-08-10 (Run 9)

### Added
- **Agentic Insight Orchestrator** (`modules/insight_orchestrator.py`) —
  Prism had grown seven independent detector modules (Auto-Insights,
  Anomaly Detection, Confounder Check, Causal Effect Estimator ATT + CATE,
  Drift, Insight Verifier) that each ran and rendered standalone, with
  nothing tying their outputs together. This adds a pure synthesis layer
  over already-computed detector output — no detection logic is re-run —
  wired into the Overview tab as a new "🧠 Agent Summary" panel above
  Auto-Insights. It normalizes each detector's own finding shape into a
  common `Claim`, groups claims that share the same subject columns (the
  de-duplication step: two detectors independently flagging the same
  variable pair collapse into one topic instead of two disconnected panel
  entries), flags **cross-detector agreement** (multiple independent
  checks on the same issue = higher confidence, badged "✅ Confirmed by N
  detectors") and one specific **contradiction pattern** — a causal ATT
  estimate whose outcome variable has an unaddressed confound Confounder
  Check already flagged — surfaced as a "🟠 Check this" flag rather than a
  hard error, since the estimate may still be directionally right. The
  deduplicated, cross-checked findings are severity-ranked into a top-5
  "what matters most" list. Optional cached Gemini narration
  (`narrate_orchestration`) follows the exact `call_gemini()` /
  fingerprint-cached / graceful-fallback convention used by
  `auto_insights.narrate_insights` and `confounder_detection.narrate_
  confounder_finding`. Stays silent — renders nothing — until at least two
  detectors have fired this session, the same "don't manufacture noise"
  convention as every detector panel it synthesizes. This cycle's required
  agentic-AI-analysis pick: a genuine planner/executor/critic pattern
  (the detectors are the executors, this is the critic that cross-checks
  and ranks their output) rather than another standalone detector. 37 new
  tests covering normalization of every detector's raw shape, grouping/
  dedup, the agreement and contradiction paths, severity ranking order,
  the silent/empty-state threshold, and the narration cache/fallback
  convention. Verified end-to-end via Playwright against
  `samples/stock_data.csv`: uploading auto-triggers Auto-Insights +
  Confounder Check (2 detectors, "Confirmed by 2 detectors" badges on the
  shared correlated pairs), and running the Causal Effect Estimator with
  a confounding covariate deliberately excluded correctly surfaced "Check
  this: the causal estimate for 'high' doesn't adjust for 'close', which
  Confounder Check found weakens the relationship between 'high' and
  'open'."

### Fixed
- **Agent Summary same-script-pass staleness** — the new panel renders
  near the top of the Overview tab, above the Causal Effect Estimator and
  Anomaly Detection panels further down. Streamlit reruns the whole
  script on a button click without restarting mid-script, so on the exact
  rerun where "Estimate causal effect" or "Find Anomalies" was clicked,
  Agent Summary was rendering with the pre-click session state and
  wouldn't reflect the new result until some unrelated later interaction
  forced a second rerun. Fixed with `st.rerun()` right after those button
  handlers write their result to session state — the same idiom already
  used throughout `app.py` for cross-panel reactivity — so Agent Summary
  updates on the very next render pass. Caught via live Playwright
  verification, not by the unit tests (which correctly exercise the pure
  orchestration logic and had no opinion on Streamlit's script-rerun
  ordering).

## 2026-08-10 (Run 8)

### Added
- **CATE by subgroup — heterogeneous treatment effects**
  (`modules/causal_inference.py`) — extends the Causal Effect Estimator
  with a "Does the effect vary by subgroup?" section. Re-runs the same
  propensity-score-matching estimate within each level of a chosen
  categorical column (2-10 groups) and compares against the pooled ATT,
  flagging a **sign reversal** (the treatment helps one segment and hurts
  another — a blanket rollout would be the wrong call) or **statistically
  meaningful heterogeneity** (non-overlapping confidence intervals) versus
  a homogeneous effect. New bar chart (`modules/visualization.py`) plots
  per-subgroup ATT with 95% CI error bars against a pooled-ATT reference
  line, colored red/green by effect sign. This cycle's required agentic-
  AI-analysis pick — the direct follow-on to Run 7's pooled ATT estimator,
  answering "okay, but does that effect actually hold for everyone?" 8 new
  tests, including recovery of an injected sign reversal on synthetic data
  and correct handling of undersized subgroups that can't support their
  own match. Optional Gemini narration via the existing `call_gemini()`
  plumbing.
- **DuckDB out-of-core ingestion for large CSV uploads**
  (`modules/data_engine.py`) — closes the "polars/DuckDB large-file path"
  backlog item flagged in every routine run since 2026-08-07 (7
  consecutive runs). For CSV uploads at or above 15MB, DuckDB's
  `read_csv_auto()` counts rows and pulls a random reservoir sample
  directly from disk, without pandas ever loading the full file into
  memory. Below the threshold — or on any DuckDB failure, including a
  guard against its own degenerate-parse edge case on malformed banner
  rows — behavior falls back to the pre-existing pandas path unchanged.
  Also a real accuracy improvement over the old behavior: the sample is
  now a genuine random draw across the whole file, not "keep the first N
  rows" (which silently over-represents whatever a file happens to be
  sorted by). `duckdb` was already a dependency (used by SQL Lab) — no new
  dependency added. 10 new tests. Verified end-to-end against a synthetic
  500,000-row/16.6MB upload: Smart Sampling correctly reported the row
  count, and the resulting 50,000-row sample showed visibly shuffled
  (non-sequential) IDs, confirming true random sampling.

## 2026-08-10 (Run 7)

### Added
- **Causal Effect Estimator** (`modules/causal_inference.py`) — a new
  "Causal Effect Estimator" panel in Overview, directly below Confounder
  Check, that estimates the Average Treatment Effect on the Treated (ATT)
  via propensity score matching: a logistic-regression propensity model,
  greedy nearest-neighbor caliper matching without replacement, covariate
  balance (standardized mean difference) reported before and after
  matching, and a bootstrap 95% confidence interval. This is the natural
  agentic follow-on to the Confounder/Simpson's-Paradox detector (Run 6) —
  that panel diagnoses "this correlation might be confounded," this one
  answers "okay, so what's the actual effect once you correct for it."
  Only renders when the dataset has a usable binary treatment column and
  enough numeric columns for an outcome plus covariates; every failure
  path (non-binary treatment, non-numeric outcome, too few units, no
  usable covariates, zero matches within the caliper) is reported in
  plain English instead of raising. Optional Gemini narration follows the
  same cached, graceful-fallback pattern as every other narration helper
  in the app. 23 new tests, including a synthetic confounded-assignment
  fixture proving the matched estimate is measurably closer to the true
  effect than a naive (unadjusted) group-mean comparison.

### Fixed / Maintenance
- Result metrics in the new Causal Effect Estimator panel initially
  overflowed their `st.metric` tiles at desktop width (the CI and
  matched-pairs strings were too long) — caught in Phase 5 screenshot
  review and fixed before shipping by moving the longer values to a
  caption under two short metric tiles.
- Investigated Run 6's open "light-theme dataframe canvas styling"
  finding (in-session theme toggle + a genuine browser reload) — does not
  reproduce; `sync_native_theme()` (Run 4) works correctly. Closed.

## 2026-08-10 (Run 6)

### Added
- **Confounder / Simpson's Paradox Detector** (`modules/confounder_detection.py`)
  — a new "Confounder Check" panel in Overview, directly below Auto-Insights,
  that automatically stress-tests the dataset's strongest correlations
  against every other column: stratified per-group Pearson correlation for
  categorical confounders, closed-form partial correlation for numeric
  ones. Flags when a relationship reverses sign once you control for a
  third variable (a true Simpson's Paradox) or collapses/weakens
  materially, ranked worst-first. Runs automatically on every dataset
  load — no button click, no Gemini call needed for detection — with an
  optional one-click Gemini narration that follows the same cached,
  graceful-fallback pattern as every other narration helper in the app.
  16 new tests.

### Fixed / Maintenance
- **Migrated off the deprecated `google-generativeai` SDK** to
  `google-genai` (`modules/ai_analyst.py`, `modules/atlas.py`) — the old
  package ended upstream support and raised a `FutureWarning` on every
  import. A new `_GeminiModel` adapter keeps every call site's
  `model.generate_content(contents) -> response.text` interface
  unchanged, so the migration stayed contained to the two files that
  build model instances (`get_model`/`get_sql_model`/`build_model` in
  `ai_analyst.py`, Atlas's router `_client()`) instead of touching the
  ~15 call sites that use `call_gemini()`. Also updates the
  conversational-turn builders for the new SDK's stricter `contents`
  shape (Part dicts, not bare strings) and `call_gemini()`'s error
  mapping (the new SDK reports errors via `.code`, and returns `None`
  rather than raising for an empty/safety-filtered response). 16 new
  tests. Closes a backlog item flagged by four consecutive prior runs.

## 2026-08-10 (Run 5)

### Added
- **Hypothesis Sweep** (`modules/hypothesis_sweep.py`) — a new panel in
  Stats Lab that automatically generates and runs every statistically
  viable pairwise hypothesis test across the dataset (Pearson correlation
  for numeric/numeric, Welch's t-test/one-way ANOVA for numeric/
  categorical, chi-square for categorical/categorical — reusing Stats
  Lab's own `suggest_test`/`run_test` dispatch), then applies
  Benjamini-Hochberg false-discovery-rate correction across the whole
  sweep before ranking what's left by effect size. Where Stats Lab tests
  one manually-picked pair at a time, this is the automated version — and
  the FDR correction is what makes running many simultaneous tests
  statistically defensible instead of implicit p-hacking. Results table +
  effect-size chart, with optional Gemini narration of the significant
  findings (cached per result fingerprint, same pattern as anomaly
  narration). 22 new tests.
- **Feature Selection Engine** (`modules/mllab.py`) — a new panel in ML
  Lab that cross-checks three independent feature-selection methods over
  the same preprocessed feature matrix: Mutual Information (nonlinear,
  model-free), an L1-regularized linear model's coefficients (Lasso for
  regression, L1-penalized Logistic Regression for classification), and
  Recursive Feature Elimination with a Random Forest estimator. Ranks
  features by consensus — how many of the 3 methods agree a feature
  matters — the same self-verifying-ensemble pattern already used for
  anomaly detection (`find_anomalies_ensemble`), applied here to picking
  features instead of flagging rows. Shows a recommended-features summary,
  per-method ranking table, and a consensus-vote chart. Closes the
  "Feature Selection Engine (mutual info/RFE/L1) for ML Lab" backlog item
  open since Run 4. 12 new tests, including planted-signal recovery for
  both classification and regression.

## 2026-08-10 (Run 4)

### Added
- **Ensemble Anomaly Consensus** (`modules/anomaly.py`) — an "Ensemble
  mode" checkbox in Anomaly Detection cross-checks Isolation Forest
  (global isolation) against LOF (local density) and DBSCAN
  (density-based clustering, eps auto-tuned via a k-distance percentile
  heuristic). Flagged rows carry a `consensus_count` (1-3) and are sorted
  by agreement, with per-method metric cards and a "🔗 N of M flagged by
  all 3 methods" summary. `narrate_ensemble_disagreement()` asks Gemini to
  explain what the agreement/disagreement pattern suggests — detection
  stays deterministic and auditable (three independent sklearn models),
  the LLM's only job is interpretation. Closes the "Advanced outlier
  detection (LOF, DBSCAN)" backlog item open since 2026-08-07; serves this
  cycle's required agentic-AI theme via the self-verifying multi-detector
  pattern. 19 new tests.

### Fixed
- **Native theme sync for `st.dataframe`/`st.table`** (`modules/theme.py`,
  `sync_native_theme()`) — these render through glide-data-grid, a
  `<canvas>` element whose colors come from Streamlit's `theme.base`
  runtime config, not the CSS this app injects. `.streamlit/config.toml`
  only sets that once, hardcoded dark, so every dataframe kept dark
  row/header styling even under the Arctic (Light) theme — flagged as an
  open finding in the 2026-08-10 Run 3 report. Now pushed via
  `st._config.set_option` on every theme switch, guarded so a future
  Streamlit version removing that private hook degrades gracefully
  instead of crashing. 7 new tests.
- **Mobile Atlas side-panel overlap** (~390px viewport) — reconfirmed by
  two prior runs but misdiagnosed as a single-cause bug. The actual root
  cause was two independent rules: (1) `.st-key-atlas_side_panel` in
  `modules/theme.py` was `position: fixed; width: 328px` unconditionally,
  and (2) `app.py` separately reserved `padding-right: 352px !important`
  on `.block-container` to make room for it — also unconditional. On a
  ~390px phone, (2) alone left ~22px for all main content regardless of
  (1). Both are now scoped to a `min-width: 769px` / `max-width: 768px`
  media-query pair: under 768px the panel stacks below main content
  instead of overlapping it, and the reserved padding drops to 0. Verified
  via layout-inspection screenshots, not just visual spot-check — see
  `.prism/audit_2026-08-10-run4.md`.

## 2026-08-10

### Added
- **Anomaly narration** (`modules/anomaly.py`) — Gemini explains the
  pattern behind IsolationForest-flagged rows in plain English (data-entry
  errors vs. genuine rare events) with one suggested next action, from an
  "✨ Explain these anomalies with AI" button in the Anomaly Detection
  expander. Narration is cached per a fingerprint of the flagged set
  (row count + index/reason hash) so re-viewing the same result doesn't
  re-spend a Gemini call. Serves this cycle's agentic-AI priority theme —
  closes a backlog item both 2026-08-07 runs flagged and left open. 6 new
  tests.
- **Atlas proactive alert HUD** (`modules/atlas.py`) — an incremental
  JARVIS-copilot slice. The orb gains an `alert` visual state (amber
  double-ring pulse + "⚠ N new insight(s)" label) that lights up
  unprompted whenever a fresh dataset load surfaces a high-severity
  Auto-Insight finding — zero extra Gemini calls, reuses the
  already-computed `auto_insights.generate_insights()` list. Clears
  itself the next time Overview renders after the user has seen it.
  Closes the "Atlas Proactive Insights" backlog item both 2026-08-07 runs
  flagged but neither built. 7 new tests.
- Baseline pytest coverage for `auto_insights`, `regression_diagnostics`,
  and STL decomposition (`forecasting.decompose_series`) — 42 tests. The
  2026-08-07 run report claimed 82 tests for these three modules, but
  `git log -- tests/` showed none were ever actually committed; discovered
  during this run's audit and backfilled as a small fix.

### Fixed
- The Atlas side panel's small header orb (`.atlas-orb-sm`) had its size
  set in `modules/theme.py` but no background/gradient/animation — those
  rules lived only in `atlas.py`'s CSS block, injected solely by
  `render_orb()`, which is skipped whenever a dataset is active (the side
  panel replaces the floating orb). The header orb was effectively
  invisible for every state, not just the new `alert` one — pre-existing,
  just never visually exercised before this run's Phase 5 screenshot
  check caught it. Fixed by injecting the CSS from both call sites.
- `atlas.raise_alert()` and `atlas.clear_alert()` could run in the same
  Streamlit script pass (Overview is the default active tab, so a fresh
  upload while already on it hits both in one execution) — clearing would
  erase the alert before the browser ever painted it. Added a one-run
  grace flag so a newly raised alert survives to be seen first.

## 2026-08-07

### Added
- **Insight Verifier** (`modules/insight_verifier.py`) — a deterministic,
  non-LLM fact-checker for Auto Analyst's Gemini-synthesized findings.
  Recomputes real statistics straight from the loaded DataFrame (row/column
  counts, per-column means/medians/nulls, category shares, pairwise
  correlations, bounded group-by means) and cross-checks every number a
  finding quotes against that reference set. Findings are now badged
  ✓ verified / ⚠ unconfirmed in the Auto Analyst tab, with a summary caption
  ("N finding(s) with confirmed figures"). Catches the classic agentic-EDA
  failure mode where an LLM's narration drifts from the data it was given,
  without any extra Gemini calls.
- **Test suite** (`tests/`, `pytest.ini`, `requirements-dev.txt`) — Prism's
  first automated test coverage. 22 tests across `insight_verifier`,
  `anomaly` (IsolationForest flagging), and `auto_analyst` (plan fallback
  logic, result summarization, findings synthesis guardrails). Run with
  `pip install -r requirements-dev.txt && pytest`.
- **Suggested next hypothesis** (`auto_analyst.suggest_followup_hypothesis`)
  — after an Auto Analyst run, Prism scans the loaded data directly (not
  LLM prose) for the single most promising column pair to formally test:
  the strongest numeric/numeric correlation above a "worth testing" bar,
  or failing that the numeric/categorical pair with the largest one-way
  ANOVA F-statistic among viable group counts. Shown as a "Suggested next
  step" card in the Auto Analyst tab with a one-click "Test in Stats Lab"
  button that pre-selects both columns. Deterministic, no extra Gemini
  calls. 5 new tests.
- **Auto-Insight Engine** (`modules/auto_insights.py`) — proactive
  statistical insights surfaced automatically on every dataset upload, no
  button click required. Scans for highly skewed/heavy-tailed
  distributions, strongly/moderately correlated numeric pairs
  (multicollinearity warnings), missing-data severity, IQR-based outlier
  prevalence, near-constant columns, high-cardinality ID-like columns,
  class imbalance in low-cardinality categoricals, and exact duplicate
  rows. Findings are severity-ranked (high/medium/low) and shown at the
  top of the Overview tab, with an optional one-click Gemini narration
  that turns the raw findings into a stakeholder-readable paragraph. 23
  new tests covering every detector plus edge cases (empty/single-row/
  all-null data).
- **Regression Diagnostics Panel** (`modules/regression_diagnostics.py`) —
  added to ML Lab for regression targets. Fits its own statsmodels OLS
  (separate from ML Lab's sklearn baseline, since inference needs
  statsmodels' standard errors) and runs the standard diagnostic battery:
  residuals-vs-fitted, Normal Q-Q, and Scale-Location plots; Shapiro-Wilk
  normality; Breusch-Pagan heteroscedasticity; Durbin-Watson
  autocorrelation; and Variance Inflation Factor (VIF) per feature for
  multicollinearity. Each check gets a plain-English verdict. 33 new
  tests, including coefficient recovery on synthetic data with known
  collinearity/heteroscedasticity.
- **Time Series Decomposition (STL)** — added to the Forecasting tab.
  Splits a time series into trend + seasonal + residual components via
  statsmodels' STL (robust to outliers by default), reusing the existing
  `prepare_series()` pipeline. Shows a 0-1 trend/seasonal strength score
  (Hyndman & Athanasopoulos heuristic) and a 4-panel observed/trend/
  seasonal/residual chart. 26 new tests, including an additive-
  reconstruction identity check and known-trend/seasonality recovery on
  synthetic data.

### Fixed
- `ai_analyst.call_gemini()` no longer crashes with a `TypeError` if the
  `google.generativeai` import failed (`google_exceptions` was `None`) —
  now matches on exception class name as a fallback. Also guards against
  safety-filtered or empty Gemini responses instead of raising on
  `response.text` access.
- `auto_analyst._summarize_result()` now truncates wide DataFrames (20+
  columns) and long string results before they're folded into the
  findings-synthesis prompt, avoiding an unbounded token cost on
  wide datasets.
