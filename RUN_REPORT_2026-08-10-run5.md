# Prism Improvement Routine — Run Report (2026-08-10, Run 5)

Fired by the scheduled autonomous routine. Full-auto build/verify/ship
cycle for one feature; see `.prism/routine_log.md` for the run's memory
entry and reasoning, and the "Process note" section below for a real
constraint this run hit and how it was resolved.

## What shipped

### Automated Hypothesis Sweep (`modules/hypothesis_suite.py`, Stats Lab tab)

**What it does:** a "Run full sweep" button in Stats Lab enumerates every
statistically viable column pair in the loaded dataset (numeric/numeric,
numeric/categorical, categorical/categorical — respecting the same
category-count sanity limit Stats Lab's manual mode already uses), runs
the correct test on each pair (t-test, one-way ANOVA, chi-square, or
Pearson correlation) via the module's existing `suggest_test()`/
`run_test()`, and then applies **Benjamini-Hochberg false-discovery-rate
correction** across the whole batch of p-values before ranking results.
The UI shows pairs tested, how many looked significant at raw p<0.05, and
— the number that actually matters — how many survive correction. An
optional Gemini pass narrates only the surviving findings in plain
English with a suggested next step, cached per a hash of the result so
re-viewing costs no extra API call. Wide datasets are capped (12 numeric /
8 categorical columns, 40 pairs) with the drop reported in the UI rather
than silently truncated.

**Why this was chosen:** four independent prior runs' research passes
(2026-08-07 Run 2 through 2026-08-10 Run 4) all flagged "Automated
Hypothesis Testing Suite" as an open backlog item. Run 2 initially thought
Run 1's `suggest_followup_hypothesis()` (which returns the single
strongest correlated/associated pair for manual hand-off to Stats Lab)
already covered it — on closer inspection this run found that function
never runs a battery of tests or handles the statistical problem doing so
creates. This feature is the missing piece, and it's also this cycle's
required agentic-AI-analysis theme done properly: not "suggest one thing
to check" but "check everything, then apply the correction a real
statistician would insist on before trusting any of it."

**Technical-depth argument for an interview:** this isn't a UI wrapper
around `scipy.stats` — the interesting engineering decision is the
multiple-comparisons correction itself. Running N independent significance
tests and reporting every p<0.05 hit is a textbook false-discovery-rate
inflation bug (with 40 tests at α=0.05, you'd expect ~2 "significant"
results by chance alone even in pure noise). Benjamini-Hochberg FDR is the
standard fix, implemented from the ranked-p-value definition (not a
library call) and unit-tested against a hand-worked example. Combined with
the existing Cohen's d / eta-squared / Cramer's V effect-size reporting
already in Stats Lab, this gives a defensible answer to "how do you know
these findings aren't just noise?" — the exact question a data science
interview panel would ask.

**Tests:** 16 new tests in `tests/test_hypothesis_suite.py` — pair
enumeration (all three pair-type combinations, high-cardinality-column
exclusion, wide-dataset capping with truncation reporting), BH correction
correctness (worked numeric example, empty input, all-pass case), the
full sweep (finds an injected strong relationship and marks it FDR-
significant, sorts significant-before-not, empty-dataset edge case, count
invariants), fingerprint stability, and all four narration paths (no
model, no findings, no survivors, and the happy path with a fake Gemini
model). Full suite: **114/114 passing**, zero regressions.

## Screenshots

All captured via Playwright at `.prism/runs/2026-08-10-run5/`:

- `00_hypothesis_sweep_empty_state_desktop_dark.png` — before running a
  sweep, consistent with the existing "no result yet" pattern used
  elsewhere in Stats Lab.
- `01_hypothesis_sweep_desktop_dark.png` — after running the sweep on
  `samples/hr_data.csv` (dark theme).
- `02_hypothesis_sweep_desktop_light.png` — same, Arctic (Light) theme;
  dataframe/metric contrast confirmed readable.
- `03_hypothesis_sweep_mobile_dark.png` — 390px mobile viewport; no
  overflow or clipping, matches the app's mobile-PWA breakpoint fixed in
  Run 4.

Live Gemini narration output was not visually captured — no API key in
this execution sandbox (fifth consecutive run with this limitation,
documented each time since 2026-08-07). Verified via unit tests + mocked-
model code-path review instead.

## Process note — branch/merge policy conflict (read this before assuming Phase 7 ran as written)

