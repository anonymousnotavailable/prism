# Prism Improvement Routine — Run Report, 2026-08-10 (Run 3)

## A note on how this landed

The routine's own instructions describe a full-auto workflow that merges
straight to `main` and pushes it. This session's operating instructions
pin all work to a specific branch (`claude/adoring-meitner-z0f7se`) and
say not to push anywhere else, or open a pull request, without being asked
directly — so that's what happened here: everything below is committed and
pushed to that branch, `main` was left untouched. **To land this, either
merge/fast-forward `main` from `claude/adoring-meitner-z0f7se` yourself, or
ask for a pull request or a direct push to `main` next time.**

## What shipped

### 1. Test-suite integrity fix (audit-sourced, not a feature)

**What it does:** the 2026-08-07 changelog entry claimed "82/82 new unit
tests" across three modules shipped by Run 2. They were never real —
`pytest` only ever collected 27 tests, because what actually merged was
`eval/*_eval.py` print/check() scripts outside `pytest.ini`'s `testpaths`.
This run ported the same fixtures and assertions into real
`tests/test_auto_insights.py`, `tests/test_regression_diagnostics.py`, and
`tests/test_forecasting_stl.py` — 36 tests, all passing, zero behavior
change.

**Why it mattered:** Run 1's own headline audit finding was "zero test
coverage = the single biggest interview-credibility gap." Run 2 believed
it had closed that gap on three features and reported so in both the
changelog and its own memory log — but hadn't. An interviewer cloning the
repo and running `pytest` would have found the same gap Run 1 flagged,
directly contradicting what the project's own paper trail claimed. Full
detail: `.prism/audit_2026-08-10.md`.

### 2. Anomaly Narration (this cycle's required agentic-AI-analysis pick)

**What it does:** the Anomaly Detection panel (Overview tab) already
flagged unusual rows with a templated one-line reason. It now has an
optional "✨ Explain these anomalies" button that sends those flagged rows
to Gemini and gets back a short plain-English explanation: what pattern
the anomalies share, one plausible real-world cause, and one concrete next
step. No extra rate-limit surface — it reuses the same shared
`call_gemini()` limiter every other AI feature in the app already respects
— and it degrades gracefully with no Gemini key configured or nothing
flagged (no wasted API call in either case).

**Why it was chosen:** every run of this routine must ship something on
the agentic-AI-analysis theme — LLM-driven insight generation on top of a
deterministic detector, not a chat wrapper around raw data. This closes a
backlog item open since Run 1 and mirrors an already-shipped, already-
tested pattern (`auto_insights.narrate_insights`) rather than inventing a
new one.

**Technical-depth argument:** this is explainable anomaly detection (XAD)
— an active research area (see `.prism/research_2026-08-10.md` for
sourced links) — implemented as a thin, cheap LLM layer *on top of* a real
statistical detector, not an LLM guessing at anomalies from raw rows. The
separation (deterministic detection → LLM narration of already-verified
facts) is the same design principle behind this repo's earlier Insight
Verifier feature, and it's exactly the kind of "don't let the LLM
hallucinate the numbers" discipline an ML-literate interviewer probes for.

### 3. Local Outlier Factor detection method

**What it does:** the same Anomaly Detection panel now has a "Detection
method" selector: Isolation Forest (existing default, tree-based) or Local
Outlier Factor (new, density-based). LOF flags points that look normal
against the whole dataset's distribution but stand out against their
nearest neighbors — a genuinely different failure mode than what
Isolation Forest catches. `n_neighbors` auto-caps to the dataset size so
small datasets don't error out on sklearn's default of 20 neighbors.

