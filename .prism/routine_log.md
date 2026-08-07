# Prism Autonomous Improvement Routine — Memory Log

This file is the routine's memory across runs. Read it first, every run.
Never rebuild or duplicate something already shipped — check here first.

---

## 2026-08-07 — Run 1 (first run of this routine's `.prism/` memory system)

**Orientation**: Repo was already a mature Streamlit app (v5+) with a huge
feature set predating this routine's memory file — Auto Cleaner, Hell Mode,
India Mode, Atlas (JARVIS-style voice copilot), Auto Analyst (agentic full
analysis), Anomaly Detection, Stats Lab, ML Lab + SHAP, SQL Lab (DuckDB),
Forecasting, Clustering, Drift, a 15-dataset corpus benchmark, and a FastAPI
tool layer. Full inventory in `.prism/audit_2026-08-07.md`. No React/
Next.js shell exists — product is the Streamlit app end to end.

**Shipped this run**:
1. **Hypothesis Engine** (`modules/hypothesis_engine.py`) — one-click
   auto-scan of every valid column-pair relationship (up to 66 pairs),
   Benjamini-Hochberg FDR correction across the batch, optional Gemini
   narration with offline fallback. Wired into the existing Stats Lab tab.
   7/7 new eval cases pass (`eval/hypothesis_engine_eval.py`), wired into
   CI. Priority-theme feature (agentic AI analysis: automated hypothesis
   suggestion, explicitly required this cycle).
2. **Mobile fix**: Atlas side panel no longer covers the whole screen on
   phone-width viewports (`display: none` below 900px via media query in
   `modules/theme.py`).

**Found, logged, NOT fixed** (top priority for next run — do this BEFORE
new features, dedicate a full cycle to mobile layout specifically):
1. **Page-level auto-scroll-to-bottom hijack.** `st.chat_input`'s mere
   presence makes Streamlit wrap the whole main content area in
   `stAppScrollToBottomContainer` and force-scroll it to the bottom on
   every load/rerun — confirmed via DOM inspection (`scrollTop` snapping
   to `scrollHeight-clientHeight`). Two mitigation attempts failed this
   run (un-fixing the Atlas panel into flow made it worse; a
   `components.html()` JS guard remembering/restoring scrollTop across
   reruns didn't win the race against Streamlit's own re-assertion) — see
   `.prism/audit_2026-08-07.md` finding #2 for the full diagnostic trail
   and what's already been ruled out, so the next attempt doesn't repeat
   it blindly.
2. **Narrow-column render at ~390px width.** Some element (not
   conclusively isolated from #1's scroll noise) renders real page text
   wrapped 1-2 characters per line in a ~20-40px strip at the left edge,
   independent of which tab is active. Needs a focused trace with #1
   neutralized first.

**Selection reasoning**: Hypothesis Engine chosen because (a) it's the
required agentic-AI-analysis feature this cycle, (b) research showed no
surveyed competitor (Julius AI, Hex, Deepnote, ChatGPT Data Analysis)
foregrounds multiple-comparisons statistical rigor — a genuine, defensible
differentiation and strong interview material, not cosmetic, (c) it composes
cleanly on top of the existing `stats_lab.py` (no duplication, no
architecture change), (d) statsmodels was already a dependency, zero new
packages. The Atlas-panel mobile fix was pulled in per Phase 1 ("bugs found
here are automatically eligible as small fixes alongside the main
features") — found while screenshot-testing the Hypothesis Engine's mobile
viewport, and clearly severe enough (breaks the app's core "installable on
phone" claim) to fix immediately rather than only log.

**Backlog for future runs** (full detail + evidence in
`.prism/research_2026-08-07.md`): self-verifying second-pass LLM critique
of Auto Analyst findings; segment/cohort auto-suggestion; Atlas copilot
proactive-insight slice (none of the 1-per-run Atlas budget was spent this
cycle — available next run); `google.generativeai` → `google.genai` SDK
migration (deprecated upstream); mechanical `use_container_width` → `width=`
cleanup.

**Guardrail check**: no secrets touched, `.env` confirmed gitignored,
no force-push, no architecture changes, no data deleted.
