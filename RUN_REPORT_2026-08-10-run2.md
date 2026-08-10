# Prism Autonomous Improvement Routine — Run Report

**Date:** 2026-08-10 (Run 4 overall — third and fourth features shipped today's second scheduled run)
**Branch:** `claude/adoring-meitner-qjt1uj` (see note below — not `main`)

> **Process note:** this session's harness assigned a specific development
> branch with an explicit instruction not to push elsewhere without live
> user approval. The routine's own Phase 7 asks for a direct push to
> `main`, but a scheduled run has no live user mid-run to approve
> deviating from that assignment, so the harness-level constraint was
> treated as authoritative — all commits below landed on
> `claude/adoring-meitner-qjt1uj`, not `main`. A human should fast-forward
> or merge that branch into `main` when reviewing this report.

---

## 1. What shipped

### Feature Selection Engine (`modules/feature_selection.py`)

**What it does:** in ML Lab, ranks candidate feature columns by predictive
value for the chosen target using three complementary, textbook methods:

- **Mutual Information** (`sklearn.feature_selection.mutual_info_classif`/
  `_regression`) — model-free, catches non-linear relationships a linear
  model would miss.
- **L1-regularized coefficients** (`LogisticRegression(penalty="l1")` for
  classification, `LassoCV` — cross-validated regularization strength —
  for regression) — the classic embedded method; L1 drives redundant
  features' weights to exactly zero, directly surfacing multicollinearity.
- **Recursive Feature Elimination** — wrapper method; importance reflects
  features *in combination*, not in isolation.

One-hot encoded categorical columns are aggregated back to their parent
feature so the ranking stays interpretable at the level the user actually
picked columns. Results synthesize into a consensus score, a ranked bar
chart, and plain-English narrative (top predictor, unanimous agreements,
zero-signal drop candidates, MI/Lasso disagreements suggesting
non-linearity). A one-click button hands the top-K recommended features
straight to the Baseline Model Runner's feature multiselect.

**Why chosen:** the single highest technical-depth item left on the
standing backlog (flagged since 2026-08-07, never built) — feature
selection is core applied-ML methodology, not just an EDA nicety, and
demonstrates knowledge of *why* you'd reach for three different methods
instead of trusting one.

**Technical-depth argument:** most portfolio projects show *a* model.
Fewer show *why specific features were chosen* before modeling, and fewer
still show three independent, well-justified methods cross-checking each
other with an explicit disagreement analysis (MI-high/Lasso-low →
"probably non-linear, your linear baseline will miss it"). That's the
difference between "I ran sklearn" and "I understand what each feature
selection method actually measures and where it fails."

**Bug caught and fixed during Phase 5 verification:** ranking against a
realistic dataset with an ID-like column (`employee_id`, one distinct
value per row) took ~10 seconds — RFE's default `step=1` does one model
fit per one-hot column, and a 300-row ID column one-hot-expands into 300
columns. Bounded the step size (~3s after the fix) and added an explicit
narrative warning for likely-ID candidate columns, so the tool teaches the
same lesson a real practitioner learns the hard way.

### Data Quality Scorecard (`modules/quality_scorecard.py`)

**What it does:** turns the Overview tab's existing 0-100 Data Health
Score into a per-column, letter-graded (A-F) scorecard — overall grade,
the 5 weighted component grades (completeness/consistency/uniqueness/
validity/outlier burden), and the 5 weakest-scoring columns. Exportable as
a one-page branded PDF (reusing the existing cleaning-certificate's fpdf2
pattern) or raw JSON. New expander on the Overview tab.

**Why chosen:** closes a backlog item flagged by both 2026-08-07 runs and
today's earlier run — "Data Quality Score with Exportable Scorecard."
Deliberately does zero new computation (reshapes data the app already
computes every load), so it's essentially free and directly reinforces
this cycle's agentic-AI theme: the scorecard is generated automatically on
every dataset load, no button click needed, same as Auto-Insights.

**Technical-depth argument:** the underlying health score was already
interview-grade (5 weighted, independently-visible components — not a
black-box number). The scorecard makes that legible to someone who isn't
a data scientist and never opens the app — a governance reviewer, a
manager, or an interviewer skimming a portfolio's screenshots. Exportable
artifacts are a concrete "deliverable," not just a UI feature.

---

## 2. Screenshots

All captured via Playwright at 1440×1000 (desktop) against a real upload
(`samples/hr_data.csv`, 300 rows). Full set in
`.prism/runs/2026-08-10-run2/`.

| File | What it shows |
|---|---|
| `01_quality_scorecard_desktop_dark.png` | Scorecard expander, dark theme — overall grade A, component grades, weakest-columns table, PDF/JSON download buttons |
| `02_feature_selection_desktop_dark.png` | Feature Selection Engine, dark theme — narrative bullets (ID-column warning, top predictor, MI/Lasso disagreement) + consensus ranking chart |
| `03_quality_scorecard_desktop_light.png` | Scorecard expander, Arctic (Light) theme |
| `04_feature_selection_desktop_light.png` | Feature Selection Engine, Arctic (Light) theme |
| `05_mobile_dark_landing_atlas_panel_blocker.png` | Documents the pre-existing Atlas side-panel mobile overlap (see §3) rather than these two features — consistent with how the 2026-08-07 Run 2 handled the same pre-existing blocker |

Two things visible in the light-theme screenshots are **pre-existing,
not regressions from this run** — documented in detail in
`.prism/routine_log.md`:
- The scorecard's weakest-columns table keeps dark row styling under the
  light theme (same root cause already flagged for two other Overview
  tables — `st.dataframe`'s canvas grid reads `config.toml`'s
  `base="dark"` directly, not Prism's CSS toggle).
- The consensus ranking chart stays dark-templated under the light theme
  — and so, confirmed during this run, does *every other* Plotly chart in
  the app (verified on the unmodified Class Distribution and
  Auto-Generated Charts). This is a new, higher-priority finding — see
  the backlog below.

Both were investigated this run (see the routine log for two fix attempts
that were tried and reverted after making things worse) rather than
shipped half-fixed.

---

## 3. Research findings NOT built (ranked backlog for future runs)

| Priority | Item | Why not this run |
|---|---|---|
| **High (new)** | App-wide Plotly light-theme bug | Just discovered during this run's own Phase 5 check; affects every chart, not just new ones. Root cause not yet isolated — needs a dedicated debugging pass (see routine log for a concrete first step). |
| High | Light-theme `st.dataframe` styling | Root cause now confirmed (canvas grid reads `config.toml`, not runtime CSS); an `st.table`+Styler fix was tried and reverted for worse contrast/formatting. Needs explicit Styler rules or a custom HTML table component. |
| High | Mobile Atlas panel overlap at ~390px | A `position: static` fix was tried and reverted — made the squeeze worse (flex-collapse), not just a squished-but-visible strip. Root cause is upstream of the panel's own CSS. |
| Medium | `google-generativeai` → `google-genai` SDK migration | Touches every Gemini call site; still needs its own dedicated, fully-regression-tested run. |
| Medium | polars/DuckDB-backed large-file path | Architecture-adjacent (SQL Lab already has DuckDB); extending it to the main dataframe pipeline is out of scope for a feature-shipping run. |
| Medium | Advanced outlier detection (LOF, DBSCAN) | Beyond the existing IQR/IsolationForest methods; a reasonable next ML Lab addition. |
| Low | Feature Selection ↔ Baseline Model auto-pipeline | This run's handoff is one click; a fully automatic "rank then train on the winners" flow is a possible future polish. |

---

## 4. Interview notes (STAR-style, verbatim-usable)

**Feature Selection Engine:**
> "I added a feature selection module to my data analysis tool that ranks
> candidate features using three independent methods — mutual information,
> L1-regularized regression, and recursive feature elimination — instead
> of trusting a single method, because each catches a different failure
> mode: mutual information catches non-linear relationships a linear model
> would miss, while L1 regularization directly surfaces multicollinearity
> by driving redundant coefficients to zero. When I tested it against a
> realistic HR dataset, I found ranking an ID-like column took 10 seconds
> because recursive elimination was doing one model fit per one-hot-encoded
> category — I fixed that by bounding the elimination step size, which cut
> it to 3 seconds, and added an explicit warning so the tool now teaches
> users to exclude ID columns instead of silently being slow."

**Data Quality Scorecard:**
> "I turned my app's data quality score into an exportable, letter-graded
> scorecard — PDF and JSON — so a non-technical stakeholder or reviewer
> could see the data quality assessment without opening the tool itself.
> It reuses computation the app already does on every upload, so it's
> effectively free, and it's generated automatically rather than requiring
> a button click, which was a deliberate design choice to match the app's
> broader 'proactive analysis' pattern rather than a passive report you
> have to remember to ask for."

---

## 5. Recommendation for next run's focus

**Start with the app-wide Plotly light-theme bug.** It's a bigger
interview-demo risk than anything else currently on the backlog — every
chart in the app, not a table or two — and now has a documented starting
point (compare `pio.templates.default` immediately before a chart-building
call in both themes to see whether the *default* is wrong at render time
or something else is pinning an earlier template). Pair it with the
already-diagnosed `st.dataframe` styling issue if there's budget left,
since both are theming-layer bugs and may share more root cause than
currently known.

Second priority: the mobile Atlas panel overlap has now had two
independent runs try quick CSS fixes and fail (both made it worse) — it
genuinely needs the "dedicated pass" both logs have called for, starting
with understanding what constrains `stMainBlockContainer`'s width when the
panel is taken out of `position: fixed`, before touching the panel's CSS
again.
