# Prism Autonomous Improvement — Run 33 (2026-08-11)

## Summary

Shipped two new statistical modules — **Changepoint Detection** and **Granger Causality**, both
wired into the Forecasting tab — plus one Phase-1-audit bugfix (Text Analytics unreachable when
`testable_cols < 2`, folded into the changepoint branch). Test suite: **788 → 831** (43 new tests),
zero regressions. Both feature branches merged `--no-ff` into `claude/adoring-meitner-7xxgfq` and
pushed.

## Bug fix (Phase 1 audit)

**Stats Lab: Text Analytics panel unreachable when `testable_cols < 2`.** Flagged by Run 32's own
backlog note and re-confirmed at the start of this run: the entire Stats Lab section — including
Text Analytics — was nested inside `if len(testable_cols) < 2: <empty state> else: <everything>`,
where `testable_cols` counts only numeric/categorical columns. Text Analytics reads a free-text
column via NLP, not numeric/categorical values, so a dataset with 1 testable column plus a
perfectly good text column could never reach it. Fixed by moving the Text Analytics block to its
own independent `text_analytics.eligible_text_columns()`-gated block at the section level (`app.py`
lines ~4835 onward), one indent level out of the `else`. Left Bayesian A/B / Power Analysis /
Survival Analysis inside the gate — they legitimately need numeric/categorical columns, unlike Text
Analytics. Verified via AppTest with a synthetic 1-numeric-column + 1-text-column dataset: the panel
now renders, and the two-column hypothesis-test picker still correctly shows its own "not enough
columns" empty state independently.

## Feature 1: Changepoint Detection

**What**: `modules/changepoint.py` — binary segmentation over a normalized CUSUM (cumulative sum)
statistic to find points where a numeric series' *level* abruptly shifted, distinct from
`forecasting.py`'s STL decomposition which explains smooth trend/seasonal movement. No `ruptures`
dependency (confirmed not installed, and the app's 32-run track record avoids new pip deps when a
solid local-compute alternative exists) — pure numpy/pandas, the tractable-to-verify textbook
sibling of PELT (same "recursively split on the strongest candidate break" idea `ruptures` itself
calls `Binseg`, minus PELT's pruning optimization, which is a performance concern this app's row
counts don't need).

**Technical depth**:
- `cusum_stat()`: the classic Page (1954) CUSUM statistic — cumulative sum of demeaned values,
  normalized by `sigma * sqrt(n)`, with the argmax location as the most likely single changepoint
  in a segment.
- `detect_changepoints()`: recursive binary segmentation via a max-heap over candidate segments
  (ranked by CUSUM statistic magnitude, so the most obvious break in the whole series is tested —
  and confirmed or discarded — before weaker candidates are even considered). Each candidate split
  is confirmed via a **permutation test** (reshuffle the segment, recompute the statistic, see how
  often a random reshuffle is at least as extreme) rather than an asymptotic threshold that assumes
  a particular noise distribution.
- **Two real correctness bugs found and fixed during TDD, before any UI work**:
  1. An unrestricted argmax search let a segment's "best" split land 1–2 points from its own edge,
     which the next recursion would then "confirm" as a spurious tiny extra changepoint. Fixed with
     `_cusum_stat_restricted()`, which only searches interior split points that leave
     `min_segment_size` points on each side.
  2. Naive binary segmentation recursively re-tests every accepted split's two halves, which —
     left uncorrected — compounds the overall false-positive rate across the whole recursion tree
     (the same "many implicit comparisons" problem `hypothesis_sweep.py` already corrects for with
     Benjamini-Hochberg across its *flat* set of tests; here the tests form a tree instead). Fixed
     with a Bonferroni-style correction keyed to the tree's worst-case depth
     (`log2(n / min_segment_size)`), documented in the module docstring and applied to the
     acceptance threshold while still reporting each split's raw permutation p-value for
     transparency.
- Explicitly documents CUSUM's real limitation (detects shifts in a series that's stationary
  *between* breaks; a strongly trending series with no real regime change can itself trip a false
  positive) — same "state the assumption, don't pretend it doesn't exist" convention as
  `did.py`'s pre-trends caveat and `power_analysis.py`'s post-hoc-power caveat.

