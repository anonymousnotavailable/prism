# Changelog

All notable changes to Prism are logged here, newest first.

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
