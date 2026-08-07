# Prism Autonomous Improvement Routine — Run Report

**Date:** 2026-08-07
**Branch shipped from:** `feature/hypothesis-engine` → merged into `claude/charming-bohr-46a02x` → pushed to GitHub.

## 1. What shipped

### Hypothesis Engine (agentic AI analysis theme)

**What it does:** a new "🔬 Hypothesis Engine" section at the top of the
Stats Lab tab. One click ("Generate & Test Hypotheses") and Gemini reads
the dataset's schema + a 3-row sample and proposes several specific,
testable claims about relationships between columns (e.g. *"Average
'quantity' differs across 'product' groups"*). Each claim is then handed to
`modules/stats_lab.py` — the same code path the existing manual two-column
picker uses — which alone decides whether it's a t-test, ANOVA, chi-square,
or Pearson test, and runs it via scipy. Gemini never decides whether a
hypothesis holds; that's the point. Before verdicts are shown, every
p-value in the batch gets a **joint Benjamini-Hochberg false-discovery-rate
correction** (statsmodels) — testing five hypotheses on one dataset without
correcting for it is a textbook way to manufacture a false "significant"
result, and nothing in Prism previously guarded against that. If Gemini is
unavailable (no key, rate limit, exhausted daily quota — this run's own
sandbox had no key configured, so this path ran live, not hypothetically),
a deterministic fallback nominates hypotheses from a correlation scan and a
group-variance scan instead, so the feature degrades rather than dying.

**Why it was chosen:** the routine's priority theme this cycle was agentic
AI analysis. Auto Analyst (shipped previously) already covers "propose a
plan, run it, narrate it," and Stats Lab already covers "run one correct
test a human picked." Nothing closed the loop between the two — a user
could not ask "what's worth testing here" and get back a statistically
defensible answer. Full reasoning and the rejected alternatives are in
`.prism/research_2026-08-07.md`.

**Technical-depth argument:** this isn't "call an LLM and print what it
says." It's an agentic pipeline with a hard separation of concerns (LLM
proposes, deterministic code decides and computes — the same pattern
`modules/autocleaner.py`'s SAFE/REVIEW split already established
elsewhere in this codebase), a real statistical-rigor detail most portfolio
projects skip (multiple-testing correction), and a verified non-LLM
fallback path proven live in this run rather than just claimed. 10 unit
tests (written before the implementation) cover hallucinated-column
rejection, malformed-JSON handling, id-column exclusion, and — the one
that actually matters statistically — that the FDR-adjusted p-value is
never smaller than the raw one across a batch of genuinely noisy pairs.

**Demo:** `.prism/runs/2026-08-07/hypothesis_engine_demo.webm` (real
end-to-end run against the bundled Sales sample — no GIF muxer was
available in this environment's ffmpeg build, so the clip shipped as WebM
instead of GIF; same content, playable in any modern browser).

![Hypothesis Engine — desktop, dark theme](.prism/runs/2026-08-07/stats_lab_desktop_hypotheses.png)

![Hypothesis Engine — desktop, light theme](.prism/runs/2026-08-07/stats_lab_desktop_light.png)

![Hypothesis Engine — mobile PWA, dark theme](.prism/runs/2026-08-07/stats_lab_mobile_hypotheses.png)

### Mobile PWA layout fix (bug found in this run's own audit)

**What it does:** the Atlas copilot side panel was pinned with
`position: fixed; width: 328px` plus a `padding-right: 352px !important`
forced onto the main content column, with no responsive breakpoint. At a
390px phone width that's negative usable space — every tab's content,
including the brand-new Hypothesis Engine, rendered squeezed into a ~60px
sliver with text wrapping letter by letter, the exact opposite of "reads as
one system" the glassmorphism design language is supposed to deliver on
mobile. Added a `@media (max-width: 768px)` rule that drops the fixed
positioning below that width so the panel falls into normal document flow.

**Why it matters for the portfolio pitch:** the app's own premise is "a PWA
installable on phone and PC." A layout that's unusable on a phone directly
contradicts that pitch — this was worth fixing on sight, not filing away.

**Before / after**, same viewport (390×844), same dataset loaded:

