# Prism Autonomous Improvement Routine — Run 15 (2026-08-11)

## Scope note

Per the standing precedent every run since Run 9 has logged: this run's
trigger asks the routine to "loop until the session is 100% used" while
also saying "use less tokens"/"don't use credits." Those are contradictory
in an open-ended sense (a genuine loop means repeatedly re-running
research/build/verify against a shrinking backlog — diminishing-returns
busywork, not token efficiency). Ran **one complete, safely verified
cycle** and stopped, consistent with the hard guardrails, which take
precedence over the scheduling prompt's phrasing.

Reused the standing backlog (`.prism/routine_log.md`) instead of
re-running the full four-source-class web research sweep, and reused Run
11's full-app audit — Run 14 was the last run to ship new UI, and this
run's own live Playwright pass through the touched paths found nothing
newly broken. Same token-efficiency reasoning Runs 9-14 already
established for this exact situation.

## ⚠️ Repo record-keeping correction (read this first)

Every prior run's report said some version of "merged into `main`, pushed
`main` to origin." This run checked that claim against the real GitHub
state and it doesn't hold:

- The repository's actual default branch (`origin/main`) is at commit
  `dd20c29` — an **unrelated project history** (a DuckDB SQL Lab /
  JARVIS-dashboard-plan line) that has never contained any of this
  routine's 14 prior runs' work.
- There has **never been a pull request** opened from
  `claude/adoring-meitner-xsga3q` into `main` (confirmed via the GitHub
  API this run — zero PRs, open or closed, in either direction).
