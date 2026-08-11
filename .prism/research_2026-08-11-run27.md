# Run 27 — Phase 2 research sweep (2026-08-11)

Backlog was flagged thin by Run 26 after three consecutive runs going deep
on ML Lab statistics (Runs 24 Excel ingestion aside, 25 and 26 both shipped
ML-Lab-adjacent stats: conformal prediction, K-Fold CV, silhouette
validation, ROC/PR curves). Per the routine's own "sweep when backlog is
thin" rule, this run ran a fresh external sweep and deliberately searched
*outside* ML Lab first.

## External sweep

- **2026 DA/DS job postings** (Dataquest, mygreatlearning, 365DataScience,
  Jobright): reproducibility ("analyses that can be re-run as data
  updates"), automation scripting, and data cleaning remain the top-cited
  categories — consistent with what Prism already covers deeply (Hell Mode,
  `cleaning.export_script`).
- **Competitor tools** (Hex Notebook Agent GA, Deepnote, Julius AI,
  Databricks AI/BI Genie): 2026 coverage centers on agentic notebook
  copilots and semantic layers — architecturally a large lift, not a fit
  for one run, and overlaps Atlas track (capped at 1 feature/run here).
- **Agentic-EDA research** (NotebookRAG arXiv 2602.17215, EDAssistant):
  reinforces reproducibility/export as a real, current concern but the
  concrete asks are notebook-generation-scale efforts, not a single-run
  slice.
- **polars/DuckDB/pandas ecosystem**: 2026 consensus is a converged
  "DuckDB (scale) + Polars (speed) + Pandas (ecosystem)" stack via Arrow —
  informative for a future architecture note, not an actionable single-run
  feature (Prism is already pandas + DuckDB-assisted CSV sampling in
  `data_engine.py`).

## Internal gap audit (before ranking — avoid re-discovering shipped work)

Read `modules/clustering.py`, `forecasting.py`, `drift.py`,
`causal_inference.py`, `confounder_detection.py`, `hypothesis_sweep.py`,
`sql_lab.py`, `hellmode.py`, `domains.py`, `atlas.py`, `cleaning.py`,
`recipes.py`, `report_writer.py`, `session_io.py` directly. Confirmed
already shipped (reject as candidates): SHAP explainability, FDR-corrected
hypothesis sweeps, silhouette validation, ROC/PR curves, conformal
prediction intervals, K-Fold CV, STL decomposition with trend/seasonal
strength score, propensity-score causal inference with CATE subgroups and
bootstrapped CIs, OLS regression diagnostics (VIF/Breusch-Pagan/Durbin-
Watson/Shapiro-Wilk), a full data-quality-assertion engine in SQL Lab
(`suggest_assertions`/`run_assertions` — a lightweight Great-Expectations
analogue), a cleaning-script exporter (`cleaning.export_script`), a recipe
save/replay system, banking/product domain packs (RFM, NPA ratio, credit
utilization, cohort retention, DAU/MAU, funnels) in `domains.py`, and PII
masking. `grep -rn "PSI\|population.stability\|backtest\|walk.forward\|
rolling.origin\|time.series.cross" modules/*.py tests/*.py` — zero hits.

## Ranked candidates

| # | Feature | Evidence / rationale | Depth (1-5) | Effort | Risk | Theme |
|---|---|---|---|---|---|---|
| 1 | **Population Stability Index (PSI) for Drift tab** | Industry-standard drift metric in banking/credit-risk model monitoring (PSI<0.1 stable, 0.1-0.25 moderate, >0.25 significant — universally cited thresholds); current `drift.py` only has an ad-hoc z-shift score and TVD, no binned-distribution PSI at all. Reinforces the existing banking domain pack (NPA/credit utilization) already in `domains.py`. | 4 | S | Low | Statistical rigor, diversify from ML Lab |
| 2 | **Rolling-origin (walk-forward) backtesting for Forecasting tab** | Hyndman & Athanasopoulos "time series cross-validation" — the standard way to validate a forecast model's real accuracy (MAPE/RMSE/MAE across multiple rolling origins) instead of trusting a single full-history fit with no held-out validation at all, which is exactly what `forecasting.run_forecast()` does today. Same textbook already cited in this codebase's STL trend/seasonal-strength heuristic, so it's a natural extension. | 4 | M | Low | Statistical rigor, diversify from ML Lab |
| 3 | DBSCAN/hierarchical alternative to KMeans-only clustering | `clustering.py` is KMeans-only (spherical-cluster assumption, no noise/outlier detection). Real gap, but Clustering tab already got a feature (silhouette) in Run 26 — risks over-indexing one tab two runs running. | 3 | M | Low | ML/statistical rigor |
| 4 | Difference-in-Differences estimator for `causal_inference.py` | Common panel/pre-post causal design not covered by the existing propensity-score matching. High depth but requires panel-structure detection and new assumptions UI — too large for one slice of a two-feature run. | 5 | L | Medium | Causal inference |
| 5 | Multiclass ROC/PR curves (`mllab.py` follow-on from Run 26) | Real but small gap; explicitly deprioritized this run to diversify away from ML Lab after 3 straight runs there. | 3 | S | Low | ML Lab (deprioritized) |
| 6 | Reproducible-script export beyond cleaning (cover ML Lab/Stats Lab/Clustering steps too) | `cleaning.export_script` only replays the cleaning log; analysis steps (models, forecasts) aren't exportable as code. Valuable but touches many modules — too broad for one run without scope creep. | 3 | L | Medium | Reproducibility |
| 7 | Great-Expectations-style schema/data-contract versioning (diff assertions across uploads) | `sql_lab.py` already has one-shot assertions; versioned schema drift-of-contract is a natural next step but overlaps candidate #1 (PSI) thematically and is a larger UI lift. | 3 | M | Low | Data quality |

## Selected this run

**#1 (PSI for Drift) and #2 (rolling-origin forecast backtesting).** Both
are verified-open, statistically substantive gaps (not cosmetic), diversify
away from ML Lab into the Drift and Forecasting tabs respectively, touch
zero Gemini calls (pure numpy/pandas/statsmodels), and neither touches the
Atlas/JARVIS copilot track. Full reasoning in `.prism/routine_log.md`.