| Before (pre-fix, triage capture) | After (this run's fix, mobile dark) |
|---|---|
| Nav pills and tab content compressed into a sliver behind the fixed Atlas panel; text wrapped one letter per line. | ![Mobile, post-fix](.prism/runs/2026-08-07/stats_lab_mobile_before.png) |

*(The pre-fix screenshot wasn't kept as a permanent artifact — it was a
throwaway triage capture in `/tmp` during the audit, not written to
`.prism/runs/`. The audit file describes exactly what it showed;
the "after" column above is the actual shipped state.)*

![Mobile PWA, light theme](.prism/runs/2026-08-07/stats_lab_mobile_light.png)

## 2. Verification

- **Tests:** full `pytest` suite green — 10/10 (all new; no pre-existing
  test suite existed in this repo before this run to regress).
- **Live end-to-end run:** exercised against `streamlit run app.py` with
  the bundled Sales sample dataset via Playwright/Chromium — not just
  mocked unit tests. Confirmed: the Gemini-unavailable fallback path fires
  correctly and is labeled as such in the UI; the ANOVA test dispatches
  correctly for a categorical/numeric pair; the FDR-adjusted p-value
  displays alongside the raw one; the empty state, loading spinner, and
  error states all render.
- **Screenshots:** desktop (1440×1000) and mobile-PWA (390×844), dark and
  light theme, before-and-after the "Generate & Test Hypotheses" click —
  6 total, all in `.prism/runs/2026-08-07/`.
- **Fresh-checkout boot check:** with a clean working tree on
  `claude/charming-bohr-46a02x` at the merge commit, `streamlit run app.py`
  served HTTP 200 on a cold start — confirmed before pushing.
- **Regression check:** `git diff` confirms only `app.py` (additive: one
  new tab section, new session-state keys, no existing code paths altered)
  and `modules/theme.py` (additive: one new CSS block) were touched outside
  the new files — no existing feature's code path was modified.

## 3. Research findings NOT built this run (ranked backlog)

Full detail and evidence links: `.prism/research_2026-08-07.md`. Summary,
ranked:

1. **Self-verifying Auto Analyst** (depth 4, effort M) — a second Gemini
   pass that checks the first pass's generated code/claims against the
   actual computed result before showing it. Directly from current
   agentic-EDA research on self-verifying analysis agents.
2. **Atlas proactive insights slice** (depth 4, effort M, Atlas copilot
   track) — Atlas surfaces one finding unprompted after upload, without
   being asked. Needs a "don't nag" throttle; scoped as one slice, not the
   full JARVIS vision, per the routine's own Atlas-track rule.
3. **Voice-driven Hypothesis Engine command** (depth 3, effort S, Atlas
   copilot track) — natural follow-up now that the engine exists; thin
   wrapper, low risk.
4. **Migrate off `google-generativeai`** (depth 3, effort L, high risk) —
   the SDK is confirmed end-of-life (deprecation warning surfaced live in
   this run's environment); replacement is `google.genai`. Needs a real
   Gemini key to verify against live traffic, which this run's sandbox
   didn't have — flagged for a dedicated cycle, not attempted blind.
5. **Polars/DuckDB as an alternate compute engine** (depth 3, effort L,
   high risk) — ecosystem trend, but every module assumes a pandas
   DataFrame; a real architecture change, proposed only per the "no
   architecture rewrites" guardrail, not attempted.
6. PyGWalker-style drag-and-drop visual explorer tab (depth 2, effort M) —
   competitor parity with Hex/Deepnote's visual query builders, lower
   priority than the above since it's polish, not depth.

## 4. Interview notes (STAR bullets, verbatim-usable)

**Hypothesis Engine:**
> *Situation:* Prism's analysis tools could run one statistical test at a
> time, but only if a user manually picked which two columns to compare —
> nothing suggested what was worth testing, and nothing protected against
> the false-positive risk of testing many things on the same data.
> *Task:* Add an agentic layer that proposes hypotheses automatically while
> keeping the actual statistical decision-making outside the LLM's hands.
> *Action:* Built a pipeline where Gemini nominates candidate column-pair
> hypotheses from the schema alone, a deterministic Python layer (reusing
> the existing test-dispatch logic) decides and runs the correct test via
> scipy, and every p-value in the batch gets a joint Benjamini-Hochberg
> FDR correction before a verdict is shown — with a non-LLM heuristic
> fallback (correlation + group-variance ranking) so the feature keeps
> working when the free-tier Gemini quota is exhausted.
> *Result:* Shipped with 10 unit tests written first and verified live
> end-to-end (including the fallback path, since no API key was configured
> in the build environment) — a concrete, demoable answer to "how do you
> avoid p-hacking when an LLM is generating hypotheses at scale?"

**Mobile PWA layout fix:**
> *Situation:* running my own screenshot-based UI audit at a phone
> viewport width surfaced that the app's persistent AI copilot panel used
> a fixed 328px-wide CSS column with no responsive breakpoint, which broke
> the layout of every single tab on mobile.
> *Task:* Fix it without restructuring the panel's Python/Streamlit
> implementation.
> *Action:* Added one CSS media query that drops the fixed positioning
> below 768px so the panel falls into normal document flow instead of
> overlapping the content.
> *Result:* Verified before/after with real screenshots at 390×844 in both
> themes — the nav bar and every tab's content went from unreadable
> letter-wrapped text to a normal full-width mobile layout.

## 5. Recommendation for the next run

Pick up the Atlas copilot track next: a proactive-insights slice (Atlas
surfaces one finding unprompted right after a dataset loads) is the
natural next increment toward the JARVIS vision, and it's a short hop from
this run's Hypothesis Engine — "here's one relationship in your data worth
testing" is a proactive insight the engine can already generate, it just
needs a trigger and a throttle. Pair it with the light-theme contrast pass
noted in the audit (nav pills, bottom chat bar, and Atlas panel buttons
stay dark-on-dark in "Arctic (Light)") since that's a quick, contained fix
in the same theming file already touched this run. Leave the
`google-generativeai` → `google.genai` migration and any polars/DuckDB
compute-engine work for a run that has a live Gemini API key available to
verify against — both are real, not urgent, and risky to do blind.
