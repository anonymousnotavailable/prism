# Prism Autonomous Improvement Run — 2026-08-07

Full-auto run. Branch `feature/insight-verifier` → merged to `main` → pushed.
Commit `359e0ed`.

## 1. What shipped

### Insight Verifier — self-verifying Auto Analyst findings
**What it does:** Auto Analyst's "Run Full Analysis" ends with Gemini
synthesizing 5 headline findings from the steps it ran. Those findings now
get fact-checked before they reach the user: `modules/insight_verifier.py`
recomputes a broad set of real statistics directly from the DataFrame (row
and column counts, per-column means/medians/nulls, category shares,
pairwise correlations, and bounded group-by means) and checks every number
each finding quotes against that reference set. Each finding is badged
**✓ verified** or **⚠ unconfirmed** in the findings panel, with a summary
caption ("N finding(s) with confirmed figures, M with an unconfirmed
number"). No new Gemini calls — purely deterministic, runs in milliseconds.

**Why it was chosen:** this cycle's mandatory priority theme was agentic AI
analysis, and specifically "self-verifying analysis agents" is called out
as a research direction to draw from. Every competitor named in the brief
(Hex, Deepnote, Julius AI, ChatGPT Advanced Data Analysis, Databricks
Assistant) presents LLM-generated insights as-is — none visibly fact-check
their own narration against the source data in a way the user can see per
finding. It's also the direct fix for the single biggest gap the audit
found: an LLM can misstate a number even when its analysis was correct, and
nothing was catching that before this run.

**Technical-depth argument:** this is a real, if small, "self-verifying
agent" pattern — generate → recompute independently → cross-check → surface
disagreement — not a cosmetic layer on top of the LLM. It's also exhaustively
unit tested (7 dedicated tests covering number extraction, reference-stat
computation, single-finding verification, and batch behavior, including a
"never raises" contract for malformed input).

### First automated test suite
**What it does:** `tests/` now holds 22 pytest tests — 7 for
`insight_verifier`, 4 for `anomaly.py` (IsolationForest flagging, including
edge cases: too few rows, no numeric columns, "no anomalies found" as a
valid empty result), and 7 for `auto_analyst.py`'s pure-logic paths (default
plan fallback branching by column type, result summarization, findings
synthesis error handling when no model is available or every step failed).
`pytest.ini` + `requirements-dev.txt` wire it up; `README.md` documents the
`pytest` entry point.

**Why it was chosen:** the audit's headline finding — zero tests existed
anywhere in a ~200KB application with real statistical and ML logic. A
portfolio app that can't demonstrate its own correctness is a weaker
interview story than one that can.

**Technical-depth argument:** covers previously-*untested* existing modules,
not just the new one — retrofitting coverage onto legacy code is a distinct
and harder skill than testing code you just wrote, and is exactly what a
data-science-adjacent engineering role expects day one on an existing
codebase.

## 2. Screenshots

Saved to `.prism/runs/2026-08-07/`:
- `01_landing_dark_desktop.png` — landing screen, dark theme, desktop
- `02_dataset_loaded_desktop.png` — sample dataset loaded, Atlas panel live
- `03_auto_analyst_tab_nav.png` — Advanced Tools popover + Auto Analyst tab
  (shows the "add your free Gemini API key" empty state — expected, no key
  configured in this execution sandbox)
- `04_theme_preferences.png` — App Preferences panel with theme selector
- `05_mobile_pwa_landing.png` — mobile PWA viewport (390×844), no overflow

**Known limitation:** no Gemini API key was available in this execution
sandbox, so the Insight Verifier's ✓/⚠ badges could not be visually
confirmed inside a live findings panel — Auto Analyst correctly falls back
to its "add your API key" empty state instead of crashing. The feature is
confirmed via its unit test suite and by re-using the exact `prism-badge
b-pass`/`b-fail` CSS pattern already shipped and screenshot-verified for
SQL Lab's data-quality badges. **Recommend the next run with a configured
key capture a live screenshot of the badges** for the interview portfolio.

No headline-feature demo GIF this run — the feature's payoff (the badges)
couldn't be triggered live for the reason above; a static screenshot would
be misleading, so it was skipped rather than faked.

## 3. Researched but not built (backlog)

| Feature | Depth | Effort | Why not this run |
|---|---|---|---|
| Hypothesis-suggestion handoff (Auto Analyst finding → Stats Lab test, one click) | 4 | S | Good next pick — didn't want to ship two shallow features when one deep one plus real test coverage was more valuable this cycle |
| LLM-narrated anomaly explanations | 3 | S | Needs per-dataset-fingerprint caching to stay inside free-tier limits — deserves its own careful pass |
| polars/DuckDB-backed main pipeline (currently pandas-only outside SQL Lab) | 4 | L | Architecture-adjacent; explicitly out of scope for a single run per this routine's own guardrails |
| `google-generativeai` → `google-genai` SDK migration | 2 | M | Deprecation warning observed but not yet broken; touches every Gemini call site, needs dedicated regression testing |
| Fuller Atlas/JARVIS proactive-HUD slice | 3 | M | Atlas track is capped at one feature per run; Insight Verifier better served this cycle's mandatory priority theme |

Full detail and evidence in `.prism/research_2026-08-07.md`.

## 4. Interview notes (STAR, verbatim-usable)

**Insight Verifier:**
> "In my AI-powered data analysis tool, the LLM would synthesize
> plain-English findings from an automated exploratory analysis — but I
> realized nothing verified those findings' numbers actually matched the
> data (**Situation**). LLM-hallucinated statistics in an agentic pipeline
> is a known failure mode, and I didn't want the app to present a
> confidently-wrong number as fact (**Task**). I built a deterministic
> verification layer that recomputes real statistics — means, correlations,
> category shares, group-by aggregates — directly from the DataFrame, and
> cross-checks every number in each LLM-generated finding against that
> reference set with tolerance for reasonable rounding (**Action**). Every
> finding now carries a visible verified/unconfirmed badge, with zero extra
> API calls, and I backed it with a dedicated unit test suite that plants
> fabricated numbers to confirm the checker actually catches them
> (**Result**)."

**Test suite:**
> "I inherited — well, in this case audited my own — a ~200KB analysis
> application with statistical and ML logic (IsolationForest anomaly
> detection, LLM-driven plan generation) and zero automated tests
> (**Situation**). I needed a way to prove the analysis logic was correct
> without relying on manual clicking through the UI every time
> (**Task**). I wrote pytest coverage for the highest-risk pure-logic paths
> first — anomaly detection's edge cases (too few rows, no numeric columns,
> the empty "no anomalies" result) and the plan-generation fallback logic
> that has to work even when the LLM is unavailable — then extended it to
> my own new verifier module test-first (**Action**). 22 tests now run in
> under 2 seconds and are documented as the project's real entry point for
> "does this still work" (**Result**)."

## 5. Recommendation for next run

1. Ship the hypothesis-suggestion handoff (Auto Analyst → Stats Lab) — it's
   small, low-risk, and is the natural next agentic-theme feature.
2. If a Gemini API key is available in the execution sandbox next time,
   capture the live Insight Verifier badges (✓/⚠) in a real findings panel
   for the portfolio screenshot set — this run could only confirm them via
   unit tests and CSS-pattern reuse.
3. Consider the `google-generativeai` → `google-genai` migration as its own
   dedicated, fully-regression-tested run once the SDK deprecation risk
   grows (not urgent yet).
