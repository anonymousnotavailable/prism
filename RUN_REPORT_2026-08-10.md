# Prism Autonomous Improvement Run — 2026-08-10 (Run 3)

Full-auto mode, per `.prism/routine_log.md`'s history of the two 2026-08-07
runs. This run's branch note: the harness for this session pinned
development to `claude/adoring-meitner-9whu1j` rather than `main` directly —
both features below were merged into that branch (not `main`) and pushed
there, functionally the same integrate-and-ship flow the routine describes.

## What shipped

### 1. Anomaly Narration (agentic-AI theme pick)

**What it does:** After running "Find Anomalies" in the Overview tab,
a new "✨ Narrate these anomalies" button asks Gemini to turn the
IsolationForest-flagged rows and their deterministic reasons into a short,
plain-English narrative with one concrete suggested next action. The
narration is cached in session state keyed by a hash of the flagged set, so
re-rendering or re-clicking never re-hits the Gemini free tier for the same
result — the app's shared `call_gemini()` rate-limit/error handling covers
quota and auth failures the same way every other AI feature in Prism does.

**Why chosen:** Closes a backlog item both 2026-08-07 runs flagged and left
open. Directly serves this cycle's required agentic-AI-analysis theme:
evidence (the flagged rows) is always computed deterministically by
`anomaly.py`, never by the model — the LLM only narrates evidence that
already exists, the same "structured evidence → narration" split
`auto_insights.narrate_insights` and `insight_verifier` already use
elsewhere in Prism.

**Technical-depth argument:** Demonstrates the difference between an LLM
*generating* a claim vs. *narrating* a claim that's already been verified —
a distinction interviewers probing "how do you keep an LLM analysis
trustworthy" specifically listen for. The fingerprint-based caching also
shows deliberate free-tier-quota awareness, not just a bare API call.

**Screenshots:** `.prism/runs/2026-08-10/anomaly_narration_desktop_dark.png`,
`anomaly_narration_desktop_light.png` — captured against the Stocks sample
dataset (Sales/Startup Funding didn't reliably produce flagged rows at
default contamination). Shows both the flagged-rows table with the new
button, and the button's own graceful "No Gemini model available for
narration" failure state (no live API key in this execution sandbox — the
same constraint both prior runs hit). No mobile screenshot — see the
Incident section below.

### 2. Feature Selection Engine

**What it does:** A new "Feature Selection Engine" panel in ML Lab, between
the Feature Engineering Assistant and the Baseline Model Runner. A "Rank
Features" button scores every candidate column by three canonical
selection methods — mutual information (filter, catches nonlinear
relationships), L1/Lasso coefficient magnitude (embedded), and Recursive
Feature Elimination (wrapper) — normalizes each to 0-1 by its own max, and
averages them into one consensus score. Results render as a grouped bar +
consensus-marker chart and a per-feature table, with a one-click "Use
recommended features below" handoff that pre-fills the Baseline Model
Runner's multiselect with the above-average-consensus subset.

**Why chosen:** Highest technical-depth score on this run's research table
(`.prism/research_2026-08-10.md`) and closes the other backlog item both
prior runs left open.

**Technical-depth argument:** Filter/embedded/wrapper is the canonical
three-way taxonomy of feature selection — covering all three, rather than
picking one, is exactly the kind of breadth a data-scientist interview
tests for. The consensus-scoring design (each method normalized
independently, any one method's failure on degenerate data dropped rather
than crashing the whole ranking) is itself a small piece of defensive,
production-minded ML engineering worth narrating in an interview.

**Verification finding:** on the Stocks sample dataset (predicting `close`
from OHLCV columns), `open`/`high`/`low` correctly rank far above
`ticker`/`date`/`volume` — and L1/Lasso correctly assigns near-zero
coefficients to the redundant, highly-correlated columns once one is
already selected, a textbook demonstration of Lasso's collinearity
behavior that showed up unprompted in real output, not a contrived example.

