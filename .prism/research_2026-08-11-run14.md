# Research — 2026-08-11, Run 14

Lightweight pass, same precedent as Runs 9-13: fourteenth cycle against this
repo, thirteen of them same-day. A full four-source-class web sweep was last
run fresh several cycles ago and the standing candidate table (below) is
still current — reused rather than re-searched, consistent with this
scheduling pattern's token-efficiency reasoning logged in every run since
Run 9.

## Standing backlog (carried forward, still valid)

| Feature | Evidence | Depth | Effort | Risk | Theme |
|---|---|---|---|---|---|
| PyGWalker-style drag-and-drop chart builder — remaining scope (draggable pill UI, faceting, explore mode) | Hex/Deepnote parity; encoding-channel slice shipped Run 13 | 2 | L | Low | Competitor parity |
| DuckDB/polars path for Auto Cleaner on large samples | Unaddressed since first logged (Run 8 follow-on) | 3 | M | Low | Ecosystem tech |
| Light-theme dataframe repaint-lag | Cosmetic/timing, investigated multiple sessions | 1 | S | Low | Polish |
| Live-Gemini screenshot verification | No API key in sandbox, 14 consecutive runs | — | — | — | N/A (env-gated) |

## New candidate for Run 14 — Zero-click anomaly detection on upload

Direct extension of this cycle's mandatory agentic-AI-analysis theme's
"auto-EDA on upload" pillar. The audit (`audit_2026-08-11-run14.md`) found
that of the orchestrator's 8 detector sources, only 2 (`auto_insights`,
confounder scan) actually run at upload time — the rest, including anomaly
detection, wait for a tab visit + button click. Agentic-EDA research
(ydata-profiling, Sweetviz, and this cycle's required reading on
self-verifying analysis agents) treats "runs automatically, ranks itself,
tells you what matters" as the baseline expectation for an auto-EDA tool;
Prism's own orchestrator already does the ranking/telling part but was
silently missing 75% of its detector coverage at the moment a user most
needs it — first upload, before they've clicked anything.

- **Evidence**: direct gap found in this run's own audit; matches the
  "automatic insight generation" and "anomaly narration" pillars named
  explicitly in this cycle's brief; the ensemble anomaly detector already
  has a narration function (`narrate_ensemble_disagreement`) sitting unused
  until a manual click — this closes the detection half of that gap.
- **Technical-depth score**: 4 — not new ML (reuses the existing
  IsolationForest+LOF+DBSCAN ensemble), but real engineering judgment:
  recognizing LOF/DBSCAN's O(n²)-ish cost means the auto-run needs a
  materially tighter row cap than the manual path, and designing the
  no-op-not-error contract so an upload-time background computation can
  never break the upload flow itself.
- **Effort**: S — the detector, its UI rendering, and its orchestrator
  adapter all already exist; this wires an existing capability to fire
  earlier and adds the bounded auto-run entry point.
- **Risk**: Low — best-effort, wrapped in try/except, silently no-ops
  outside its safe row/column bounds, falls back to the pre-existing manual
  "Find Anomalies" flow untouched.
- **Roadmap theme**: agentic v2 (this cycle's mandatory theme).

## Selection

Run 14 ships this one feature. Scoped deliberately narrow (S effort) rather
than reaching for the PyGWalker L-effort remainder or the DuckDB/polars M-
effort item — this is the fourteenth cycle today; per Runs 10/12's logged
reasoning, an already-thin backlog plus repeated same-day firing favors a
precise, well-tested slice over another large build. PyGWalker and the
DuckDB/polars Auto Cleaner path remain backlog for a run with more budget
or a fresh day's cycle.
