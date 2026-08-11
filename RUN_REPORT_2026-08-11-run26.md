# Prism Autonomous Improvement — Run 26 (2026-08-11)

## Summary

Run 25 closed conformal prediction intervals and k-fold cross-validation
for ML Lab, and recommended silhouette-score cluster validation as Run
26's strongest remaining backlog item. This run built that, plus a
second gap found by re-reading `modules/mllab.py` directly:

1. **Silhouette-Score Cluster Validation** — the Clustering tab's K
   suggestion is now a hybrid elbow + silhouette method instead of
   elbow alone, and the resulting clustering gets a plain-English
   silhouette-score verdict.
2. **ROC-AUC / Precision-Recall Curves** — ML Lab's binary classification
   baseline now reports threshold-independent quality metrics, not just
   accuracy/F1/confusion matrix.

Both are pure local scikit-learn compute (zero Gemini calls, zero
free-tier rate-limit exposure). Full test suite: 479 green before this
run → 510 green after (31 new tests, zero regressions). Merged to
`claude/adoring-meitner-7xxgfq` and pushed.

## Why these two

Both gaps were confirmed real by reading the code directly, not just
searching:

- `grep -rn "silhouette" modules/*.py tests/*.py` → zero hits.
  `clustering.py`'s `suggest_k()` only ever computed KMeans inertia
  (elbow method); the Clustering tab never surfaced any independent
  cluster-quality signal.
- `grep -rln "roc_auc|roc_curve|precision_recall_curve|calibration"
  modules/*.py` → only an unrelated string match in `hellmode.py`
  ("recalibration"). Reading `run_baseline_models()` in full confirmed
  classification metrics were capped at accuracy + weighted F1 + a
  confusion matrix — despite the tab already having a class-imbalance
  detector and SMOTE resampling, exactly the scenario where accuracy is
  most misleading.

