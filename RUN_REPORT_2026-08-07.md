# Prism Autonomous Improvement Routine — Run Report
**Date**: 2026-08-07 · **Branch**: `claude/charming-bohr-svi5n2` (pushed, not merged — see note below)

## 0. A note on branch policy this run

This session's operating instructions require developing and pushing only
to `claude/charming-bohr-svi5n2`, never a different branch without explicit
permission, and never opening a PR unless asked. The routine brief's own
Phase 7 ("merge each feature branch into `main` yourself... push `main`")
conflicts with that. I followed the stricter, more specific session policy:
everything below is committed and pushed to `claude/charming-bohr-svi5n2`,
not merged to `main`. A fresh clone of that branch was verified to compile
and pass the full eval suite before finishing (see §2).

## 1. What shipped

### Hypothesis Engine — automatic multi-column hypothesis scan with FDR correction
**What it does**: A new "🔬 Auto-Scan All Column Pairs" control in Stats
Lab. One click tests every valid pairwise relationship among up to 12
columns (66 pairs) — reusing Stats Lab's existing test-selection and
execution pipeline (t-test / ANOVA / chi-square / Pearson) rather than
duplicating it — then applies a **Benjamini-Hochberg false-discovery-rate
correction** across the whole batch of p-values. The UI shows "raw
significant (p<0.05)" next to "significant after FDR correction" side by
side, so the gap between them is visible, not hidden. Gemini narrates the
corrected-significant findings in plain English when a key is configured;
without one (or on any Gemini error/rate-limit), it falls back to a
templated summary built straight from the numbers — the feature never
depends on Gemini to be useful.

**Why chosen**: This cycle's required theme was agentic AI analysis,
specifically calling out "hypothesis suggestion." Live research (Julius
AI, Hex, Deepnote, ChatGPT Data Analysis) found none of the surveyed
competitors foreground multiple-comparisons correction — they generate
single ad hoc insights per question, not a batch-tested, statistically
guarded pass. That's a real, defensible gap, not cosmetic polish.

**Technical-depth argument**: Testing 66 hypotheses at p<0.05 without
correction would produce several false positives by chance alone even in
pure noise — this is exactly the kind of statistical pitfall a junior
analyst misses and a senior one catches. Verified empirically in the eval
suite: 12 fully independent random columns (66 pure-noise pairs) produced
3 raw "significant" results at p<0.05 and 0 after FDR correction. Built on
`statsmodels.stats.multitest.multipletests` (already a Prism dependency),
not hand-rolled.

**Tests**: `eval/hypothesis_engine_eval.py`, 7 deterministic cases
(planted strong correlation found and flagged significant; planted group
difference found; FDR correction suppressing noise false-positives on the
66-pair pure-noise case above; single-column dataset degrades to an empty,
non-crashing result; a 20-column dataset correctly truncates to 12 scanned
columns; Gemini-free templated narration fallback; empty-scan narration).
**7/7 pass.** Wired into `.github/workflows/ci.yml` alongside the existing
Auto Cleaner suite.

**Screenshots** (desktop, `.prism/runs/2026-08-07/`):
- `desktop_dark_statslab_before.png` / `desktop_dark_statslab_after.png`
- `desktop_light_statslab_before.png` / `desktop_light_statslab_after.png`

Both themes render cleanly: readable contrast, the existing `insight-card`
component reused for narrated findings (no new visual language invented),
metrics and the tested-pairs table all render correctly, empty/loading
states present (spinner while scanning, "No scan yet" empty state before
the first run).

### Fix — Atlas side panel covered the entire screen on phone-width viewports
**What it does**: `modules/theme.py`'s Atlas copilot panel
(`.st-key-atlas_side_panel`) was `position: fixed; width: 328px; right: 0`
with zero responsive handling. On any phone-width viewport that fixed
panel covers nearly the whole screen, burying every tab underneath it —
directly undermining the "installable on phone" PWA pitch. Now hidden
below 900px via a media query. Atlas remains fully reachable through the
always-visible `st.chat_input` command bar at the bottom of the page,
which is a separate element this fix doesn't touch.