**Placement**: Forecasting tab, immediately after STL Decomposition, reusing the existing
datetime/numeric column pickers and `forecasting.prepare_series()` output — no new selectors
needed, matching Run 32's own recommendation for where this should live.

**STAR**: *Situation* — Run 32's backlog flagged changepoint detection as a confirmed, zero-hit gap
after a full grep sweep, and this run's own fresh sweep re-confirmed it. *Task* — implement it
without adding a new pip dependency, matching the app's established footprint discipline.
*Action* — wrote 22 tests first (TDD) covering single/multiple/no-shift detection, NaN handling,
non-numeric rejection, the `max_changepoints` cap, verdict text, chart shapes, and narration; caught
and fixed the edge-artifact and compounding-false-positive bugs above purely from test failures
before writing a line of UI code; wired into the Forecasting tab; verified end-to-end via 3 AppTest
passes against the real `app.py`. *Result* — a statistically rigorous panel (documented, tested
correction for a real algorithmic pitfall most from-scratch binary-segmentation implementations
miss) shipped with zero new dependencies and zero regressions.

## Feature 2: Granger Causality

**What**: `modules/granger_causality.py` — does one numeric time series' past help predict
another's future, beyond what that series' own past already explains? The time-series-precedence
sibling of `causal_inference.py`'s cross-sectional propensity-score matching and `did.py`'s
before/after panel comparison. Identified via a fresh, broader gap sweep this run (not carried over
from a prior backlog note) — confirmed zero hits for `granger|adfuller|kpss|stationarity|
autocorrelation|acf|pacf` across the whole `modules/` tree despite `statsmodels` already being a
pinned dependency.

**Technical depth** (light WebSearch sanity check confirmed each step against current best
practice before implementing):
- `prepare_pair()`: aligns two numeric columns onto a shared, regularly-spaced datetime axis
  (duplicate timestamps averaged, gaps linearly interpolated) — same regularization idea as
  `forecasting.prepare_series()`, extended to a column pair so both stay index-aligned.
- `difference_until_stationary()`: Augmented Dickey-Fuller-driven auto-differencing, capped at 2 —
  testing Granger causality on non-stationary series is a textbook way to get spurious
  "significant" results driven by shared trends rather than real predictive information. Both
  series are differenced by whichever order the more-persistent one needed, so they stay aligned
  and directly comparable.
- Lag order chosen via `statsmodels.tsa.api.VAR.select_order()`'s AIC-minimizing pick on the
  two-variable system — not guessed, and not p-hacked by trying every lag until one looks
  significant.
- `statsmodels.tsa.stattools.grangercausalitytests` run in **both directions** (X→Y and Y→X) at
  the selected lag, since Granger causality is not symmetric and a detected feedback loop (both
  directions significant) is itself a distinct, informative finding — not just a nice-to-have.
- Handles the `verbose` deprecation FutureWarning in statsmodels 0.14.6 by suppressing it inside a
  scoped `warnings.catch_warnings()` block rather than letting it leak into the app's log output.
