# Changelog

Notable changes to Prism. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
History before this file existed lives in `git log`.

## 2026-08-07

### Added
- **Statistical verification layer for Auto Analyst.** Every headline
  finding Gemini writes now gets cross-checked against a real
  `scipy.stats` hypothesis test run on whichever columns the finding
  actually names (reuses Stats Lab's `suggest_test`/`run_test` — no new
  statistics engine). Each finding is badged ✅ statistically verified,
  ⚠️ not statistically significant, or ℹ️ descriptive/not testable, in
  both the Auto Analyst tab and Atlas's spoken run summary. Zero extra
  Gemini calls, zero network I/O, fully deterministic.
  (`modules/auto_analyst.py::verify_findings`, `app.py`, `modules/theme.py`)
- First automated test suite (`tests/`, `pytest.ini`,
  `requirements-dev.txt`) — 11 tests covering the new verification logic.
