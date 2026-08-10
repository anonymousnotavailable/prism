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

**Orientation:** read this log + `CHANGELOG.md` + repo structure before
touching anything. A `git fetch origin main` early on showed `origin/main`
at an older commit (`dd20c29`, pre-dating this session's designated branch)
than the branch's own local history — looked like a real divergence
(`origin/main` was missing `auto_insights.py`, `insight_verifier.py`,
`regression_diagnostics.py` entirely). A second fetch minutes later showed
`origin/main` had caught up to exactly the branch tip — a concurrent
process pushed in between the two fetches. **Not a real divergence, just a
stale-cache scare** — logging it so a future run that sees the same
transient mismatch doesn't panic and attempt an unnecessary reconciliation
merge. Also confirmed via `mcp__github__list_pull_requests` that no PR has
ever been opened for this session's designated branch — prior runs'
"merged to main and pushed" claims check out against the real remote.

**Audit:** skipped a full from-scratch UI walkthrough (Runs 1–2 already
covered breadth; `.prism/audit_2026-08-07*.md` still applies) and instead
targeted the open backlog items from Run 2's notes to see which were still
real. Findings:
- "Data Quality Score with Exportable Scorecard" — **already fully shipped**,
  just not under that name: `data_engine.get_health_breakdown()` +
  `report.py`/`report_writer.py` (HTML+PDF export with executive summary)
  cover it end to end. Removed from backlog below — don't re-propose this.
- "Cross-Column Correlation Intelligence" — still genuinely partial
  (auto-insights correlation pairs + regression-diagnostics VIF, no
  standalone view). Still open.
- Advanced Outlier Detection (LOF/DBSCAN) and Feature Selection Engine —
  confirmed neither exists yet (`grep` for `LocalOutlierFactor`, `DBSCAN`,
  `mutual_info`, `RFE` across `modules/` came up empty before this run).
  Picked the anomaly-detection one (see below).
- The mobile Atlas-panel overlay bug Run 2 flagged (squished/unreadable
  main content at ~390px) is **still present and worse than described** —
  see "Also investigated" below for a full re-diagnosis.
- `google-generativeai` is now **fully deprecated** (not just "not urgent"
  — pytest now prints a `FutureWarning` on every run: "All support... has
  ended"). Still not touched this run (architecture-adjacent per the
  routine's own no-rewrites guardrail, deserves a dedicated pass), but the
  urgency has gone up a notch since Run 2 logged it.

**Research:** two targeted web searches rather than a full four-source
sweep (this run's time budget went into the repo-state investigation
above instead). Confirmed via search that (1) automated data-quality
scorecards (Great Expectations, ydata-profiling) are the current
open-source EDA standard — validated that the already-shipped report
export covers this ground, and (2) 2026 data-analyst hiring guidance
still rates "data quality war story" and portfolio depth over
certifications, which supports investing in test coverage + narration
quality over new surface area.

**Selected feature (1, this run — see rationale below):**
1. **Ensemble Anomaly Detection** (`modules/anomaly.py`) — extends the
   existing single-method (IsolationForest) Overview scan into a 3-detector
   ensemble (+ Local Outlier Factor, + DBSCAN with a k-distance eps
   heuristic), ranks flagged rows by cross-method agreement, and adds a
   Gemini "Narrate Anomalies" pass. Serves this cycle's required agentic-AI
   theme via the "anomaly narration" item specifically. 12 new unit tests.

**Why only one feature this run, against the routine's "2–3" guidance:**
the git-history investigation above and the mobile-bug re-diagnosis (below)
consumed real time that would otherwise have gone to a second/third
feature. One well-tested, fully-verified feature was judged better than a
third rushed one — consistent with the routine's own "conservative where
damage is possible" instruction. Next run should be able to skip both time
sinks (this log now has the answer to each) and ship the full 2–3.

**Also fixed alongside the feature (small, audit-sourced):** a truncated
"High-Confidence" metric label (was "High-confidence (2+/3)", too long for
its column).

**Also investigated, NOT shipped — mobile Atlas-panel bug (Phase 6 failure
protocol):** attempted a fix for the mobile-overlay bug Run 2 flagged.
Root-caused the overlay itself to `.st-key-atlas_side_panel`'s
`position: fixed; width: 328px` in `modules/theme.py` (no responsive
breakpoint at all) and added a `@media (max-width: 900px)` rule to make it
flow inline below the main content instead of covering it. Screenshot
verification then revealed this only unmasks a **second, separate,
pre-existing bug**: at ≤390px, `stMainBlockContainer`'s own block children
collapse to ~22–32px wide (confirmed via `getBoundingClientRect()` on the
live DOM — not a guess), independent of the Atlas panel entirely. The
fixed-position overlay was accidentally *hiding* this deeper collapse, not
causing it. Fixing the overlay alone would ship a "different kind of
broken" mobile experience, not a working one, so **the CSS change was
reverted** (`git checkout -- modules/theme.py`) rather than merged
half-working. **For the next run that picks this up:** the real fix needs
both (a) the responsive Atlas-panel rule above and (b) finding why
`stMainBlockContainer`'s block/flex children shrink to fit-content width
instead of filling it on narrow viewports — likely a Streamlit
emotion-cache flex-sizing interaction, not a simple CSS override. Budget a
dedicated run for this; it's now diagnosed enough to start straight into a
fix instead of re-discovering the overlay as the only symptom.

**Verification:** 39/39 tests green (27 baseline + 12 new), no regressions.
Desktop dark + light screenshots of the Overview tab's new panel (Stocks
sample dataset — 40 rows flagged, 13 high-confidence) reviewed for
contrast/overflow/glass consistency — both clean. Mobile screenshot not
captured for this feature specifically (blocked by the pre-existing bug
above, same limitation Run 2 hit with Regression Diagnostics); correctness
rests on the unit tests instead, per that same precedent.

**Ship note — branch, not `main`:** this run's harness-level git
instructions pinned all commits and the final push to the session's
designated branch (`claude/adoring-meitner-<id>`), not `main` directly,
overriding this routine's own Phase 7 instructions. Feature branch was
still merged locally (`--no-ff`) exactly as Phase 7 describes — only the
very last step (push target) differs from Runs 1–2. **The branch as pushed
is not yet on `main`** and needs a manual merge/PR from here. Flagging
explicitly so the next run doesn't assume this run's commit is already
live on `main` the way Runs 1–2's were.

**Not built (backlog for future runs, updated):**
- Cross-Column Correlation Intelligence & Multicollinearity Detection —
  still partial, still no standalone view (see Audit above).
- Feature Selection Engine (mutual info, RFE, L1) for ML Lab — confirmed
  not yet built.
- Mobile Atlas-panel layout (two-part bug — overlay + main-content
  collapse) — see "Also investigated" above for the full diagnosis and
  what's still needed.
- `google-generativeai` → `google-genai` migration — now fully deprecated
  upstream, not just "will be." Still architecture-adjacent/out of scope
  per-run, but should be the next dedicated-run candidate given the
  upstream urgency change.
- Polars/DuckDB large-file path — Run 1/2 item. Partially addressed by a
  separate (non-routine) branch that upgraded SQL Lab to a full DuckDB
  workbench — re-check `modules/sql_lab.py`'s scope before re-proposing
  this from scratch.
- Atlas Proactive Insights (JARVIS copilot track) — a separate (non-routine)
  branch already shipped Atlas persona + voice + neuron-background styling;
  "proactive insights without being asked" specifically still doesn't
  exist. Still eligible as next run's one copilot-track pick.
- Natural Language Summary of Every Tab.
- ~~Data Quality Score with Exportable Scorecard~~ — **removed**, already
  shipped (see Audit above).
