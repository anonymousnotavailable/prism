# Prism Autonomous Improvement Run — 2026-08-10

## Branch note (read this first)

This session was assigned a designated branch,
`claude/adoring-meitner-flrait`, with a hard rule: develop and push only
there, never push to a different branch (including `main`) without
explicit permission, and never open a pull request unless asked. That
constraint takes precedence over this routine's own Phase 7 instruction to
merge features into `main` and push it directly. **Everything below is
committed and pushed to `claude/adoring-meitner-flrait`, not `main`.**

To land it once reviewed:
```
git fetch origin claude/adoring-meitner-flrait
git checkout main && git merge --ff-only origin/claude/adoring-meitner-flrait
git push origin main
```
(A fast-forward is possible because this branch was cut directly from
`main`'s current tip and nothing else has landed on `main` since.)

## What shipped

### 1. Anomaly Narration

**What it does:** In the Overview tab's Anomaly Detection expander, after
"Find Anomalies" flags rows via IsolationForest, a new **🧠 Explain these
anomalies** button asks Gemini to read the flagged rows' `anomaly_reason`
strings and write 2-4 sentences: what pattern connects the flags (a shared
driver column, or "these look scattered/independent"), plus one concrete
next action. If Gemini isn't available — no API key, rate-limited, quota
exceeded, safety-filtered — it falls back to `deterministic_narration()`,
a template that parses the same `anomaly_reason` strings to name the most
common driver column and its share of the flagged set, so the feature
always says something specific instead of showing a dead-end error.

**Why chosen:** This cycle's mandatory theme is agentic AI analysis, and
this was an explicit backlog item from the 2026-08-07 Run 1 log ("a
genuinely agentic upgrade would have Gemini narrate the flagged set... do
not rebuild"). Competitor research (Julius AI, Deepnote alternatives
coverage) confirms "LLM explains why an anomaly matters + suggests next
steps" is now table-stakes for AI data tools, not a differentiator to skip.

**Technical-depth argument:** Reuses the shared `ai_analyst.call_gemini()`
path (same per-session rate limiter, same quota/safety-filter error
handling as every other Gemini call in Prism) rather than a bespoke call,
so it costs nothing extra against the free-tier budget and inherits
existing hardening. The deterministic fallback isn't just a "sorry" message
— it re-derives a real answer (most common driver column, its share of
flags) from data already computed, which is the harder, more defensible
design than an LLM-or-nothing feature.

### 2. Feature Selection Engine

**What it does:** New "Feature Selection Engine" section in ML Lab, above
the existing Baseline Model Runner. Click "🎯 Rank features" and every
candidate column is scored three independent ways against the chosen
target — mutual information, an ANOVA/F-test, and an L1-regularized linear
model's (LogisticRegression/Lasso) kept coefficient magnitude — then the
three per-method ranks are averaged (Borda count) into one combined score.
An elbow heuristic recommends how many top features to keep (the smallest
prefix covering ~80% of total combined importance) and pre-selects them in
the feature multiselect below, so a user can go straight from "rank" to
"train" with a sensible default instead of guessing.

**Why chosen:** Highest technical-depth score on this run's research
table, and an explicit unbuilt backlog item from 2026-08-07 Run 2
("Feature Selection Engine (mutual info, RFE, L1) for ML Lab"). Feature
relevance/selection shows up repeatedly in 2026 data-analyst interview
prep material as expected applied-ML ground, distinct from the
model-fitting ML Lab already covers.

**Technical-depth argument:** Rank aggregation (Borda count) across
heterogeneous scoring methods is a real, citable technique for exactly the
problem it solves here — combining scores on incompatible scales (bits of
mutual information vs. F-statistics vs. regression coefficients) without
inventing an ad hoc weighting. Handling categorical columns (label-encoded
for ranking only, not for the actual training pipeline downstream), rows
with missing values (dropped, not silently NaN-propagated), all-null
columns (excluded, not a crash), and single-class targets (explicit error)
are the kind of edge cases a take-home ML exercise is specifically graded
on. Zero LLM calls — pure scikit-learn, already a hard dependency via
`mllab.py`/`anomaly.py`, so no free-tier exposure at all.

## Screenshots

All in `.prism/runs/2026-08-10/`:

- `anomaly_narration_desktop_dark.png` / `anomaly_narration_desktop_light.png`
  — the Stocks sample dataset, 20 rows flagged, narration panel showing
  the real deterministic-fallback text (no Gemini key configured in this
  sandbox, so this is the failure-handling path exercised for real, not
  mocked).
- `feature_selection_desktop_dark.png` / `feature_selection_desktop_light.png`
  — the Startup Funding sample dataset, target=`sector`, ranked table +
  "Recommended: top 5 feature(s)" caption + pre-selected multiselect.
- `anomaly_narration_mobile_dark.png` — does **not** show the feature
  cleanly; it documents a pre-existing bug instead (see Incident note
  below).

## Research not built (ranked backlog for future runs)

See `.prism/research_2026-08-10.md` for the full table with evidence
links. Highlights, best next picks first:

1. **Data Quality Score — exportable scorecard.** The score itself already
   ships (`data_engine.get_health_breakdown`); this is just wiring an
   export button (JSON/CSV) around existing data. S effort, low risk,
   quick portfolio-visible win for whichever run has spare budget.
2. **Convert `eval/*_eval.py` scripts to real `tests/*.py` pytest files.**
   Not a feature, but the single highest-leverage correctness fix
   available — three shipped modules currently have zero pytest coverage
   despite the changelog implying otherwise. See Incident/Audit note.
3. **Fix the mobile Atlas-panel overlap (~390px).** Confirmed a second
   time this run; now a prerequisite for any new Atlas UI and actively
   costing verification time on unrelated features.
4. **Atlas Proactive Insights (JARVIS copilot track)** — blocked on #3.
5. **`google-generativeai` → `google-genai` migration** — still flagged by
   two prior runs as needing its own dedicated pass.
6. Advanced Outlier Detection (LOF, DBSCAN), polars/DuckDB large-file path
   — unchanged status from 2026-08-07's backlog.

## Interview notes (STAR-style, verbatim-usable)

**Anomaly Narration:**
> "I added an LLM narration layer on top of an existing IsolationForest
> anomaly detector — the model already flagged which rows were unusual and
> which column drove each flag, but a data analyst still had to read a
> table of numbers to find the pattern. I had Gemini synthesize that table
> into a short explanation and a suggested next action, routed through the
> app's existing rate-limited API wrapper so it couldn't blow the free-tier
> quota. The part I'm most proud of is the failure path: if the API call
> fails for any reason, I don't just show an error — I fall back to a
> deterministic summary that parses the same structured reason strings the
> model would have read, so the feature still gives a real, specific
> answer instead of a dead end."

**Feature Selection Engine:**
> "I built a feature-ranking tool for the ML Lab that combines three
> different feature-importance signals — mutual information, an ANOVA
> F-test, and an L1-regularized model's surviving coefficients — because
> each one has a different blind spot on its own. I used Borda-count rank
> aggregation to combine them onto one comparable scale instead of trying
> to normalize wildly different units like F-statistics and regression
> coefficients directly. I also wrote the edge-case handling first as
> tests before the implementation — all-null columns, single-class
> targets, missing values — because those are exactly the inputs a messy
> real-world dataset (or an interviewer's take-home) will actually throw
> at it."

## Incident / honesty notes

- **The "82 new unit tests" claim in the 2026-08-07 changelog entries
  doesn't hold up.** Those checks exist and run cleanly, but as
  `eval/*_eval.py` custom scripts, not `tests/*.py` pytest files —
  `pytest tests/` today does not exercise `auto_insights.py`,
  `regression_diagnostics.py`, or the STL addition to `forecasting.py` at
  all. Not a claim I'm making about today's work (today's 21 new tests
  are real `tests/*.py` files, verified: `pytest tests/ -q` → `44 passed`)
  — flagging it because the routine's own memory file should be accurate
  for whoever reads it next.
- `pytest tests/` fails to even collect on a fresh `pip install -r
  requirements-dev.txt` — `cryptography` (pulled in transitively by
  `google-generativeai`) needs `cffi`, which isn't pinned.
  `pip install cffi` fixes it; not added to `requirements-dev.txt` this
  run (small, safe, but touching dependency pins wasn't this run's job —
  flagged for the next run instead).
- Mobile screenshot verification for this run's anomaly narration feature
  was not possible — the pre-existing Atlas-panel mobile overlap bug
  (first documented 2026-08-07 Run 2) swallows the main content column at
  ~390px width. Confirmed again, screenshot kept as evidence rather than
  discarded.
- Found, not fixed: Arctic (Light) theme leaves `st.dataframe`/Plotly/
  Atlas-panel chrome dark. Pre-existing and app-wide (visible on elements
  this run didn't touch too), so out of scope for a feature-shipping run;
  logged for a dedicated theming pass.

## Recommendation for next run's focus

1. Fix the mobile Atlas-panel overlap first — it's now blocking clean
   verification of unrelated features two runs running, and it's a
   prerequisite for the still-open Atlas/JARVIS-copilot-track backlog
   item.
2. Port `eval/*_eval.py` into real `tests/*.py` files — mechanical, low
   risk, closes a real coverage gap, and stops future runs from citing
   test counts that don't actually run in CI.
3. Then pick up the Data Quality exportable scorecard (small, high
   portfolio visibility) and/or the Arctic-light theming fix.
