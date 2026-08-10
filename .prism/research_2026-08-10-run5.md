# Research — 2026-08-10 (Run 5)

Four prior runs (2026-08-07 x2, 2026-08-10 Run 3, Run 4) already surveyed
industry practice, competitor tools (Hex/Deepnote/Julius/ChatGPT ADA/
Databricks Assistant), and ecosystem tech in depth — see their research
files for full citations. This run's research is a targeted refresh on the
standing backlog plus confirming this cycle's picks are genuinely unbuilt,
rather than a full re-survey of all four source classes.

## Ranked candidates

| Feature | Evidence | Depth | Effort | Risk | Roadmap theme |
|---|---|---|---|---|---|
| Auto-Verified Hypothesis Testing | Self-verifying agentic EDA is the explicit theme of this cycle's mandate; "suggest → verify" is the core loop distinguishing agentic analysis tools (Julius AI, Databricks Assistant) from static auto-EDA reports | 4 | S | Low — pure composition of existing, already-tested `suggest_test`/`run_test`/`interpret_result` | Agentic AI analysis (required this cycle) |
| Feature Selection Engine (mutual info / L1 / RFE) | Classic feature in every applied-ML curriculum and a near-universal ask in DS interview loops (feature relevance, filter/embedded/wrapper methods); confirmed via codebase inspection that `mllab.suggest_features()` is feature *engineering* (encoding/scaling), not feature *selection* — genuinely unbuilt, not a Run 4 backlog mislabel repeat | 4 | M | Low — new pure function + new UI section, no existing code touched | ML Lab depth |
| polars/DuckDB large-file backend | `duckdb` is already a pinned dependency (`requirements.txt`) and used in SQL Lab — the ingestion/analysis path itself still loads everything into a single in-memory pandas DataFrame | 5 | L | Medium-high — touches the core data-loading path every tab depends on | Architecture-adjacent (explicitly deferred per guardrail: "no architecture rewrites without a dedicated session") |
| `google-generativeai` → `google-genai` SDK migration | Upstream package is end-of-life (`FutureWarning` on every import); four Gemini call sites | 2 (hygiene) | M | Medium — behavior-sensitive migration across every AI feature, needs a dedicated regression pass | Code health |
| Advanced Tools popover auto-close | Found during this run's own screenshot review (see audit file) | 1 | S | Low | UX polish (not this cycle's priority — logged for a future small-fix pass) |

## Selection reasoning

Selected **Auto-Verified Hypothesis Testing** (required agentic theme) and
**Feature Selection Engine** (ML depth, second slot). Both are S/M effort,
low risk, and close specific, previously-identified gaps rather than
re-surveying from scratch — consistent with four prior runs already having
done the broad four-source-class sweep this cycle's mandate calls for.
polars/DuckDB was again deferred: still L effort and architecture-adjacent,
and the guardrail against architecture changes without a dedicated session
applies as much this run as the prior four. The `google-genai` migration
was deferred for the same reason as Run 4 — needs a dedicated regression-
tested session, not a slot alongside two other features.
