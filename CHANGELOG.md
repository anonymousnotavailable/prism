# Changelog

All notable changes to Prism are logged here, newest first.

## 2026-08-07

### Added
- **Hypothesis Engine** (Auto Analyst tab) — proposes falsifiable
  hypotheses about the active dataset and verifies each one itself with a
  real scipy.stats test via Stats Lab. Gemini proposes candidates when a
  key is configured; a deterministic correlation/variance-ranked heuristic
  covers every case otherwise, including zero-key installs. A hypothesis
  is only ever marked CONFIRMED off a computed p-value, never a model's
  say-so. (`modules/hypothesis_engine.py`)
- Gemini response caching + short backoff retry in `call_gemini`
  (`modules/ai_analyst.py`) — identical prompts now serve from an
  in-process LRU cache instead of re-hitting the API, and a transient
  `ResourceExhausted` gets up to 2 short backoff retries before surfacing
  the quota-exceeded message.

### Notes
- No breaking changes; both additions are pure backend + one new UI
  section, gated to work identically with or without a configured
  `GEMINI_API_KEY`.
