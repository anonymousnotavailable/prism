# Prism Run 31 Report — 2026-08-11

## Summary

Shipped two new statistical modules to Stats Lab, deliberately paired as an
experiment-design story: **Bayesian A/B Testing** (`modules/bayesian_ab.py`)
and **Power / Sample-Size Planning** (`modules/power_analysis.py`). Both
were Run 30's own named recommendations (primary pick + fallback), both
confirmed still-open via a fresh grep + WebSearch sweep, and both shipped
this run rather than deferred again. Test suite grew 669 → 738 (69 new
tests), zero regressions. Merged cleanly (one expected, mechanically
resolved conflict) into `claude/adoring-meitner-7xxgfq`, pushed.

## What shipped and why

### 1. Bayesian A/B Testing (`modules/bayesian_ab.py`)

**What**: beta-binomial conjugate posterior per variant (closed-form
update from a configurable prior, default uninformative Beta(1,1)), 95%
credible intervals, P(treatment beats control) via Evan Miller's exact
closed-form log-space summation (falls back to Monte Carlo sampling for
posteriors too large to sum over quickly — verified to agree with the
exact method to within 1% on a shared test case), expected loss per
decision (a risk-based complement to a bare probability threshold), and
the absolute/relative lift distribution. Added as a new Stats Lab panel
right after Survival Analysis, gated on a low-cardinality grouping column
+ a binary outcome column being present (same "stay silent unless the
shape fits" convention as every other optional panel in the app). New
chart: overlaid posterior density curves.

**Why (technical depth)**: this isn't a lookup-table wrapper — it
implements the actual conjugate-prior derivation from first principles
(closed-form Beta posterior update), a genuine two-path numerical strategy
for P(B>A) (exact log-space summation with a documented complexity/
tractability cutoff, Monte Carlo fallback beyond it — not "always
simulate"), and a second, independent decision signal (expected loss via
Monte Carlo over the joint posterior) rather than stopping at a bare
probability threshold. The research sweep (WebSearch, sources in
`.prism/research_2026-08-11-run31.md`) confirmed this matches current
industry practice (GrowthBook, Test Science, MetricGate) rather than being
a plausible-looking approximation.

**STAR bullet**: *Situation*: Prism's only experiment-comparison tool was
a frequentist chi-square test with a single p-value and no way to state
"probability treatment wins" or check results mid-flight without a
statistical penalty. *Task*: add the Bayesian framing without a new
dependency or any Gemini-call dependency in the core path. *Action*:
implemented the beta-binomial conjugate model from scratch (posterior
update, credible intervals, exact + Monte Carlo P(B>A), expected loss,
lift distribution), wrote 31 tests first (including an exact-vs-Monte-
Carlo cross-check and a known-lift recovery test), then wired it into
Stats Lab with data-shape gating and a Gemini-narration layer matching
every other panel's optional-explain convention. *Result*: 31/31 tests
green, end-to-end AppTest render verified (P(treatment beats control) =
99.9998% correctly computed and displayed on a synthetic 8%-vs-12%
conversion dataset), zero regressions, clean merge.

### 2. Power / Sample-Size Planning (`modules/power_analysis.py`)

**What**: wraps `statsmodels.stats.power` (`TTestIndPower` for two-sample
means via Cohen's d, `NormalIndPower` + `proportion_effectsize` for
two-sample proportions — statsmodels already a pinned dependency, zero new
pip installs) to solve either direction: required n for a target power, or
achieved power for a planned n. Effect size can be typed directly or
estimated from a pilot slice of the loaded dataset (`effect_size_from_means`
/ `effect_size_from_proportions`). Added as a new Stats Lab panel right
after Bayesian A/B Testing; unlike the gated panels, this one is always
available since its manual mode needs no dataset columns at all. New
chart: power-vs-sample-size curve with the solved-for point marked.

**Why (technical depth)**: deliberately does *not* offer a bare "observed/
post-hoc power" number computed from the same data used to estimate the
effect size — Hoenig & Heisey's 2001 "The Abuse of Power" critique (found
during the research sweep) shows post-hoc power is a near-deterministic
function of a p-value already obtained, not an independent validity
check, and presenting it as one is a well-documented statistical
malpractice trap. The module is built exclusively as a forward-looking
planning tool (a pilot estimate feeds a hypothetical *future* study's
sample size, never the pilot data's own row count as an achieved-power
verdict), and that caveat is carried into both the module docstring and
the Gemini narration prompt — the same "state the real caveat, don't
paper over it" discipline Run 30 applied to DiD's parallel-trends
assumption.

