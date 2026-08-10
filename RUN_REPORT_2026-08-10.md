# Prism Autonomous Improvement Run — 2026-08-10

Full-auto run per `.prism/routine_log.md`'s standing instructions. Two
features shipped plus one bundled small fix (test-coverage gap) and one
bug fix discovered during Phase 5 verification. All branches merged to
`main`, tested, and pushed.

## 1. What shipped

### Anomaly narration (agentic-AI theme — required this cycle)

**What it does:** In the Overview tab's Anomaly Detection panel, after
IsolationForest flags unusual rows, a new "✨ Explain these anomalies with
AI" button asks Gemini to explain the pattern in plain English — is this
likely data-entry error or a genuine rare event? — and suggests one
concrete next action. The narration is cached against a fingerprint of
the exact flagged set (row count + index/reason hash), so switching tabs
and coming back doesn't burn another free-tier Gemini call for a result
already shown.

**Why chosen:** Both 2026-08-07 runs' backlogs flagged this as open —
`anomaly.py` had templated reason strings but no narration layer. This
cycle's priority theme requires an agentic-AI feature; this was the
highest-evidence, lowest-risk candidate (see `.prism/research_2026-08-10.md`).

**Technical-depth argument:** It's the "insight discovery" step from the
agentic-EDA research pattern (arXiv 2508.02744) applied concretely: a
statistical detector (IsolationForest over numeric columns) hands its
raw output to an LLM step whose only job is *interpretation*, not
detection — keeping the actual anomaly-finding deterministic and
auditable while using the LLM for what LLMs are actually good at. The
caching-by-fingerprint design is a direct, deliberate response to the
routine's "design for rate-limit handling and caching" constraint, not
an afterthought.

### Atlas proactive alert HUD (JARVIS-copilot track, ≤1/run cap)

**What it does:** Atlas's orb gains a new `alert` visual state — an amber
double-ring pulse with a "⚠ N new insight(s)" label — that appears
**unprompted** the moment a freshly uploaded dataset contains a
high-severity Auto-Insight finding (severe missing data, high duplicate
rate, etc.). No button click, no question asked. It clears the next time
the user actually views the Overview tab's findings.