A light web-search sanity check (per this run's Phase 2 instruction)
confirmed both are still current, uncontested 2025/2026 best practice:
elbow narrows a candidate K range, silhouette picks the winner within
it; and for imbalanced classification, "the consensus is to use both
ROC-AUC and Precision-Recall curves together, with PR-AUC being
particularly valuable for understanding performance on the minority
class." No full fresh research sweep was needed since both picks were
already well-scoped and verifiably open — see
`.prism/routine_log.md`'s Run 26 entry for the full reasoning and
sources.

Neither feature touches the Atlas/JARVIS copilot track (0 this run,
under the 1/run cap) and neither is the agentic-AI-analysis theme (last
shipped Runs 22/23, not mandatory every run) — both are pure
statistical/ML-rigor closures on existing tabs, matching this run's
"reject cosmetic polish, prefer statistical rigor / ML / reproducibility"
filter.

## What shipped

### 1. Silhouette-Score Cluster Validation (`modules/clustering.py`)

`suggest_k()` now fits KMeans once per K (as before) but also scores
each fit with `sklearn.metrics.silhouette_score`. The elbow method
(sharpest inertia drop-off) narrows to a rough candidate, then the
final suggested K is whichever K in a small window around that
candidate has the best silhouette score — combining both signals
instead of trusting either alone, since inertia decreases monotonically
with K by construction and can't by itself distinguish a genuinely good
K from an arbitrary one.

New functions: `compute_silhouette_scores()`, `build_silhouette_chart()`,
`silhouette_verdict()`. `run_clustering()` now also returns the chosen
K's mean silhouette score. UI: a second chart (silhouette score by K)
shown alongside the existing elbow chart, and a plain-English verdict
below the cluster scatter plot using the standard Kaufman & Rousseeuw
interpretation bands (strong/reasonable/weak/no real structure).

Verified with 19 new tests using `sklearn.datasets.make_blobs` —
well-separated synthetic blobs correctly recover the true cluster count
(e.g., 3-center blobs → suggested K=3, silhouette > 0.5) and score-band
verdicts match expected text for each range.

### 2. ROC-AUC / Precision-Recall Curves (`modules/mllab.py`)

`run_baseline_models()` now also returns `fitted_models` (both Baseline
and Random Forest, not just the Random Forest kept for SHAP) and
`y_test`, so curves can be built without a second fit.
`compute_roc_pr_curves()` is deliberately binary-classification only —
multiclass ROC/PR needs a one-vs-rest scheme with its own UI decision,
out of scope here — and returns per-model ROC curve + AUC and
Precision-Recall curve + average precision, plus the no-skill baseline
rate (share of the test set that's the positive class).

New functions: `compute_roc_pr_curves()`, `build_roc_chart()`,
`build_pr_chart()`, `roc_pr_verdict()`. UI: wired in right after the
confusion matrix — side-by-side ROC and PR charts (both models
overlaid, plus reference lines) and a verdict that explicitly flags
when the positive class is skewed enough that the PR curve should be
weighted over ROC-AUC alone. Multiclass targets get a graceful
explanatory caption instead of a fabricated chart.

12 new tests, plus a real-data check against `samples/hr_data.csv`
(attrition prediction from department/job_title only): both models
scored **84.75% accuracy** — looks solid — but **ROC-AUC came out
~0.45 (0.447 Baseline / 0.453 Random Forest), worse than random
guessing**, with the verdict correctly
flagging the imbalanced positive class and recommending the PR curve
over ROC-AUC. This is exactly the accuracy-hides-a-broken-model failure
mode the feature exists to catch, caught live on real data, not just in
synthetic unit tests.

## Verification

- Full test suite: 479 → 510 passing, zero regressions
  (`python3 -m pytest -q`).
- 31 new tests: `tests/test_clustering.py` (19, first direct test
  coverage for `modules/clustering.py`) and `tests/test_mllab_roc_pr.py`
  (12, first direct test coverage exercising
  `run_baseline_models()`'s classification path end-to-end).
- App launches cleanly on the merged branch (`streamlit run app.py`,
  HTTP 200, no traceback in server logs), checked both after each
  individual feature merge and again after both merges landed.
- Both features were also exercised directly against real sample data
  (`samples/hr_data.csv` for ROC/PR) rather than only synthetic test
  fixtures, surfacing a genuine real-world example of the failure mode
  each feature is designed to catch.

### Screenshot verification not performed this run

Playwright's Chromium download was checked again this run
(`python3 -m playwright install chromium`) and still fails:
`Download failed: server returned code 403 body 'request rejected: host
not permitted'. URL: https://cdn.playwright.dev/...` — confirmed via
`curl $HTTPS_PROXY/__agentproxy/status` as a policy denial, not a cert
or setup issue, same blocker Run 25 hit. No browser automation was
available this run.

As with Run 25, this is a lower-risk gap: both new UI sections reuse
standard Streamlit widgets (`st.plotly_chart` in `st.columns`,
`st.caption`, `st.expander`) placed inside already-existing tab
containers (Clustering, ML Lab), no new CSS or custom layout. Verified
instead via a live server smoke test (`streamlit run app.py`, HTTP 200,
clean logs) plus direct function-level runs against real sample CSVs
end-to-end. Worth a screenshot pass in both themes once Playwright
access returns, per the same note Run 25 left.

## Backlog not built this run

- Multiclass ROC/PR (one-vs-rest per-class curves or macro-average) —
  deliberately deferred as a separate, smaller follow-on to keep this
  run's scope tight and low-risk; the binary case covers the majority
  of real classification datasets and is where accuracy is most
  commonly misleading.
- Pandera-style schema/data-contract validation (Run 25's research
  candidate #4) — still has meaningful overlap with the existing
  `drift.py` new/missing-category detection; needs clearer
  differentiation before it's worth building separately.
- Polars/DuckDB backend adoption — explicitly out of scope per this
  run's "no architecture rewrites" guardrail; still only a proposal.
- Light-theme repaint lag, mobile-viewport Playwright gap, Atlas/HUD
  maturity, live-Gemini verification — unchanged from prior runs'
  backlog notes; still cosmetic/out-of-scope/structural.

## STAR-style interview bullets

**Silhouette-Score Cluster Validation:**
> Identified via direct grep + code reading that Prism's Clustering tab
> suggested K using only the elbow method (KMeans inertia drop-off),
> which by construction can't distinguish a genuinely good clustering
> from an arbitrary one since inertia decreases monotonically with K.
> Implemented the standard hybrid remedy — elbow to narrow a candidate
> range, silhouette score to pick the winner within it — confirmed
> against current 2025/2026 sources as still uncontested best practice,
> plus a plain-English silhouette verdict using the standard
> Kaufman & Rousseeuw interpretation bands. Verified true-cluster-count
> recovery on synthetic separable blobs (`sklearn.datasets.make_blobs`)
> with 19 new tests — the first direct test coverage `modules/
> clustering.py` had received across 25 prior improvement runs.

**ROC-AUC / Precision-Recall Curves:**
> Found that ML Lab's baseline classification runner reported only
> accuracy/F1/confusion matrix despite already having a class-imbalance
> detector and SMOTE option — exactly the condition under which
> accuracy is most misleading. Extended the existing model-fit output
> (zero re-training cost) to add binary ROC-AUC and Precision-Recall
> curves with a verdict that explicitly recommends PR over ROC-AUC when
> the positive class is skewed, then proved the value live against a
> real HR attrition dataset where accuracy showed 84.75% but ROC-AUC
> revealed the model was performing worse than random guessing —
> catching the exact failure mode the feature was built to surface, not
> just passing synthetic unit tests.

## Recommendation for Run 27

The verifiably-open, non-cosmetic backlog is now thin again after this
run closes both of Run 25's strongest candidates. Recommend:

1. **Multiclass ROC/PR** (one-vs-rest per-class curves, small and
   focused) as a quick follow-on if a small, low-risk feature is
   wanted, **or**
2. **A fresh Phase 2 research sweep** — this is the more likely right
   call, since the two most recent sweeps (Run 25's and this run's
   lighter check) have both been substantially spent. Prism's
   statistical/ML toolkit is now quite deep (SHAP, OLS diagnostics,
   conformal prediction, k-fold CV, silhouette validation, ROC/PR) —
   Run 27 should look outward again at competitor tools (Hex/Deepnote/
   Julius AI/ChatGPT ADA/Databricks Assistant), the polars/DuckDB
   ecosystem, and fresh agentic-EDA research rather than mining this
   run's leftovers, which are now genuinely secondary in scope.

Also worth flagging structurally: Playwright/Chromium has now been
blocked by sandbox egress policy for at least two consecutive runs
(confirmed independently both times via the agent-proxy status
endpoint and a real `playwright install` attempt, not assumed). If this
persists, a future run might consider whether the routine's
verification protocol should formally adopt AppTest + live-smoke-test
as the standing default rather than treating it as a per-run fallback
to rediscover.
