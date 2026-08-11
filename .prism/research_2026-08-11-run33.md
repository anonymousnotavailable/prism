# Run 33 research — 2026-08-11

## Gap sweep

Fresh grep sweep across `modules/*.py` + `app.py` (word-boundary safe) for common EDA/stats
feature areas before picking. Confirmed already fully shipped (not gaps): PCA (`clustering.py`),
RFM segmentation + churn flags (`domains.py`), propensity-score-matched causal effects
(`causal_inference.py`), Difference-in-Differences with parallel-trends check (`did.py`),
IsolationForest/LOF/DBSCAN ensemble anomaly detection with driver explanations (`anomaly.py`),
SHAP, conformal prediction intervals, cross-validation, ROC/PR, feature selection (`mllab.py`),
survival analysis / Kaplan-Meier (`survival.py`), Bayesian A/B + frequentist power analysis
(Run 31), text analytics — sentiment/TF-IDF/NMF (Run 32). This is a mature, wide surface; most
"obvious" stats/ML feature ideas are already present.

Zero-hit gaps confirmed genuinely open: **changepoint/CUSUM detection** (carried over from Run 32
backlog — re-confirmed with `changepoint|cusum|ruptures|pelt\b`, zero real hits), and
**Granger causality** (`granger|adfuller|kpss|stationarity|autocorrelation|acf\b|pacf\b`, zero
real hits — `regression_diagnostics.py` has Durbin-Watson for residual autocorrelation but nothing
tests whether one time series' past predicts another's future, and nothing tests stationarity).

## Changepoint / CUSUM detection

No `ruptures` in the environment (`pip show ruptures` → not found) and the app's established
policy across 32 runs has been to avoid new pip dependencies when a solid local-compute
implementation exists. Sanity-checked current best practice:

- PELT (Pruned Exact Linear Time) is the modern standard for *multiple* changepoint detection at
  scale, but a correct pruned-DP implementation is a meaningfully bigger, harder-to-verify piece
  of code than this app's other single-module features, and the pruning is a performance
  optimization, not a correctness requirement, at the row counts this app actually handles.
- **Binary segmentation with a CUSUM test statistic** (recursively split on the strongest mean
  shift, test significance via permutation, recurse into each half) is the textbook simpler
  alternative — same family of algorithm ruptures itself offers as `Binseg`, well documented (e.g.
  Lancaster University's MATH337 changepoint course notes), and tractable to implement correctly
  in pure numpy with a permutation test for significance instead of an asymptotic threshold.
- Confirmed CUSUM's core assumption from the sweep: it detects mean shifts in a series that's
  stationary *between* changepoints; not appropriate for detecting shifts in a trending series
  without first removing trend. Framed the panel's caveat text around this explicitly (same
  "state the assumption, don't pretend it doesn't exist" convention as `did.py`'s pre-trends
  caveat and `power_analysis.py`'s post-hoc-power caveat).

Decision: pure numpy/scipy implementation, no new dependency — `modules/changepoint.py`, binary
segmentation via a max-heap over candidate segments (by CUSUM statistic magnitude), permutation
test per candidate split for significance, capped by `max_changepoints`. Placed in the Forecasting
tab right after STL Decomposition (reuses the same `forecast_dt_col`/`forecast_num_col` selection
and `forecasting.prepare_series()` output — no new column pickers needed), per Run 32's own
recommendation.

## Granger causality (second pick)

Sanity-checked current best practice (Number Analytics' changepoint/Granger guides, statsmodels
docs, and general econometrics sources):

- Both series should be (checked for) stationarity before testing — non-stationary series can
  produce spurious "causality" findings. Standard fix: Augmented Dickey-Fuller test, difference
  until stationary (capped at 2 differences to avoid over-differencing).
- Lag order matters and should be chosen systematically (AIC/BIC), not guessed — `statsmodels.tsa.
  api.VAR.select_order()` on the two-variable system gives this directly, already available via
  the pinned `statsmodels` dependency, zero new installs.
- `statsmodels.tsa.stattools.grangercausalitytests` does the per-lag F/chi2/likelihood-ratio tests
  once stationarity + lag order are handled; its `verbose` argument is deprecated
  (`FutureWarning`) in the installed 0.14.6 — call with `verbose=False` inside a
  `warnings.catch_warnings()` suppression, matching the "call the library correctly and quietly"
  convention already used elsewhere for statsmodels calls.
- The single most-repeated caveat across every source: Granger causality tests *predictive
  precedence*, not true causation — "predictability, not causality" has to be in the module's own
  framing, not just documentation, same as every other causal-flavored module in this app
  (`causal_inference.py`, `did.py`) already does for its own assumption.

Decision: `modules/granger_causality.py` — auto-stationarity via ADF + auto-differencing,
AIC-selected lag via `VAR.select_order`, bidirectional test (X→Y and Y→X, since Granger causality
is not symmetric and a feedback loop is itself a useful finding), placed in the Forecasting tab
alongside changepoint detection (both are time-series diagnostics that pair with the existing
STL/backtest panels already there) rather than in Overview next to PSM/DiD, since it needs a
regularly-spaced datetime axis the way STL/forecast do, not just a binary treatment column.

## Why these two together

Both are 100% local numpy/scipy/statsmodels compute (zero Gemini calls in the estimation path,
narration is the same opt-in click-gated layer every other module uses), zero new pip
dependencies, M effort each, and both were confirmed still-open by a fresh sweep rather than
assumed from Run 32's notes alone. Neither touches Atlas/JARVIS this run — the intent-router track
was substantively extended last run (Run 32) and neither of this run's picks has an obvious
one-command auto-fill shape the way Bayesian A/B and Power Analysis did (both need a *pair* of
user-chosen columns with no single obvious "run the last thing" default), so it's left for a
dedicated Atlas-focused run rather than bolted on as an afterthought.
