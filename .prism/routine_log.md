# Prism Autonomous Improvement Routine — Log

This file is the routine's memory across runs. Each entry records what shipped,
what was skipped and why, and open backlog for the next run. Never rebuild or
duplicate a shipped feature — check this log before starting Phase 3.

---

## 2026-08-07 — Run 1

**Shipped:** (1) Auto Hypothesis Engine (`modules/hypothesis_engine.py`) —
Gemini proposes testable hypotheses, `stats_lab`'s real scipy pipeline
verifies them, deterministic rule-based fallback with no API key. New Stats
Lab tab section. (2) Anomaly Detection sensitivity slider (1-25%,
previously fixed 5%) + Gemini narration of flagged rows as a group, with a
deterministic fallback. Both 100% agentic-theme fits. Bonus fix:
`stats_lab.suggest_test()` crashed on `col_a == col_b` — guarded.

**Skipped / deferred:** Atlas copilot track (budget available, spent on
higher-priority agentic-theme work instead — free to use next run). polars/
DuckDB engine swap (architecture change, out of scope per guardrails).
Streaming AI Analyst chat, saved SQL history, theme persistence — all
README Roadmap items, lower depth, good candidates to batch in a lighter
run.

**Found but NOT fixed (top priority for next run):** mobile-PWA viewport
(<480px) layout collapse — main content column squishes to ~40px wide
whenever the Atlas panel is present, reproduces on every tab, pre-existing
(not caused by this run's changes). `modules/theme.py` has zero `@media`
breakpoints today. See `.prism/audit_2026-08-07.md` for full detail and a
suggested fix direction. Left unfixed deliberately — untested structural
CSS change late in a long session was judged too risky to ship without a
dedicated verification pass.

**Eval:** `eval/hypothesis_engine_eval.py` 9/9 (100%), no Gemini key
required. `eval/autocleaner_eval.py` regression suite still 8/8 (100%).

**Next run recommendation:** fix the mobile layout collapse first (blocks
the PWA claim from holding up in a live demo — highest interview risk of
anything currently in the repo), then either CUPED/sequential A/B testing
in Stats Lab (direct extension of this run's hypothesis work) or the
Atlas proactive-insights slice (budget untouched this run).

