# Prism Improvement Routine — Memory Log

This file is the routine's cross-run memory. Each run appends a dated entry
below. Read it in full at the start of every run before deciding what to
build — never rebuild something already shipped here.

---

## 2026-08-07 — Run 1 (first run of this specific routine)

**Orientation finding:** the repo's git history already shows extensive prior
feature work (SQL Lab/DuckDB workbench, Atlas HUD copilot with proactive
insights, SHAP explainability, Titan Enrichment via Open-Meteo, Chaos
Intensity stress-test, a 15-dataset corpus benchmark, AI sandbox hardening
against LFI/SSRF). None of that was done under `.prism/` memory (this
directory didn't exist yet), so this run creates the memory file for the
first time. Also worth noting: the routine's own briefing describes Prism as
having a "React/Next.js glassmorphic PWA shell" — that is **not** what's in
the repo. Prism is a single-file Streamlit app (`app.py`, ~200KB) with a
`modules/` package, styled via a custom HUD/glassmorphism CSS theme injected
through `modules/theme.py`. All future runs should treat Streamlit + Python
modules as the real architecture and disregard the Next.js description.

**Audit highlights:** see `.prism/audit_2026-08-07.md`. Headline finding —
**zero automated tests existed anywhere in the repo** before this run. For a
data-science portfolio piece, that's the single biggest interview-credibility
gap: an interviewer asking "how do you know this works" had no answer.

**Selected feature (this run):** Insight Verifier — a self-verifying
statistical fact-checker for Auto Analyst's Gemini-written findings, plus a
starter pytest suite (22 tests) covering it and two previously-untested
modules (`anomaly.py`, `auto_analyst.py`). Full reasoning in
`.prism/research_2026-08-07.md` and the run report.

**Scope decision:** shipped one deep feature instead of 2-3 shallow ones.
The run's own guardrails ask for conservative, token-efficient work; a
single well-tested, well-verified feature beats three rushed ones the next
run has to firefight. Web research this cycle was a light pass (no live
Gemini key was available in the execution sandbox to exercise the
Gemini-dependent path visually — verified via unit tests instead).

**Second feature shipped same run (`feature/hypothesis-handoff`):**
budget allowed a second, well-scoped low-risk pick from the backlog below —
`auto_analyst.suggest_followup_hypothesis()` scans the loaded data directly
(strongest numeric/numeric correlation, else largest ANOVA F-stat across a
categorical split) and offers a one-click handoff into Stats Lab with both
columns pre-selected. 5 more tests (27 total). Same merge/push/fresh-clone-
boot verification as the first feature. This closes out that backlog item —
do not rebuild it.

**Not built (backlog for next run):**
- Anomaly narration: `modules/anomaly.py` already flags rows with a
  templated `anomaly_reason` string; a genuinely agentic upgrade would have
  Gemini narrate the flagged set in plain English with a suggested next
  action, cached per dataset fingerprint to stay inside free-tier limits.
- Migrate `google-generativeai` → `google-genai`: the old SDK now raises a
  `FutureWarning` on import (support ended). Not urgent, but growing risk;
  do NOT do this as a rushed patch — it touches every Gemini call site in
  `ai_analyst.py`, `auto_analyst.py`, `atlas.py`, needs its own dedicated
  run with full regression testing.
- polars/DuckDB-backed large-file path: `data_engine.py` is pandas-only;
  competitor tools (Hex, Deepnote) lean on DuckDB/polars for big files.
  SQL Lab already uses DuckDB — extending that engine to back the main
  dataframe pipeline for large files is an architecture-adjacent change,
  flag for a dedicated future run rather than a quick patch.
- Live Gemini API key not available in this execution sandbox — could not
  visually confirm the new verification badges render inside a real
  Auto Analyst run. Confirmed via unit tests + code-path review instead.
  Next run with a configured key should screenshot the actual findings
  panel with ✓/⚠ badges showing.

**Outcome:** two feature branches (`feature/insight-verifier`,
`feature/hypothesis-handoff`) built, tested (27/27 pytest green), smoke-
booted the full Streamlit app (HTTP 200, no traceback) after each merge,
screenshotted desktop/mobile/dark/light nav paths, both merged to `main`
and pushed. Final fresh-clone-from-scratch boot check on `main` passed.
Commits: `359e0ed` (verifier), `b5b4c8c` (report), `e988e6a` (hypothesis
handoff).
