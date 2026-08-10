# Research — 2026-08-10, Run 5

Light live web pass, layered on the standing competitor/ecosystem
landscape already recorded in prior runs' research files (unchanged
findings aren't repeated here).

## Ranked candidate table

| Feature | Evidence | Technical-depth (1-5) | Effort | Risk | Roadmap theme |
|---|---|---|---|---|---|
| Feature Selection Engine (mutual info / L1 / RFE consensus) | Mutual-information-based selection is a standard, currently-taught technique ([CodeSignal](https://codesignal.com/learn/courses/dimensionality-reduction-with-feature-selection/lessons/mastering-feature-selection-with-mutual-information-in-python), [Medium](https://guhanesvar.medium.com/feature-selection-based-on-mutual-information-gain-for-classification-and-regression-d0f86ea5262a)); 2026 data-analyst job descriptions explicitly list "statistical reasoning" and feature-relevance work alongside SQL/Python ([Dataquest](https://www.dataquest.io/blog/data-analyst-skills/), [LoopCV](https://www.loopcv.pro/skills/data-analyst/)) | 4 | M | Low — additive ML Lab section, no schema/architecture change | Agentic AI analysis (auto-generated insight about which features matter) |
| `google-generativeai` → `google-genai` migration | Package now emits a hard end-of-support `FutureWarning` on every import (confirmed this run's own test output) | 2 (execution risk, not depth) | M | Medium — touches every Gemini call site, needs its own regression pass | Reliability, not a roadmap theme |
| polars/DuckDB large-file ingestion path | DuckDB already used for SQL Lab; ecosystem adoption for larger-than-memory analysis continues (standing finding, re-confirmed, no new evidence this pass) | 3 | L | Medium-high — architecture-adjacent per guardrail | Ecosystem tech |
| Self-verifying agent frameworks (AutoVerifier-style refutation passes) | Active 2026 research direction for agentic data-science pipelines ([arXiv survey](https://arxiv.org/pdf/2508.02744), [AutoVerifier](https://arxiv.org/html/2604.02617v1)) | 5 | L (as a pattern to reuse, not a new subsystem) | Low | Already the pattern behind Ensemble Anomaly Consensus (Run 4) and this run's Feature Selection Engine — noting it's validated as the right shape to keep reusing, not a new build |

## Selection

Feature Selection Engine was the clear pick: highest technical-depth-to-risk
ratio, directly closes a backlog item flagged by two prior runs, and its
3-method-consensus design continues the "self-verifying ensemble" pattern
research confirms is the right shape for agentic EDA in 2026 — rather than
trusting one model's importance score, cross-check it the same way
Ensemble Anomaly Consensus (Run 4) cross-checks anomaly detectors.

`google-generativeai` migration was considered but rejected for this run
specifically because it touches every Gemini call site in the app
(`ai_analyst.py`, and every module's narration function) — exactly the
kind of change the guardrail asks to isolate to its own dedicated,
regression-tested session rather than bundle alongside a feature that
touches unrelated code. Recommended as next run's sole focus (see run
report).