**Why chosen**: Found while screenshot-testing the Hypothesis Engine's
mobile viewport (Phase 1's "bugs found here are automatically eligible for
a small fix alongside the main features"). Severe enough — a full-screen
unremovable overlay on every phone — to fix immediately rather than only
log.

**Screenshot**: `.prism/runs/2026-08-07/mobile_dark_overview.png` — the
Atlas chat bubble/quick-action chips no longer render as a full-screen
takeover at 390px width (verified via computed-style check:
`getComputedStyle(panel).display === "none"` at that viewport).

## 2. Verification

- Full eval suite: **15/15 passing** (7 new Hypothesis Engine cases + 8
  existing Auto Cleaner cases) — no regressions.
- `python -m py_compile` clean across every tracked `.py` file.
- Fresh clone of the pushed branch re-verified independently (clean
  compile + both eval suites green) before finishing, per Phase 7.4.
- Screenshots captured at desktop (1440×960) and mobile-PWA (390×844)
  widths, both themes, via Playwright against a locally launched instance
  of the app with the bundled `samples/sales_data.csv`.

## 3. Honest gap: mobile is still broken beyond the one fix above

Screenshot-testing the mobile viewport surfaced **two more pre-existing
bugs**, independent of anything built this run, that I was not able to fix
in this cycle:

1. **Page-level auto-scroll-to-bottom hijack.** `st.chat_input`'s mere
   presence makes Streamlit wrap the whole main content area in
   `stAppScrollToBottomContainer` and force-scroll it to the bottom on
   every load/rerun — confirmed via live DOM inspection (`scrollTop`
   snapping to `scrollHeight − clientHeight`, e.g. 14,580 of 15,424px,
   with zero user interaction). Two different mitigations were attempted
   and both reverted rather than shipped half-working (full diagnostic
   trail in `.prism/audit_2026-08-07.md`, so the next run doesn't repeat
   them blindly).
2. **A narrow-column render at ~390px width**, not yet conclusively
   isolated from bug #1's noise.

Both are logged as the top priority for the next run in
`.prism/routine_log.md`. I'm reporting this plainly rather than only
showing the one screenshot that looks clean — the mobile PWA experience is
genuinely not solid yet, and a scheduled routine that quietly ships one fix
while sitting on two known-broken findings without saying so would be
worse than useless.

## 4. Research findings not built (ranked backlog)

Full detail and sourcing in `.prism/research_2026-08-07.md`. In brief,
carried forward for future runs:

| Feature | Depth | Effort | Theme |
|---|:---:|:---:|---|
| Self-verifying 2nd-pass LLM critique of Auto Analyst findings | 4 | M | Agentic AI analysis |
| Segment/cohort auto-suggestion (unprompted group-difference surfacing) | 3 | M | Agentic AI analysis |
| Atlas proactive-insight slice (voice HUD track) | 4 | M | Atlas copilot — none of this run's 1-per-cycle Atlas budget was spent, available next run |
| `google.generativeai` → `google.genai` SDK migration | 2 | L | Infra health (deprecated upstream, fires a warning on every import today) |
| `use_container_width` → `width=` mechanical cleanup | 1 | S | Infra health (log noise only) |

## 5. Interview notes (STAR, verbatim-usable)

**Hypothesis Engine**: *"I noticed Prism's manual hypothesis testing tool
only checked two columns a user picked by hand — so I built an automated
scanner that tests every valid pairwise relationship across a dataset at
once, and applied a Benjamini-Hochberg false-discovery-rate correction
across the batch, because testing dozens of hypotheses at a flat p<0.05
threshold produces false positives by chance alone. I proved it worked
with a synthetic test: 66 pairwise tests on pure random noise gave 3 'raw
significant' results and 0 after correction — that gap is exactly the bug
I was guarding against."*

**Mobile fix**: *"I don't just trust that a feature 'looks done' — I
screenshot-test every UI change at both desktop and mobile widths before
shipping. Doing that here surfaced a real, severe bug — the app's own
AI-copilot panel had no responsive handling at all and covered the entire
screen on any phone, undermining the product's core 'installable PWA'
pitch. I fixed the one I could safely resolve, and rather than pretend the
rest of mobile was fine, I diagnosed two deeper pre-existing bugs down to
the exact DOM element and documented what I'd already ruled out, so the
next pass doesn't waste time rediscovering it."*

## 6. Recommendation for next run

**Dedicate the next cycle's first block specifically to mobile-viewport
layout — no new features that cycle** — using
`.prism/audit_2026-08-07.md` findings #2 and #3 as the starting point
rather than a fresh audit. This is now the single biggest gap between
Prism's actual quality and its "installable on phone and PC" pitch, and
it's been diagnosed enough (exact failing elements, exact `scrollTop`
values, two ruled-out approaches) that it should be a bounded fix, not
another exploratory session. After that: the self-verifying Auto Analyst
critique pass is the strongest next agentic-theme candidate (highest
depth score in the backlog table, low effort, fits the free-tier budget
with one extra Gemini call).
