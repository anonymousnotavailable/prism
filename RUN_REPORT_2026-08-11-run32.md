# Run 32 Report — 2026-08-11

## Summary

Shipped two features on `claude/adoring-meitner-7xxgfq` (pushed at `7c86429`):

1. **Atlas: Bayesian A/B Test + Power Analysis voice/typed commands** — extends the intent
   router's keyword fast path (Run 17, `a4aff81`) to invoke and explain the two Stats Lab
   panels Run 31 shipped.
2. **Text Analytics** (`modules/text_analytics.py`, new module) — sentiment scoring, TF-IDF
   keyword extraction, and NMF topic modeling for a free-text column, new Stats Lab panel.

Test suite: **738 → 788 passing, zero regressions.** Pushed to
`origin/claude/adoring-meitner-7xxgfq`. `main` untouched.

---

## Feature 1: Atlas intent-router extension

### What / why

Run 31 flagged the Atlas/JARVIS copilot track as 15 runs overdue and recommended, as a
concretely scoped starting point, wiring Atlas's intent router to the two new stats panels it
had just shipped. Read `modules/atlas.py` in full before touching anything, to match its
established two-layer pattern exactly: `classify_intent_fast()` (zero-Gemini keyword match)
first, `classify_intent()`'s single Gemini call only as fallback, dispatch through
`COMMAND_REGISTRY` (a plain dict app.py populates with its own functions — atlas.py only owns
routing).

Four new `APP_COMMAND` actions:

- **`run_bayesian_ab`** / **`run_power_analysis`** — navigate to Stats Lab and auto-run the
  panel using a deterministic best-guess column pairing. Since a spoken/typed command has no
  column pickers to fall back on, two new pure functions do the guessing:
  `bayesian_ab.auto_select_columns(df, column_types)` and
  `power_analysis.auto_select_inputs(df, column_types)`, each mirroring the panel's own
  selectbox eligibility rules exactly (2-8-level categorical/text/boolean column as the
  variant/group, a different eligible outcome column). Falls back to "navigate there and let
  the user configure it" when no obvious pairing exists — never guesses past that point, the
  same conservative bar as the existing fast path.
- **`explain_bayesian_ab`** / **`explain_power_analysis`** — voice/typed counterparts to each
  panel's existing "✨ Explain this" button, reusing the same `narrate_bayesian_ab()`/
  `narrate_power_analysis()` calls and narration cache.

Read-only compute commands (no `guarded()`/`push_undo_snapshot()` needed — Atlas never mutates
data through these, same as every other non-destructive stats-panel command).

### Files

- `modules/atlas.py` — router prompt schema/rules extended, 15 new fast-path phrase entries.
- `modules/bayesian_ab.py` — `auto_select_columns()`.
- `modules/power_analysis.py` — `auto_select_inputs()`.
- `app.py` — four new `_cmd_*` functions, registered in `COMMAND_REGISTRY`.
- `tests/test_atlas.py`, `tests/test_bayesian_ab.py`, `tests/test_power_analysis.py` — 14 new
  tests (5 + 5 + 4).

### STAR

**Situation:** Atlas's intent router hadn't been extended since Run 17; two brand-new,
genuinely useful stats panels (Bayesian A/B, Power Analysis) shipped in Run 31 with no voice/
typed entry point.
**Task:** Wire them in using the router's own established pattern, without inventing a parallel
mechanism, and without attempting a full auto-configure of every input a panel exposes.
**Action:** Added two pure, independently-testable auto-column-selection functions (rather than
duplicating that logic inline in `app.py`), extended the router's action schema/fast-path/rules,
and added thin `_cmd_*` glue in `app.py` that composes them — matching the exact shape of every
existing Atlas command (`_cmd_auto_clean`, `_cmd_run_recipe`, etc.).
**Result:** 14 new unit tests plus a 7-scenario AppTest verification (see below) confirm the
full chat-input-to-computed-result path works, including the two honest failure modes (no
eligible columns; no Gemini key for narration).

### Verification

