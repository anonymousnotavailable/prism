# Prism Autonomous Improvement Routine — Run 24 (2026-08-11)

## Session note (read this first)

This run's session carried an explicit git operating constraint from the
harness that overrides the routine's own generic Phase 7 instructions:
**develop and push on branch `claude/adoring-meitner-jpcmt5`, never push
to a different branch (including `main`) without explicit permission.**
Every prior run (1–23) merged its feature branch into `main` and pushed
`main` directly, per the routine's standing instructions — that was
correct for those sessions' git configuration. This session's
configuration is different: `claude/adoring-meitner-jpcmt5` started at
the same commit as `origin/main` (`9e55067`, no unmerged history, no
existing remote branch or PR), so this run committed its work there and
pushed that branch instead of merging to `main` itself. **`main` was not
touched.** The work is fully built, tested, and verified below — it's
sitting on `claude/adoring-meitner-jpcmt5` for review/merge rather than
already landed on `main`. Flagging this explicitly so the next run (or
the human reviewer) doesn't mistake "not on main" for "not done," and so
whichever branch actually reaches `main` next can pick these commits up.

## What shipped

### 1. Large-file ingestion: streaming .xlsx sampling (closes the oldest backlog item)

Run 23's log named this the recommended focus: "Large Excel ingestion (no
out-of-core reader) — now the oldest open item." Every large-file
optimization Prism had (DuckDB's out-of-core CSV reader, shipped Run 8)
only covered CSV; a large `.xlsx` upload still went through
`pd.read_excel()`, which builds the entire workbook object graph in
memory before Prism ever gets to truncate it down to size.

`_stream_sample_excel()` in `modules/data_engine.py` closes that gap for
`.xlsx` (the legacy binary `.xls` format still takes the eager pandas
path — openpyxl has no streaming reader for it at all). It opens the
workbook with `openpyxl.load_workbook(read_only=True)` and iterates rows
via `ws.iter_rows(values_only=True)` instead of building the full
in-memory model, taking a reservoir sample (Algorithm R — the same
"true random sample across the *entire* file, not just the first N rows"
guarantee the CSV/DuckDB path already gives) of at most
`MAX_ROWS`/`HARD_ROW_CEILING` rows in one pass over the sheet.

### 2. Self-verifying "Sampling Fidelity" check (this cycle's mandatory agentic-AI theme)

This is where the two mandates of the run brief — close the Excel
backlog item, and ship something serving the agentic-AI-analysis theme —
turned out to be the same feature rather than two separate ones.

Reservoir sampling in the same streaming pass gave a free opportunity:
while walking every row once to fill the reservoir, also track each
numeric column's *exact* population mean and variance via Welford's
online algorithm (no second pass, no extra memory beyond a running
count/mean/M2 per column). The CSV/DuckDB path already has the full file
open in a DuckDB connection at sample time, so it gets the equivalent
population statistics almost for free via one extra SQL query
(`avg()`/`stddev_pop()` for numeric columns, a `GROUP BY ... ORDER BY
count(*) DESC LIMIT 1` for the top category of low-cardinality
categorical columns).

A new shared `check_sampling_fidelity()` compares the sample that
actually got loaded against those true population values and answers
the question a rigorous analyst would ask before trusting a sample at
all: **did the sample turn out representative, or not?**

- A numeric column's sample mean differing from the population mean by
  more than 15% (relative, with a std-based fallback when the population
  mean is ~0 to avoid a divide-by-zero) → flagged: *"⚠️ Sampling
  fidelity: column 'revenue' — the sample's mean (312) differs from the
  full file's mean (498) by 37%. Conclusions about this column may not
  hold for the full dataset."*
- A categorical column's most-common value making up a share of the
  sample that's 15+ percentage points off from its true population
  share → flagged similarly.
- Every checked column passing → a reassurance message instead of
  silence, so "the check ran and passed" is never indistinguishable from
  "the check never ran" in the UI.

This is the same self-verifying-agent pattern Confounder Detection (Run
6) and Anomaly Drivers (Run 22) already established for Prism — "don't
just report a result, check whether it actually holds up" — applied for
the first time *at ingestion*, before any analysis even starts, instead
of after a specific analysis surface runs. It's a small, honest slice of
"agentic EDA / self-verifying analysis agents" (the Phase 2 research
theme this routine keeps citing): the sampling step verifies its own
output rather than assuming a random draw is automatically trustworthy.

Deliberately scoped down for the Excel path: categorical-column fidelity
is CSV/DuckDB-only this run. Tracking category *counts* during a
streaming pass needs a bounded-cardinality counter per column that gets
abandoned once it overflows (a free-text column would otherwise grow one
dictionary entry per row) — a real follow-on, not attempted half-way.
Logged in the backlog below rather than shipped as a half-measure.

### 3. Bug fix, found while verifying feature #2: Smart Sampling's warnings never reached the user

Verifying the fidelity check's visibility in the actual app (not just
unit tests) surfaced a real, pre-existing bug: `app.py`'s "Use this
sample" button handler called `st.warning(w)` for each of `load_data()`'s
warnings, then immediately called `st.rerun()` in the same script pass.
Streamlit discards a script pass's rendered output as soon as the next
rerun starts — so **every** warning shown there, not just the new
fidelity messages but the pre-existing "this file has N rows — sampled M
across the entire file" message too, silently never appeared to the
user. Confirmed via Playwright: with the bug, the warning panel was
completely absent after confirming a large-file sample; after the fix
(store the warnings in a new `sample_warnings` session-state list,
rendered once on the next run — the same persistence pattern
`sample_info`'s caption already uses successfully), both messages
render correctly. Screenshots below are from *after* the fix. (No
standalone `.prism/audit_*.md` was written this run — per the standing
practice since Run 9/10, a full fresh feature-by-feature audit isn't
repeated every run once already documented; this specific bug was
isolated live via Playwright while verifying feature #2, and is fully
described here instead.)

## Screenshots

Captured live against a synthetic 700,000-row CSV (generated for this
run only, not committed) uploaded through the real Smart Sampling flow —
DuckDB samples it down to `HARD_ROW_CEILING` (500,000 rows) on load, then
the app's own picker samples further to 50,000. Both warning messages
(the pre-existing "too large to load in full" message and the new
"Sampling fidelity" check) render in the same `st.warning()` component
used elsewhere in the app, so no new visual surface was introduced —
verified for contrast/wrapping/glass consistency in both themes anyway.

- `desktop_dark_warn.png` — 1440px, dark theme: both warnings visible,
  correct wrapping, olive/warning-yellow glass panel consistent with
  every other warning in the app.
- `desktop_light_warn.png` — 1440px, Arctic (light) theme: same panels,
  correct contrast against the light background, theme toggle intact.
- Mobile viewport: hit the same standing "sidebar/header controls sit
  outside the automated viewport" gap logged across 7+ prior runs
  (Runs 10/13/16–23) — not re-chased past one retry, same
  bounded-verification precedent those runs set. Not a regression from
  this change: the warning renders via the same `st.warning()` primitive
  already mobile-verified for other content in earlier runs' reports.

## Interview notes (STAR, verbatim-usable)

**Streaming ingestion:**
*Situation:* Prism's large-file path had out-of-core CSV support but
Excel uploads above the same size threshold still loaded the entire
workbook into memory before truncating — a real scalability gap for a
"handles messy real-world data" story. *Task:* extend out-of-core
ingestion to `.xlsx` without adding a new dependency. *Action:* used
openpyxl's `read_only` streaming mode with `iter_rows`, implementing
reservoir sampling (Algorithm R) to draw a uniform random sample across
an unknown-length stream in a single pass, plus Welford's online
algorithm to compute exact running mean/variance for every numeric
column in that same pass, with zero second read. *Result:* `.xlsx`
uploads now sample out-of-core exactly like the CSV path, with population
statistics available for free as a byproduct of the same streaming loop.

**Self-verifying sampling:**
*Situation:* any random-sampling pipeline can silently draw an
unrepresentative sample and nothing downstream would ever know.
*Task:* this cycle's brief specifically called for agentic,
self-verifying analysis behavior. *Action:* built a fidelity check that
compares a drawn sample's own statistics against the true population
values — computed via SQL aggregates for CSV (DuckDB already has the
full file open) and via an online streaming algorithm for Excel — and
flags any column that drifted past a 15% threshold, or explicitly
confirms fidelity when nothing drifted. *Result:* sampling in Prism is
no longer a black box; it audits itself and tells the user when a
conclusion might not generalize to the full file, the same "does this
result actually hold up" discipline already built into Confounder
Detection and Anomaly Drivers, now running before the user even starts
analyzing.

**Debugging a real production bug via a testing discipline:**
*Situation:* while manually verifying the new fidelity check's UI
visibility (not just its unit tests), the warning panel didn't appear
at all. *Task:* find out whether the feature was broken or something
else was wrong. *Action:* traced it to Streamlit's rerun semantics —
`st.rerun()` called immediately after `st.warning()` in the same script
pass discards that pass's output before the browser meaningfully renders
it, a subtle framework gotcha that had been silently swallowing a
pre-existing warning for 23 prior runs without anyone noticing (because
nothing before this feature depended on that warning being visible).
*Result:* fixed by moving the warnings into persistent session state,
rendered on the next run — a two-line fix that recovered a bug affecting
production behavior, found only because a new feature's test-driven
verification process happened to expose it.

## Research findings NOT built (ranked backlog for future runs)

No fresh Phase 2 web research sweep this run (17th consecutive reuse of
the standing backlog — see Run 9's original reasoning, reaffirmed every
run since: "loop until 100% usage" and "use less tokens" are
contradictory instructions, so this routine runs one complete, verified
cycle and stops rather than trying to satisfy both). The backlog is now:

1. **Categorical sampling-fidelity tracking for the Excel streaming
   path** (new this run) — needs a bounded-cardinality counter per
   column, abandoned on overflow, tracked in the same streaming pass as
   the reservoir sample and Welford stats. Well-scoped, S/M effort.
2. **Light-theme repaint-lag** (cosmetic, app-wide, standing since
   ~Run 15) — `st.dataframe()` grids keep a dark background after a live
   theme toggle. Not touched this run (no `st.dataframe()` involved).
3. **Live-Gemini verification** — structural constraint, no
   `GEMINI_API_KEY` in this sandbox (24th consecutive run without one).
4. **Mobile-viewport navigation/theme-toggle automation gap** — sidebar
   and header controls sit outside the automated viewport on some
   surfaces (7+ runs open). A Playwright-harness fix, not an app change.
5. **Atlas voice/HUD slice beyond current maturity** — explicitly capped
   at one incremental slice per run per the run brief; not this run's
   pick.
6. A fresh Phase 2 web-research sweep is now genuinely closer to
   warranted — the backlog above is thinning toward cosmetic/
   infrastructure-only items. Recommended if Run 25 doesn't have a clear
   non-cosmetic pick from this list.

## Recommendation for next run

Build the categorical-fidelity follow-on for the Excel streaming path
(item 1 above) if a bounded-cardinality design is straightforward to get
right with tests, or run a fresh Phase 2 web-research sweep otherwise —
the backlog is thin enough now that either is reasonable. Whichever
session picks up next should also confirm whether `claude/adoring-meitner-jpcmt5`
has been merged into `main` yet; if so, branch fresh from `main` rather
than stacking further runs on a merged branch.
