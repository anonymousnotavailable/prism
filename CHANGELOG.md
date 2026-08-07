# Changelog

All notable changes to Prism are logged here, newest first. This file
starts with this entry — earlier history lives in `git log` (Auto Cleaner,
Hell Mode, India Mode, Atlas, SHAP explainability, the corpus benchmark,
SQL Lab's DuckDB workbench, and the security-hardening passes all predate
this file).

## 2026-08-07

### Added — Hypothesis Engine: automatic multi-column scan with FDR correction
Stats Lab previously only tested exactly the two columns a user manually
picked. `modules/hypothesis_engine.py` adds a one-click "Auto-Scan All
Column Pairs" that enumerates every valid pairwise relationship among up
to 12 testable columns (66 pairs), runs each through Stats Lab's existing
test-selection/execution pipeline, and applies a Benjamini-Hochberg
false-discovery-rate correction across the whole batch — the guard a
careful analyst applies before trusting any single p-value out of a dozen
tests run back to back, and the reason "raw significant" and "significant
after FDR correction" are reported as two separate numbers in the UI.
Gemini narration of the significant findings is optional and additive,
with a fully offline templated fallback. 7 new deterministic eval cases in
`eval/hypothesis_engine_eval.py` (planted correlation, planted group
difference, FDR correction suppressing noise false-positives on 66
pure-noise pairs, edge cases), wired into CI alongside the existing Auto
Cleaner suite.

### Fixed — Atlas side panel covered the entire screen on phone-width viewports
`modules/theme.py`'s persistent Atlas copilot panel was `position: fixed;
width: 328px` with no responsive handling at all — on any phone-width
viewport it covered nearly the whole screen, burying every tab underneath
it. Hidden below 900px via a media query; Atlas stays fully reachable
through the always-visible chat-input command bar, which is a separate
element. Two deeper, pre-existing mobile layout bugs were found and
diagnosed but not resolved this cycle (a page-level auto-scroll-to-bottom
hijack tied to Streamlit's `st.chat_input`, and a narrow-column render at
~390px) — see `.prism/audit_2026-08-07.md` for full diagnostics, logged as
next run's top priority.
