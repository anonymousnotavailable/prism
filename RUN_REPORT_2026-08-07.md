# Prism Improvement Routine — Run Report, 2026-08-07

Branch: `claude/charming-bohr-xoxvof` (pushed to origin; see note on git
workflow at the bottom). First run of the memory-tracked routine —
`.prism/routine_log.md` did not exist before today.

## 1. What shipped

### Hypothesis Generator
**What it does:** a one-click, autonomous statistical-hypothesis engine on
the Overview tab. It scans every plausible pair of columns in the active
dataset, ranks them with a cheap deterministic pre-screen (variance-ratio
for numeric-vs-categorical, a chi-square-shaped proxy for
categorical-vs-categorical, absolute correlation for numeric-vs-numeric —
no scipy call yet), then runs the strongest candidates through the
existing Stats Lab's real significance tests (Welch's t-test, one-way
ANOVA, chi-square test of independence, Pearson correlation) and returns a
ranked list: a plain-English claim, the actual p-value and effect size,
a supported/not-supported verdict, and assumption-check warnings
(normality, low expected cell counts).

**Why it was chosen:** this cycle's mandated priority theme is agentic AI
analysis — auto-EDA, hypothesis suggestion, anomaly narration. Prism
already had guided stats testing (pick two columns yourself) and anomaly
narration (`modules/anomaly.py`); it had nothing that answered "what should
I even be testing?" on its own. Research (`.prism/research_2026-08-07.md`)
confirmed none of the surveyed competitor tools (Hex, Deepnote, Julius,
ChatGPT Advanced Data Analysis) do ranked, auto-generated, *tested*
hypotheses as a one-click feature — they generate charts and narratives and
leave significance testing to a follow-up question.

**The technical-depth argument:** this isn't an LLM narrating a hunch. The
screening step is a real statistical heuristic (an eta-squared preview,
computed from group means and variances — the same quantity ANOVA derives
properly, just cheaper), and every verdict returned to the user comes from
an actual `scipy.stats` call (t-test/ANOVA/chi-square/Pearson), including
p-values, named effect sizes (Cohen's d, eta-squared, Cramer's V, Pearson
r) with conventional small/medium/large labels, and Shapiro-Wilk
normality-assumption warnings. It runs correctly with **zero Gemini API key
configured** — an optional "Narrate with AI" pass only turns the
already-computed results into a paragraph, mirroring the SAFE/REVIEW
determinism guarantee `modules/autocleaner.py` already established for
Auto Cleaner. Current agentic-EDA research (arXiv 2510.04023) explicitly
flags full-pipeline autonomous success below 1% on hard benchmarks as the
frontier's real state — this feature deliberately stays inside a narrow,
fully-verifiable slice instead of over-claiming autonomy.

**Where it lives:** `modules/hypothesis_engine.py` (243 lines), wired into
`app.py`'s Overview tab as a new "Hypothesis Generator" expander,
positioned right after the existing Anomaly Detection expander, following
the same glass-container / expander pattern as every other Overview
section.

### Test suite (new: `tests/`)
The repo had zero unit tests before this run — only `eval/`, an LLM-output
eval harness, which tests prompt quality, not deterministic logic. Added
17 tests in `tests/test_hypothesis_engine.py` (unit) and
`tests/test_hypothesis_engine_integration.py` (integration, against the
bundled `samples/sales_data.csv`, exercised through the real
`data_engine.detect_column_types → hypothesis_engine.generate_hypotheses`
pipeline, no mocking). Covers: empty/None/degenerate input, each of the
three hypothesis kinds against synthetic data with a known ground-truth
effect (and a known *non*-effect, verified against whatever scipy actually
returns rather than an assumed verdict), the cardinality filter, the
`MAX_HYPOTHESES_RETURNED` cap, ranking order, and the deterministic
no-Gemini narration fallback (including a model=None guard added *because*
a test caught it trying to call Gemini during a "nothing to narrate" path).

```
$ python3 -m pytest tests/ -q
.................
17 passed in 2.07s
```

## 2. Screenshots

All captured via Playwright against a live `streamlit run app.py` on this
branch, loading the bundled Sales sample dataset.

**Desktop (1440×900), dark theme (Prism HUD) — top of the new section:**
`.prism/runs/2026-08-07/desktop_hypotheses_top_dark.png`

**Desktop, dark theme — full results (scrolled):**
`.prism/runs/2026-08-07/desktop_hypotheses_dark.png`

**Desktop, light theme (Arctic):**
`.prism/runs/2026-08-07/desktop_hypotheses_light.png`

