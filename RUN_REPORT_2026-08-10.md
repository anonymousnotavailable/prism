# Prism Autonomous Improvement Run — 2026-08-10

## 1. What shipped

### Anomaly Narration (`modules/anomaly.py`, `app.py`)

**What it does:** the Anomaly Detection panel (Overview tab) already flagged
unusual rows via IsolationForest with a templated per-row reason string
(e.g. *"revenue is 95.9x above the column median"*). This run adds an
**"✨ Explain these anomalies"** button that sends the flagged set's summary
to Gemini and gets back a 2-4 sentence plain-English explanation of what the
anomalies likely mean for the dataset, plus **one concrete suggested next
action** — investigate a specific column, exclude the rows, or treat them as
a valid rare segment. It's deliberately non-generic: the prompt is built
from the actual flagged reasons, not a static template.

Two failure/efficiency behaviors were built in from the start, not bolted on:
- **No wasted Gemini calls.** If nothing was flagged, the function returns a
  static "nothing to investigate" message without ever calling the model.
- **Fingerprint-cached.** The narration is cached in session state keyed on
  a new `anomaly_fingerprint()` (a hash of the flagged row index). Re-
  rendering the page, switching tabs, or Streamlit's normal rerun cycle
  reuses the cached narration instead of re-spending a free-tier request —
  only a genuinely new "Find Anomalies" run (different flagged rows)
  invalidates it.

**Why chosen:** this run's mandated priority theme was agentic AI analysis —
auto-EDA, automatic insight generation, anomaly narration was explicitly
named in the routine's own brief. It was also sitting in the backlog since
2026-08-07 Run 1 as an identified-but-unbuilt gap, so this closes an
existing item rather than opening a new one.

**Technical-depth argument for an interview:** this isn't "call an LLM and
show the text." It (1) builds the prompt from real computed statistics
(reasons derived from IsolationForest + median-deviation ratios) rather than
raw data dumped at the model, keeping the request small and the output
grounded; (2) has an explicit no-op path so a "nothing anomalous" result
costs zero API calls, which matters concretely on a free tier with a hard
per-session rate limit (`ai_analyst.py`'s existing `_check_rate_limit()`);
and (3) caches by content fingerprint instead of by "was a button clicked
this session," which is the correct invalidation semantics — a stale cache
would show yesterday's narration for today's re-run on different data.

## 2. Screenshots

All captured with Playwright against the pre-installed Chromium
(`/opt/pw-browsers/chromium`), saved under `.prism/runs/2026-08-10/`:

- `overview_desktop-dark.png` — baseline Overview tab, dark theme, no
  regression from this change.
- `anomaly_flagged_desktop-dark.png` — Anomaly Detection expander with 10
  planted anomalies flagged and the new "✨ Explain these anomalies" button
  visible.
- `anomaly_explain_nokey_desktop-dark.png` — the button clicked with no
  `GEMINI_API_KEY` configured in this sandbox, showing the graceful
  "No Gemini model available for narration." warning instead of a crash —
  the failure-state path this routine's Phase 4 explicitly requires.
- `anomaly_flagged_desktop-light.png` — same panel in light theme. Readable
  and functional, but surfaced a **pre-existing** bug: `st.dataframe`
  widgets don't follow Prism's light/dark toggle (stay dark-canvas
  regardless of theme). Logged in the routine log as backlog, not fixed
  here — out of scope for this feature and needs a dedicated pass.
- `overview_mobile-dark.png` — 390px viewport. Re-confirms the pre-existing
  Atlas-panel mobile-reflow bug first logged 2026-08-07 (sidebar text
  rendering as a squished vertical strip). Not caused by this run's change;
  not fixed here for the same reason.

No live Gemini API key was available in this execution sandbox, so the
narration's actual model output couldn't be screenshotted — the
no-key failure path was verified instead, and the request/response
plumbing is covered by 11 unit tests with a mocked model.

## 3. Research findings NOT built (ranked backlog for future runs)

| Feature | Effort | Notes |
|---|---|---|
| Atlas Proactive Insights (JARVIS copilot track) | M | Skipped twice now (2026-08-07 ×2, 2026-08-10). Next run should seriously prioritize this — it's the routine's own named copilot track and has gone three runs untouched. |
| `google-generativeai` → `google-genai` SDK migration | M | Old SDK raises `FutureWarning` on every import; not urgent but growing risk. Touches every Gemini call site — needs its own dedicated, fully-regression-tested run. |
| Dataframe/table widgets ignore the light/dark theme toggle | S–M | New finding this run (see screenshots above). `modules/theme.py` only styles the `stDataFrame` container border, not Streamlit's internal glide-data-grid canvas colors. |
| Polars/DuckDB-backed large-file pipeline | L | `data_engine.py` is pandas-only; SQL Lab already proves DuckDB works in this codebase. Architecture-adjacent — flagged for a dedicated run three runs running now. |
| Data Quality Score with exportable scorecard | M | Health score already exists in Overview; this would package it as a standalone, downloadable artifact. |
| Advanced outlier detection (LOF, DBSCAN) | M | Beyond the existing IsolationForest/IQR methods. |
| Feature Selection Engine (mutual info, RFE, L1) for ML Lab | M | Not started. |
| Natural-language summary of every tab | M | Not started. |

## 4. Interview notes (STAR-style, verbatim-usable)

> **Anomaly Narration.** *Situation:* Prism's anomaly detector (IsolationForest)
> flagged unusual rows but only explained them with a templated string like
> "column X is 95x above the median" — useful for an analyst, not for a
> stakeholder skim. *Task:* turn that into a genuinely agentic explanation
> without blowing a free-tier Gemini rate limit. *Action:* I built a
> narration layer that summarizes the flagged set's actual statistics into a
> compact prompt, short-circuits entirely (zero API calls) when nothing was
> flagged, and caches the response in session state keyed on a content
> fingerprint of the flagged row indices — so the same detection result never
> triggers a second paid-adjacent call. *Result:* shipped with 11 passing
> unit tests covering the cache-invalidation logic, the no-model and
> no-result error paths, and prompt-content correctness, verified against
> both a mocked Gemini model and a real Streamlit boot with screenshots in
> both themes.

## 5. Recommendation for next run's focus

1. **Atlas Proactive Insights** — the copilot track has been skipped three
   runs in a row despite being explicitly named in the routine's brief.
   It's a good next pick precisely because it's been deferred, not because
   it's trivial.
2. Consider a dedicated "theme consistency" pass: this run found the
   dataframe-widget light-mode gap: might be worth pairing with the
   already-logged mobile Atlas-panel reflow bug in one focused UI-fidelity
   run, since both are cosmetic-but-visible in a live demo.
3. `google-generativeai` → `google-genai` migration keeps getting deferred
   (logged 3 runs running) — the risk is low urgency but non-zero; worth
   scheduling explicitly rather than leaving it as perpetual backlog.
