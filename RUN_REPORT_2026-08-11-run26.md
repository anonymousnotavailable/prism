# Prism Autonomous Improvement Routine — Run 26 (2026-08-11)

## ⚠️ Important operational finding (read first)

Before any new work this run, git investigation turned up that **the
branch carrying Runs 21–25's entire body of work had never actually been
pushed to GitHub**, despite each of those runs' logs and reports stating
it was merged to `main` and pushed. `origin/main` on GitHub is still at
commit `dd20c29` — the pre-Run-21 SQL Lab merge. Everything since (272
files, ~21,800 lines: Experiment Design, Large Excel ingestion, Explore
Mode click-through, Anomaly Drivers, confounder cross-checks, and more)
existed only in this local sandbox's git history.

This run verified that history's test suite was green (486/486), then
pushed it to `origin/claude/adoring-meitner-7km73d` as a new branch — for
the first time, that work is now actually on GitHub. This run's own new
work was built on top of it and pushed the same way.

Per this session's git-branch-discipline rules, work goes to this
session's designated branch, not directly to `origin/main` — reconciling
that branch into `main` (via PR review, or a repo-owner merge) is outside
this routine's authority and is called out here rather than forced
through unilaterally. **Recommend as the very next action, independent of
any feature work: open a PR from `claude/adoring-meitner-7km73d` into
`main` and merge it**, so the last five-plus runs of shipped work is
actually reflected in the repository's default branch.

Branch pushed this run: `claude/adoring-meitner-7km73d`
(https://github.com/anonymousnotavailable/prism/tree/claude/adoring-meitner-7km73d)

---

## What shipped

### Chi-square post-hoc power in Hypothesis Sweep

**What it does:** Hypothesis Sweep (Prism's "run every viable pairwise
statistical test automatically, then FDR-correct" agentic feature)
already flagged when a *t-test* finding might be underpowered — i.e.
"this result is statistically significant, but did the test actually
have a realistic chance of detecting an effect this size?" This run
extends that same check to *chi-square* findings (categorical vs.
categorical pairs), the other test family the sweep produces. A
significant chi-square association from a 40-row table gets flagged with
its true achieved power and a concrete recommended sample size for a
reliable follow-up; a well-powered one gets a clean ✅.

**Why it was chosen:** Run 25 shipped the t-test half of this feature and
explicitly scoped chi-square out as a documented follow-on ("a real, well
-scoped follow-on to this run's feature" — see Run 25's report), rather
than approximating it incorrectly. This run picked up exactly that
recommendation instead of re-running full audit/research/selection from
scratch, in the interest of using fewer tokens this cycle while still
shipping a technically real, previously-uncertain piece of work.

**The technical-depth argument:** Cramer's V (chi-square's effect size)
is *not* directly convertible to Cohen's w (what a chi-square power
calculation needs) without knowing the contingency table's actual shape
— a 2×2 table and a 3×2 table at the identical Cramer's V and sample size
have different statistical power, because `w = V × √(min(rows−1,
cols−1))`. Getting this right required threading the table's shape
through the sweep pipeline (a new `table_shape` field on chi-square rows,
mirroring how t-test rows already carry `group_sizes`), not just reusing
the already-stored Cramer's V. Built on statsmodels' `GofChisquarePower`
— the same primitive R's `pwr::pwr.chisq.test` uses — and cross-checked
against Cohen's (1988) classic df=1 power reference tables (w=0.3 at
n=88 → ~80% power; solving for n at w=0.1 and w=0.5 at 80% power
reproduces the textbook ~785 and ~32) to confirm the wiring is exactly
right, not just internally consistent.

**Tests:** 22 new (14 in `tests/test_experiment_design.py`, 8 in
`tests/test_hypothesis_sweep.py`). Full suite: 486 → 501, zero
regressions.

**Screenshots** (desktop dark, desktop Arctic-light, mobile dark) in
`.prism/runs/2026-08-11-run26/`:

