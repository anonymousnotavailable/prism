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

**Orientation:** read this file in full plus both 2026-08-07 audits before
doing anything. No run happened between 08-07 and 08-10 — this is the next
run in sequence, not a concurrent one. Confirmed via `git log` that nothing
shipped since the last entry above.

**Regression check:** `pytest` 27/27 green, plus all three `eval/*.py`
harnesses (auto_insights 23/23, regression_diagnostics 33/33,
stl_decomposition 26/26) — 109/109 total, no bit-rot in prior features.
Sandbox needed `pip install --force-reinstall cffi` to unblock a
`_cffi_backend` import panic in the `google-generativeai` dependency chain
before tests would even collect — not a Prism bug, but pinned
`cffi>=1.16` in `requirements-dev.txt` as a small fix so it doesn't repeat.

**Audit:** `.prism/audit_2026-08-10.md`. Re-confirmed both carried-forward
findings from 08-07 are still open (mobile Atlas panel has zero responsive
breakpoints; `google-generativeai` deprecation warning). Also documented
that `eval/*.py` (82 checks) never run under plain `pytest` — deliberate
split, not a bug, but flagged for a future run to consider consolidating.

**Research:** `.prism/research_2026-08-10.md`. Web research across all
four source classes confirmed: (1) the 2026 agentic-analytics consensus
shape is deterministic-detect -> LLM-narrate, which Prism's Auto-Insight
Engine already does but `anomaly.py` still doesn't; (2) no surveyed
competitor (Hex, Deepnote, Julius, ChatGPT ADA) ships a standalone
exportable data-quality-scorecard artifact, and Prism already has the
underlying weighted health-score math (`get_health_breakdown`) sitting
unexported; (3) no new ecosystem dependency justified this cycle.

**Selected features (2, this run):**
1. **Anomaly Narration** (`modules/anomaly.py` — `narrate_anomalies()`,
   `anomaly_fingerprint()`) — this run's agentic-theme pick. Extends the
   existing IsolationForest flagging with a Gemini narration pass over the
   *aggregated reason set* (never raw row values — PII-safe by
   construction, since `_reason_for_row()` only ever emits
   "`column` is `Nx` above/below median" strings). Result is cached in
   `st.session_state` keyed by a fingerprint of (dataset shape, flagged
   count, reason multiset) so re-opening the Anomaly Detection expander on
   unchanged data never re-calls Gemini — directly satisfies the routine's
   "design for rate-limit handling and caching" guardrail. Closes the
   backlog item both 08-07 runs left open ("Anomaly narration").
2. **Data Quality Scorecard** (`modules/quality_scorecard.py`) —
   deterministic (no Gemini call at all). Turns the existing weighted
   Data Health Score (`data_engine.get_health_breakdown`) into a
   standalone, letter-graded (A-F) per-column scorecard with prioritized
   remediation bullets, downloadable as self-contained HTML or Markdown —
   the missing "exportable" half of the 08-07 Run 2 backlog item
   ("Data Quality Score with Exportable Scorecard"). Distinct from the
   existing `report.py` Auto-EDA report (that's a kitchen-sink dump of
   quality + stats + charts; this is a focused, single-purpose,
   portfolio-shareable deliverable — the two intentionally don't merge).

**Atlas copilot track:** not used this run (no copilot-track feature
selected) — consistent with the guardrail that it's optional per run, not
mandatory.

**Bundled small fixes (audit-sourced, not counted against the 2-3 feature
budget):** mobile Atlas panel responsive CSS (theme.py — the confirmed
still-open bug from both prior runs); `cffi>=1.16` pin in
requirements-dev.txt.

**Not built (backlog, carried forward + refined):**
- Feature Selection Engine (mutual info/RFE/L1) for ML Lab — still open,
  medium risk (touches ML Lab's model-fit flow), good next-run candidate.
- Advanced outlier detection (LOF, DBSCAN) beyond IQR/IsolationForest.
- `google-generativeai` -> `google-genai` migration — still flagged as
  needing its own dedicated run with full regression coverage across
  `ai_analyst.py`, `auto_analyst.py`, `atlas.py`, `auto_insights.py`, and
  now also the new `anomaly.py` narration call site.
- polars/DuckDB large-file path — still architecture-adjacent, still open.
- Consolidate `eval/*.py` into `pytest`-discoverable tests (or add a
  documented `make test` / README target that runs both) so `pytest` alone
  isn't silently under-reporting coverage.
- Atlas full JARVIS voice HUD — still untouched; next run is a reasonable
  candidate to spend its one copilot-track slot here if 2-3 solid
  non-copilot features aren't found first.

**CRITICAL discovery during Phase 5 (screenshot verification) — read
`.prism/audit_2026-08-10.md`'s last section before starting next run.**
While screenshotting the mobile Atlas panel fix, found a far more severe,
**pre-existing** mobile bug the mobile fix above does not (and structurally
cannot) address: below ~768px viewport width, the entire main-content
column collapses to a tiny fraction of the screen (measured 22px wide at a
390px phone viewport) — every tab, not just Atlas, renders as 1-2
characters per line and the app is unusable on a phone. Confirmed via a
clean worktree diff against the pre-this-run commit that this predates
this run entirely (present with or without any of this run's changes).
Diagnosed as far as: `stMainBlockContainer` itself is correctly full-width,
but its child `stVerticalBlock` (a Streamlit-internal emotion-cache class,
not Prism's own CSS) collapses following `content_width ≈ viewport_width −
368px` up to ~768px — consistent with something reserving the sidebar's
*expanded* width even while it's visually collapsed off-canvas. Forcing
`width:100% !important` on that element did not fix it (rules out a
simple flex-basis override), and no `calc()`/sidebar-width reference
exists anywhere in `modules/theme.py`, so this looks like a Streamlit
1.50.0 internal layout behavior rather than something Prism's own CSS
causes. **Not fixed this run** — root-causing an upstream-shaped layout
bug safely was judged too large/risky to land inside this run's budget
alongside the selected features (see the routine's own "be conservative
where damage is possible" guardrail). A repro/diagnostic script is saved
at `.prism/runs/2026-08-10/diagnose_mobile_width_bug.py` — **next run
should make this the #1 priority**, starting from the reproduction steps
listed in the audit file. This is a bigger interview-credibility risk than
any single missing feature: a "PWA" that's unreadable on an actual phone.

**TL;DR (5 lines):** Shipped Anomaly Narration (Gemini explains flagged
rows, agentic-theme pick, PII-safe, fingerprint-cached) and Data Quality
Scorecard (exportable A-F quality artifact), plus a mobile Atlas-panel CSS
fix and a `cffi` dev-dependency pin. 127/127 tests green (45 pytest + 82
eval), merged and pushed clean, fresh-clone boot verified. Discovered but
did NOT fix a much more severe pre-existing mobile layout bug (main
content collapses to ~22px wide below 768px) — documented in detail as
next run's top priority. `RUN_REPORT_2026-08-10.md` has full details.
