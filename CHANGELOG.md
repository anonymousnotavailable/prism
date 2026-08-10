# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-10

### Added
- **Anomaly Narration** (`modules/anomaly.py`) — after "Find Anomalies"
  flags rows in the Overview tab, a new "🧠 Explain these anomalies"
  button asks Gemini to turn the row-by-row `anomaly_reason` table into a
  short plain-English narrative: what pattern (if any) connects the
  flagged rows, and one concrete next action. Shares the existing
  `ai_analyst.call_gemini()` rate limiter/quota handling used everywhere
  else in Prism, so it costs nothing extra against the free-tier budget.
  On any failure — no API key, rate-limited, quota exceeded, safety
  filter — falls back to `deterministic_narration()`, a template-based
  summary that parses the most common driver column straight out of the
  existing `anomaly_reason` strings, so the feature never dead-ends on a
  failure banner. 12 new tests.
- **Feature Selection Engine** (`modules/feature_selection.py`) — new
  section in ML Lab, above the Baseline Model Runner. Ranks every
  candidate feature column against the chosen target by three independent
  signals — mutual information (`mutual_info_classif`/`_regression`), an
  ANOVA/F-test (`f_classif`/`f_regression`), and an L1-regularized linear
  model's kept coefficients (`LogisticRegression(penalty='l1')`/`Lasso`) —
  then Borda-count averages the per-method ranks into one combined score,
  so no single method's blind spot dominates. An elbow heuristic
  recommends how many top features to keep (smallest prefix covering
  ~80% of combined importance) and pre-selects them in the feature
  multiselect below. Handles non-numeric feature columns (label-encoded
  for ranking only), missing values (rows dropped), all-null columns
  (excluded, not a crash), and single-class targets (explicit error, not
  a stack trace). 9 new tests.

### Fixed
- Streamlit's "widget created with a default value but also had its value
  set via the Session State API" warning on ML Lab's feature multiselect
  — was harmless but noisy; the initial default now only seeds
  `st.session_state` on first render instead of being passed as both
  `default=` and a session-state write in the same script run.

### Notes
- Reconfirmed a pre-existing bug (first found 2026-08-07 Run 2): at
  ~390px mobile width the Atlas side panel doesn't reflow and squeezes
  main content into an unreadable strip — blocked a clean mobile
  screenshot of this run's features. See `.prism/audit_2026-08-10.md`.
- Found (not fixed — needs a dedicated theming pass): the "Arctic
  (Light)" theme repaints the page background and sidebar but not
  `st.dataframe` tables, Plotly chart backgrounds, or the Atlas panel
  chrome, which stay dark. Pre-existing, app-wide, not introduced by
  today's features but visible in this run's own light-theme screenshots.

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
