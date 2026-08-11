# Prism Autonomous Improvement Routine — Run 28 Report

**Date:** 2026-08-11
**Branch:** `claude/adoring-meitner-7xxgfq` (synced from Run 27 tip `c98bdfb`, pushed to `134eb48`)

## What shipped

### 1. Multiclass (one-vs-rest) ROC/PR curves — `modules/mllab.py`

`compute_roc_pr_curves()` previously carried an explicit "deliberately
binary-only" comment and returned `None` for any target with more than 2
classes. This run extends it to N-class targets via the standard
one-vs-rest (OvR) scheme: each class gets its own binary "this class vs.
everything else" ROC and Precision-Recall curve, plus a macro-averaged
(unweighted mean across classes) AUC/AP as the single headline number —
scikit-learn's own documented approach to multiclass ROC-AUC.

- `compute_roc_pr_curves()` now returns `{"mode": "binary" | "multiclass", ...}`
  so callers can branch on shape; binary behavior is byte-for-byte
  unchanged (existing tests pass unmodified except for the one that
  asserted `None` for multiclass, which now asserts real curves).
- New `build_multiclass_roc_chart(curves, model_name)` and
  `build_multiclass_pr_chart(curves, model_name)` — one line per class,
  titled with the macro-AUC/AP.
- New `multiclass_roc_pr_verdict(curves)` — plain-English summary naming
  the single weakest-performing class by per-class AUC (the class most
  likely being confused with the others, worth checking in the
  confusion matrix first).
- `app.py` ML Lab tab: replaced the prior "shown for binary
  classification only" caveat with a live model selector and both
  multiclass charts + verdict for 3+ class targets.

**Why this over cosmetic alternatives:** classification metrics were
capped at accuracy + weighted F1 + a confusion matrix for anything but
binary targets — exactly where accuracy is most misleading (multiclass
with class imbalance) and no threshold-independent quality signal
existed at all. This closes that gap using the same statistically
standard technique (OvR) already implicitly used by scikit-learn's own
multiclass ROC-AUC utilities, not a bespoke heuristic.

### 2. "Export as Python Script" for ML Lab — `modules/mllab.py` + `app.py`

New `export_baseline_script(feature_cols, target_col, task_type,
use_smote, original_filename)` generates a standalone, runnable `.py`
file that reproduces the exact ColumnTransformer preprocessing pipeline
(median-impute + scale numerics, most-frequent-impute + one-hot
categoricals), the 80/20 train/test split (`random_state=42`, matching
the in-app run), optional SMOTE resampling on the training set only, and
both baseline models (Logistic/Linear Regression + Random Forest) with
printed metrics and a confusion matrix for classification.

- Mirrors the existing `cleaning.export_script()` pattern (which only
  replays cleaning-log steps) but scoped specifically to the ML Lab
  baseline-model pipeline — the training pipeline itself had no
  reproducible-script path before this.
- Wired into `app.py` as a `st.download_button("📄 Export as Python
  Script", ...)` next to the feature-importance chart, using the same
  feature/target/task-type/SMOTE choices the user already made for the
  in-app run.
- Handles regression vs. classification model swaps, an empty feature
  list, and column names with special characters (all `!r`-quoted, not
  string-interpolated raw).

