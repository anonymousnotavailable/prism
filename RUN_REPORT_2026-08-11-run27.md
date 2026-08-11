# Run 27 Report — 2026-08-11

## What shipped

### 1. Population Stability Index (PSI) — `modules/drift.py`
The Drift tab (compares the active dataset against a second uploaded
dataset, e.g. "last month") previously scored numeric-column drift with
an ad-hoc z-shift heuristic and categorical drift with total-variation
distance — no industry-standard metric at all. Added `compute_psi()`:
bins the comparison dataset onto the baseline dataset's own quantile
edges (deciles by default) and sums `(pct_b - pct_a) * ln(pct_b/pct_a)`
across bins — the textbook PSI construction used throughout credit-risk
and ML-model-monitoring practice, with universally-cited thresholds
(< 0.10 stable, 0.10-0.25 moderate shift, > 0.25 significant shift
warranting review). Wired into the Drift tab's summary table (new PSI
column) and each column's detail expander (plain-English verdict via
`psi_verdict()`).

**Technical-depth argument:** PSI is not cosmetic polish — it's the
metric a credit-risk or ML-monitoring reviewer would ask for by name,
and its absence was a real, verified gap (`grep -rn "PSI|population.
stability" modules/*.py tests/*.py` → zero hits before this run). The
implementation handles the edge cases that make PSI easy to get wrong:
an epsilon floor prevents `log(0)`/divide-by-zero when a bin is empty in
one distribution (e.g. dataset B entirely outside dataset A's historical
range in a tail bin), a constant/near-constant baseline correctly
returns `None` instead of degenerate bin edges, and NaNs are dropped
before binning.

### 2. Rolling-Origin (Walk-Forward) Forecast Backtesting — `modules/forecasting.py`
The Forecasting tab's `run_forecast()` fit an ETS/SARIMAX model once on
full history and reported a parametric 95% confidence band — but never
validated the model against any held-out data, so users had no signal on
whether the forecast was actually trustworthy before betting on it.
Added `rolling_origin_backtest()`: fits the same model on progressively
earlier cutoffs (an expanding training window that only slides forward
in time, mirroring `_fit_and_forecast()`'s logic — refactored out of
`run_forecast()` so both share one code path), forecasts the held-out
horizon from each cutoff, and scores against the actual values that
followed. This is Hyndman & Athanasopoulos' "time series cross-
validation" — the standard technique for validating forecast accuracy
without letting future data leak into training (a naive shuffled K-Fold
would be invalid here). Reports mean MAE/RMSE/MAPE across windows plus a
plain-English verdict using Lewis (1982)'s widely-cited MAPE
interpretation bands (excellent < 10% / good < 20% / reasonable < 50% /
unreliable), and a window-by-window actual-vs-predicted chart.

**Technical-depth argument:** this closes the same class of "trust but
don't verify" gap that K-Fold CV (Run 25) and silhouette validation
(Run 26) closed elsewhere in the app, applied correctly to the
time-series case where the naive analogue (shuffled CV) is statistically
invalid — the implementation deliberately uses expanding, forward-only
windows for exactly that reason. Also handles: near-zero actuals in
MAPE (masked out rather than exploding to infinity), requesting more
backtest windows than the series can support (silently capped, not
crashed), and confirmed via test to never mutate the caller's input
series.

## Why these two (selection reasoning)

Run 26 flagged the backlog as thin after three consecutive runs
concentrated on ML Lab/Clustering statistics (Runs 24 Excel ingestion
aside, 25 and 26 both ML-Lab-adjacent). Per the routine's own rule, this
run ran a fresh Phase 2 web research sweep — 2026 DA/DS job posting
surveys, Hex/Deepnote/Julius AI/Databricks competitor coverage,
NotebookRAG/agentic-EDA research, and the polars/DuckDB/pandas ecosystem
consensus — plus a direct read of every relevant module
(`clustering.py`, `forecasting.py`, `drift.py`, `causal_inference.py`,
`confounder_detection.py`, `hypothesis_sweep.py`, `sql_lab.py`,
`hellmode.py`, `domains.py`, `atlas.py`, `cleaning.py`, `recipes.py`,
`report_writer.py`, `session_io.py`) to avoid re-discovering already-
shipped work. That read confirmed the toolkit is unusually deep already
— SQL Lab already has a Great-Expectations-style assertion engine, Hell
Mode already covers disguised nulls/Indian numbers/date resolution/
fuzzy merge/unit normalization/zero sentinels, `domains.py` already has
banking + product analytics packs (RFM, NPA ratio, credit utilization,
cohort retention, funnels), and `cleaning.export_script` already gives
reproducible cleaning-step code export.

Full ranked candidate table (7 candidates) is in
`.prism/research_2026-08-11-run27.md`. PSI and rolling-origin
backtesting ranked #1 and #2: both verified-open (zero grep hits before
this run), both pure statistical-rigor closures rather than cosmetic
polish, both diversify away from ML Lab into the Drift and Forecasting
tabs, and both were scoped small enough (S and M effort) to build and
verify solidly in one run — unlike the larger candidates surfaced
(DBSCAN/hierarchical clustering would have been a third straight run on
the Clustering tab; a Difference-in-Differences causal estimator and
full reproducible-script export across all analysis tabs were both
flagged too large for a single two-feature run, logged as Run 28+
candidates).

## Verification evidence

- Full pytest suite: **510 → 543 passed, zero regressions** (17 new PSI
  tests + 16 new backtest tests = 33 total).
