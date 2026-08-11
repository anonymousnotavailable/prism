# Prism Autonomous Improvement — Run 29 Report (2026-08-11)

## Summary

Shipped two features, both merged cleanly into `claude/adoring-meitner-7xxgfq`:

1. **DBSCAN + Agglomerative Hierarchical clustering** for the Clustering tab (`modules/clustering.py`)
2. **Market Basket Analysis (Apriori association rules)** for Domain Lens → Product Analytics (`modules/market_basket.py`, new module)

Test suite: **564 → 611 passing, zero regressions.** App verified to launch cleanly (HTTP 200, clean logs) after each merge. Pushed to `origin/claude/adoring-meitner-7xxgfq`.

## What shipped and why

### 1. DBSCAN + Agglomerative Hierarchical clustering

`modules/clustering.py` was KMeans-only — a spherical-cluster, fixed-K
algorithm with no way to detect noise/outliers or inspect a merge
hierarchy. This was Run 27's own candidate #3, deferred twice for
scheduling reasons (never because the gap closed) and explicitly handed
to this run as a recommendation.

- **DBSCAN** (`run_dbscan`): density-based clustering that finds
  arbitrary-shaped clusters and explicitly labels points that don't
  belong to any dense region as `"Noise"`, rather than forcing every
  point into some cluster the way KMeans does. No K to pick — density
  parameters (`eps`, `min_samples`) implicitly determine cluster count.
  `eps` is suggested via `suggest_eps()`, a k-distance-plot elbow
  heuristic (Ester et al. 1996) — sort each point's distance to its
  `min_samples`-th nearest neighbor and find the sharpest upward bend —
  shown to the user as a chart (`build_dbscan_eps_chart`), mirroring the
  existing KMeans elbow/silhouette-chart UX rather than just picking a
  number silently. This is deliberately different from `anomaly.py`'s
  own `_dbscan_eps` (a fully-automated 90th-percentile heuristic for an
  unattended pipeline call) — the Clustering tab is interactive, so a
  human-inspectable elbow chart is the more consistent choice, matching
  how KMeans' own K suggestion is presented.
- **Agglomerative Hierarchical** (`run_hierarchical`): ward/complete/
  average/single linkage, with a dendrogram (`build_dendrogram_chart`,
  via `plotly.figure_factory.create_dendrogram` wrapping scipy's
  `linkage` — no new dependency, both packages already installed) so the
  merge structure is inspectable, not just a final K-cluster assignment.
- Both return the same `cluster_stats`/`scatter_df`/
  `pca_explained_variance`/`silhouette_score` shape as the existing
  `run_clustering` (KMeans), so a new shared `_render_cluster_result()`
  helper in `app.py` renders the PCA scatter, silhouette verdict,
  cluster-stats table, and "Name Segments with AI" button identically
  across all three algorithms — no UI duplication.
- The Clustering tab gained an algorithm radio picker; switching
  algorithms clears any stale result from a different algorithm's
  result-dict shape (a DBSCAN result has no `"k"`, a KMeans one has no
  `"n_clusters"`/`"noise_count"` — rendering one under the other's
  branch would `KeyError`).

**Technical-depth argument:** this isn't cosmetic — it's a genuine
statistical-method gap. KMeans' spherical-cluster assumption fails on
real segmentation data with elongated or non-convex groups, and it has
no concept of "this point doesn't belong to any segment." DBSCAN and
hierarchical clustering are the two standard textbook alternatives every
clustering course teaches alongside KMeans, and Prism previously offered
neither as a user-facing segmentation option (DBSCAN existed only inside
`anomaly.py`'s outlier ensemble, a different use case — flagging noise,
not producing labeled segments).

### 2. Market Basket Analysis (Apriori association rules)

New module `modules/market_basket.py` — a from-scratch Apriori
implementation (Agrawal & Srikant 1994's join-and-prune candidate
generation, itemsets up to size 3) mining frequent itemsets and
association rules (support/confidence/lift) from a (Basket ID, Item)
column pair. Zero coverage existed anywhere in Prism before this run
(`grep` confirmed no `apriori`/`association.rule`/`frequent.itemset`/
`market.basket` hits anywhere).

- `mlxtend` (the standard Python Apriori library) is not installed, and
  installing a new dependency for one feature was avoidable — Apriori is
  a well-understood, ~150-line algorithm that's easy to implement
  correctly and test exhaustively, so it was built with only
  `itertools`/`collections` (already-installed stdlib) rather than
  adding a pip dependency.
