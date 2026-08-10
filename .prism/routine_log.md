# Prism Improvement Routine — Memory Log

This file is the routine's cross-run memory. Each run appends a dated entry
below. Read it in full at the start of every run before deciding what to
build — never rebuild something already shipped here.

**Note:** 2026-08-07 had two independent routine runs execute concurrently
(same day, separate sessions). Both are logged below in the order they
merged to `main`. Future runs: treat both entries as "already shipped" —
the backlog items each one lists as "not built" are still open unless the
other entry says otherwise.

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

---

## 2026-08-07 — Run 2 (concurrent session, independent selection)

**Orientation:** ran independently and in parallel with Run 1 above (same
day). Did not have Run 1's results available at selection time — the
overlap turned out to be zero (different features picked from different
parts of the research table), but future runs should note this file can
race under concurrent scheduling and read the full day's history before
assuming what's "already shipped."

**Audit:** `.prism/audit_2026-08-07-run2.md` (renamed from this run's
original `audit_2026-08-07.md` to avoid clobbering Run 1's file during
merge). Found the same "no test coverage" gap Run 1 identified (independently
confirms it was real) plus 27 additional findings (error-handling gaps,
zero-variance edge cases, hardcoded config) — see that file for the full
severity-ranked list. Also found, while verifying screenshots, a forward-
compatibility risk: `datetime_intel.detect_gaps()` breaks under pandas 3.0
for non-fixed-duration frequency offsets (BusinessDay, MonthEnd) — currently
harmless since the only caller passes `freq="D"` and requirements.txt pins
pandas 2.3.3, but will need a fix whenever that pin moves.

**Selected features (3, this run):**
1. **Auto-Insight Engine** (`modules/auto_insights.py`) — proactive
   statistical scan (distribution skew/kurtosis, correlation pairs, missing-
   data severity, IQR outlier rate, near-constant/high-cardinality columns,
   class imbalance, duplicate rows) that runs automatically on every
   dataset load and surfaces severity-ranked findings at the top of
   Overview, with an optional Gemini narration pass. Serves this cycle's
   agentic-AI priority theme.
2. **Regression Diagnostics Panel** (`modules/regression_diagnostics.py`) —
   fits its own statsmodels OLS (separate from ML Lab's sklearn baseline)
   and runs the standard interview-grade battery: residuals-vs-fitted,
   Normal Q-Q, Scale-Location plots, Shapiro-Wilk normality, Breusch-Pagan
   heteroscedasticity, Durbin-Watson autocorrelation, VIF multicollinearity.
   Surfaced in ML Lab, gated to regression tasks.
3. **Time Series Decomposition (STL)** — added to `modules/forecasting.py`,
   reusing the existing `prepare_series()` pipeline. Splits a series into
   trend/seasonal/residual with a 0-1 strength score per component, shown
   as a 4-panel chart in the Forecasting tab below the existing forecast.

**Also fixed alongside features (small, audit-sourced):** guarded
`ai_analyst.call_gemini()` against `google_exceptions` being `None` (import
failure) and against safety-filtered/empty Gemini responses; truncated wide
DataFrames in `auto_analyst._summarize_result()` before they hit the
synthesis prompt.

**Not built (backlog for next run):**
- Automated Hypothesis Testing Suite — **NOTE: Run 1 above shipped
  `suggest_followup_hypothesis()`, which covers most of this. Re-check its
  scope before building anything here; likely just needs a UI polish pass,
  not new logic.**
- Cross-Column Correlation Intelligence & Multicollinearity Detection —
  partially covered now by this run's Auto-Insight Engine (correlation
  pairs) and Regression Diagnostics (VIF), but no standalone dedicated view.
- Data Quality Score with Exportable Scorecard
- Polars/DuckDB large-file path — same item Run 1 flagged; still open,
  still architecture-adjacent, still needs a dedicated run.
- Advanced Outlier Detection (LOF, DBSCAN) — beyond the IQR/IsolationForest
  already present.
- Feature Selection Engine (mutual info, RFE, L1) for ML Lab.
- Atlas Proactive Insights (JARVIS copilot track) — at most one such feature
  per run per the routine's own guardrail; not picked this run since none
  of the 3 selections needed to be the copilot-track pick.
- Natural Language Summary of Every Tab.
- `google-generativeai` → `google-genai` migration — same item Run 1
  flagged. Still not urgent, still needs its own dedicated run.

**Screenshot verification note:** Playwright automation against Streamlit's
segmented-control + popover navigation proved flaky (element interception,
DOM-order selectbox ambiguity) and cost significant iteration to get right.
Auto-Insights got full desktop dark/light + mobile dark screenshots.
Regression Diagnostics has no visual screenshot — correctness rests on 33
passing unit tests instead, since the panel reuses UI primitives
(`st.metric`, `st.dataframe`, `st.plotly_chart`) already visually verified
elsewhere. STL Decomposition got desktop dark/light screenshots (including
its empty state). Next run: consider a small helper module/fixture for
reliable Streamlit E2E navigation (label-based selectbox lookup, retry-with-
coordinates for popover clicks) to avoid repeating this cost.

**Also discovered mid-run:** a pre-existing mobile layout issue — at ~390px
viewport width, the Atlas side panel doesn't reflow and overlaps/squishes
main content into an unreadable strip. Confirmed via worktree comparison
that this predates this run's changes (present on `main` before either
Run 1 or Run 2). Not fixed this run (out of scope for the selected
features, and mobile-panel CSS reflow deserves its own focused pass rather
than a rushed fix inside a feature-shipping run). Flagged here so a future
run doesn't rediscover it from scratch — the app's own "mobile-PWA" usable
breakpoint is closer to ~640-768px than a true phone width today.

