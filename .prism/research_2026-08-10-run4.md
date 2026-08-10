# Prism Research — 2026-08-10, Run 4

Same-day fourth run of the routine (see `routine_log.md` for the full
history — Runs 1-3 across 2026-08-07 and 2026-08-10 already shipped Insight
Verifier, hypothesis handoff, Auto-Insight Engine, Regression Diagnostics,
STL Decomposition, Anomaly Narration, and the Atlas proactive alert HUD).
This run's web pass is light on purpose — the backlog carried by prior runs
already contained two strong, unbuilt, non-duplicative candidates directly
from the standing research; the searches below were run to (a) validate
those picks are still the right call and (b) refresh the four source
classes with anything genuinely new since the 08-07/08-10 passes.

## Industry practice
Data-analyst interview prep content for 2026 (LockedIn AI, DataCamp, Exponent,
KORE1, Interview Guys) consistently lists SQL, statistics, and — new
emphasis vs. older guides — **AI-assisted workflow judgment and data
validation** as explicit 2026 interview foci. Ensemble outlier detection and
formal data-quality scoring are called out as more senior/specialized
topics, not entry-level — i.e. exactly the kind of thing that makes a
portfolio piece stand out relative to a typical bootcamp project.
[Data Analyst Interview Questions 2026 (DataCamp)](https://www.datacamp.com/blog/how-to-prepare-for-a-data-analyst-interview) ·
[LockedIn AI 2026 prep guide](https://www.lockedinai.com/blog/data-analyst-interview-questions-prepare-guide)

## Competitor tools
Hex/Julius/Deepnote/Databricks coverage in 2026 roundups (Julius AI, Deepnote,
NomadLab) frames the competitive axis as "writes-SQL-with-AI-assist" (Hex)
vs. "no-code chat analyst" (Julius, Databricks Genie) vs. "Jupyter-native
collaboration" (Deepnote) — none of the roundups surfaced a dedicated,
exportable data-quality-scorecard feature as a named differentiator for any
of them, suggesting it's still whitespace rather than a "catch up to
competitors" feature.
[Hex Competitors 2026 (Julius)](https://julius.ai/articles/hex-competitors) ·
[AI Data Analyst Platforms 2026 (NomadLab)](https://nomadlab.cc/blog/2026/05/ai-data-analyst-platforms-2026-hex-julius-cortex-genie-thoughtspot)

## Ecosystem tech
2026 coverage (dev.to, CodeCut, Python in Plain English, codecentric)
converges on a **"pandas + Polars + DuckDB hybrid stack"** as the emerging
default rather than any one library winning outright — DuckDB for
out-of-core SQL on files larger than RAM, Polars for parallel in-memory
transforms, pandas for the glue/ecosystem compatibility Prism already
depends on. This reconfirms the standing backlog item (DuckDB/polars-backed
large-file path) rather than surfacing anything new — still correctly
flagged as architecture-adjacent and deferred to its own dedicated run per
the routine's guardrails, not attempted here.
[Python Data Processing 2026 (dev.to)](https://dev.to/dataformathub/python-data-processing-2026-deep-dive-into-pandas-polars-and-duckdb-2c1) ·
[pandas vs Polars vs DuckDB (CodeCut)](https://codecut.ai/pandas-vs-polars-vs-duckdb-comparison/)

## Agentic EDA research
Recent papers (DataSage — multi-agent debate + external knowledge retrieval
for insight discovery; QUIS — question-guided insight generation) point
toward multi-role/self-verifying agent pipelines as the current EDA
research frontier, beyond Prism's existing single-pass Auto-Insights +
Insight Verifier combo. Noted as a **future** direction (a "debate" pass
between two Gemini calls arguing for/against a finding before it's shown)
rather than this run's pick — meaningfully bigger in scope than a
single-run slice, and Prism's existing Insight Verifier already covers the
core "don't show an unverified statistical claim" risk this class of
research targets.
[DataSage (arXiv 2511.14299)](https://arxiv.org/pdf/2511.14299) ·
[QUIS (arXiv 2410.10270)](https://arxiv.org/pdf/2410.10270)

Separately, an ensemble-outlier-detection survey (EQAF) reports ensemble
voting across complementary detectors "substantially outperforming
individual methods" (F1 61-79% vs. lower single-method scores) — direct
support for this run's ensemble-detection pick over a single-algorithm
upgrade.
[Ensemble Anomaly Detection Framework (arXiv 2606.20079)](https://arxiv.org/pdf/2606.20079)

## Ranked candidate table

| Feature | Evidence | Technical-depth (1-5) | Effort | Risk | Roadmap theme |
|---|---|---|---|---|---|
| **Ensemble outlier detection (LOF + DBSCAN + IsolationForest, consensus voting)** | EQAF survey confirms ensembles beat single methods; backlog item open since 08-07 Run 2 | 5 | M | Low | Agentic AI analysis (built) |
| **Exportable Data Quality Scorecard** (grade + issues + recommendations + Gemini summary) | 2026 interview guides flag data validation/quality as a growing focus; whitespace vs. named competitor features; backlog item open since 08-07 Run 2 | 4 | M | Low | Agentic AI analysis (built) |
| Mobile Atlas panel overlap fix | Confirmed regression during this run's own screenshot verification (pre-existing, flagged by 08-10 Run 3's audit too) | 2 | S | Low | Bug fix (partially built — see caveat below) |
| Light-theme table styling fix | Same source as above | 2 | S | Low | Bug fix (built) |
| Multi-agent "debate" verification pass (DataSage-style) | arXiv 2511.14299 | 5 | L | Med | Agentic AI analysis (not built — next-run candidate) |
| Feature Selection Engine (mutual info / RFE / L1) for ML Lab | Standing backlog, reconfirmed relevant to interview-skill signal | 4 | M | Low | ML Lab |
| Advanced clustering-based outlier detection beyond IQR (now partially superseded by this run's ensemble pick) | Standing backlog | — | — | — | Superseded — see note |
| polars/DuckDB-backed large-file path | 2026 "hybrid stack" consensus reconfirms relevance | 5 | L | Med-High | Architecture-adjacent — proposal only, not built |
| `google-generativeai` → `google-genai` SDK migration | FutureWarning already firing on every import | 2 | M | Med (touches every Gemini call site) | Tech debt — needs dedicated run |
| General mobile responsive layout audit (<640px) | This run's own screenshot evidence — squish predates and outlives the Atlas-panel-specific fix | 3 | M | Low-Med | Bug fix — next-run candidate |

**Note on "Advanced outlier detection (LOF/DBSCAN)"**: this run's Ensemble
Outlier Detection feature closes that exact backlog item (both algorithms
plus IsolationForest, with consensus voting rather than a bare swap) —
marking it built, not carrying it forward.