**Mobile (390×844) landing screen — correctly responsive:**
`.prism/runs/2026-08-07/mobile_landing.png`

**Mobile, after loading a dataset — pre-existing layout bug (see Findings, not
introduced by this change):**
`.prism/runs/2026-08-07/mobile_after_load.png`

No ffmpeg was available in this sandbox to render a demo GIF (`apt-get
install ffmpeg` failed on a 404'd package mirror, not a permissions issue —
noting this honestly rather than fabricating a GIF). The screenshot
sequence above stands in as the demo trail: landing → dataset loaded →
Hypothesis Generator expanded and run → ranked, tested results.

## 3. Audit findings (full detail in `.prism/audit_2026-08-07.md`)

1. **[HIGH, not fixed]** Mobile viewport layout breaks once a dataset is
   active — the main content column collapses to a ~30px sliver while the
   Atlas panel keeps full width. Landing screen is fine; every tab past it
   is effectively unusable on a real phone width. Root cause not isolated
   this run (native `st.columns()` in use, so likely a wrap/min-width
   interaction somewhere in the Atlas panel's CSS) — flagged as next run's
   top priority rather than guessed at under time pressure.
2. **[LOW, not fixed]** The bottom "Ask Atlas" chat bar keeps dark styling
   in the light theme.
3. **[INFO]** `google-generativeai==0.8.6` is EOL upstream (observed
   directly: import prints a deprecation notice pointing at `google.genai`).
   Still functional; migration is a real multi-site change for its own run.

## 4. Research NOT built this run (full ranked table in `.prism/research_2026-08-07.md`)

| Feature | Depth | Effort | Why held back |
|---|---|---|---|
| Backfill unit tests for existing modules | 3 | M | This run's test budget went to the new feature; strong next-run candidate |
| Fix mobile layout bug | — | M | Needs its own diagnostic pass, not a drive-by guess |
| Migrate to `google.genai` SDK | 2 | M | Touches every Gemini call site — own future run |
| Polars fast-path for large-file ingestion | 4 | L | Needs real before/after benchmarks, its own run |
| PyGWalker drag-and-drop tab | 2 | M | Competitor parity, cosmetic-leaning — lower priority than stats depth |
| **Atlas proactive insights** (surface a finding unprompted post-upload) | 4 | M | Next run's Atlas-track slice — held back so this run's one feature slot went to the mandated agentic-analysis theme |
| Self-verifying insight agent (LLM claim → auto pandas check → confirm/retract) | 5 | L | Matches the research theme directly; a strong v2 of the Hypothesis Generator once it's proven out over a run or two |

## 5. Interview notes

> **Hypothesis Generator:** *"I built an auto-EDA feature that doesn't stop
> at 'here's a chart' — it scans every plausible pair of columns in a
> dataset, cheaply pre-screens them so it's not blindly running hundreds of
> tests, then runs the strongest candidates through real significance
> tests — t-tests, ANOVA, chi-square, Pearson correlation, with proper
> effect sizes and Shapiro-Wilk normality checks — and ranks the results by
> actual statistical evidence. It's fully deterministic and reproducible
> with zero AI API key configured; an LLM only phrases the summary
> afterward, never decides what's significant. I wrote 17 tests first,
> including synthetic datasets with a known ground-truth effect so I could
> verify the pipeline finds real signal and correctly rejects noise, not
> just that it doesn't crash."*

## 6. Recommendation for next run

Two clear priorities, roughly in this order:
1. **Diagnose and fix the mobile layout bug** (Finding #1) — it currently
   undercuts the "installable on phone, PWA" pitch on the app's own landing
   claims. Give it a dedicated pass: isolate the exact CSS/column cause,
   fix, then screenshot *every* tab at mobile width in both themes per the
   routine's own Phase 5 checklist (this run only spot-checked Overview).
2. **Atlas proactive insights** as the next Atlas-track slice — surface a
   top finding unprompted right after upload, reusing Auto Analyst's
   synthesis step rather than duplicating it, careful not to spam or repeat
   what a user hasn't asked for yet.

Backfilling unit tests for the existing (untested) modules is a good
lower-stakes filler if a run has budget left after its main feature — high
interview signal, low risk, no new UI to verify.

---

*Git workflow note: this session's harness specified a fixed branch
(`claude/charming-bohr-xoxvof`) with an explicit "never push to a different
branch without permission" constraint. That overrides the routine's Phase 7
default of merging into and pushing `main` directly. All work here was
merged into and pushed to that designated branch instead of `main` —
`main` was left untouched. See `.prism/routine_log.md` for the same note,
so the next run (which may or may not have the same constraint) knows why.*
