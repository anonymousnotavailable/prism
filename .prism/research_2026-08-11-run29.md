# Run 29 — Phase 2 research sweep (2026-08-11)

Run 28's recommendation: ship DBSCAN/hierarchical clustering (Run 27's
candidate #3, deliberately deferred twice now — once in Run 27 to avoid a
second straight run on Clustering after Run 26's silhouette work, once
implicitly in Run 28 which spent its two slots on ROC/PR + script export
instead) paired with a fresh Phase 2 sweep, since Run 27's ranked table
(candidates #4, #6, #7) is now down to items explicitly flagged too large
for a single two-feature run (DiD causal estimator — L effort/medium risk;
cross-module reproducible-script export — L effort; schema-contract
versioning — overlaps PSI thematically, M effort UI-heavy).

## External sweep

- **2026 DA/DS job postings** (365DataScience Data Analyst/Data Scientist
  Job Outlook 2026, IABAC, Refonte Learning): SQL/Python/visualization
  still dominate; EDA "remains a fundamental skill that separates
  experienced professionals from those who only know tools"; agentic
  orchestration is the emerging differentiator but as a *workflow* skill,
  not a specific missing statistical technique — nothing here points at a
  concrete new Prism capability beyond what's already tracked.
- **Competitor tools** (Hex, Deepnote, Julius AI, ChatGPT ADA — Julius.ai's
  own 2026 comparison roundups, NomadLab's Hex vs Julius vs Cortex/Genie
  survey): market has stabilized into four lanes (chat-first, notebook/
  workspace, spreadsheet-first, warehouse-native BI-copilots) — all still
  chat-over-code-execution products, architecturally out of reach for a
  single-run slice and already noted as such in Run 27's sweep (Atlas/
  JARVIS track, capped at 1 feature/run here regardless).
- **Agentic-EDA research** (arXiv 2510.04023 LLM-Based Data Science Agents
  survey, arXiv 2606.00051 Business Utility of LLMs as EDA Agents): both
  flag *trust/safety mechanisms* as the field's biggest known gap ("over
  90% lack explicit trust and safety mechanisms") — Prism already answers
  this directly via `insight_verifier.py` (deterministic fact-checking of
  every Gemini-synthesized finding, shipped 2026-08-07), so this is a
  confirmation the existing architecture is on the right track, not a new
  candidate.
- **Market basket analysis / association rules** (Apriori/Zhang's-metric
  writeups, mlxtend docs): a textbook retail/e-commerce analytics
  technique ("customers also bought", cross-sell), commonly cited
  alongside RFM segmentation in the same product-analytics literature —
  and Prism's Domain Lens already ships RFM but nothing itemset/
  association-rule-shaped. `mlxtend` (the standard Python apriori library)
  is not installed and adding a new pip dependency for one feature is
  avoidable — a bounded, capped, from-scratch Apriori (itemsets up to
  size 3, `itertools`/`collections` only) is a well-known, easily-tested
  algorithm and keeps the dependency footprint at zero.

## Internal gap audit (before ranking)

Read `modules/clustering.py`, `modules/anomaly.py`, `modules/domains.py`,
`app.py`'s Clustering and Domain Lens tab wiring directly.
`grep -rniE "apriori|association.rule|frequent.itemset|market.basket|
AgglomerativeClustering|DBSCAN|dendrogram|hierarchical" modules/*.py
tests/*.py app.py` confirms:
- `clustering.py` is KMeans-only (elbow + silhouette K selection, PCA
  scatter, Gemini segment naming) — no density-based or hierarchical
  algorithm anywhere in the Clustering tab.
- The only existing `DBSCAN` usage is in `anomaly.py`'s ensemble anomaly
  detector (`find_anomalies_ensemble`), which uses DBSCAN purely to flag
  `-1`-labeled points as outliers (with its own automated 90th-percentile
  k-distance `eps` heuristic, `_dbscan_eps`) — it never surfaces DBSCAN's
  actual cluster assignments as a segmentation result. Genuinely different
  purpose from a Clustering-tab "run DBSCAN and see your segments" feature,
  confirming candidate #1 below is not already covered.
- Zero hits anywhere for apriori/association-rule/frequent-itemset/market-
  basket — a real, unbuilt gap, confirming candidate #2.

## Ranked candidates

| # | Feature | Evidence / rationale | Depth (1-5) | Effort | Risk | Theme |
|---|---|---|---|---|---|---|
| 1 | **DBSCAN + Agglomerative Hierarchical clustering algorithms for the Clustering tab** | `clustering.py` is KMeans-only (spherical-cluster, fixed-K assumption, no noise detection). DBSCAN finds arbitrary-shaped clusters and explicitly labels noise/outliers; hierarchical (Ward linkage) needs no upfront distance-metric commitment and yields an inspectable dendrogram. Both are standard textbook alternatives Prism's own docstring for elbow+silhouette already frames as "K selection is hard" — DBSCAN sidesteps picking K at all. Run 27/28's own recommended pick, twice deferred for scheduling reasons only. | 4 | M | Low | ML/statistical rigor, diversify within Clustering |
| 2 | **Market Basket Analysis (Apriori association rules) for Domain Lens → Product Analytics** | Textbook retail/product-analytics technique, cited alongside RFM (which Prism already ships) in the same literature; zero coverage today. Bounded, dependency-free Apriori (itemsets ≤3, capped item vocabulary) is well-understood, easily tested, and fits the existing Domain Lens column-mapper UI pattern. | 4 | M | Low | Statistical rigor, new Domain Lens capability |
| 3 | Difference-in-Differences estimator (`causal_inference.py`) | Still open from Run 27 (candidate #4) — panel/pre-post causal design not covered by existing propensity-score matching. Flagged L effort/medium risk (panel-structure detection, new assumptions UI) — too large for this run's two-feature budget again. | 5 | L | Medium | Causal inference (deferred again) |
| 4 | Cross-module reproducible-script export (Clustering/Stats Lab/Forecasting, beyond the ML-Lab-scoped version Run 28 shipped) | Still open from Run 27 (candidate #6), narrowed once already (ML Lab baseline export shipped Run 28). Remaining scope (clustering + forecasting + stats lab) still touches 3 modules — L effort, better split across 2-3 future runs than crammed into one slot here. | 3 | L | Medium | Reproducibility (deferred again) |
| 5 | Survival analysis (Kaplan-Meier) for churn/time-to-event in Domain Lens | Common product-analytics technique (time-to-churn curves), but `lifelines` isn't installed and a from-scratch KM estimator plus log-rank testing is a heavier lift than Apriori for comparable value — logged as a Run 30+ candidate if the backlog runs thin again. | 3 | M | Low | New Domain Lens capability (not selected) |

## Selected this run

**#1 (DBSCAN + Hierarchical clustering) and #2 (Market Basket Apriori
rules).** Both are verified-open, statistically/algorithmically
substantive gaps (not cosmetic), zero new pip dependencies, zero Gemini
calls (pure numpy/pandas/scipy/sklearn compute), and neither touches the
Atlas/JARVIS copilot track. #1 diversifies *within* Clustering (new
algorithms, not a new metric on the existing one); #2 opens a genuinely
new Domain Lens capability rather than adding to an already-deep tab.
Full reasoning in `.prism/routine_log.md`.
