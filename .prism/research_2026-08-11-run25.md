# Prism Research — 2026-08-11 (Run 25)

Fresh Phase 2 web sweep, as Run 24 recommended (16 consecutive prior runs
had reused earlier research; the backlog thinned to cosmetic-only items,
which is this routine's own stated trigger for a fresh sweep).

## Industry practice

- Data-analyst interviews in 2026 test SQL (always), statistics, Python/
  pandas EDA, and business communication; ~40-50% also test pandas
  operations and data cleaning directly. ([dataquest.io](https://www.dataquest.io/blog/data-analyst-interview-questions-and-answers/), [lockedinai.com](https://www.lockedinai.com/blog/data-analyst-interview-questions-prepare-guide))
- The "2026 stack" framing (pandas vs Polars vs DuckDB) treats tool choice
  itself as a signal of maturity — knowing *when* to reach for an
  out-of-core/vectorized tool over plain pandas is called out as "the
  real skill." Prism already has a DuckDB-backed large-CSV/Excel path
  (Runs ~18 and 24), so this is already covered. ([python.plainenglish.io](https://python.plainenglish.io/the-python-data-analyst-stack-in-2026-duckdb-polars-and-the-death-of-pandas-790f92b39722))

## Competitor tools

- Hex/Deepnote/Julius/ChatGPT-ADA all lean on **conversational, proactive
  suggestion** as the differentiator over a plain notebook — the value
  isn't just running an analysis, it's the tool telling you *what to run
  next*. ([deepnote.com compare pages](https://deepnote.com/compare/juliusai-vs-deepnote), [nomadlab.cc](https://nomadlab.cc/blog/2026/05/ai-data-analyst-platforms-2026-hex-julius-cortex-genie-thoughtspot))
- This directly motivated this run's selected feature: Prism's own
  Agent Summary already ranks findings across detectors but stopped at
  "here's what matters" — it didn't yet close the loop into "here's the
  one-click next thing to do about it."

## Ecosystem tech

- No new signal beyond what's already shipped (DuckDB out-of-core path,
  Polars not adopted — pandas + DuckDB covers the out-of-core story
  Prism needs without a second dataframe engine to maintain).

## Agentic EDA research

- Recent papers (DataSage, QUIS: Question-guided Insight Generation,
  "LLM-Based Data Science Agents" survey) converge on the same shape:
  raw findings alone are low-value; the differentiator is **routing**
  findings into concrete next actions and verifying claims before
  presenting them. Prism already has the verification half
  (`insight_verifier.py`, `verify_narration()` across every narration
  surface). This run's feature adds the routing half at the top-level
  cross-detector summary. ([arxiv 2511.14299](https://arxiv.org/pdf/2511.14299), [arxiv 2410.10270](https://arxiv.org/pdf/2410.10270), [arxiv 2510.04023](https://arxiv.org/pdf/2510.04023))

## Ranked candidate table

| Feature | Evidence | Depth (1-5) | Effort | Risk | Theme |
|---|---|---|---|---|---|
| **Agent Summary → one-click next step (SELECTED)** | Competitor proactive-suggestion pattern; QUIS/DataSage "routing" pattern | 4 | S | Low | Agentic AI analysis |
| Question-guided insight generation (QUIS-style: user picks a question, Prism plans + runs the analysis) | arxiv 2410.10270 | 5 | L | Medium (needs a new planning layer) | Agentic AI analysis |
| Polars-backed fast-path for wide (500+ col) datasets | 2026 stack articles | 3 | M | Medium (second dataframe engine to maintain) | Ecosystem tech |
| Fix "not valid UTF-8" false-positive banner | This run's own audit (Finding 2) | 1 | S | Low | Portfolio polish |
| Light-theme repaint lag | Carried backlog, Run 17+ | 2 | M | Low | Portfolio polish |
| Atlas voice/HUD maturity slice | Roadmap theme, explicitly capped at 1/run | 4 | L | Medium | Atlas copilot |

**Selected:** Agent Summary → one-click next step. Highest depth-to-
effort ratio, directly serves this cycle's mandatory agentic-AI theme,
zero new dependencies, and closes a gap this run's own code-reading
confirmed was real (no existing "what to do next" affordance anywhere in
the orchestration layer).