- All 15 runs' actual work lives only on `origin/claude/adoring-meitner-
  xsga3q`. Every run's internal "main" was a same-named local branch that
  never left that run's own session.

This is not a mistake made *this* run — it's consistent with this
session's hard git-operation rules ("develop and push only to
`claude/adoring-meitner-xsga3q`," "never push to a different branch
without explicit permission"), which override the scheduling prompt's
literal "merge into main and push main" instruction. But it does mean
**none of this routine's 15 runs of shipped features are visible on the
repo's default branch or in any open pull request today.** Not resolving
it unilaterally (opening a PR) since the guardrails require an explicit
human ask before creating one — flagging it here and in the routine log
so it's the first thing the next run (or the human) sees.

## What shipped

### "Suggest a chart" auto-encoding recommendation

**What it does:** A new "✨ Suggest a chart" button in the Manual Chart
Builder (Visualize tab) reads the currently loaded dataset and
recommends a complete chart encoding — chart type, X-axis, Y-axis,
Color, Facet, and Aggregation — with a plain-English reason, then
pre-fills every selectbox so the user can keep tweaking from there.
Fully deterministic, no Gemini call.

Ranking logic (`modules/visualization.suggest_chart_encoding`), most to
least interesting:
1. Strongest numeric/numeric correlation (if it clears r ≥ 0.3) →
   **Scatter**, colored by a low-cardinality categorical when one exists.
2. Else the numeric/categorical pair with the largest one-way ANOVA
   F-statistic among viable group counts → **Bar of the mean**, faceted
   by a second low-cardinality categorical when one exists.
3. Else a datetime + numeric column → **Line** (time trend).
4. Else a lone numeric column → **Histogram**.
5. Else a lone categorical column → **Bar of counts**.

**Why chosen:** Runs 13 and 14 both shipped grammar-of-graphics encoding
channels (Color, Aggregation, Facet) for the Manual Chart Builder and
explicitly logged "explore mode that auto-suggests encodings" as the
next open piece of that PyGWalker-inspired backlog item. This run closes
exactly that gap. It also satisfies this cycle's mandatory
agentic-AI-analysis theme — an automatic, explainable "what should I look
at next" recommendation — using the same "read the data, not the LLM's
prose" pattern `auto_analyst.suggest_followup_hypothesis` already
established for Stats Lab. Being fully rule-based, it needed no
`GEMINI_API_KEY` (this sandbox still has none — 15th consecutive run with
that constraint), which meant it was the one candidate this run could
verify **completely live**, not just via unit tests.

**Technical-depth argument:** Statistically-grounded chart selection
(correlation-strength ranking, one-way ANOVA F-statistic group-difference
ranking, cardinality-windowed split-column selection) is a real,
citable data-science skill — "which visualization actually answers the
question" — not a UI convenience. It's the same statistical reasoning an
analyst does by hand before opening a plotting library, made explicit,
deterministic, and testable.

## Verification

- **Tests:** 11 new tests in `tests/test_chart_suggestion.py`, written
  first (TDD), covering every ranking branch, the empty/all-null edge
  cases, and a dedicated test that every suggestion the function can
  produce actually builds a real chart via `build_manual_chart` without
  raising. Full suite: **310 → 321/321 passing** after merge, zero
  regressions.
- **Live screenshots** (Playwright, `samples/sales_data.csv`, three
  viewport/theme combinations — desktop 1440×900 dark, desktop 1440×900
  light/Arctic, mobile 390×844 dark): clicked "Suggest a chart," got
  *"'quantity' looks like it varies meaningfully across 'region'
  groups,"* and the resulting Bar-of-means chart (region × mean quantity)
  rendered correctly with all six selectboxes pre-filled to match, in all
  three combinations. No overflow, no clipping, glass panels consistent,
  reason caption readable in both themes. This is the first run since at
  least Run 9 to get a **complete** 3-way live pass for a new feature
  with zero automation gaps — the recurring "mobile sidebar-expander"
  Playwright gap earlier runs logged didn't apply here since this control
  lives in main content, not the sidebar. Screenshots saved to
  `.prism/runs/2026-08-11-run15/`.
- **Environment:** hit the known `_cffi_backend` sandbox gap (documented
  since Run 12); same fix applied (`pip install --force-reinstall
  --no-cache-dir cffi`).
- **Secrets hygiene:** re-checked `.gitignore` — `.env`, `.venv/`,
  `venv/`, `.streamlit/secrets.toml` all covered. No secrets touched or
  committed.
- **Fresh-checkout sanity:** `python -c "import ast; ast.parse(open('app.py').read())"`
  passes; full suite green on `claude/adoring-meitner-xsga3q` post-merge
  (this session doesn't have a real `GEMINI_API_KEY`, so a full
  `streamlit run` smoke pass is the closest available proxy to a
  fresh-checkout launch check — done above, no traceback).

### Screenshots

| Desktop dark | Desktop light (Arctic) | Mobile dark |
|---|---|---|
| `.prism/runs/2026-08-11-run15/desktop_dark_03_after_suggest.png` | `.prism/runs/2026-08-11-run15/desktop_light_03_after_suggest.png` | `.prism/runs/2026-08-11-run15/mobile_dark_03_after_suggest.png` |

## Research findings NOT built (backlog for future runs)

| Item | Status | Notes |
|---|---|---|
| PyGWalker-style draggable pill UI / multi-step explore mode | Open | This run shipped the single-suggestion slice; a true drag-and-drop interaction model is out of scope per the no-architecture-rewrite guardrail (would need a custom Streamlit JS component) |
| Tier-2 proactive alert pattern extended to Pie charts | Open | No forcing "silent detector" gap identified yet for Pie, unlike the confounder case Run 13 closed |
| Large-Excel out-of-core ingestion | Open | Run 14 identified this as the narrower remaining piece of the DuckDB Auto Cleaner item (`.xlsx`/`.xls` excluded from the streaming reader); no dependency-free streaming path currently available |
| Light-theme dataframe/chart repaint lag | Open | Cosmetic, not re-attempted this run |
| Live-Gemini verification | Blocked | 15th consecutive run with no real `GEMINI_API_KEY` in this sandbox — not actionable from inside a run |
| **Main-branch/PR gap (new, highest priority)** | **Open** | See the correction section above — resolve before adding much more history on top of the unmerged feature branch |

## Interview notes (STAR-style, verbatim-usable)

- **"Suggest a chart" auto-encoding recommendation:** *"I built a
  rule-based recommendation engine for Prism's chart builder that reads
  the loaded dataset directly — running pairwise correlation strength and
  one-way ANOVA F-statistics across every numeric/categorical combination
  — and suggests the single most informative chart type and encoding,
  with a plain-English explanation of why. I chose a deterministic,
  statistics-first approach over calling out to the LLM so it works
  offline, costs nothing per suggestion, and is fully unit-testable; I
  wrote 11 tests first, including one that exhaustively verifies every
  suggestion the ranker can produce is actually renderable by the
  downstream chart builder, then verified the feature end-to-end with
  Playwright across three device/theme combinations before merging."*

## Recommendation for the next run

1. **Resolve the main-branch/PR gap first.** Fifteen runs of verified,
   tested work exist only on a feature branch with no PR and no path to
   the repo's actual default branch. Get explicit direction from the
   human (open a PR? merge directly? is the feature branch intentionally
   the working branch?) before continuing to stack more unmerged history
   on top of it.
2. If that's resolved, the next-highest-value remaining item is still the
   **large-Excel out-of-core ingestion** gap (Run 14's narrower spinoff)
   or a **fresh four-source-class web research sweep** — this run and
   several before it reused the same backlog; an entirely new sweep is
   overdue and might surface higher-signal candidates than what's left on
   the current list.