- `python3 -m py_compile app.py` — clean syntax check after both UI
  wiring changes.
- Playwright/Chromium: blocked by sandbox egress policy for a **3rd
  consecutive run** — confirmed directly via `curl --max-time 15
  https://cdn.playwright.dev/...` → `403 CONNECT tunnel failed`, not
  retried further per this run's brief. No UI screenshots this run.
- Live server smoke test: `streamlit run app.py --server.headless true
  --server.port 8503` → `curl -o /dev/null -w "%{http_code}"
  http://localhost:8503` → **HTTP 200**, clean logs (no tracebacks,
  no import errors) on the fully-merged branch.
- Direct function-level verification against real sample data
  (`samples/stock_data.csv`, ACME ticker close price):
  - `rolling_origin_backtest(series, "D", horizon=14, n_windows=5)` ran
    5 windows successfully, mean MAPE 8.29% → correctly verdicted
    "excellent forecast accuracy."
  - `compute_psi()` against a synthetic 63%-mean-shift copy of the same
    series returned PSI 8.28 → correctly verdicted "significant shift,
    review the model/segment," well above the 0.25 threshold.
- Both feature branches merged into `claude/adoring-meitner-7xxgfq`
  with `--no-ff`; only one trivial auto-merge in `app.py` (adjacent
  session-state-key additions), no conflicts.

## STAR bullets

**Population Stability Index (PSI) for Drift Monitoring**
- *Situation:* Prism's Drift tab compared two datasets column-by-column
  but only offered an ad-hoc z-shift heuristic for numeric drift — not
  the metric practitioners actually reference.
- *Task:* Add the industry-standard, quantile-binned PSI metric with
  correct edge-case handling (empty bins, constant baselines, NaNs).
- *Action:* Implemented `compute_psi()` using baseline-quantile binning
  and an epsilon floor against log(0)/divide-by-zero, `psi_verdict()`
  with standard thresholds, wrote 17 tests first (TDD) covering
  identical/shifted/moderate distributions and every edge case, then
  wired into the existing Drift tab UI.
- *Result:* Correctly flagged a synthetic 63% mean shift on real stock
  data as PSI 8.28 ("significant"), zero regressions across 543 tests.

**Rolling-Origin Forecast Backtesting**
- *Situation:* `run_forecast()` fit once on full history with a
  parametric CI band but no held-out accuracy check — users had no way
  to know if a forecast was trustworthy before relying on it.
- *Task:* Add time-series-safe backtesting (expanding windows sliding
  strictly forward in time — a shuffled K-Fold would leak future data).
- *Action:* Refactored the shared ETS/SARIMAX fit logic into
  `_fit_and_forecast()`, built `rolling_origin_backtest()` on top of it
  with safe-MAPE handling and window-count capping, wrote 16 tests first
  including a mathematical invariant check (RMSE >= MAE) and a
  non-mutation guarantee, then added a "Run Backtest" panel to the
  Forecasting tab.
- *Result:* Verified end-to-end on real stock-price data — 5 backtest
  windows, 8.3% mean MAPE, correctly verdicted "excellent"; zero
  regressions across 543 tests.

## Backlog not built this run (logged for Run 28+)

From `.prism/research_2026-08-11-run27.md`'s ranked table:
- **DBSCAN/hierarchical clustering** alternative to KMeans-only
  `clustering.py` (depth 3, effort M) — real gap, deferred to avoid a
  third straight run concentrated on the Clustering tab.
- **Difference-in-Differences estimator** for `causal_inference.py`
  (depth 5, effort L) — high-depth panel/pre-post causal design, needs
  panel-structure detection and new assumptions UI; too large for one
  slice of a two-feature run.
- **Reproducible-script export beyond cleaning** — extend
  `cleaning.export_script`'s pattern to ML Lab/Stats Lab/Clustering
  analysis steps, not just the cleaning log (depth 3, effort L) — valuable
  but touches many modules, scoped too broadly for one run.
- **Multiclass ROC/PR curves** (`mllab.py`, Run 26's suggested follow-on)
  — real but small gap, explicitly deprioritized this run to diversify
  away from three consecutive ML-Lab-adjacent runs.

## Recommendation for Run 28

Backlog is healthier now (PSI + backtesting closed two verified gaps),
but still has real open items above. Suggested priority: **multiclass
ROC/PR curves** (small, closes the last ML Lab classification gap,
S effort) paired with either **DBSCAN/hierarchical clustering** (M
effort, now safe to revisit the Clustering tab after a two-run gap) or a
scoped-down slice of **reproducible-script export** (e.g. just ML Lab's
`run_baseline_models()` step, not the full cross-tab sweep). If neither
feels right on re-inspection, run another fresh Phase 2 sweep — this
run's research file has 3 more candidates logged with reasoning for why
they were deferred, not rejected.

## Environment notes

- No reinstall needed this run — `pip install -r requirements.txt
  -r requirements-dev.txt` reported everything already satisfied.
- Playwright/Chromium egress blocked for a 3rd consecutive run
  (Runs 25, 26, 27) — this is very likely a stable sandbox policy at
  this point, not transient. Future runs may want to stop re-attempting
  it each time and go straight to the AppTest/live-server fallback,
  unless the routine brief is updated to reflect this as the norm.
- Cleaned up two stale local branches left over from Run 26
  (`feature/silhouette-cluster-validation`, `feature/roc-pr-curves`),
  confirmed fully merged via `git branch --merged` before deleting.