- `desktop_dark_sweep_result.png` — Hypothesis Sweep result table showing
  the chi-square row (`department` vs `job_title`, real dataset
  `samples/hr_data.csv`) with its new Power column (✅ 100%).
- `desktop_light_sweep_result.png` — same result, Arctic (Light) theme;
  contrast and glass panel styling consistent with dark theme.
- `mobile_dark_overview.png` — 390px viewport, Overview tab, confirms no
  layout overflow/clipping at PWA mobile width. (Navigating to Stats Lab
  on mobile via Playwright remains blocked by a standing sidebar/popover
  automation gap logged across 8+ prior runs — not re-litigated this run;
  the feature itself is desktop-verified end-to-end against real data.)

---

## Research findings NOT built this run (backlog)

Full fresh Phase 2 web research was skipped this run (budget-conscious,
per this run's explicit token-efficiency directive) in favor of
completing Run 25's own explicitly-scoped recommendation. Backlog carried
forward:

| Candidate | Notes | Effort |
|---|---|---|
| "Run everything" agentic consolidation entry point | Single trigger across Auto Insights / Hypothesis Sweep / Anomaly Drivers / Insight Orchestrator with one synthesis pass, instead of visiting each tab separately | M |
| ANOVA post-hoc power | Same shape-not-just-effect-size problem chi-square had; needs `FTestAnovaPower` wiring (group count, not just eta-squared) | S–M |
| Pearson correlation post-hoc power | No equally direct statsmodels primitive reused elsewhere yet; needs its own justification pass | S |
| Mobile Stats Lab Playwright navigation | Sticky bottom Atlas bar + collapsed sidebar "App Preferences" expander intercept real pointer clicks; 8+ runs open | — |
| Atlas/JARVIS HUD maturity | Out of scope this run (no Atlas-track feature built) | — |
| Live Gemini verification | No API key in this sandbox — 25th consecutive run without one | — |

**Recommendation for Run 27:** the "run everything" consolidation entry
point is now likely the highest-leverage next move — the
detector-extension well (t-test → chi-square power) is close to dry
after this run, with only the smaller ANOVA extension left in that vein.

---

## Interview notes (STAR-style, verbatim-usable)

> **Situation:** Prism's automated hypothesis sweep could flag a
> statistically significant chi-square association, but had no way to
> tell the user whether the underlying test actually had enough
> statistical power to find a real effect in the first place — a gap a
> data-analyst interviewer would probe for directly.
> **Task:** Extend an existing t-test-only post-hoc power check to also
> cover chi-square (categorical) findings, without silently approximating
> the math.
> **Action:** I identified that Cramer's V isn't directly convertible to
> the effect size a chi-square power calculation needs (Cohen's w) —
> it requires knowing the contingency table's actual shape, since a 2×2
> and a 3×2 table at the same V and n have different statistical power.
> I threaded the table's shape through the pipeline and built the check
> on statsmodels' `GofChisquarePower`, then validated it against Cohen's
> (1988) classic reference power tables to confirm the implementation was
> exact, not just self-consistent.
> **Result:** Shipped with 22 new tests (full suite: 486→501, zero
> regressions), verified live against a real dataset in both dark and
> light themes.

---

## Recommendation for next run

Two independent priorities, not mutually exclusive:

1. **Non-feature, high priority:** open and merge a PR from
   `claude/adoring-meitner-7km73d` into `main` so the accumulated work
   from Runs 21–26 actually lands in the repository's default branch —
   currently `origin/main` is five-plus runs behind what's actually been
   built and tested.
2. **Feature work:** build the "run everything" agentic consolidation
   entry point — a single trigger that runs Auto Insights, Hypothesis
   Sweep, Anomaly Drivers, and the Insight Orchestrator together and
   presents one synthesized report, rather than requiring a user to visit
   four separate tabs. This is now the clearest remaining high-leverage
   agentic-AI-analysis move; the narrow statistical-power-extension vein
   (t-test → chi-square) is nearly exhausted after this run.
