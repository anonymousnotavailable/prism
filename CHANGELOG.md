# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-10

### Added
- **Anomaly Narration** (`modules/anomaly.py::narrate_anomalies`) — Gemini
  turns IsolationForest's flagged rows and their deterministic reasons into
  a short, stakeholder-readable narrative with a suggested next action, via
  the app's existing shared rate-limit/error handling (`call_gemini`). The
  narration is cached in session state keyed by a hash of the flagged set
  (`anomaly_fingerprint`), so repeat renders or clicks on the same result
  never re-hit the Gemini free tier. Surfaced in the Overview tab's Anomaly
  Detection panel behind a new "✨ Narrate these anomalies" button. Closes
  the Anomaly Narration backlog item from the 2026-08-07 runs; serves this
  cycle's agentic-AI-analysis priority theme. 7 new tests.
- **Feature Selection Engine** (`modules/mllab.py::rank_features`) — new ML
  Lab panel, between the Feature Engineering Assistant and the Baseline
  Model Runner. Ranks every candidate feature column by three canonical
  methods — mutual information (filter, nonlinear-aware), L1/Lasso
  coefficient magnitude (embedded), Recursive Feature Elimination
  (wrapper) — normalizes each to 0-1 by its own max, and averages them
  into a consensus score. Shows a grouped bar + consensus-marker chart and
  a per-feature score table, with a one-click "Use recommended features
  below" handoff that pre-fills the Baseline Model Runner's feature
  multiselect with the above-average-consensus subset. Any single method
  failing on degenerate data is dropped from that feature's consensus
  instead of failing the whole ranking. Closes the Feature Selection
  Engine backlog item from the 2026-08-07 runs. 9 new tests.
- **Real pytest coverage for three previously-untested modules**
  (`tests/test_auto_insights.py`, `test_regression_diagnostics.py`,
  `test_stl_decomposition.py`) — the 2026-08-07 Run 2 CHANGELOG entry
  claimed "82 new unit tests" for `auto_insights.py`,
  `regression_diagnostics.py`, and the STL addition to `forecasting.py`,
  but those tests were only ever standalone `eval/*.py` scripts, never
  wired into `pytest`. Ported them as real tests. Suite: 27 → 73 passing.
  Full writeup in `.prism/audit_2026-08-10.md`.

### Investigated, not fixed (see `.prism/audit_2026-08-10.md`)
- The 2026-08-07 Run 2 finding that Prism's Atlas side panel overlaps main
  content at ~390px viewport widths was root-caused further: the panel's
  own CSS isn't the real problem (two attempted fixes there were reverted
  after making things worse or merely unmasking it), and the actual bug is
  a pre-existing Streamlit layout quirk that collapses the *entire*
  Overview tab's main content to a ~22px sliver on phone widths,
  independent of the Atlas panel. Repro evidence and a suggested fix
  shape are logged for a dedicated future run.
- Plotly charts across the whole app (not just this run's new chart) keep
  a dark plot area even when Prism's in-app theme is switched to light —
  traced to `.streamlit/config.toml`'s hardcoded native dark `base` plus
  every `st.plotly_chart(...)` call omitting `theme=None`. Cosmetic,
  app-wide, pre-existing; logged for backlog.

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
