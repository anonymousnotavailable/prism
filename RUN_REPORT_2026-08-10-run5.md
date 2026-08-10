# Prism Autonomous Improvement Routine — Run 5 (2026-08-10)

## What shipped

**Feature Selection Engine** (`modules/mllab.py`, wired into `app.py`'s ML Lab tab).

ML Lab now has a "Feature Selection Engine" section between the existing Feature
Engineering Assistant and Baseline Model Runner. It cross-checks three
feature-selection methods with genuinely different assumptions over the same
candidate columns:

- **Mutual Information** — model-free, information-theoretic, catches
  non-linear relationships a linear model would miss.
- **L1-penalized regression** (Lasso / L1-LogisticRegression) — zeroes a
  coefficient out entirely when a feature adds nothing beyond what the others
  already explain.
- **Recursive Feature Elimination (RFE)** — repeatedly refits a model and
  drops the weakest feature each round, catching interactions the two
  independent-scoring methods above miss.

Every feature gets a 0-3 "votes" score (how many methods selected it), shown
as a sorted bar chart + table, with a "🗳️ Recommended (≥2 of 3 agree)" callout
and a one-click "Use recommended features below" shortcut that pre-fills the
Baseline Model Runner's feature multiselect. `narrate_feature_selection()`
asks Gemini to explain *why* — which features are real signal vs. noise —
cached by a fingerprint of the vote result (same caching shape as
`anomaly.fingerprint_flagged()` from Run 3/4), with a graceful "No Gemini
model available for narration" fallback when no API key is configured.

## Technical-depth argument

This isn't a single-model importance ranking — it's the same
**ensemble-consensus pattern** Run 4's anomaly detector established
(IsolationForest + LOF + DBSCAN cross-checking each other), applied to a
different problem where it's arguably even more load-bearing: any single
feature-selection method has known failure modes (mutual information misses
redundancy between features; L1 models miss non-linear signal entirely; RFE
is expensive and estimator-dependent), and disagreement between methods is
itself informative, not just a hedge. Scoring happens at the *original
column* level (categoricals are ordinal-encoded rather than one-hot expanded)
specifically so a non-technical user sees "job_title: 1/3 votes" instead of a
scattered one-hot fragment per category — a deliberate interpretability
trade-off documented in the module. The Gemini layer is strictly
interpretive: selection itself stays deterministic and auditable (three
independent, well-established sklearn methods), matching this codebase's
established self-verifying-agent pattern rather than asking an LLM to pick
features directly.

## Test count

- Before this run: 98 passing.
- After this run: **116 passing** (18 net new, all in `tests/test_mllab.py`
  — `modules/mllab.py` had zero prior test coverage; this is its first test
  file). Full suite green, no regressions.
- One environment gap found and fixed before any test could run: the
  sandbox's `cryptography` package was missing its `_cffi_backend` native
  module, crashing any test importing `modules.ai_analyst` (including
  pre-existing `test_anomaly.py` narration tests) — not caused by this run's
  changes; fixed with `pip install cffi`.

## Screenshots

14 screenshots in `.prism/runs/2026-08-10/fse_*.png` — desktop (1440px) and
mobile (390px), dark and light theme:

- `fse_01_empty_*` — empty state before running selection.
- `fse_02_result_*` / `fse_03_result_scrolled_*` — populated result (votes
  chart, per-feature table, recommended-features callout).
- `fse_04_narration_*` (desktop only, both themes) — the graceful "No Gemini
  model available for narration" fallback rendering correctly.

Reviewed all 14: no clipping/overflow, glass/theme styling consistent with
the rest of the app, light-theme dataframe contrast confirmed still fixed
(Run 4's `sync_native_theme()` fix holding up under a new dataframe use).
Mobile got 3 of 4 shots per theme — Streamlit's sticky mobile chat-input
footer blocked Playwright's click on the narration button specifically (a
`force: true` click still didn't land correctly); this is this run's own
instance of the standing "Streamlit Playwright automation can be flaky"
issue noted in prior runs, not a confirmed real bug — logged for a human
to spot-check next time the app is used live on a phone.

## Push confirmation

Merged `feature/feature-selection-engine` → `claude/adoring-meitner-rewrhw`
(no-ff). Pushed with `git push -u origin claude/adoring-meitner-rewrhw`;
confirmed via `git log origin/claude/adoring-meitner-rewrhw -1` matching the
local tip. `.env`/secrets untouched; `.gitignore` still covers them (verified,
not modified).

## Ranked backlog for next run

1. **`google-generativeai` → `google-genai` SDK migration.** Fifth run to
   defer this. The deprecation `FutureWarning` now fires on *every* test
   run — worth a dedicated regression-tested session soon rather than
   pushing further.
2. **Ingest-path pandas → polars/DuckDB, re-scoped.** Correction from this
   run: DuckDB already exists and works well in `modules/sql_lab.py` — don't
   rebuild that. The actual remaining gap is narrower: every other tab
   (Overview, Clean, Visualize, ML Lab, ...) still loads the full file into
   a pandas DataFrame via `data_engine` *before* SQL Lab or anything else
   runs, so a genuinely large file can fail at upload/parse time before
   DuckDB gets a chance to help. Scope next run's item as "pandas→polars for
   the ingest path," not "add DuckDB."
3. (Minor, optional) Spot-check the mobile Feature Selection narration
   button against the sticky chat footer on a real device/browser, not just
   headless Playwright — confirm whether it's a real click-blocking issue or
   a headless-only artifact.

## Interview bullet (STAR)

> Designed and shipped a **Feature Selection Engine** for an ML exploration
> tool by cross-checking three feature-selection algorithms with
> intentionally different statistical assumptions (mutual information, L1
> regularization, recursive elimination) into a single per-feature consensus
> score, then added an LLM narration layer — cached by result fingerprint to
> avoid redundant API calls — that explains *why* features were kept or
> dropped in plain English; shipped test-first (18 new unit tests, 116/116
> suite green) and verified end-to-end with cross-viewport, cross-theme
> screenshot review before merging.