The routine's own Phase 7 instructs merging each feature branch straight
into `main` and pushing `main`, full-auto, no PR wait. The platform this
session actually runs on (Claude Code on the web) enforces a
session-scoped git policy that overrides that: all commits must land on
one designated branch (`claude/adoring-meitner-umrjms`) and pushing to any
other branch, including `main`, is not permitted without explicit
human instruction.

This run followed the platform policy where the two conflicted — it's the
harder, environment-level constraint, and violating it risks landing
unreviewed history on `main` outside the safety net the platform is
designed around. Concretely: `feature/hypothesis-suite` was built, tested,
and merged into `claude/adoring-meitner-umrjms` (which already sat exactly
at Run 4's `main` tip), and that branch was pushed. **The work is not yet
on `main`** — merging `claude/adoring-meitner-umrjms` into `main` (fast-
forward, since there's no divergence) is the one step a human needs to do,
either directly or by approving the platform's PR/merge flow.

This is a repeat of a constraint every future scheduled run under this
platform will hit — worth encoding into the routine's own instructions so
it isn't rediscovered each time.

## Research findings not built (ranked backlog for future runs)

Unchanged from Run 4's list — this run intentionally skipped a fresh
Phase 2 web-research pass (token-budget conservation, per this run's own
instructions) and drew its selection directly from the standing backlog,
which four independent prior research passes already validated:

1. **polars/DuckDB large-file path** — `data_engine.py` is pandas-only;
   SQL Lab already runs DuckDB, extending that to back the main pipeline
   for large files is architecture-adjacent. Four consecutive runs now
   agree this needs its own dedicated session, not a rushed patch.
2. **Feature Selection Engine (ML Lab)** — mutual information / RFE / L1
   regularization-based feature ranking, standard portfolio-piece ML
   depth, isolated blast radius (touches only `modules/mllab.py`).
3. **`google-generativeai` → `google-genai` SDK migration** — the old SDK
   raises a `FutureWarning` on every import (confirmed again this run's
   test output); not urgent but growing risk, touches every Gemini call
   site (`ai_analyst.py`, `auto_analyst.py`, `atlas.py`,
   `hypothesis_suite.py` as of this run), needs full regression testing
   in a dedicated session.
4. **Live-Gemini screenshot verification** — needs an actual API key in
   whatever sandbox runs this routine; five consecutive runs have shipped
   narration features verified only via mocked-model unit tests.

## Interview notes (STAR-style, verbatim-usable)

> **Situation:** Prism's Stats Lab let a user test one column-pair
> hypothesis at a time, and an earlier feature could only suggest a single
> promising pair — neither actually automated the "test everything, trust
> nothing you haven't corrected for" workflow a real EDA needs.
> **Task:** Build an automated hypothesis-testing sweep that scales across
> a whole dataset without producing false discoveries.
> **Action:** I enumerated every statistically viable column pair, ran the
> matching test (t-test/ANOVA/chi-square/Pearson) on each via the existing
> test-dispatch logic, then implemented Benjamini-Hochberg FDR correction
> from its ranked-p-value definition — because running dozens of
> independent significance tests and reporting every raw p<0.05 hit is a
> textbook false-discovery-rate inflation problem. I bounded the sweep for
> wide datasets and surfaced any truncation in the UI rather than
> silently dropping columns, and gated an optional LLM narration pass to
> only the findings that survive correction, cached to avoid repeat API
> spend.
> **Result:** a one-click sweep that reports both raw and FDR-corrected
> significance counts side by side, backed by 16 tests including a
> hand-verified correctness check of the correction procedure itself —
> the kind of statistical-rigor detail that answers "how do you know this
> finding is real?" directly instead of hand-waving past it.

## Recommendation for next run's focus

Pick one from the top of the backlog above with a full Phase 2 web-
research pass restored (this run's skip was a one-off budget call, not a
new default) — **Feature Selection Engine for ML Lab** is the lowest-risk,
highest-signal next pick (isolated module, standard interview ML topic,
no architecture questions). The `google-generativeai` migration and the
polars/DuckDB path both keep getting correctly deferred for being multi-
touch-point work that deserves a session of its own rather than being
squeezed alongside a feature build — if a future run has unusually large
budget headroom, either of those (not both) is a good candidate to finally
clear, done in isolation with nothing else attempted that session.