**Why it was chosen:** backlog item since Run 2 ("Advanced Outlier
Detection: LOF, DBSCAN"), scoped down to LOF alone this run to keep the
UI/test surface to one added control. Ships in the same commit as #2 since
both live in `modules/anomaly.py` and the same UI expander.

**Technical-depth argument:** tree-based vs. density-based outlier
detection is a standard applied-ML contrast (global isolation vs. local
density deviation) that a data-science interview panel would recognize
immediately — and picking the right one for a given dataset shape is a
real decision, not a checkbox. Offering both, side by side, on the same
data signals that distinction is understood rather than memorized.

## Screenshots

Desktop, dark theme — method selector, Isolation Forest results, LOF
results (all clean on the sample sales dataset — a legitimate "no
anomalies found" outcome for both methods, not a bug):

- `.prism/runs/2026-08-10/anomaly_method_selector_desktop_dark.png`
- `.prism/runs/2026-08-10/anomaly_flagged_isolation_forest_desktop_dark.png`
- `.prism/runs/2026-08-10/anomaly_flagged_lof_desktop_dark.png`

Desktop, Arctic (Light) theme:

- `.prism/runs/2026-08-10/anomaly_flagged_desktop_light.png` — also
  documents a **newly found, pre-existing bug**: the top nav bar and
  bottom command input stay dark-styled under the light theme while
  everything else switches. Not caused by this run (no CSS touched), not
  fixed this run (deserves its own dedicated theming pass), logged in
  `.prism/audit_2026-08-10.md` and the routine log for the next run.

Mobile, dark theme:

- `.prism/runs/2026-08-10/mobile_dark_top_atlas_reflow_bug_still_present.png`
  — the anomaly panel itself wasn't reachable at 390px width because of
  the **already-logged** (Run 2, 2026-08-07) Atlas side-panel reflow bug
  that squeezes main content into an unreadable strip. Reconfirmed still
  present, not re-fixed (out of scope, same reasoning as Run 2's).

No live Gemini API key was available in this execution sandbox, so the
"✨ Explain these anomalies" narration output itself wasn't visually
captured — verified via unit tests (a fake-model harness exercising the
real `call_gemini()` code path) instead, same limitation Run 1 hit and
noted for the same reason.

## Verification

- `pytest`: **70/70 passing** (27 at the start of this run → 63 after the
  test-suite integrity fix → 70 after the anomaly features' own new tests).
- Fresh Streamlit boot after each merge: HTTP 200, no traceback, checked
  three times across the run (after the fix, after the feature merge, and
  once more from the final state of `claude/adoring-meitner-z0f7se`).
- No `.env`/secrets touched or committed; `.gitignore` still covers `.env`.

## Research findings not built (ranked backlog for future runs)

Full table with sourced evidence: `.prism/research_2026-08-10.md`. Summary,
highest priority first:

1. **Feature Selection Engine** (mutual info / RFE / L1) for ML Lab —
   depth 4, effort M, low-medium risk. Top candidate for next run.
2. **polars/DuckDB unified large-file backend** — depth 4, effort L,
   architecture-adjacent; needs its own dedicated run per this routine's
   own no-architecture-rewrite guardrail.
3. **`google-generativeai` → `google-genai` SDK migration** — not urgent,
   but the deprecation warning is real and the SDK is unmaintained; needs
   a dedicated regression-tested run (touches every Gemini call site).
4. Two now-confirmed, still-open bugs, both deliberately deferred rather
   than rush-fixed: the mobile Atlas panel CSS reflow at ~390px (Run 2),
   and the light-theme dark-nav-bar styling gap (this run).

Dropped from the backlog entirely this run: "Data Quality Score with
exportable scorecard" — re-checked and found effectively already shipped
via `modules/report.py`/`modules/report_writer.py`'s existing HTML/PDF
export (health score, missing/outlier/duplicate breakdown, Gemini
narrative). Won't resurface unless a concrete new gap is found.

## Interview notes (STAR-style, verbatim-usable)

**Test-suite integrity fix:**
> "I audited our own project's test coverage claims against what `pytest`
> actually collected, found a 55-test gap between what the changelog
> claimed and what a fresh clone would show a reviewer, traced it to test
> scripts that lived outside pytest's configured test path, and ported
> them into real, passing pytest tests — closing the gap without changing
> any behavior."

**Anomaly Narration:**
> "I designed an explainable-anomaly-detection feature that keeps the LLM
> strictly downstream of a deterministic statistical detector — Isolation
> Forest/LOF find the anomalies and compute the numeric reasons, Gemini
> only narrates facts it's handed, never invents its own — so the feature
> gets LLM-quality explanations without the classic LLM-hallucinates-
> the-data failure mode, and it's built to degrade gracefully and stay
> within a free-tier rate limit."

**Local Outlier Factor:**
> "I extended our anomaly detection from a single tree-based method to a
> selectable tree-based-vs-density-based pair, handling the practical
> edge case (LOF's neighbor count exceeding small datasets) that a naive
> implementation would crash on, so users can choose the right detector
> for their data's shape instead of getting one-size-fits-all results."

## Recommendation for next run's focus

Build the **Feature Selection Engine** (mutual info / RFE / L1) for ML
Lab — it's the highest-scored untouched backlog item, reuses ML Lab's
existing UI patterns, and adds a distinct ML-capability signal (feature
importance / dimensionality reasoning) that this repo doesn't have yet.
Pair it, if budget allows, with a dedicated light-theme CSS pass to close
both styling bugs (mobile Atlas reflow + light-theme dark nav bar) found
across the last two runs — bundle them together since both are the same
class of work (theme.py CSS audit) rather than doing two separate
half-runs on styling.
