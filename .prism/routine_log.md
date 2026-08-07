# Prism Autonomous Improvement Routine — Run Memory

This file is the routine's memory across runs. Every run appends a summary
below (newest first). **Read this before starting new work — never rebuild
or duplicate a feature already shipped here.**

This file did not exist before the 2026-08-07 run despite the repo already
carrying a rich commit history (SHAP explainability, Titan Enrichment,
Chaos Intensity, a full DuckDB SQL Lab workbench, Atlas's planning
capability, India Mode, the Indian PII Vault, Hell Mode, and more — see
`git log` and `README.md`'s Features section for the full existing
surface). Treat the commit history and README as the authoritative record
of everything shipped before this file started tracking runs.

---

## 2026-08-07

**Shipped:**
1. **Hypothesis Engine** (`modules/hypothesis_engine.py` + new Stats Lab
   UI section) — Gemini proposes testable column-pair hypotheses; Python/
   scipy/statsmodels alone decides the test and runs it; a joint
   Benjamini-Hochberg FDR correction is applied across every hypothesis in
   the batch before a verdict. Falls back to a deterministic heuristic
   generator when Gemini is unavailable. 10 unit tests.
2. **Mobile PWA layout fix** — the Atlas side panel's fixed-position CSS
   had no mobile breakpoint and broke every tab's layout at phone widths;
   added a `max-width:768px` rule so it stacks in normal flow instead.
   Found via this run's own Playwright screenshot audit.

**Skipped / backlog (not built this run):** migrating off the now-EOL
`google-generativeai` SDK (large, needs a live key to verify — see
`.prism/research_2026-08-07.md`); a self-verifying Auto Analyst second
pass; an Atlas proactive-insights slice; polars/DuckDB as an alternate
compute engine (architecture change — proposal only per guardrails).

**Scope note:** this run shipped one feature + one bug fix, not the full
2-3 features the routine template suggests. The Hypothesis Engine's
statistical-rigor requirements (correct test dispatch, real multiple-
testing correction, a working non-LLM fallback, live end-to-end
verification against the real app rather than only mocked tests) took the
full budget for a feature that could survive a technical interview
question about it. A second, thinner feature was available but would have
diluted verification depth on both — skipped deliberately, not from
running out of time.

**Environment note:** no `GEMINI_API_KEY` was configured in this run's
sandbox, so every AI path was exercised in its degraded/fallback state
live, not just by reading the code. This is a decent proxy for "free-tier
quota exhausted," one of the failure modes the routine explicitly asks
every feature to handle.

**Next run should:** pick up the Atlas-copilot-track candidates (proactive
insights slice, or a voice command wrapping the new Hypothesis Engine) and
the self-verifying Auto Analyst idea from `.prism/research_2026-08-07.md`'s
backlog table. Also worth a dedicated cycle: the `google.genai` SDK
migration (needs a real Gemini key available to verify against, unlike
this run's sandbox) and a broader light-theme contrast pass (audit finding
#3 — nav pills, bottom chat bar, and Atlas panel buttons stay dark-on-dark
in "Arctic (Light)").