- Counting at each Apriori level walks each *transaction's* own item
  combinations (bounded by that basket's size) rather than checking
  every global candidate against every transaction — the standard way to
  keep Apriori counting tractable, avoiding an O(baskets × candidates)
  blowup.
- Three tractability caps, all reported back in the result dict so the
  UI can tell the user when they've been triggered: `MAX_DISTINCT_ITEMS`
  (only the top-N most frequent items are considered past the singleton
  level), `MAX_BASKETS` (deterministic random sampling for huge
  transaction logs), `MAX_FREQUENT_PER_LEVEL` (caps candidate-generation
  blowup when the support floor is very low on a huge item vocabulary).
- Wired into Domain Lens → Product Analytics (thematically paired with
  the existing RFM segmentation — both are classic retail/product-
  analytics techniques cited together in the literature) with its own
  Basket ID/Item column mapper, min_support/min_confidence sliders, a
  top-rules-by-lift bar chart, the rules table, and a raw
  frequent-itemsets expander. A result with frequent itemsets but zero
  qualifying rules is *not* treated as an error — it renders the
  itemsets table with a "try lowering the threshold" hint instead of a
  dead end.

**Technical-depth argument:** a real, from-scratch implementation of a
canonical data-mining algorithm (not a library call), with genuine
algorithmic-tractability engineering (candidate pruning, per-transaction
combination counting, deterministic sampling) rather than a naive
brute-force itemset scan that would choke on real data. Verified against
synthetic data with known ground-truth structure (see below), not just
"doesn't crash."

## Why these over the alternatives

- **Difference-in-Differences** (causal_inference.py) — still flagged
  L-effort/medium-risk (needs panel-structure detection + a new
  assumptions UI), deferred a third consecutive run for the same reason
  Runs 27 and 28 deferred it.
- **Cross-module reproducible-script export** (beyond the ML-Lab-scoped
  slice Run 28 shipped) — still spans 3+ modules (Clustering, Forecasting,
  Stats Lab), better split across future runs than crammed into one slot.
- **Survival analysis (Kaplan-Meier)** — would need either a new
  `lifelines` dependency or a heavier from-scratch KM+log-rank
  implementation than Apriori for comparable value; logged as a Run 30+
  candidate if the backlog runs thin again.

Both selected features are pure numpy/pandas/scipy/sklearn compute (zero
Gemini calls, zero free-tier exposure), and neither touches the Atlas/
JARVIS copilot track (0/1 this run, well within the 1-feature cap).

## Verification evidence

Playwright/Chromium was **not retried** this run — 4 consecutive prior
runs confirmed it blocked by sandbox egress policy (`curl` to
`cdn.playwright.dev` → 403), and this run's own brief explicitly said to
go straight to the fallback rather than re-litigate a stable policy.

Fallback verification method used instead:

1. **Full test suite**: 564 → 611 passing (47 new tests: 19 clustering +
   28 market basket), zero regressions, run after each feature branch
   and again on the final merged `claude/adoring-meitner-7xxgfq`.
2. **Live `streamlit run` smoke tests**: three separate runs (one per
   feature branch, one on the final merged state) — each confirmed
   `curl localhost:PORT` → HTTP 200 with clean startup logs (no
   tracebacks, no import errors).
3. **Direct function-level verification against real/synthetic data**:
   - DBSCAN + Hierarchical run against `samples/stock_data.csv`'s
     OHLCV+volume columns (400 real rows): DBSCAN found 1 dense regime
     cluster + 20 noise points (5%), correctly returned
     `silhouette_score: None` (can't score a single real cluster);
     Hierarchical (ward, k=4) split the same data into 4 regimes at
     silhouette 0.32 — both algorithms ran end-to-end against production
     sample data without error.
   - Market Basket Analysis run against a synthetic 2,000-basket,
     4,115-row transaction log with **known co-purchase structure baked
     in** (Bread+Butter always paired ~40% of baskets, Beer+Chips always
     paired ~35%, an occasional Bread+Butter+Jam triple). The Apriori
     implementation recovered the exact designed structure: Beer→Chips
     confidence 1.000/lift 2.73, Bread→Butter confidence 1.000/lift
     2.60, and correctly surfaced the `{Bread, Butter, Jam}` triple
     itemset at support 0.189 — proof the join-and-prune candidate
     generation and support/confidence/lift math are correct, not merely
     plausible-looking output.

## Backlog not built (Run 30+ candidates)

From `.prism/research_2026-08-11-run29.md`'s ranked table:

| Candidate | Depth | Effort | Why deferred |
|---|---|---|---|
| Difference-in-Differences estimator (`causal_inference.py`) | 5 | L | Panel-structure detection + new assumptions UI — too large for a two-feature run, deferred 3 runs running |
| Cross-module reproducible-script export (Clustering/Stats Lab/Forecasting) | 3 | L | Spans 3+ modules; ML-Lab-scoped slice already shipped Run 28 |
| Survival analysis (Kaplan-Meier) for Domain Lens | 3 | M | Needs `lifelines` dependency or heavier from-scratch KM+log-rank implementation |

## STAR bullets

**DBSCAN + Hierarchical clustering** — *Situation:* Prism's Clustering
tab offered only KMeans, unable to detect non-spherical clusters or flag
outlier points. *Task:* add density-based and hierarchical alternatives
without duplicating the existing K-selection/scatter/naming UI. *Action:*
implemented DBSCAN with an interactive k-distance-plot eps suggestion and
Agglomerative clustering with a dendrogram (zero new dependencies),
refactored the shared rendering path into one helper function reused by
all three algorithms. *Result:* 19 new tests, verified against real OHLCV
stock data recovering sensible regime clusters; zero regressions across
611 total tests.

**Market Basket Analysis** — *Situation:* zero association-rule-mining
capability existed in Prism despite it being a standard retail/product-
analytics technique paired with the RFM segmentation Prism already ships.
*Task:* add Apriori-based frequent-itemset and rule mining without a new
pip dependency. *Action:* built a from-scratch, tractability-capped
Apriori implementation (join-and-prune candidate generation, per-
transaction combination counting) and wired it into Domain Lens.
*Result:* 28 new tests; verified against synthetic transaction data with
known ground-truth co-purchase structure, exactly recovering the designed
lift/confidence values and a size-3 itemset — proof of algorithmic
correctness, not just crash-free execution.

## Run 30 recommendation

The candidate table above is down to genuinely large items (DiD, full
cross-module script export) or dependency-adding ones (survival
analysis). Recommend Run 30 either (a) take on Difference-in-Differences
as a single dedicated feature if it can be scoped down to a common-case
slice (2-period panel, no fixed-effects generalization) rather than the
full L-effort version, or (b) run a fresh Phase 2 sweep before picking —
this run's sweep surfaced Market Basket Analysis as a genuinely new,
well-scoped find, suggesting the backlog isn't as exhausted as it might
look from the leftover L-effort items alone.
