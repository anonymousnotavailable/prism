# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-07

### Added
- **Hypothesis Engine** (`modules/hypothesis_engine.py`, new Stats Lab
  section): Gemini proposes candidate testable relationships between
  columns; Python alone decides which statistical test fits and runs it
  (never Gemini — mirrors the existing Auto Cleaner SAFE/REVIEW split);
  every p-value in the batch gets a joint Benjamini-Hochberg FDR correction
  before a SUPPORTED/REJECTED verdict is assigned. Falls back to a
  deterministic correlation/group-variance heuristic generator when Gemini
  is unavailable (no key, rate limit, daily quota) instead of going dark.
  10 new unit tests in `tests/test_hypothesis_engine.py`.

### Fixed
- **Mobile PWA layout**: the Atlas side panel's fixed 328px right column
  (plus the 352px content padding it forced) left effectively zero usable
  width at phone viewport widths — every tab's content rendered squeezed
  into a sliver with text wrapping letter-by-letter. Added a
  `@media (max-width: 768px)` rule (`modules/theme.py`) that drops the
  fixed positioning below that breakpoint so the panel falls into normal
  document flow instead. Found via this run's own screenshot audit.

### Backlog (researched, not built this run — see `.prism/research_2026-08-07.md`)
- Migrate off the now-EOL `google-generativeai` SDK to `google.genai`.
- Self-verifying Auto Analyst (a second LLM pass checks the first pass's
  claims against the actual result).
- Atlas proactive insights slice (surfaces a finding unprompted after upload).
- Voice-driven Hypothesis Engine command.
- Polars/DuckDB as an alternate compute path for large files (architecture
  change — proposal only, not attempted).
