# Run 31 research sweep — 2026-08-11

## Gap confirmation (grep, before WebSearch)
`grep -rniE "bayesian|posterior|beta.binomial|credible interval" modules/*.py app.py` — zero
hits. `grep -rniE "power.analysis|sample.size|statsmodels.stats.power"` — zero real hits (only
unrelated `sample_size` param name in `hellmode.py` and a comment). Both gaps flagged by Run 30
as open candidates are confirmed still-open, unbuilt, and not duplicative of anything shipped in
Runs 1-30 (checked against `did.py`, `survival.py`, `causal_inference.py`, `hypothesis_sweep.py`,
`stats_lab.py` — none of them touch experiment design/AB-test framing).

## Pick 1: Bayesian A/B testing (beta-binomial)
WebSearch confirms current best practice matches this run's brief almost exactly:
- Beta prior + binomial likelihood -> closed-form Beta posterior, no MCMC/simulation needed for
  the core update (GrowthBook, MetricGate docs).
- Standard reporting surface: posterior mean/median, a credible interval (95% CI = "95% probability
  the true rate is in this range", the direct, more intuitive reading a frequentist CI does not
  support), and "probability B beats A" computed from the joint posterior — the framing popularized
  by VWO/Optimizely-style tools per the brief.
- A cited practical advantage over frequentist testing: no fixed-N peeking penalty — Bayesian
  posteriors can be checked at any time without inflating false-positive rate the way repeated
  frequentist significance checks do. This pairs naturally with Pick 2 (power analysis is exactly
  the frequentist tool for pre-committing to a fixed N to avoid that same peeking problem) — the two
  features tell a coherent "how to run a trustworthy experiment, Bayesian and frequentist" story
  when placed together in Stats Lab.
- Also surfaced: "expected loss" / risk-based stopping rules (choose B unless the expected loss of
  being wrong is negligible) as a more decision-theoretic alternative to a bare probability
  threshold — folded into the implementation as a secondary decision signal alongside P(B>A).
Sources: https://www.growthbook.io/insights/bayesian-statistics ,
https://testscience.org/characterize-system/test-evaluation-analyses/bayesian-credible-intervals/ ,
https://metricgate.com/docs/bayesian-binomial-beta-update/

## Pick 2: Power / sample-size analysis
WebSearch confirms `statsmodels.stats.power` (already a pinned dependency via `statsmodels`, used
by `did.py`) is the standard tool: `TTestIndPower` for two independent-sample mean comparisons
(Cohen's d effect size) and `NormalIndPower` + `proportion_effectsize` for two-proportion
comparisons — both solve for any one of {effect size, n, alpha, power} given the other three via
`solve_power()`. No new dependency, pure closed-form/root-finding compute.
One documented pitfall folded into the module's docstring and UI caption: *observed* ("post-hoc")
power computed from the same data used to run a hypothesis test is a near-deterministic function of
the p-value and is widely criticized as misleading (Hoenig & Heisey, "The Abuse of Power", 2001) —
the module is framed as a forward-looking planning tool (how many samples does a *future* test need
to reliably detect an effect of a given size) rather than a retroactive "was my finished test
strong enough" verdict, and the UI carries that caveat explicitly rather than presenting a bare
achieved-power number as a certificate of validity.
Source: https://www.statsmodels.org/stable/generated/statsmodels.stats.power.TTestIndPower.html

## Atlas/JARVIS track
Last touched at Run 17 (`a4aff81`, "Atlas: zero-Gemini keyword fast path for unambiguous
commands") — 14 runs ago, confirmed via `git log --follow -- modules/atlas.py` and cross-checked
against `.prism/routine_log.md` mentions ("Atlas voice/HUD slice beyond current maturity" logged
as deferred in at least 8 subsequent runs). Genuinely overdue by the routine's own "several runs"
bar. Considered for this run's second slot but not selected — see selection reasoning in
`routine_log.md`: the two stats picks both carry more verifiable technical depth (closed-form
posterior derivation + a real hypothesis-testing-adjacent decision rule; root-finding power
solvers wired to real effect-size estimation from user data) than the realistic "small incremental
slice" of Atlas would (most remaining Atlas gaps are UX/latency polish — Web Speech API, TTS
quality — not deep computational work). Logged as a strong Run 32 candidate; the brief's
`no-force` clause is deliberately used here.