**Screenshots:** `.prism/runs/2026-08-10/feature_selection_desktop_dark.png`
(chart), `feature_selection_desktop_dark_applied.png` (table + recommended
handoff applied to the Baseline Model Runner's multiselect),
`feature_selection_desktop_light.png`.

**Demo:** `.prism/runs/2026-08-10/feature_selection_demo.webm` (headline
feature, this run) — target selection → Rank Features → chart + table →
"Use recommended features below" handoff into the Baseline Model Runner's
multiselect. Recorded via Playwright video capture; saved as `.webm` rather
than an animated `.gif` because this execution sandbox's `ffmpeg` build
only has the `webm`/`image2` muxers compiled in, no `gif`/`apng` muxer.

### 3. Small fix: real pytest coverage for three modules (not counted against the 2-3 feature budget)

The 2026-08-07 Run 2 entry in `CHANGELOG.md`/`routine_log.md` claimed "82
new unit tests" for `auto_insights.py`, `regression_diagnostics.py`, and
the STL addition to `forecasting.py`. Those tests existed only as
standalone `eval/*.py` scripts with a bespoke print-harness, never wired
into `tests/` or `pytest.ini`. Ported all three into real pytest files.
Suite went from 27 → 73 passing. Full writeup in
`.prism/audit_2026-08-10.md` — this was the single biggest finding of this
run's audit phase and directly affects whether "we have automated tests"
is a true claim about this codebase.

## Incident: mobile Atlas-panel-overlap fix attempted and reverted

Tried to fix the 2026-08-07 Run 2 finding that Prism's Atlas side panel
overlaps main content at ~390px viewport widths. Two CSS approaches:

1. Un-fixing the panel's `position` at narrow widths — made it worse (the
   panel's Streamlit column collapsed to a few px wide, wrapping every
   character onto its own line).
2. `display: none` on the panel below 768px (Atlas stays reachable via the
   separate `st.chat_input` bar already fixed to the viewport bottom) —
   cleanly hid the panel, but revealed that the *main content itself* is
   independently squished to a ~22px sliver on phone widths, a deeper
   pre-existing Streamlit layout bug unrelated to the panel.

Both attempts reverted rather than ship a fix that only hides the symptom.
Full diagnostic trail, repro evidence
(`.prism/runs/2026-08-10/mobile_content_squish_bug_evidence.png`), and a
suggested fix shape are in `.prism/audit_2026-08-10.md`, so a future run
can pick this up without repeating the same two dead ends. This is now a
strong candidate for being *the* focus of a dedicated future run — see
Recommendation below.

## Research findings not built (full ranked table in `.prism/research_2026-08-10.md`)

- **Exportable Data Quality Scorecard** — the score itself already exists
  (`data_engine.get_health_breakdown`); only a Markdown/JSON export is
  missing. Lower depth-to-effort than this run's two picks.
- **`google-generativeai` → `google-genai` SDK migration** — now flagged
  by all three runs. Still correctly scoped as its own dedicated run
  (touches every Gemini call site), but the "not urgent" framing is aging.
- **Atlas Proactive Insights (JARVIS copilot track)** — routine guardrail
  caps this to one such feature per run; not picked this run to keep scope
  to two well-tested features instead of three rushed ones.
- Advanced outlier detection (LOF/DBSCAN), NL-to-chart layer (Julius-AI
  style), real-time collaboration (Deepnote style) — lower priority or
  architecture-adjacent; see research doc.

## Interview notes (STAR-style, verbatim-usable)

**Anomaly Narration:** *"I noticed our anomaly detector (IsolationForest)
only showed users a table of flagged rows with no interpretation, so
analysts had to manually eyeball what was actually unusual. I added a
Gemini-powered narration layer that explains the flagged rows in plain
English and suggests one concrete next action — but designed it so the
LLM only narrates evidence a deterministic model already computed, never
generates the anomaly claims itself, and cached the result per result-set
fingerprint so repeat views never waste API quota. This kept the feature
inside the free tier while making a raw ML output actually actionable for
a non-technical stakeholder."*

**Feature Selection Engine:** *"Before adding a feature-selection step to
our ML Lab, I researched the three canonical families — filter, embedded,
wrapper — and realized most tools only implement one, which biases the
result toward whatever that one method is good at. I built a consensus
ranker that runs mutual information, L1/Lasso, and Recursive Feature
Elimination independently, normalizes each to a common scale, and averages
them, so no single method's blind spot dominates. Testing it on a stock
OHLCV dataset showed the Lasso component correctly zeroing out
coefficients on highly collinear features once one was already selected —
exactly the textbook behavior, which gave me confidence the implementation
was statistically sound, not just superficially plausible."*

## Recommendation for next run

Two strong candidates, both now flagged repeatedly:

1. **Mobile content-squish bug** (this run's incident above) — it affects
   the *entire* Overview tab on phone widths, undermining Prism's
   "installable on phone" PWA claim more than the Atlas-panel framing Run 2
   originally gave it. Start from the repro evidence and suggested fix
   shape already logged.
2. **`google-generativeai` → `google-genai` migration** — three runs
   deferred now. Worth being the whole focus of one run: touches every
   Gemini call site (`ai_analyst.py`, `auto_analyst.py`, `atlas.py`,
   `anomaly.py`, `auto_insights.py`) and needs full regression testing
   across all of them, which is exactly why it keeps getting (correctly)
   deferred rather than rushed.

Either is a better next-run anchor than another net-new feature — Prism
now has good feature breadth across agentic EDA, ML Lab, and stats; the
next highest-leverage work is paying down the two pieces of debt above.