- **Naming bug caught during TDD**: the main entry point was originally named `test_granger_
  causality`, which pytest tried to collect as a zero-argument test function the moment it was
  imported into the test module's namespace (`from modules.granger_causality import
  test_granger_causality` shadows the real signature). Renamed to `run_granger_causality` before
  it ever reached a commit.
- Every result and verdict explicitly frames the finding as *predictive precedence, not proof of a
  true causal mechanism* — the single most-repeated caveat across every source checked, and the
  same "state the assumption" convention `causal_inference.py` and `did.py` already follow.

**Placement**: Forecasting tab, after Changepoint Detection, with its own "Potential cause (X)" /
"Effect (Y)" column pickers (gated on 2+ numeric columns, unlike the single-target panels above it)
— chosen over Overview (next to PSM/DiD) because it needs a regular datetime axis the way
STL/backtest do, not just a binary treatment column.

**STAR**: *Situation* — this run's second slot needed a fresh gap sweep since the app's stats/ML
surface (PCA, RFM, PSM, DiD, ensemble anomaly detection, SHAP, conformal prediction, survival
analysis, Bayesian A/B, power analysis, text analytics — all already shipped) left few obvious gaps.
*Task* — find and validate a second genuinely-open, technically substantive pick. *Action* — grepped
broadly, found Granger causality as a zero-hit gap, WebSearch-verified the ADF-stationarity /
AIC-lag-selection / bidirectional-test pipeline against current best practice before writing any
code, TDD'd 21 tests including an injected lag-1 relationship (forward significant, reverse not) and
a non-stationary random-walk pair (relationship only surfaces after auto-differencing), caught the
`test_` naming collision before it became a real bug. *Result* — a second real econometric technique
shipped alongside changepoint detection, same zero-new-dependency, zero-regression bar.

## Verification evidence

- Full pytest suite: 788 (start) → 810 (after changepoint) → 831 (after Granger causality), zero
  regressions at every stage.
- `python3 -c "import ast; ast.parse(...)"` syntax check after every `app.py` edit.
- Live `streamlit run app.py` smoke test on each feature branch: HTTP 200, clean logs, no
  exceptions.
- `streamlit.testing.v1.AppTest`, one fresh instance per scenario, **exactly one `.run()` call
  each** — reconfirmed this run (before writing any new code, on the untouched base branch) that a
  *second* `.run()` on any single AppTest instance throws `TypeError: 'NoneType' object is not
  iterable` on an unrelated widget, extending Run 30/31/32's documented harness quirk. Worked around
  by pre-seeding `session_state` with a precomputed result (bypassing the button click entirely for
  the "full render" scenarios) instead of chaining `.click().run()` sequences:
  - Changepoint Detection: 3 passes (panel renders with zero exceptions; full
    verdict+chart+table render with a precomputed 1-shift result exactly matching the injected
    synthetic step function; tiny-dataset graceful render below the forecast minimum-history bar).
  - Granger Causality: 3 passes (panel renders with zero exceptions; full verdict+metrics+chart
    render with a precomputed forward-significant/reverse-not result; single-numeric-column
    dataset gracefully hides the panel with zero exceptions).
  - Text Analytics bugfix: 1 pass confirming the panel renders with only 1 numeric column present
    while the two-column hypothesis-test picker independently shows its own empty state.
  - Re-ran the Changepoint AppTest passes again after Granger Causality was added, confirming no
    interaction between the two new panels sharing the same Forecasting tab.
- Playwright/Chromium **not retried** — 8th consecutive confirmed-blocked run per sandbox egress
  policy; documented per the brief's fallback instructions rather than attempted and failed again.

## Backlog not built this run

- **Web Speech API voice-quality/latency polish for Atlas** — still the standing recommendation
  from Runs 31/32; neither of this run's two picks had an obvious "run the last thing" auto-fill
  shape for the intent router the way Bayesian A/B / Power Analysis did, so Atlas was left alone
  again rather than bolted on as an afterthought. Now 16 runs since its last substantive touch
  (Run 17) if you don't count Run 32's stats-panel wiring slice.
- **Multivariate / panel-data changepoint detection** — this run's implementation is univariate
  (one series at a time); detecting a *shared* changepoint across several correlated metrics at
  once (e.g. every product line's revenue stepping at the same date) is a natural, meaningfully
  harder follow-on, not attempted here.
- **Granger causality on more than 2 series at once** (a full VAR-based multivariate Granger test,
  or Granger causality graphs à la the arXiv sources checked during research) — deliberately scoped
  to the pairwise case for this run; a genuine larger follow-on if there's demand.

## Run 34 recommendation

1. **Atlas / JARVIS voice-quality track** — genuinely the most overdue item in the backlog at this
   point (16 runs since Run 17's last real slice, only touched incidentally at Run 32). A dedicated
   run focused on Web Speech API latency/quality and the animated HUD styling explicitly deferred
   twice now would close a real gap rather than adding a fifth/sixth stats module to an already very
   wide surface.
2. If another stats/ML slot is picked instead: multivariate changepoint detection (shared
   structural breaks across several correlated series) is the most natural, still-tractable
   extension of this run's `modules/changepoint.py`, and would reuse most of its machinery.
3. The app's stats/ML surface is now wide enough that Run 34's Phase 2 research should lean harder
   toward a genuinely fresh sweep (not assuming remaining backlog notes are still the best
   available picks) — most "obvious" ideas checked this run turned out to already be shipped.
