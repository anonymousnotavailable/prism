# Phase 2 Research Sweep — Run 25 (2026-08-11)

Fresh web research sweep, as recommended by Run 24 (16 consecutive prior
runs had reused an earlier sweep since the backlog stayed well-scoped;
Run 24 closed the last well-scoped non-cosmetic item — large Excel
ingestion — leaving only cosmetic-only and explicitly out-of-scope
Atlas/HUD items, which per this routine's own rule triggers a new sweep).

Searches run (WebSearch tool, live, 2026-08-11): DA/DS job-posting skill
requirements 2026; Hex/Deepnote/Julius AI/ChatGPT ADA/Databricks
Assistant feature comparisons 2026; polars/pandas/DuckDB/PyGWalker
ecosystem adoption 2026; agentic EDA / autonomous data-science-agent
research 2026; data quality / schema validation (Pandera/Great
Expectations) best practice 2026; conformal prediction / SHAP /
explainability-uncertainty convergence 2026; MAPIE conformal prediction
intervals; Hex Magic AI / Deepnote AI agent feature specifics 2026.

Before ranking candidates, the codebase was read directly
(`modules/mllab.py`, `modules/forecasting.py`, `modules/hypothesis_sweep.py`,
`modules/clustering.py`, `modules/drift.py`, `modules/causal_inference.py`,
`modules/confounder_detection.py`) to check what Prism has already
shipped in 24 prior runs, since several obvious candidates turned out to
already exist: SHAP explainability (`mllab.explain_with_shap`), FDR-
corrected multi-test hypothesis sweeps (`hypothesis_sweep.py`, already
uses `statsmodels.stats.multitest.multipletests(method="fdr_bh")`),
parametric forecast confidence intervals (`forecasting.run_forecast`
already returns ETS/SARIMAX prediction intervals), propensity-score
causal inference with bootstrap CIs, and OLS regression diagnostics
(VIF/Breusch-Pagan/Durbin-Watson/Shapiro-Wilk). This is a genuinely deep
statistical toolkit already — the ranking below is filtered to what is
verifiably *not yet present*.

## Ranked candidates

| # | Feature | Evidence / link | Technical depth (1-5) | Effort | Risk | Roadmap theme |
|---|---|---|---|---|---|---|
| 1 | **Conformal prediction intervals for ML Lab regression** (uncertainty quantification alongside point predictions) | MAPIE / scikit-learn-contrib docs (github.com/scikit-learn-contrib/MAPIE); "SHAP + conformal prediction" cited as an emerging 2026 XAI/UQ convergence trend (sciencedirect.com/science/article/pii/S095219762500363X) | 5 | M | Low (pure local compute, no new heavy dep — implemented as split-conformal from scratch, same philosophy as existing modules) | Statistical/ML rigor |
| 2 | **K-fold cross-validation for ML Lab baseline metrics** (currently a single 80/20 split only — no CV anywhere in the codebase, confirmed via `grep -rn "cross_val\|KFold" modules/`) | Standard practice flagged in every DA/DS job-posting and interview-prep source surveyed (dataquest.io, acciojob.com); a single train/test split for model comparison is a textbook methodology weak spot a hiring panel would flag first | 4 | M | Low (sklearn `cross_validate` over existing preprocessing pipeline; additive, doesn't change existing single-split UI) | Statistical/ML rigor |
| 3 | Silhouette-score cluster validation (clustering.py only has elbow/inertia, no silhouette) | Standard unsupervised-learning rigor check; absent per `grep -n silhouette modules/` | 3 | S | Low | ML rigor |
| 4 | Pandera-style schema/data-contract validation on re-upload | 56% of data engineers cite data quality as top challenge (dbt Labs 2025 State of Analytics Engineering, via endjin.com); Pandera 0.29 (Jan 2026) widely covered | 3 | M | Medium (meaningful overlap with existing `drift.py` new/missing-category detection — would need care to differentiate, not purely additive) | Data engineering reliability |
| 5 | Polars/DuckDB as a default backend swap for large in-memory ops | "DuckDB + Polars + Pandas" hybrid workflow named as the 2026 trend (codecut.ai, kanaries.net) | 4 | L | High (architecture-adjacent — touches every module that takes a DataFrame; explicitly out of scope per this run's "no framework rewrites" guardrail) | Ecosystem tech — proposal only |
| 6 | DeepAnalyze-style fully agentic multi-turn analyst report generation | DeepAnalyze-8B, agentic LLM for end-to-end data science (emergentmind.com/papers/2510.16872) | 5 | L | High (needs a much larger context/tool-loop than Gemini 2.5 Flash free tier comfortably affords per-request; Prism already has `auto_analyst.py`/`insight_orchestrator.py`/`hypothesis_sweep.py` covering large parts of this shipped across Runs 21-23) | Agentic AI — already substantially covered |
| 7 | PyGWalker-style drag-and-drop visual chart builder | Named explicitly in this run's brief as ecosystem tech to check | 2 | M | Low, but largely cosmetic/UX rather than technical-depth (Prism's Explore Mode + Manual Builder, shipped Run 23, already covers a chart-in-clicks workflow) | UX — lower priority per this run's filter |
| 8 | Julius-AI-style single-turn "upload CSV, ask in English, get chart" flow | julius.ai/articles/ai-tools-for-data-analysis | 2 | S | Low | Already substantially covered by existing `ai_analyst.py` ask_and_execute pipeline |

## Selected for Run 25

**#1 (Conformal Prediction Intervals) and #2 (K-Fold Cross-Validation)** —
both close verifiable, non-cosmetic ML-methodology gaps in `mllab.py`,
both score highest on technical depth among candidates that are not
already shipped, both run entirely on local scikit-learn/statsmodels
compute (zero Gemini calls, so no free-tier rate-limit exposure at all),
and both are additive to the existing baseline-model UI rather than
replacing tested behavior. See `.prism/routine_log.md` for the full
selection rationale, including why this run leans away from the
agentic-AI theme.
