# Prism Autonomous Improvement Run — 2026-08-07

Branch: `claude/charming-bohr-b1kkfy` (this session's designated branch —
see note on scope, below). Full diff: `feature/hypothesis-engine` merged in.

**Note on scope vs. the routine brief:** the routine's context describes a
React/Next.js PWA shell; the actual repo is a mature single-file Streamlit
app (`app.py`) that already ships most of the roadmap (Auto Cleaner, Auto
Analyst, Stats Lab, ML Lab, Domain Lens, Atlas voice copilot, SQL Lab, SHAP,
PII Vault, a 15-dataset corpus benchmark). This run adapted to what's
actually there rather than rebuilding against a description that doesn't
match. Per this session's operating constraints, work stayed on the
designated branch and was **not** merged into `main` or pushed there —
`main` is untouched and still green.

## 1. What shipped

### Hypothesis Engine (agentic AI analysis theme)
**What it does:** a new section in the Auto Analyst tab. One click proposes
several falsifiable hypotheses about the active dataset — Gemini-generated
when a key is configured, always falling back to a deterministic
correlation/variance-ranked heuristic that needs no API key at all — then
verifies *every one itself* by dispatching straight into Stats Lab's real
`scipy.stats` machinery. Results render as CONFIRMED / NOT CONFIRMED /
INCONCLUSIVE cards with the test used, p-value, and effect size.

**Why chosen:** the research pass (below) converged on the same point from
three angles: 2026 agentic-EDA research (AutoVerifier, the LLM
data-science-agent survey) treats self-verification as the new baseline,
not automation alone; none of Hex/Deepnote/Julius AI publicly lean into
adversarially checking their own AI output; and Prism's own eval showed
Auto Analyst's "5 findings" are Gemini narrating its own results with
nothing re-checking them. This closes that gap without duplicating Auto
Analyst — it's a test-first agent, not another summarizer.

**Technical-depth argument:** the verdict is never a model's opinion. A
hypothesis is CONFIRMED only when this app computes p < 0.05 from a real
t-test/ANOVA/chi-square/Pearson test dispatched by column type, with
Shapiro-Wilk normality and expected-cell-count assumption checks folded
into the narrative — the same rigor Stats Lab already holds itself to,
applied by an agent instead of a human picking columns.

### Gemini response caching + backoff retry
**What it does:** `call_gemini()` (shared by every AI feature in the app)
now serves identical prompts from a bounded in-process LRU cache instead of
re-hitting the API, and retries a transient `ResourceExhausted` up to twice
with short backoff before surfacing the quota-exceeded message.

**Why chosen:** directly observed failure — `eval/eval_results.md` shows 9
of 25 eval questions skipped on quota exhaustion mid-run. This is the
guardrail-mandated "add backoff/caching rather than hammering the API,"
built as a fix for a bug the audit reconfirmed, not a speculative feature.

**Technical-depth argument:** reliability engineering under a hard
constraint (free-tier quota) is itself a real data-platform skill — this
is the same category of tradeoff as caching a slow query or backing off a
flaky upstream API in a production pipeline.

Both features: 20 unit tests total (13 + 7), all green, alongside the full
existing suite. No regressions.

## 2. Screenshots

Desktop dark: `.prism/runs/2026-08-07/hypothesis_engine_dark.png`
Desktop light: `.prism/runs/2026-08-07/hypothesis_engine_light.png`
Mobile (390×844, also shows a pre-existing bug — see §3): `.prism/runs/2026-08-07/mobile_overview_dark.png`

No demo GIF this run — skipped in favor of spending the verification budget
on cross-theme screenshot review; static screenshots above cover the
feature end-to-end (empty state → heuristic run → CONFIRMED/NOT CONFIRMED
cards).

## 3. Audit findings (not built, logged for next run)

- **[High] Mobile layout break** — the fixed Atlas side panel doesn't
  collapse below ~640px width; on phone it overlaps nearly the entire main
  content column. This is the top-priority item for the next run — it
  breaks the "installable on phone" PWA claim on the primary interaction.
- **[Low] Light-theme leak** — `st.chat_input`'s bar keeps a hardcoded dark
  background under the "Arctic (Light)" theme.
- **[Info]** `google.generativeai` is upstream-deprecated in favor of
  `google.genai` — no functional break yet, flagged for a future migration
  run.

Full detail: `.prism/audit_2026-08-07.md`.

## 4. Research backlog (ranked, not built this run)

Full table with sources: `.prism/research_2026-08-07.md`. Top of backlog:

1. **Critic/adversarial pass on Auto Analyst's own findings** — same
   verify-don't-just-narrate pattern as Hypothesis Engine, applied to Auto
   Analyst's existing 5-finding synthesis instead of new hypotheses.
2. **polars/DuckDB-backed profiling for large files** — SQL Lab already
   depends on DuckDB; Overview/profiling is still pure pandas, no large-file
   performance story.
3. **Atlas proactive/unprompted insights** — the next JARVIS-copilot-track
   slice (one per run, per the routine's own cap); this run's slot went to
   the agentic-analysis priority theme instead.
4. PyGWalker-style drag-and-drop chart builder (competitor parity, lower
   technical depth than 1-3, deprioritized accordingly).

## 5. Interview notes (STAR bullets, verbatim-usable)

**Hypothesis Engine:**
> "I noticed our AI analyst tool would generate findings and just narrate
> them back with no verification — a hiring panel's first question would be
> 'how do you know that's real?' So I built a Hypothesis Engine that
> separates *proposing* a claim from *proving* it: it generates candidate
> hypotheses (via LLM or a deterministic correlation-ranking fallback), then
> runs the actual statistical test — t-test, ANOVA, chi-square, or Pearson,
> picked automatically by column type — and only marks something confirmed
> off a real p-value it computed itself, with normality assumption checks
> surfaced alongside. It works identically with zero API key configured,
> since the fallback path never depends on the LLM being available."

**Gemini caching/backoff:**
> "Our free-tier LLM eval was failing 9 of 25 questions to quota exhaustion
> mid-run. Instead of just widening the rate limit, I added an in-process
> LRU cache keyed on the exact prompt — so repeated identical questions,
> which happen constantly across our eval harness and multi-step agentic
> flows, cost zero extra API calls — plus short backoff retries for
> transient rate-limit errors before failing. It's the same pattern I'd
> reach for caching a slow upstream call or backing off a flaky API in a
> production data pipeline."

## 6. Recommendation for next run

Fix the mobile Atlas-panel overlap first — it's a correctness bug on the
app's stated core value prop (installable on phone), not a nice-to-have,
and should get its own dedicated run with full before/after screenshot
verification across all 6 themes given the CSS blast radius. Pair it with
the light-theme chat-input fix (same CSS review pass, low incremental
cost). Second priority: the Auto-Analyst critic pass (research item #1) to
extend this run's self-verification pattern to the app's existing flagship
feature, not just the new one.