**Why chosen:** Backlog item from both 2026-08-07 runs ("Atlas Proactive
Insights" / JARVIS track), never built. The routine caps JARVIS-track
features at one per run — this is a genuinely incremental slice (a new
orb state plus the wiring to trigger it), not the full copilot vision.

**Technical-depth argument:** Zero additional Gemini calls — it's pure
reuse of a computation (`auto_insights.generate_insights()`) the app
already runs on every upload, surfaced as an unprompted signal instead of
a scrollable list the user has to notice themselves. That reuse-not-
recompute design, plus the same-run self-clear bug this run's own
verification caught and fixed (see below), is exactly the kind of subtle
Streamlit state-timing issue that's easy to gloss over and worth being
able to explain in an interview.

### Bundled small fix: backfilled test coverage (42 tests)

`CHANGELOG.md` and `routine_log.md` both claimed the 2026-08-07 run
shipped 82 tests for `auto_insights`, `regression_diagnostics`, and STL
decomposition. `git log --all -- tests/` proved otherwise — those tests
were never committed. Found during this run's audit, treated as a small
fix rather than re-litigated: 42 tests backfilled covering the main
detector/fit/diagnostic paths plus empty/single-row/collinear/
heteroscedastic edge cases (see `tests/test_auto_insights.py`,
`tests/test_regression_diagnostics.py`, `tests/test_forecasting_stl.py`).

## 2. Bug found and fixed during verification

Phase 5's screenshot check on the alert HUD found it wasn't actually
visible: the side panel's small header orb had sizing CSS but no
background/gradient/animation rules — those live in a block only injected
by `render_orb()`, which is skipped once a dataset is active (the side
panel replaces the floating orb). This was a **pre-existing** issue
affecting every orb state, not something this run's feature introduced —
it had just never been visually checked closely before. Fixed by
extracting `atlas.inject_orb_css()` and calling it from both render paths.
A second bug (the alert clearing itself in the same script pass it was
raised in, since Overview is the default tab) was fixed alongside with a
one-run grace flag. See `9f6a632` for the full fix and reasoning.

## 3. Screenshots

All captured via `.prism/runs/2026-08-10/screenshot_features.py`
(Playwright, headless Chromium) against a locally running instance, using
a small crafted CSV (`alert_demo.csv`) with a 75%-missing column to
reliably trigger the high-severity alert path.

**Orb alert state — desktop, dark:**
![orb alert dark](.prism/runs/2026-08-10/01_orb_alert_desktop_dark.png)

**Anomaly Detection panel with the new narration button — desktop, dark:**
![anomaly narrate dark](.prism/runs/2026-08-10/02_anomaly_narrate_button_desktop_dark.png)

**Orb alert state — desktop, light (Arctic theme):**
![orb alert light](.prism/runs/2026-08-10/04_orb_alert_desktop_light.png)

**Anomaly Detection panel — desktop, light:**
![anomaly narrate light](.prism/runs/2026-08-10/05_anomaly_narrate_button_desktop_light.png)

**Orb alert state — mobile, dark:**
![orb alert mobile](.prism/runs/2026-08-10/06_orb_alert_mobile_dark.png)

No live-Gemini-output screenshot of the anomaly narration text itself —
this sandbox has no configured `GEMINI_API_KEY` (same documented
limitation as both 2026-08-07 runs). The graceful fallback message
("I can't reach Gemini right now — no API key is configured") was
incidentally exercised during screenshot capture and rendered correctly
rather than crashing — a small positive signal for the app's error
handling. Narration logic itself is covered by 6 unit tests using a fake
model object standing in for the Gemini client.

The mobile screenshot also reconfirms a bug flagged (not caused) by
2026-08-07 Run 2: at ~390px width the Atlas side panel doesn't reflow and
squeezes main content into an unreadable vertical sliver. Still open,
still flagged for a dedicated CSS-reflow pass — not touched this run.

No demo GIF this run — both shipped features are best shown as static
before/after state (an orb color change, a new button) rather than a
multi-step interaction; the screenshots above cover it more clearly than
a recording would.

## 4. Research findings NOT built (backlog)

See `.prism/research_2026-08-10.md` for full evidence/scoring. Ranked,
highest depth first:

| Feature | Depth | Effort | Why not this run |
|---|---|---|---|
| polars/DuckDB large-file backend | 5 | L | Architecture-adjacent (touches `data_engine.py` pipeline-wide); flagged for a dedicated run by both prior runs, reconfirmed here |
| Feature Selection Engine (mutual info/RFE/L1) for ML Lab | 4 | M | Not this cycle's priority theme; queued |
| Advanced outlier detection (LOF, DBSCAN) | 4 | M | Needs its own eval harness to present method disagreement sensibly; queued |
| Data Quality Score with exportable scorecard | 3 | M | Lower urgency than the agentic-theme picks this cycle |
| `google-generativeai` → `google-genai` migration | 2 (hygiene) | M | Touches 4 Gemini call sites; needs a dedicated run with full regression testing, not a rushed patch |
| Light-theme dataframe styling on Overview (new finding) | — | S | Discovered during this run's own screenshot review; small fix, queued for next run |

## 5. Interview notes (STAR-style, verbatim-usable)

**Anomaly narration:**
> "I built a self-verifying anomaly pipeline where an IsolationForest
> model does the actual outlier detection — deterministic, auditable,
> no LLM involved — and Gemini's role is strictly interpretation: turning
> 'these 12 rows got flagged' into 'this looks like data-entry error in
> one field, here's what I'd check first.' I cached the narration by a
> fingerprint of the flagged set specifically because Gemini's free tier
> has rate limits, so re-viewing the same result never re-spends a call."

**Atlas proactive alert HUD:**
> "I found and fixed a real bug in my own feature during code review
> before shipping it: the alert I'd built to prove out 'proactive,
> unprompted' insight surfacing was clearing itself in the same script
> pass it was raised in, because Streamlit re-executes top-to-bottom and
> the default tab happened to contain both the trigger and the clear
> condition. I traced it with a one-run grace flag rather than papering
> over it with a delay, and wrote tests that specifically cover the
> same-run-vs-later-run distinction so it can't regress silently."

**Backfilled test coverage:**
> "During a routine audit I found our own changelog had over-claimed test
> coverage — three modules with zero actual committed tests despite the
> report saying 82. Rather than just noting it, I treated it as a bug and
> backfilled 42 real tests covering the statistical edge cases that
> matter (heteroscedasticity, collinearity, empty/single-row inputs) —
> because a portfolio project's credibility rests on its claims matching
> its repo, not on the changelog reading well."

## 6. Recommendation for next run

1. **Fix the mobile Atlas panel overlap** (~390px viewport) — reconfirmed
   present in this run's own screenshots, flagged by two prior runs now.
   It's a real "app breaks in a live demo" risk on an actual phone.
2. **Light-theme dataframe styling** on Overview's Missing-Values/Outliers
   tables — small, self-contained, found this run.
3. If a Gemini API key becomes available in the execution sandbox, redo
   the anomaly-narration and Auto-Insights-narration screenshots with the
   real LLM output visible — three runs in a row have now shipped
   Gemini-dependent features never visually confirmed end-to-end.
4. Consider the polars/DuckDB large-file backend as a **dedicated**
   run (not squeezed alongside feature work) given its architecture-wide
   blast radius — it's the highest-depth item still on the backlog.

---

# Addendum — Run 4 (same day)

A fourth automated pass against this repo, later the same day. One
feature plus one bundled bug fix, deliberately smaller in scope than the
routine's usual 2-3 features — see reasoning below and in
`.prism/routine_log.md`'s Run 4 entry.

## 1. What shipped

### ML Lab Feature Selection Engine

**What it does:** A new "Feature Selection Engine" section in ML Lab,
between the existing Feature Engineering Assistant and Baseline Model
Runner. Pick a target, click "Rank Features", and every other column gets
scored by mutual information against it (catches non-linear relevance a
correlation coefficient alone would miss entirely), cross-checked for
near-duplicate pairs via pairwise correlation, and flagged for
multicollinearity via VIF (variance inflation factor) — the standard
statistical diagnostic that catches a feature being a linear combination
of several others even when it isn't highly correlated with any single
one (see `tests/test_feature_selection.py::test_flags_high_multicollinearity_via_vif`
for a worked example a plain correlation check would miss). A "Use
recommended features" button hands the non-redundant subset straight to
the Baseline Model Runner's feature multiselect below, and an optional
"✨ Explain this ranking with AI" button gets a cached Gemini narration of
the result (same fingerprint-caching pattern as anomaly narration — no
repeat Gemini calls on re-view).

**Why chosen:** ML Lab's existing Feature Engineering Assistant answers
"how should I treat each feature" (encode/scale/expand); nothing in the
app answered the earlier question, "which features are actually worth
keeping." Runner-up candidate was an LOF/DBSCAN outlier-detection
ensemble layered onto the existing IsolationForest anomaly detector —
rejected in favor of this because it's a genuinely new analytical
capability rather than a second algorithm answering a question Prism
already answers; carried forward as next run's top feature-backlog pick.

**Technical-depth argument:** Mutual information (not correlation) as the
primary relevance signal, VIF as the multicollinearity diagnostic, and
correlation-based redundancy pruning are all standard feature-selection
tooling straight out of a data scientist's actual pre-modeling workflow —
exactly what a hiring panel would expect someone to reach for before
training a model, not just a nice-to-have UI addition. 16 new tests,
including one that specifically demonstrates VIF catching a
multicollinear feature that pairwise correlation alone misses.

### Bundled small fix: light-theme dataframe styling

**What it does:** Overview's "Missing Values by Column" and "Outliers
(IQR method)" tables — plus this run's new Feature Selection ranking
table — now render via a new `ui.render_html_table()` helper instead of
`st.dataframe()`, so they correctly re-theme when the user switches to
Light mode.

**Why chosen:** Flagged as an open finding in the previous run's own
audit (`.prism/audit_2026-08-10.md`); root-caused this run: `st.dataframe()`
renders through a canvas-based grid (glide-data-grid) that only reads
`.streamlit/config.toml`'s static `base = "dark"` setting — Prism's
runtime light/dark toggle just injects CSS on top of the DOM, which a
canvas grid never sees. A plain HTML table styled with the app's own
`--prism-*` CSS custom properties sidesteps the problem entirely for
tables small enough not to need native sort/resize.

## 2. Bug found and fixed during Phase 5 verification

`feature_selection.fingerprint_ranking()` and `narrate_selection()`
originally built row text via `ranking.itertuples()` then indexed rows
with `r['MI Score']` — but `itertuples()` renames non-identifier column
names (ones containing spaces, like `"MI Score"`) to positional fields, so
this raised `TypeError: tuple indices must be integers or slices, not str`
the moment "Rank Features" was actually clicked in the running app. The
original unit tests all passed regardless, because they only exercised
the empty-ranking and no-model early-return paths — neither touches the
buggy line. Caught by the Playwright screenshot in Phase 5 (see
`02_feature_selection_desktop_dark.png`'s first capture, which showed a
raw Streamlit traceback instead of the ranking table). Fixed by switching
both functions to `ranking.to_dict("records")`; added two regression
tests using a realistic ranking shape (one with a mocked `call_gemini`)
so this exact class of bug — unit tests all green while the live-app path
crashes — can't silently return.

## 3. Screenshots

All in `.prism/runs/2026-08-10-run4/`:

- `01_overview_tables_desktop_dark.png` / `02_feature_selection_desktop_dark.png` — desktop, dark theme
- `03_overview_tables_desktop_light.png` / `04_feature_selection_desktop_light.png` — desktop, light theme (confirms the styling fix — tables are readable light-on-dark-text instead of stuck dark)
- `05_overview_tables_mobile_dark.png` — mobile, dark theme

**Mobile ML Lab screenshot not obtained** — see the escalated Atlas-panel
finding below; this is a pre-existing app limitation, not a regression
introduced by this run's changes.

## 4. New findings (not fixed this run, backlog)

1. **Mobile Atlas panel overlap — escalated.** Two prior runs flagged
   this as "needs a focused CSS reflow pass." At 390px width it's worse
   than described: the Atlas side panel is fixed/sticky and squeezes the
   entire main content column to roughly 30px wide, making the nav bar —
   and therefore every tab past Overview — unreachable on mobile without
   first collapsing the panel. This currently blocks mobile PWA usability
   outright, not just a visual nit. **Recommended as next run's top
   priority.**
2. The "Ask Atlas about your data…" chat input bar keeps a black
   background in Light theme (visible in this run's light-theme
   screenshots) — likely the same canvas/fixed-theme-source class of bug
   as the dataframe fix above, in a different component.
3. ML Lab's "Class Distribution" Plotly chart keeps a dark background in
   Light theme — `modules/visualization.py` sets the Plotly template once
   at import time and it doesn't re-apply on the runtime theme toggle.
   Worth a dedicated pass across every chart in the app, not a one-off.

## 5. Interview notes (STAR-style, verbatim-usable)

**Feature Selection Engine:**
> "I added a feature-selection step to the ML Lab using mutual information
> rather than plain correlation, specifically because correlation misses
> non-linear relationships and can't catch a feature that's a linear
> combination of several others — for that I added a VIF check, the same
> multicollinearity diagnostic you'd use in a real modeling workflow. I
> wrote a test that constructs exactly that case — a feature built as
> `0.5*a + 0.5*b` — to prove VIF flags it even though it isn't strongly
> correlated with `a` or `b` individually."

**Bug caught in my own Phase 5 review:**
> "My unit tests for a new caching function all passed, but they only
> exercised the early-return paths — empty input, missing model. When I
> actually clicked the feature in the running app during screenshot
> verification, it crashed: I'd used `itertuples()` then indexed a column
> with a space in its name using bracket syntax, which only works on
> `to_dict('records')`, not positional namedtuples. Rather than just
> patching the line, I added a regression test using a realistic shape of
> the actual data so the specific gap in my original tests — passing
> green while missing the one path that mattered — can't recur silently."

## 6. Operational note: branch-policy recovery

Mid-run, the designated development branch was found deleted from origin
(its content had already reached `main`, matching this repo's actual
merge-via-PR convention rather than the routine's generic "push main
directly" instruction). Recovered by recreating the branch from a fresh
`origin/main` fetch and cherry-picking this run's one work commit onto
it — verified via `git merge-base --is-ancestor` before trusting either
ref, so no work was at risk of being lost or silently discarded. Per this
session's fixed branch policy (never push to a branch other than the
designated one), this run's work was pushed to `claude/adoring-meitner-a28q0n`
and a pull request opened into `main`, rather than pushing `main` directly
as the routine's Phase 7 literally describes — the two conflict, and the
stricter, more conservative branch policy was treated as authoritative.
Full account in `.prism/routine_log.md`'s Run 4 entry, written so a future
run recognizes this as a recoverable situation rather than a corruption.

## 7. Recommendation for next run

1. **Fix the mobile Atlas panel overlap** — now confirmed to make the app
   effectively unusable on a real phone below ~400px, not just visually
   inconsistent. Top priority.
2. **Advanced outlier detection ensemble (LOF/DBSCAN)** — this run's
   runner-up candidate, carried forward.
3. Light-theme fixes for the chat input bar and Plotly chart backgrounds
   (both new findings above) — likely small, self-contained.
4. Still open from prior runs: polars/DuckDB large-file backend (dedicated
   run), `google-generativeai` → `google-genai` migration (dedicated run —
   the deprecation warning now fires on every single test invocation).
