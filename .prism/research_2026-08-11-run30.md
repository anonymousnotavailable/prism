# Run 30 research sweep — 2026-08-11

## Part 1: DiD sanity check (per this run's brief — a pre-committed pick, not a fresh candidate search)

WebSearch: "difference-in-differences parallel trends assumption pre-trend
test 2025 2026 best practices two-way fixed effects pitfalls"

Key findings, folded directly into `modules/did.py`'s docstring and
narration prompt (not just read and discarded):

- **Pre-trend testing is standard but flawed.** It's common practice to
  test for pre-treatment differences in trends as a proxy for whether the
  parallel-trends assumption is plausible — but a recent literature
  (Roth 2022 and others) shows conventional pre-tests have low power and
  conditioning on their result introduces pre-test bias.
- **Absence of a significant pre-trend is not proof.** Parallel
  pre-trends is neither necessary nor sufficient for parallel trends to
  hold in the post-period — this is the single most important caveat and
  is stated explicitly in `did.py`'s `_PRETREND_CAVEAT` constant and
  surfaced verbatim in the app's UI, not just buried in a docstring.
- **Bilinski & Hatfield (2019)**: recommend allowing for a linear trend
  difference by default rather than a bare level-difference DiD, and
  thinking about *what kind* of parallel-trends violation is plausible
  rather than a binary pass/fail pre-test. (Noted as a Run 31+ extension
  — Prism's DiD ships the standard 2x2-with-interaction estimator plus
  an optional pre-trend placebo check; a linear-trend-adjusted DiD
  variant is a reasonable follow-up, not required for this run's scope.)

Sources:
- https://blogs.worldbank.org/en/impactevaluations/revisiting-difference-differences-parallel-trends-assumption-part-i-pre-trend
- https://blogs.worldbank.org/en/impactevaluations/revisiting-difference-differences-parallel-trends-assumption-part-ii-what-happens
- https://arxiv.org/pdf/2310.15796 (equivalence testing for pre-trends)
- https://www.sciencedirect.com/science/article/abs/pii/S0304407623001318 (2023 DiD econometrics synthesis)

## Part 2: fresh gap sweep for the second pick

WebSearch: "agentic EDA tool new feature 2026 data analysis platform
competitor Hex Julius AI ChatGPT ADA capability gap" — mostly confirmed
the competitive landscape is converging on agentic multi-step analysis
(Hex, Databricks Genie, Fabric/Copilot) rather than surfacing a specific
missing statistical technique; didn't return a decisive single pick, so
the deciding signal came from the direct codebase grep below instead.

Codebase grep (`modules/*.py`, `app.py`, `tests/*.py`) for candidate gaps:

| Technique | grep hits | Verdict |
|---|---|---|
| `survival\|kaplan.meier\|log.rank\|lifelines` | 0 | **Open gap** — selected |
| `bayesian\|posterior\|beta.binomial` | 0 | Open gap — Run 31+ candidate |
| `power.analysis\|sample.size\|minimum.detectable` | 0 (false positives only) | Open gap — Run 31+ candidate |
| `cohort\|retention` | many (`domains.py` retention cohorts) | Already covered, not a gap |
| `shap\|feature.importance\|permutation.importance` | many (`mllab.py` feature-selection suite: mutual info, L1, RFE, permutation) | Already covered, not a gap |
| `sentiment\|nlp\|tfidf\|topic.model` | 0 | Open gap but out of scope this run (would need new NLP dependency or heavy from-scratch tokenizer — not a good fit for "pure local compute, no new dependency" bar this run aimed for) |

## Selection reasoning (see `.prism/routine_log.md` for the full writeup)

1. **Difference-in-Differences** — pre-committed by this run's brief;
   confirmed still open and well-scoped by re-reading
   `modules/causal_inference.py` in full before starting.
2. **Survival Analysis** — Run 29's own candidate #5 (deferred twice for
   capacity, not fit), confirmed still a real gap by the grep above,
   picked over Bayesian A/B testing and power analysis because it pairs
   thematically with the existing `domains.py` churn-flag proxy (a
   genuinely stronger version of an already-shipped idea) and because a
   from-scratch numpy/pandas/scipy implementation (no `lifelines`
   dependency) was confirmed tractable within this run's effort budget.

## Backlog for Run 31+

- **Bayesian A/B testing** (beta-binomial posterior + credible intervals
  for two-proportion tests) — zero coverage today, natural fit for
  Stats Lab next to the existing frequentist t-test/chi-square/ANOVA
  suite, pure scipy.stats (Beta distribution), no new dependency.
- **Power / sample-size analysis** (minimum detectable effect calculator,
  pre-experiment planning) — zero coverage today, pure scipy/numpy
  (normal-approximation power formulas), no new dependency. Slightly
  different in kind from Prism's "analyze the data you uploaded" pattern
  (it's pre-experiment planning, not post-hoc analysis) but can use an
  uploaded dataset's own baseline rate/variance as the calculator's
  starting point, same as how Stats Lab already suggests tests from real
  columns.
- **DiD with a linear pre-trend adjustment** (Bilinski & Hatfield 2019's
  recommended default) as a documented enhancement to `modules/did.py`,
  not a blocker — the current placebo-check-only version is a legitimate,
  textbook-standard implementation on its own.
- Sentiment/NLP analytics remains open but needs either a new dependency
  (e.g. a lightweight lexicon) or a heavier from-scratch tokenizer/
  classifier — bigger scope than a single run slot, revisit if a future
  run's effort budget allows a dependency addition.