**Outcome:** three feature branches (`feature/auto-insight-engine`,
`feature/regression-diagnostics`, `feature/stl-decomposition`) built, tested
(82/82 new unit tests green across the three modules, no regressions in the
existing autocleaner eval), merged to `main` in sequence, pushed.

---

## 2026-08-10 — Run 3

**Orientation:** read this file in full plus `CHANGELOG.md` before selecting
anything — confirmed Insight Verifier, hypothesis-handoff, Auto-Insight
Engine, Regression Diagnostics, and STL Decomposition are all already
shipped and did not re-attempt any of them. Also note for future runs: this
run's execution sandbox was missing `pytest`, `playwright`, and `cffi`
(the last one broke `google.generativeai`'s import chain, which broke test
*collection*, not just individual tests) — all three had to be `pip
install`-ed before anything could run. See `.prism/audit_2026-08-10.md`.

**Branch note (harness policy, read before assuming Phase 7 ran as
written):** this execution environment assigns each session a fixed
integration branch (`claude/adoring-meitner-htm9xo`) and forbids pushing
anywhere else without explicit user permission — a stricter rule than the
routine's own Phase 7 ("merge to main, push main"). At the start of this
run that branch and `main` pointed at the identical commit, so the
substitution is a name only, not a scope change: the feature branch was
merged into `claude/adoring-meitner-htm9xo` (not into a `main` checkout
directly) and that branch was pushed. No pull request was opened (default
policy: only open one if explicitly asked). A human merging that branch
into `main` completes Phase 7 exactly as the routine intends. Future runs
in this same kind of session should expect the same substitution.

**Audit:** `.prism/audit_2026-08-10.md` — a scoped pass (not a full
tab-by-tab re-walk; Runs 1/2 already logged 30+ findings, still open).
Re-confirmed the mobile Atlas-panel overlap is still unfixed (still out of
scope — needs its own dedicated CSS pass). New finding: `st.dataframe`'s
canvas-rendered grid doesn't pick up the custom "Arctic (Light)" theme's
background, staying dark under an otherwise-light chrome — cosmetic, not a
contrast failure, not fixed this run.

**Research:** `.prism/research_2026-08-10.md` — light web pass across all
four source classes. Headline finding: none of Julius AI/ChatGPT/Hex/
Deepnote narrate *unsupervised anomaly-detection output* in plain English
specifically (they narrate summary stats and chat answers) — a real, if
narrow, gap that lines up with the backlog item below.

**Selected feature (this run):** Anomaly Narration
(`modules/anomaly.py::narrate_anomalies`) — closes the "Anomaly narration"
backlog item both 2026-08-07 runs flagged: `find_anomalies()` already
tagged each flagged row with a templated `anomaly_reason`; this adds a
"🧠 Narrate Anomalies" button that asks Gemini to synthesize the flagged set
into a short plain-English paragraph plus one concrete next action, in the
Overview tab's existing Anomaly Detection expander. One scoped feature
again this run (not 2-3) — same reasoning as Run 1: a single well-tested
feature that closes a real backlog item beats a rushed third pick, and this
run's own guardrails ask for conservative, token-efficient work.

**Serves this cycle's priority theme (agentic AI analysis):** yes — the
Auto-Insight Engine (Run 2) already covers proactive stats-on-upload;
Anomaly Narration is the equivalent treatment for anomaly detection,
completing the same "raw findings → Gemini synthesis" pattern across both
surfaces. Not an Atlas-copilot-track pick (no voice/HUD/proactive-surfacing
work this run).

**Outcome:** `feature/anomaly-narration` built test-first (12 new tests,
32/32 total green, no regressions), merged into `claude/adoring-meitner-
htm9xo`, pushed. Playwright screenshots at desktop dark/light (full flow,
including the "no Gemini key configured" graceful-failure state — this
sandbox has no `GEMINI_API_KEY`) and mobile dark/light (mobile screenshots
mostly reconfirm the known Atlas-panel overlap bug above, not a regression
from this feature) saved to `.prism/runs/2026-08-10/`. Fresh-clone-from-
`claude/adoring-meitner-htm9xo` boot check passed (HTTP 200).

**Not built (backlog, unchanged additions from this run's research):**
- Data Quality Score with exportable scorecard — still open (Run 2).
- Feature Selection Engine (mutual info, RFE, L1) for ML Lab — still open
  (Run 2), and this run's job-posting research reconfirms ML skills are the
  3rd most-demanded in data-scientist postings — good next-run candidate.
- Advanced outlier detection (LOF, DBSCAN) beyond IQR/IsolationForest —
  still open (Run 2).
- Polars/DuckDB-backed large-file pipeline — still open (Run 1/2),
  reconfirmed by this run's ecosystem research as a live 2026 trend;
  still architecture-adjacent, still needs its own dedicated run.
- `google-generativeai` → `google-genai` migration — still open (Run 1/2);
  the deprecation `FutureWarning` is now visible in every single pytest run.
  Worth prioritizing soon purely to stop the warning noise, even though it's
  not urgent functionally yet.
- Atlas proactive insights (JARVIS copilot track) — still unclaimed by any
  run so far; next run is a reasonable place to spend this cycle's one
  allowed copilot-track pick.
- Mobile Atlas-panel CSS reflow — reconfirmed again this run (3rd time
  logged), still not fixed. Recommend a future run spend its "small fixes"
  budget here specifically, since it's now blocking clean mobile
  screenshots for every UI-touching run.