**Why this over cosmetic alternatives:** reproducibility ("analyses
that can be re-run as data updates") was independently flagged by Run
27's own DA/DS job-posting research as a top-cited 2026 industry
priority, and Prism already had this pattern proven out for cleaning
steps — the model-training pipeline was the one piece of ML Lab that
could only ever be reproduced by re-clicking through the app, never
handed to a colleague, checked into a repo, or run in a scheduled job.

## Technical-depth argument

Both features are genuine statistical/software-engineering closures, not
UI polish:
- Multiclass ROC/PR required correctly handling per-class label presence
  in a *test set* (a class can be OvR-computable in the label set but
  have zero test-set representatives after the 80/20 split — handled by
  skipping that class's curve rather than crashing or silently
  fabricating a degenerate curve), plus a genuine macro-averaging
  decision (unweighted mean, consistent with scikit-learn's
  `average="macro"` convention) rather than a shortcut.
- Script export required faithfully mirroring `run_baseline_models()`'s
  exact preprocessing/split/SMOTE logic in generated *string* code
  (not just describing it), including safe `!r` quoting for arbitrary
  column names and correct reader selection (`read_csv` vs.
  `read_excel`) — verified by literally executing the generated code as
  a subprocess in CI-style round-trip tests, not just eyeballing the
  string output.

## Verification evidence

Playwright/Chromium was **not** retried this run — confirmed blocked by
sandbox egress policy for 4 consecutive runs now (25 through 28), and
this run's own brief explicitly said to stop re-litigating a confirmed-
stable policy and go straight to the fallback. Verification used:

1. **Full pytest suite**: 543 → 564 passed, zero regressions (`python3
   -m pytest -q`). Breakdown: 543 baseline + 10 net new in
   `test_mllab_roc_pr.py` (22 tests, was 9 before edits removed one and
   added many net +10) + 11 new in `test_mllab_script_export.py`.
2. **Live `streamlit run` smoke test**: run twice — once per feature
   branch before merging, once after both `--no-ff` merges landed on
   `claude/adoring-meitner-7xxgfq`. Each time: `curl` to `localhost:8501`
   returned HTTP 200 and the server log showed no tracebacks, just the
   normal "You can now view your Streamlit app" banner.
3. **Direct function-level verification against a real sample CSV**
   (`samples/hr_data.csv`, a genuine 6-class `department` target):
   - `compute_roc_pr_curves()` correctly returned `mode: "multiclass"`
     with 6 per-class curves and a macro-AUC of 1.000 (department is
     near-perfectly predictable from `job_title` in this sample, so a
     saturated AUC is the *correct* result, not a bug — confirmed by
     inspecting the confusion matrix, which is a clean diagonal).
   - `export_baseline_script()` was called with the *exact same*
     feature/target/task-type configuration, written to disk, and run
     as `python3 exported_hr.py` in a clean subprocess — it printed
     `Baseline: accuracy=1.0000, f1=1.0000` / `Random Forest:
     accuracy=1.0000, f1=1.0000` plus a matching diagonal confusion
     matrix, confirming the exported script is a literal, faithful
     reproduction of the in-app run and not just plausible-looking text.
4. `ast.parse(open("app.py").read())` syntax-checked after every edit.

## Backlog not built this run

- **DBSCAN/hierarchical clustering** (Run 27's candidate #3, its other
  offered option alongside script export) — deliberately set aside to
  avoid stacking both of this run's features on Clustering/ML-adjacent
  statistics right after Run 27's own diversification effort. Still a
  real, open gap (`clustering.py` remains KMeans-only, no noise/outlier-
  aware alternative) — no reason it's gotten worse, good Run 29
  candidate if the theme-balance math favors it.
- **Difference-in-Differences causal estimator** (`causal_inference.py`)
  and **broader reproducible-script export across Clustering/Stats
  Lab/Forecasting** (beyond this run's ML-Lab-scoped slice) — both still
  flagged too large for a single two-feature run per Run 27's research;
  unchanged assessment.
- Full ranked table with rationale remains in `.prism/research_2026-08-
  11-run27.md`.

## STAR bullets

**Multiclass ROC/PR curves**
- **Situation:** ML Lab's classification evaluation was capped at
  accuracy + weighted F1 + a confusion matrix for any target with more
  than 2 classes — no threshold-independent quality signal at all, with
  a comment in the code explicitly marking multiclass as out of scope.
- **Task:** Close the gap without a UI/scope explosion (per-class curves
  need a defensible aggregation and a way to pick which curve to look
  at).
- **Action:** Implemented the standard one-vs-rest scheme with
  macro-averaged AUC/AP, added a model-selectable multiclass chart pair
  and a verdict naming the weakest class, and handled the edge case
  where a class exists in the label set but not in a given train/test
  split's test fold.
- **Result:** 22 tests (was 9) covering 3-class and 4-class synthetic
  targets, curve-shape/bounds invariants, macro-average correctness, and
  verdict content; verified against a real 6-class HR dataset end to
  end.

**"Export as Python Script" for ML Lab**
- **Situation:** Prism's cleaning pipeline already had a proven
  "export as reproducible script" pattern, but the ML Lab model-training
  pipeline — arguably the more valuable half to reproduce outside the
  app — had none.
- **Task:** Add a scoped, faithful script exporter for just the ML Lab
  baseline-model run (deliberately not all of ML Lab/Stats Lab/
  Clustering, which Run 27's research flagged as too broad for one
  slice) without silently drifting from what `run_baseline_models()`
  actually does.
- **Action:** Generated code that mirrors the real preprocessing/split/
  SMOTE/model-fit logic line-for-line, with safe `!r`-quoting for
  arbitrary column names, and proved fidelity with subprocess round-trip
  tests that actually execute the generated script rather than just
  asserting on its text.
- **Result:** 11 new tests including 3 full round-trip executions
  (classification, regression, SMOTE-on-imbalanced-data); manually
  verified against `samples/hr_data.csv` that the exported script's
  printed metrics match the in-app run's configuration exactly.

## Run 29 recommendation

Two reasonable directions, either fits a single two-feature run:

1. **DBSCAN/hierarchical clustering** for `clustering.py` (Run 27's
   deferred candidate #3) — safe to build now since this run avoided
   stacking on Clustering, giving it a full run's gap. Adds a
   density/hierarchy-aware alternative to the current KMeans-only
   approach, with genuine noise/outlier detection KMeans structurally
   can't offer.
2. **A fresh Phase 2 research sweep** — Run 27's ranked table is now
   fully exhausted of small/medium picks (both #1/#2 shipped Run 27,
   #5/#6-scoped shipped this run); the two remaining unbuilt candidates
   (#3 DBSCAN, #4 Difference-in-Differences, #6-full breadth) are either
   already covered above or explicitly flagged too large for one run.
   Run 29 should do a fresh external sweep per the routine's own
   "backlog thin" rule rather than stretch the same table further.

Recommend: DBSCAN/hierarchical clustering as one pick (small, safe,
well-understood), paired with one fresh-sweep-sourced pick for the
second — avoids a fifth consecutive run leaning on the same research
artifact while still shipping a known-good, low-risk item.
