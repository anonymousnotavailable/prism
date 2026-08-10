# Changelog

All notable changes to Prism are logged here, newest first.

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