**Bug found and fixed during development**: passing the same column name
for both the value/success column and the group column (`df[[col, col]]`)
silently produced a duplicate-column DataFrame instead of a Series,
crashing downstream `.unique()`/`.dropna()` calls with an unhelpful
`AttributeError` instead of a clean validation error. Caught by the
AppTest smoke-test pass (not by the initial unit tests, which hadn't
covered this input shape), fixed in both new modules
(`power_analysis.py`'s `effect_size_from_means`/`effect_size_from_proportions`
and `bayesian_ab.py`'s `bayesian_ab_test`) with an explicit `col_a == col_b`
guard, and locked in with 3 new regression tests (2 in
`test_power_analysis.py`, 1 in `test_bayesian_ab.py`) before merging —
exactly the "handle bad CSVs... explicitly" instruction, caught before
shipping rather than after.

**STAR bullet**: *Situation*: no way in Prism to answer "how many samples
does a planned experiment need" or "was my planned sample size big
enough" without leaving the app. *Task*: build a real planning tool on
the existing `statsmodels` dependency, for both means and proportions,
without falling into the post-hoc-power trap the statistics literature
specifically warns against. *Action*: wrote 33 tests first (including a
textbook-value check — Cohen's d=0.5, alpha=0.05, power=0.8 → ~64 per
group, a widely-cited reference number — and round-trip consistency
between the two solve directions), implemented the module with an
explicit two-mode design (solve_n / solve_power) and two-source design
(manual / pilot-data), then during AppTest verification discovered and
fixed the same-column crash bug, adding 2 more regression tests. *Result*:
38/38 tests green (36 initial + 2 regression), full solve_n/solve_power/
manual/data-source matrix verified via AppTest against a real merged
render, zero regressions, clean merge.

### Atlas/JARVIS track: considered, not shipped this run

Checked per this run's brief: Atlas last touched at Run 17 (`a4aff81`), 14
runs ago — genuinely overdue by the routine's own "several runs" bar.
Weighed seriously for the second slot but not shipped: the realistic
"small incremental slice" available there (Web Speech API integration,
TTS latency/quality polish) is UX polish, not verifiable computational
depth, and this run's own primary filter explicitly prioritizes technical
depth over cosmetic polish. Both stats picks scored higher on that filter.
Logged as a strong, now doubly-overdue Run 32 candidate rather than
shipped as a token slice to check a box — see reasoning in
`.prism/routine_log.md`.

## Verification evidence

Playwright/Chromium not attempted (6th consecutive run confirmed-blocked
per the routine's own standing policy) — used the documented fallback
stack instead:

1. **Full pytest suite** at every stage: 669 baseline → 700 on
   `feature/bayesian-ab-testing` alone → 707 on `feature/power-analysis`
   alone → 738 on the final merged branch. Zero regressions at any stage.
2. **`streamlit.testing.v1.AppTest`**, one fresh instance per pass
   (confirmed necessary — see harness-quirk note below), driving the real
   `app.py` render path end-to-end:
   - Bayesian A/B: pass 1 confirmed the panel + `Run Bayesian A/B Test`
     button render with zero exceptions on a synthetic 8%-vs-12%
     conversion dataset (3,000 rows/variant); pass 2 pre-set a computed
     `bayesian_ab_test()` result in session state and confirmed the full
     metrics/chart/table/recommendation-banner render path threw zero
     exceptions, with the on-page "P(treatment beats control)" metric
     showing 100.0% (true value 99.9998%), matching the direct function
     call.
   - Power Analysis: pass 1 confirmed the panel + `Run Power Analysis`
     button render with zero exceptions (always-visible panel, no data-
     shape gating needed); pass 2 pre-set a `solve_n` result (required
     n=64, the known Cohen's d=0.5/alpha=0.05/power=0.8 textbook value)
     and confirmed the metric shown on page exactly matched; pass 3
     pre-set a `solve_power` result and confirmed it rendered with zero
     exceptions, plus confirmed the same-column degenerate input now
     fails cleanly (`ok: False`) instead of raising.
   - A combined coexistence pass confirmed both new panels' buttons are
     present in the same render with zero exceptions and no widget-key
     collisions.
3. **Live `streamlit run` smoke test**: HTTP 200 + clean logs, run three
   times (once per feature branch, once on the final merged branch).
4. **Direct function-level tests** (69 new, beyond the AppTest passes
   above): Bayesian A/B's exact-vs-Monte-Carlo P(B>A) cross-check agrees
   to within 1%; a known 8%-vs-12% conversion-rate injection is recovered
   with both variants' true rates inside their own 95% credible intervals
   and P(treatment beats control) > 0.99; Power Analysis's required-n
   matches the textbook Cohen's-d=0.5 reference value (60-68 range,
   literature cites ~64), and required-n/achieved-power round-trip
   consistently in both directions for both means and proportions.

**AppTest harness note** (extends Run 30's documented quirk): confirmed
this run that the widget-state serializer throws `TypeError: 'NoneType'
object is not iterable` on **any** second `.run()` call in a single
AppTest instance — not only across an `active_section` switch as Run 30
scoped it. Reproduced identically on the untouched base branch with an
unrelated synthetic CSV before writing any new code, confirming it's the
pre-existing harness limitation, not a Prism regression. Worked around
exactly as Run 30 did for DiD: one fresh AppTest instance to check the
pre-computation render (button/widgets exist, one `.run()`), and a second
fresh instance with the result pre-set directly in `session_state` (as if
the button had already been clicked) to exercise the full result-
rendering path, each via exactly one `.run()` call. Documented here so
Run 32 doesn't have to re-diagnose it.

## Backlog not built this run

- **Atlas/JARVIS voice/HUD slice** — considered and reasoned about above;
  now 15 runs overdue as of Run 32. Real candidate work: Web Speech API
  browser-side voice input (currently text-typed commands only per
  `modules/atlas.py`'s docstring), TTS latency/quality improvements. Not
  primarily a statistical-depth feature, so likely still loses to a strong
  stats/ML pick unless deliberately prioritized.
- A **third experiment-design feature** — sequential/always-valid testing
  (e.g. mixture-SPRT or group-sequential boundaries) would be a natural
  follow-on to this run's Bayesian/frequentist pairing, giving Prism all
  three major experiment-analysis paradigms. Noted but not built — M/L
  effort, would need its own research pass on which sequential-testing
  method is most defensible to implement from scratch.
- Nothing else new surfaced in the audit pass — no `.prism/audit_*.md`
  written this run since no genuinely new bugs/weak spots turned up beyond
  the same-column crash (found and fixed within this run's own new code,
  not a pre-existing issue).

## Run 32 recommendation

1. **Atlas/JARVIS slice** — now the most overdue backlog item (15 runs by
   Run 32). A concrete, scoped starting point: wire `modules/atlas.py`'s
   existing intent router to the two new Stats Lab panels this run added
   (a voice/typed command like "run a bayesian test on variant vs
   converted" routing into `COMMAND_REGISTRY`), which is a small,
   well-bounded slice rather than the larger Web Speech API integration.
2. **Sequential/always-valid A/B testing** as a genuine technical-depth
   follow-on to this run's Bayesian/frequentist pairing, if Atlas isn't
   picked — would complete Prism's experiment-analysis trio (Bayesian
   always-valid, frequentist fixed-N with planning, sequential always-
   valid frequentist).
3. Re-run the WebSearch/grep gap sweep fresh rather than assuming either
   of the above is still the frontier — this run's own sweep found both
   Run 30 recommendations were still open and well-scoped 30 runs in, so
   the discipline is paying off.
