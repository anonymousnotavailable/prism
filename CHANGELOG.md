# Changelog

All notable changes to Prism are documented here, newest first.

## 2026-08-07

### Added
- **Auto Hypothesis Engine** (`modules/hypothesis_engine.py`, Stats Lab tab).
  Gemini proposes up to 5 testable hypotheses about the active dataset from
  its schema and summary stats; each is then run through Stats Lab's
  existing `scipy.stats` test-selection pipeline for a real verdict
  (confirmed / not confirmed / untestable) backed by an actual p-value and
  effect size — the LLM only proposes, it never verifies its own claims.
  Falls back to a deterministic rule-based generator (strongest numeric
  correlations + widest categorical group splits) when no Gemini key is
  configured or a call fails, so the feature always works.
- **Configurable anomaly-detection sensitivity + narration**
  (`modules/anomaly.py`, Overview tab). The Anomaly Detection panel now has
  a sensitivity slider (1%-25% expected anomaly rate, was a fixed 5%) and a
  2-3 sentence plain-English narration of what the flagged rows have in
  common as a group, not just a per-row reason — narration falls back to a
  deterministic summary when Gemini is unavailable.

### Fixed
- `stats_lab.suggest_test()` no longer crashes with a raw scipy
  `ValueError` when asked to test a column against itself — returns a
  clean error message instead. Unreachable from the Stats Lab UI (two
  separate column pickers already prevent it) but reachable from any
  programmatic caller, including the new Hypothesis Engine's own eval
  suite, which is what caught it.

### Known issues (not fixed this run — see `.prism/audit_2026-08-07.md`)
- Main content column collapses to ~40px wide at mobile-PWA viewport
  widths (<480px) whenever the Atlas panel is present — pre-existing,
  reproduces on every tab. Logged as next run's top priority.
- The sticky "Ask Atlas anything..." command bar stays dark-themed in
  Arctic (Light) mode.
