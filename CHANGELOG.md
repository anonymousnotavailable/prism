# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-10

### Added
- **Anomaly Narration** — the Anomaly Detection panel (Overview tab) gets
  an optional "✨ Explain these anomalies" button. Sends the already-flagged
  rows' reasons to Gemini and gets back a 3-5 sentence plain-English
  explanation of the pattern, a plausible real-world cause, and one
  concrete next step. No extra rate-limit surface (reuses the existing
  shared `call_gemini` limiter); degrades gracefully with no Gemini model
  configured or nothing flagged. 3 new tests, including the repo's first
  test to exercise the actual `generate_content()` call path via a fake
  model.
- **Local Outlier Factor detection method** — Anomaly Detection now has a
  method selector: Isolation Forest (existing default) or Local Outlier
  Factor, a density-based method that catches outliers that look normal
  against the whole dataset but stand out against their nearest neighbors.
  `n_neighbors` auto-caps to the dataset size so it doesn't break on small
  data. 4 new tests.

### Fixed
- **Test-suite integrity**: `CHANGELOG.md`'s 2026-08-07 entry claimed
  "82/82 new unit tests" for Auto-Insight Engine, Regression Diagnostics,
  and STL Decomposition. They were never actually collected by `pytest` —
  what shipped was `eval/*_eval.py` print-based scripts outside
  `pytest.ini`'s `testpaths`. Ported the same assertions into real
  `tests/test_auto_insights.py`, `tests/test_regression_diagnostics.py`,
  and `tests/test_forecasting_stl.py` (36 tests). `pytest` now actually
  shows 70 passing tests. See `.prism/audit_2026-08-10.md`.

### Known issues (logged, not fixed this run)
- Arctic (Light) theme: the top nav bar and bottom command input stay
  dark-styled instead of switching with the rest of the page. Pre-existing,
  found during this run's screenshot verification.

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
