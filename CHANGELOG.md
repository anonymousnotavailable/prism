# Changelog

All notable changes to Prism are logged here, newest first. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-08-07

### Added
- **Statistical Verification Layer for Auto Analyst** (`modules/insight_verifier.py`).
  After a "Run Full Analysis" pass (from the Auto Analyst tab or Atlas's
  `execute_plan` command), Prism now independently re-derives the dataset's
  strongest numeric correlations and categorical/numeric group splits
  straight from the dataframe and runs each through Stats Lab's existing
  test suite (t-test / ANOVA / chi-square / Pearson). The result is a new
  "🔬 Statistically Verified" panel showing real p-values, effect sizes, and
  normality warnings next to Gemini's prose findings — and, since it never
  calls Gemini, it still works even when the LLM findings fail or the
  free-tier quota is exhausted.
- **Auto-narrated anomaly explanations** (`modules/anomaly.py::narrate_anomalies`).
  A "🗣️ Narrate anomalies" button in the Anomaly Detection panel sends the
  flagged rows' reasons to Gemini for a short paragraph explaining the
  pattern, which column(s) drive it, and whether it looks like a data-entry
  error or a genuine signal worth investigating — cached per unique flagged
  set so re-viewing the same result doesn't re-hit the API.
- `tests/` — the repo's first automated unit test suite (pytest), covering
  both features above with mocked Gemini calls (offline, no API key or
  network needed). Wired into CI (`.github/workflows/ci.yml`).

### Notes
- Both features run entirely within the Gemini free tier: the verification
  layer makes zero additional Gemini calls, and anomaly narration is
  button-triggered (not automatic) plus content-hash cached.
