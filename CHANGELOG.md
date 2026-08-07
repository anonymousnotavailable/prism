# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-07

### Added
- **Hypothesis Generator** (Overview tab): an autonomous "what should I even
  be testing?" layer on top of Stats Lab. Scans every plausible column pair
  in the active dataset, pre-screens them with a cheap deterministic
  signal-strength heuristic, runs the strongest candidates through real
  significance tests (Welch's t-test, one-way ANOVA, chi-square, Pearson —
  via the existing `modules/stats_lab.py`), and returns a ranked list of
  plain-English hypotheses each backed by an actual p-value, effect size,
  and assumption-check warnings. Works with zero Gemini API key configured
  (the verdict is always the real scipy result); an optional "Narrate with
  AI" button adds a short Gemini-phrased prose summary on top, purely
  cosmetic and gracefully absent without a key. New module:
  `modules/hypothesis_engine.py`. New test suite: `tests/` (first in the
  repo — 17 tests covering the ranking/screening logic, each hypothesis
  kind on data with a known ground-truth effect, edge cases, and an
  end-to-end integration test against a bundled sample dataset).