- 14 new unit tests (pure functions, no Streamlit dependency) — all green.
- End-to-end via `streamlit.testing.v1.AppTest`. Hit the confirmed "second real `.run()` throws
  on an unrelated multiselect widget" harness quirk (reproduced first on an untouched baseline
  command, `"go to Clustering"` — genuinely pre-existing, not introduced this run). Worked
  around it with a new technique: monkeypatch `st.chat_input` to return the target utterance
  exactly once, so the real `chat_input → _process_atlas_utterance → atlas.handle_utterance →
  dispatch → _cmd_*` path executes for real inside a **single** `.run()` call (Streamlit's own
  `st.rerun()` calls inside that path are handled automatically within one `AppTest.run()`).
  7 scenarios, all zero-exception: successful run+explain for both panels; no-eligible-columns
  fallback for both (still navigates, says why); explain-before-any-result graceful message;
  explain-with-result-but-no-Gemini-key graceful narration failure.
- Live `streamlit run` smoke test: HTTP 200, clean logs.

---

## Feature 2: Text Analytics

### What / why

Ran a broader gap sweep (word-boundary-safe this time — an initial naive `grep "shap"` false-
positived on "shape"/"reshape" substrings and briefly suggested SHAP explainability was an open
gap; it is not, `modules/mllab.py` + ML Lab's SHAP panel already ship it in full). Confirmed real,
zero-hit gaps: text analytics (sentiment/TF-IDF/topic-model — zero matches anywhere) and
changepoint/CUSUM detection (also zero matches). Picked text analytics: broader utility for a
general-purpose EDA tool (most real datasets carry some free-text field — reviews, comments,
support tickets — while changepoint detection only applies to time series, already reasonably
served by STL decomposition + forecasting), and more technical surface per module (three real
techniques vs. one formula).

`modules/text_analytics.py` — pure numpy/pandas/scikit-learn, **zero new pip dependencies**
(nltk/textblob/vaderSentiment, the "obvious" sentiment-analysis libraries, are deliberately NOT
added, to keep the footprint flat):

- **Sentiment**: a ~90-word hand-curated polarity lexicon (-3..+3), with token-window negation
  flipping (`"not good"` → negative) and intensifier/diminisher scaling (`"very good"` >
  `"good"` > `"slightly good"`). Documented throughout as a heuristic first read on direction/
  proportion, not a trained classifier — misreads sarcasm and long-range negation, stated
  explicitly in the module docstring (same "state the honest limitation" convention as
  `power_analysis`'s post-hoc-power caveat from Run 31).
- **Keyword extraction**: `TfidfVectorizer` ranked by summed corpus TF-IDF weight — frequent
  *and* distinctive, not just frequent.
- **Topic modeling**: TF-IDF + NMF, `n_topics` auto-clipped to what the corpus can actually
  support (never more topics than documents or vocabulary size) rather than raising.
- `eligible_text_columns()` distinguishes actual prose (average ≥ 3 words/cell) from ID/code-
  like columns `data_engine.detect_column_types()` would also tag `"text"` — same "stay silent
  rather than force it" gating convention as every other conditionally-rendered Stats Lab panel.

Wired into Stats Lab after Power Analysis: column picker → Analyze button → sentiment bar +
most-positive/negative sample rows → top-terms bar → topic-share bar → cached "✨ Explain this"
Gemini narration. Three new `visualization.py` chart functions
(`plot_sentiment_distribution`, `plot_top_terms`, `plot_topic_shares`), same "return `None` on
not-ok" contract as every existing chart helper.

### Files

- `modules/text_analytics.py` (new).
- `modules/visualization.py` — three new chart functions.
- `app.py` — new Stats Lab panel, session defaults, import.
- `tests/test_text_analytics.py` (new, 36 tests).

### Bad-input handling

- Huge files: capped at 50k rows (matches `survival`/`bayesian_ab`'s `_MAX_ROWS` convention,
  samples down deterministically with `random_state=42`).
- Runaway single cells: capped at 5,000 chars before tokenization.
- Empty/too-short corpus, missing column, all-stopword corpus (empty TF-IDF vocabulary),
  more-topics-requested-than-corpus-can-support: all return `{"ok": False, "error": "..."}`,
  never raise.
- No Gemini key: narration gracefully returns an error string, same as every other `narrate_*`.

### STAR

**Situation:** No module in Prism had ever looked inside a free-text column's actual content —
only counted its nulls/uniqueness, despite `data_engine.detect_column_types()` already
distinguishing "text" from "categorical".
**Task:** Fill the gap with genuine technical depth (not a cosmetic word cloud), without adding
a new pip dependency, and with the same honesty-about-limitations standard the rest of the app
holds.
**Action:** Built three independently-testable, independently-gated analysis functions (any one
failing — e.g. too few docs for topic modeling — doesn't block the others from rendering) plus a
deliberately hand-built (not borrowed) sentiment lexicon with real negation/intensifier handling
rather than a naive bag-of-words count.
**Result:** 36 new tests plus a 2-scenario AppTest verification recovered the exact 50/50
positive/negative split of a synthetic corpus built with a known ground truth, confirming the
whole pipeline (lexicon scoring → TF-IDF → NMF) works correctly end to end, not just per-function.

### Verification

- 36 new unit tests (30 module-level covering sentiment/negation/intensifiers/eligibility/
  keywords/topics/narration, 6 chart-function) — all green.
- End-to-end via `AppTest`, same single-`.run()`-call technique as Feature 1 but monkeypatching
  `st.button` instead of `st.chat_input` (fires the "Analyze Text" button exactly once; the
  panel's own internal `st.rerun()` is handled automatically within that one call). 2 scenarios:
  successful run (sentiment/keywords/topics all render, zero exceptions, recovered 50.0% /
  0.0% / 50.0% positive/neutral/negative split exactly matching the synthetic corpus's known
  50/50 construction); silent no-crash when no column qualifies as prose.
- Live `streamlit run` smoke test: HTTP 200, clean logs, on the final merged branch.

---

## Merge / push

Both branches merged `--no-ff` into `claude/adoring-meitner-7xxgfq` with **zero conflicts** (the
two features touch non-overlapping regions: Atlas's changes are in the `_cmd_*`/
`COMMAND_REGISTRY` region of `app.py` and `modules/atlas.py`; Text Analytics's are the Stats Lab
panel body and new chart functions). `CHANGELOG.md` and `.prism/routine_log.md` updated. Pushed
to `origin/claude/adoring-meitner-7xxgfq` (`86685fa..7c86429`). Feature branches deleted (fully
merged). `main` never touched.

---

## Backlog not built this run

- **Changepoint/CUSUM detection** — confirmed real, zero-hit gap during this run's research
  sweep. Deferred in favor of Text Analytics's broader applicability; a solid Run 33+ candidate,
  implementable pure-numpy (no `ruptures` dependency needed for a basic CUSUM/binary-segmentation
  approach).
- **Atlas voice UX polish** (Web Speech API latency/quality, animated HUD styling) — explicitly
  out of scope for this run's brief; the intent-router wiring done here is a prerequisite slice,
  not a substitute.
- **Stats Lab's `testable_cols < 2` gate** — noticed during AppTest debugging that *all* of
  Stats Lab's panels (including Bayesian A/B, Power Analysis, and now Text Analytics) are nested
  inside a top-level `if len(testable_cols) < 2` early-return, even though panels like Text
  Analytics don't logically need 2 numeric/categorical columns (they need a text column). Not a
  bug introduced this run — it's how Bayesian A/B and Power Analysis were already structured —
  and not fixed here to stay in scope, but worth a small Run 33 UX nit: a dataset with exactly 1
  categorical/numeric column plus a good text column currently can't reach Text Analytics at all.

## Run 33 recommendation

1. **Changepoint/CUSUM detection** — the other confirmed-real gap from this run's sweep, pure-
   numpy tractable, pairs naturally with the existing STL Decomposition panel in Forecasting.
2. **Stats Lab's `testable_cols` gate** — small, well-scoped UX fix: let panels that don't need
   2 numeric/categorical columns (Text Analytics, and arguably Bayesian A/B / Power Analysis
   which only need categorical/binary columns) render independently of that gate.
3. Atlas: Web Speech API voice-quality/latency work, now that two more panels are wired into the
   command surface — a natural next increment once this run's groundwork has had a run or two to
   settle.
