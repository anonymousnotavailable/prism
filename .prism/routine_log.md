# Prism Autonomous Improvement Routine — Memory Log

This file is the routine's cross-run memory. Each run appends a dated entry
summarizing what shipped, what was skipped and why, and open backlog items.
**Never rebuild or duplicate a feature already logged as shipped below.**

## Pre-existing state (discovered at first routine run, 2026-08-07)

The repo is a mature Streamlit app (`app.py`, `modules/*.py`), NOT the
React/Next.js PWA shell described in the routine's generic context — that
context is stale/aspirational for this repo and should be disregarded where
it conflicts with what actually exists. Already shipped, per `git log`,
before this routine's first run (do not rebuild):

- Auto Analyst (`modules/auto_analyst.py`) — agentic "Run Full Analysis":
  Gemini drafts an ordered EDA plan, executes each step via the sandboxed
  pandas-exec engine, synthesizes 5 headline findings.
- Atlas copilot (`modules/atlas.py`, `voice_input.py`) — JARVIS-style planning
  agent with persona, neuron-network HUD background, mic input (edge-tts/gTTS
  voice out, streamlit-mic-recorder voice in).
- Stats Lab (`modules/stats_lab.py`) — guided hypothesis testing (t-test,
  ANOVA, chi-square, Pearson) with effect sizes, normality checks.
- Anomaly Detection (`modules/anomaly.py`) — IsolationForest + plain-English
  reasons.
- Hell Mode / AutoCleaner (`modules/hellmode.py`, `autocleaner.py`) — messy
  Indian-data cleaning with a corpus benchmark (`tools/corpus_gauntlet.py`,
  15-dataset registry).
- India domain pack (`modules/india.py`, `domains.py`, PII vault, Geo Lens).
- ML Lab (`modules/mllab.py`) with SHAP explainability.
- SQL Lab (`modules/sql_lab.py`) — full DuckDB workbench.
- Forecasting, clustering, drift detection, dashboard builder, report writer,
  story mode, data dictionary, dataset knowledge, enrichment (Open-Meteo).
- Security hardening: sandboxed AI code-exec (LFI/SSRF fixes), Chaos
  Intensity stress test.
- Two premium HUD themes, screenshot-audited UI fixes.

No `CHANGELOG.md`, no automated test suite existed before this run.

---

## Run — 2026-08-07

**Shipped** (branch `feature/auto-analyst-stat-verification`, merged into
`claude/trusting-curie-ntxjvu` and pushed — see guardrail note below on why
not `main`):
1. **Statistical Verification Layer for Auto Analyst** (`modules/insight_verifier.py`) —
   independently re-derives the dataset's strongest relationships and runs
   them through `stats_lab`'s real hypothesis tests (t-test/ANOVA/chi-square/
   Pearson), surfaced as a "🔬 Statistically Verified" panel with p-values and
   effect sizes. Zero extra Gemini calls. Wired into both the Auto Analyst
   tab and Atlas's `execute_plan`.
2. **Auto-narrated anomaly explanations** (`modules/anomaly.py::narrate_anomalies`) —
   a "🗣️ Narrate anomalies" button that has Gemini explain the flagged
   IsolationForest rows as a group; content-hash cached.

**Why these two**: research (`.prism/research_2026-08-07.md`) and the audit
(`.prism/audit_2026-08-07.md`) converged on the same gap — Auto Analyst had
zero statistical rigor despite `stats_lab.py` already having the machinery,
and this cycle's priority theme was agentic AI analysis. Anomaly narration
was the cheapest complementary win (single cached LLM call on data already
computed) matching what Tableau Pulse/Hex market as "auto-explain anomalies."
No Atlas-copilot-track feature was built this run (both features are
core-analysis, not JARVIS/voice/HUD work) — that's within the "at most one
per run, not mandatory" rule.

**Tests**: repo's first automated suite (`tests/`, pytest), 13 tests, all
green; existing `eval/autocleaner_eval.py` regression suite unaffected
(100%, 8/8). CI updated to run pytest.

**Skipped this run** (see `.prism/research_2026-08-07.md` for the full
ranked table — not rebuilding these without re-reading this log first):
- Hypothesis auto-generation queue for Atlas (candidate #7) — good next-run
  pick, natural extension of the verification layer built this run.
- Cohort/RFM module, causal-inference-lite, A/B power calculator, PyGWalker
  tab, Polars fast path for Hell Mode, time-series decomposition narration,
  drift-to-hypothesis bridge — none started.

**New audit findings, not fixed this run** (logged for next run, see
`.prism/audit_2026-08-07.md` for screenshots):
- Light theme ("Arctic"): the main dataframe grid, nav segmented-control
  pills, and a couple of Atlas-panel elements don't pick up the light
  palette — stay dark-styled, low contrast in a few spots.
- Mobile viewport (390×844): main analysis content wasn't reachable by
  scrolling past the Atlas panel in a quick manual pass — needs a proper
  interactive mobile-nav investigation, not a blind CSS fix.
- `google.generativeai` SDK is fully deprecated upstream (FutureWarning on
  every import) — migrating to `google.genai` is a real future task, but
  is a cross-cutting change touching every Gemini call site, out of scope
  for a single run without dedicated regression coverage first.

**Guardrail note**: the routine's generic instructions say "merge into main
and push main." This repo session's explicit git operating instructions
(hard constraint, takes precedence) assign a specific development branch
(`claude/trusting-curie-ntxjvu`) and forbid pushing elsewhere or opening a
PR without being asked. Followed the harder constraint: merged the feature
branch into the assigned branch and pushed there, did not touch `main`,
did not open a PR.

---

