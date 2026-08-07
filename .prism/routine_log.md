# Prism Autonomous Improvement Routine — Run Log

This file is the routine's memory across runs. Read it first, every run.
Never rebuild or duplicate something already shipped here.

---

## 2026-08-07 — Run 1 (first run under this routine's `.prism/` convention)

**Context found on arrival:** Prism is a mature, single-file Streamlit app
(`app.py`, ~200KB) with 30+ modules — NOT the React/Next.js PWA shell this
routine's boilerplate context describes. Prior (non-`.prism`-logged) work had
already shipped: Auto Cleaner (SAFE/REVIEW deterministic pipeline), Auto
Analyst (agentic plan→execute→synthesize), Stats Lab, Forecasting,
Clustering, Domain Lens (product/banking), ML Lab (feature engineering +
baseline models + SMOTE), SHAP explainability, Atlas voice copilot with a
persistent HUD side panel, SQL Lab (DuckDB workbench), Hell Mode cleaning,
PII Vault, anomaly detection, geo enrichment, and a 15-dataset corpus
benchmark. This is already most of the roadmap in the routine brief.

**Shipped this run:**
1. **Hypothesis Engine** (`modules/hypothesis_engine.py`, wired into the Auto
   Analyst tab) — proposes falsifiable hypotheses about the active dataset
   (Gemini-generated when a key is configured, always falling back to a
   deterministic |Pearson r| / between-group-variance heuristic ranking with
   zero API dependency), then verifies every one itself via Stats Lab's real
   scipy.stats machinery — CONFIRMED only ever comes from a computed p-value,
   never a model's claim. Serves this cycle's agentic-AI-analysis priority
   theme with a genuinely self-verifying design. 13 unit tests, all passing.
2. **Gemini response cache + short backoff retry** (`modules/ai_analyst.py`
   `call_gemini`) — identical prompts (repeat eval questions, repeated
   Hypothesis Engine / Auto Analyst calls) now serve from an in-process LRU
   cache instead of re-hitting the API or the per-session rate limit; a
   transient `ResourceExhausted` gets up to 2 short backoff retries before
   surfacing the quota-exceeded message. Directly targets the quota
   exhaustion seen in `eval/eval_results.md` (questions 17-25 all skipped).
   7 unit tests, all passing.

**Found, NOT fixed this run (logged for next run's priority):**
- **Mobile PWA-breaking layout bug**: the fixed-position Atlas side panel
  does not collapse/stack below ~640px viewport width — it overlaps the main
  tab content almost entirely, leaving only a sliver of the actual
  Overview/Clean/etc. content visible on a phone. Screenshot:
  `.prism/runs/2026-08-07/mobile_overview_dark.png`. This is the single
  highest-priority item for the next run — it breaks the "installable on
  phone" PWA promise on the primary interaction, not a cosmetic nit.
- **Light theme leak**: `st.chat_input` (the "Ask Atlas anything" bar,
  fixed to the viewport bottom, present on every screen) keeps a hardcoded
  dark background even when the "Arctic (Light)" theme is active — visibly
  mismatched. Screenshot: `.prism/runs/2026-08-07/hypothesis_engine_light.png`.
- `google.generativeai` (the SDK Prism uses) is fully deprecated upstream in
  favor of `google.genai` — no functional break yet, but `pip install`
  prints a `FutureWarning` on every import. Worth a migration pass eventually
  (non-trivial: different client/call shape), not a same-run fix.

**Research candidates NOT built** (see `.prism/research_2026-08-07.md` for
the full ranked table) — top of backlog for future runs: polars/DuckDB-backed
profiling for large-file speed, a critic/adversarial-verification pass on
Auto Analyst's own findings (not just Hypothesis Engine), PyGWalker-style
drag-and-drop chart building, Atlas proactive/unprompted insight surfacing
(the next JARVIS-track slice).

**Guardrail check:** no `.env`/secrets touched (`.gitignore` already covers
`.env`); no force-push; no history rewrite; no architecture changes; stayed
inside Gemini free tier (the shipped feature *reduces* API calls via
caching, made zero real Gemini calls during verification — no key was
configured in this environment).
