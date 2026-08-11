"""
Bayesian A/B Testing — the beta-binomial conjugate model for comparing two
variants' conversion rates, the Bayesian counterpart to modules.stats_lab's
frequentist chi-square test of independence.

Where the frequentist test answers "is this difference in conversion rate
statistically significant at alpha=0.05" with a single p-value, the Bayesian
framing answers the question practitioners actually ask during an
experiment: "what's the probability the treatment is better than control,
and by how much" — via a full posterior distribution per variant rather
than a point estimate. This is the standard beta-binomial conjugate update
(a Beta(prior_alpha, prior_beta) prior + binomial-observed successes/trials
gives a closed-form Beta posterior, no MCMC or simulation needed for the
update itself) plus three decision-support numbers built on top of it:

  - A credible interval (the direct, intuitive read a frequentist confidence
    interval does not support: "there's a 95% probability the true rate is
    in this range", not "95% of intervals built this way would contain the
    true rate").
  - P(treatment beats control) — computed via Evan Miller's closed-form
    summation when the posterior's success count is small enough to be
    tractable, falling back to Monte Carlo sampling (still numerically
    exact in expectation, negligible error at 200k draws) for large counts.
  - Expected loss of each decision (the average regret if you pick a
    variant and turn out to be wrong) — a risk-based complement to a bare
    probability threshold, useful when a team needs to decide *now* rather
    than wait for P(B>A) to cross an arbitrary bar.

One practical advantage over the frequentist test this sits next to: a
Bayesian posterior can be checked at any time without the "peeking" penalty
that inflates a frequentist test's false-positive rate under repeated
significance checks — modules.power_analysis is the frequentist tool for
pre-committing to a fixed sample size to avoid that same problem, and the
two are deliberately placed together in Stats Lab.

Pure numpy/scipy — no new dependency, same footprint philosophy as
modules.did and modules.survival. 100% local compute; narrate_bayesian_ab()
is an optional plain-English layer on an already-computed result, same
call_gemini() plumbing and graceful no-model fallback as every other
narrate_* helper in the app. Callers are responsible for caching its
result, same convention as those.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import special as scipy_special
from scipy import stats as scipy_stats

# Below this many trials, a variant's posterior is too wide to be worth
# comparing — same "stay silent rather than force it" convention as
# modules.survival's _MIN_GROUP_SIZE.
_MIN_TRIALS_PER_VARIANT = 10
# Tractability cap on raw event-level rows, same convention as
# modules.survival._MAX_ROWS — aggregation itself is O(n) so this is generous.
_MAX_ROWS = 200_000
# Monte Carlo draw count for P(B>A), expected loss, and lift — settled
# empirically at a Monte Carlo standard error well under 0.2% for
# proportions in the typical 1%-99% range.
_MC_SAMPLES = 200_000
# Evan Miller's closed-form P(B>A) summation is O(alpha_b) — exact and fast
# for typical conversion counts, but switches to Monte Carlo above this to
# avoid a slow inner loop on very large posteriors (still numerically
# equivalent, MC error is negligible at _MC_SAMPLES draws).
_EXACT_MAX_ALPHA_B = 1500
# The conventional "declare a winner" bar for P(treatment beats control),
# mirrored on the low side for "declare control the winner instead".
_STRONG_EVIDENCE = 0.95


def beta_posterior(successes: int, trials: int, prior_alpha: float = 1.0, prior_beta: float = 1.0) -> tuple[float, float]:
    """The beta-binomial conjugate update: Beta(prior_alpha, prior_beta) prior
    + `successes` observed out of `trials` -> Beta(prior_alpha + successes,
    prior_beta + failures) posterior, in closed form. Raises ValueError on
    invalid counts (this is a low-level math primitive, unlike the
    app-facing functions below which never raise).
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("successes must be between 0 and trials, and both must be non-negative.")
    failures = trials - successes
    return prior_alpha + successes, prior_beta + failures


def posterior_summary(alpha: float, beta: float, credible_level: float = 0.95) -> dict:
    """Summarize a Beta(alpha, beta) posterior: mean, median, mode (None
    when alpha<=1 or beta<=1, where the density has no interior maximum),
    std, and a `credible_level` equal-tailed credible interval.
    """
    tail = (1 - credible_level) / 2
    mean = alpha / (alpha + beta)
    median = float(scipy_stats.beta.ppf(0.5, alpha, beta))
    mode = (alpha - 1) / (alpha + beta - 2) if alpha > 1 and beta > 1 else None
    std = float(scipy_stats.beta.std(alpha, beta))
    ci_low = float(scipy_stats.beta.ppf(tail, alpha, beta))
    ci_high = float(scipy_stats.beta.ppf(1 - tail, alpha, beta))
    return {
        "mean": mean, "median": median, "mode": mode, "std": std,
        "ci_low": ci_low, "ci_high": ci_high, "credible_level": credible_level,
    }


def _prob_b_beats_a_exact(alpha_a: float, beta_a: float, alpha_b: int, beta_b: float) -> float:
    """Evan Miller's closed-form P(B > A) for two independent Beta
    posteriors, exact when alpha_a and alpha_b are positive integers (true
    whenever both priors use integer alpha, the common case). Computed in
    log-space via betaln + logsumexp to stay numerically stable for large
    counts.
    """
    log_terms = [
        (
            scipy_special.betaln(alpha_a + i, beta_b + beta_a)
            - np.log(beta_b + i)
            - scipy_special.betaln(1 + i, beta_b)
            - scipy_special.betaln(alpha_a, beta_a)
        )
        for i in range(int(alpha_b))
    ]
    return float(np.clip(np.exp(scipy_special.logsumexp(log_terms)), 0.0, 1.0))


def _prob_b_beats_a_monte_carlo(alpha_a: float, beta_a: float, alpha_b: float, beta_b: float,
                                 n_samples: int = _MC_SAMPLES, random_state: int = 42) -> float:
    rng = np.random.default_rng(random_state)
    a_samples = rng.beta(alpha_a, beta_a, size=n_samples)
    b_samples = rng.beta(alpha_b, beta_b, size=n_samples)
    return float(np.mean(b_samples > a_samples))


def prob_b_beats_a(alpha_a: float, beta_a: float, alpha_b: float, beta_b: float,
                    n_samples: int = _MC_SAMPLES, random_state: int = 42) -> dict:
    """P(a random draw from B's posterior exceeds a random draw from A's) —
    the "probability treatment beats control" number. Uses the exact
    closed-form summation when alpha_a/alpha_b are both whole numbers and
    alpha_b is small enough to sum over quickly, otherwise falls back to
    Monte Carlo (still exact in expectation). Returns {"value", "method"}.
    """
    use_exact = (
        float(alpha_a).is_integer() and float(alpha_b).is_integer()
        and 1 <= alpha_b <= _EXACT_MAX_ALPHA_B
    )
    if use_exact:
        try:
            value = _prob_b_beats_a_exact(alpha_a, beta_a, int(alpha_b), beta_b)
            if np.isfinite(value):
                return {"value": value, "method": "exact"}
        except (ValueError, FloatingPointError):
            pass
    value = _prob_b_beats_a_monte_carlo(alpha_a, beta_a, alpha_b, beta_b, n_samples, random_state)
    return {"value": value, "method": "monte_carlo"}


def expected_loss(alpha_a: float, beta_a: float, alpha_b: float, beta_b: float,
                   n_samples: int = _MC_SAMPLES, random_state: int = 42) -> dict:
    """Expected regret of each decision, via Monte Carlo over the joint
    posterior: `choose_treatment` = E[max(A - B, 0)] (how much you'd lose,
    on average, by picking B if A actually turns out better), and
    `choose_control` = E[max(B - A, 0)] symmetrically. A risk-based
    complement to a bare P(B>A) threshold — useful for "decide now" calls
    even while P(B>A) still sits in the inconclusive middle.
    """
    rng = np.random.default_rng(random_state)
    a_samples = rng.beta(alpha_a, beta_a, size=n_samples)
    b_samples = rng.beta(alpha_b, beta_b, size=n_samples)
    return {
        "choose_treatment": float(np.mean(np.maximum(a_samples - b_samples, 0.0))),
        "choose_control": float(np.mean(np.maximum(b_samples - a_samples, 0.0))),
    }


def lift_distribution(alpha_a: float, beta_a: float, alpha_b: float, beta_b: float,
                       credible_level: float = 0.95, n_samples: int = _MC_SAMPLES,
                       random_state: int = 42) -> dict:
    """Monte Carlo distribution of B - A (absolute lift) and (B - A) / A
    (relative lift), summarized as a mean plus a `credible_level`
    equal-tailed interval on each. Relative lift is undefined (excluded)
    on draws where A's sampled rate is exactly 0.
    """
    rng = np.random.default_rng(random_state)
    a_samples = rng.beta(alpha_a, beta_a, size=n_samples)
    b_samples = rng.beta(alpha_b, beta_b, size=n_samples)
    abs_diff = b_samples - a_samples
    tail = (1 - credible_level) / 2

    valid = a_samples > 0
    rel_diff = abs_diff[valid] / a_samples[valid]
    rel_mean, rel_low, rel_high = (
        (float(rel_diff.mean()), float(np.quantile(rel_diff, tail)), float(np.quantile(rel_diff, 1 - tail)))
        if len(rel_diff) else (None, None, None)
    )
    return {
        "absolute_mean": float(abs_diff.mean()),
        "absolute_ci_low": float(np.quantile(abs_diff, tail)),
        "absolute_ci_high": float(np.quantile(abs_diff, 1 - tail)),
        "relative_mean": rel_mean,
        "relative_ci_low": rel_low,
        "relative_ci_high": rel_high,
    }


def _coerce_binary(series: pd.Series) -> Optional[pd.Series]:
    """Coerce an exactly-2-valued column to a 0/1 int Series, preferring an
    obvious "success" value (1, True, "yes", "converted", ...) as 1 when one
    is present among the two, otherwise falling back to the second sorted
    value — same convention as modules.survival's event-column coercion.
    Returns None if the column doesn't have exactly 2 distinct values.
    """
    uniques = series.dropna().unique().tolist()
    if len(uniques) != 2:
        return None
    positive_aliases = {
        1, "1", True, "true", "yes", "y", "converted", "success", "purchase",
        "purchased", "clicked", "signed_up", "won", "win",
    }
    sorted_uniques = sorted(uniques, key=str)
    positive_value = next(
        (v for v in sorted_uniques if str(v).strip().lower() in positive_aliases or v in positive_aliases),
        sorted_uniques[-1],
    )
    return (series == positive_value).astype(int)


def bayesian_ab_test(
    df: pd.DataFrame,
    variant_col: str,
    success_col: str,
    control_value=None,
    treatment_value=None,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    credible_level: float = 0.95,
    min_trials_per_variant: int = _MIN_TRIALS_PER_VARIANT,
    max_rows: int = _MAX_ROWS,
    random_state: int = 42,
) -> dict:
    """App-facing entry point. `variant_col` identifies which group each row
    belongs to; `success_col` is a binary success/failure flag. If the
    dataset has exactly 2 variant levels, they're picked automatically
    (alphabetically: first = control, second = treatment); with 3+ levels,
    `control_value`/`treatment_value` must be given explicitly to pick the
    pair to compare.

    Returns a dict, always with an "ok" key:
      ok=False: {"ok": False, "error": "<why>"}
      ok=True:  {"ok": True, "variant_col", "success_col", "control_value",
                 "treatment_value", "control": {...}, "treatment": {...},
                 "prob_treatment_beats_control", "expected_loss", "lift",
                 "recommendation", "warnings"}
      where "control"/"treatment" are each {"value", "trials", "successes",
      "observed_rate", "posterior_alpha", "posterior_beta", "summary"}.

    Never raises — missing columns, a non-binary outcome column, too few
    rows in a variant, an ambiguous variant column, or a non-positive prior
    are all reported as ok=False with a plain-English reason.
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    for col, label in ((variant_col, "Variant"), (success_col, "Outcome")):
        if col not in df.columns:
            return {"ok": False, "error": f"{label} column '{col}' not found in the dataset."}
    if variant_col == success_col:
        return {"ok": False, "error": "variant_col and success_col must be different columns."}
    if prior_alpha <= 0 or prior_beta <= 0:
        return {"ok": False, "error": "Prior alpha and beta must both be positive."}

    sub = df[[variant_col, success_col]].dropna().copy()
    if sub.empty:
        return {"ok": False, "error": "No complete rows after dropping missing values."}

    warnings = []
    if len(sub) > max_rows:
        sub = sub.sample(n=max_rows, random_state=random_state)
        warnings.append(f"Dataset sampled down to {max_rows:,} rows for tractability.")

    levels = sorted(sub[variant_col].dropna().unique().tolist(), key=str)
    if control_value is not None or treatment_value is not None:
        if control_value not in levels or treatment_value not in levels:
            return {
                "ok": False,
                "error": f"control_value/treatment_value must both be present levels of '{variant_col}' ({levels}).",
            }
        if control_value == treatment_value:
            return {"ok": False, "error": "control_value and treatment_value must be different."}
    elif len(levels) == 2:
        control_value, treatment_value = levels[0], levels[1]
    else:
        return {
            "ok": False,
            "error": (
                f"'{variant_col}' has {len(levels)} levels — Bayesian A/B testing compares exactly 2 at a "
                "time. Pass control_value/treatment_value to pick which two to compare."
            ),
        }

    success_binary = _coerce_binary(sub[success_col])
    if success_binary is None:
        n_vals = sub[success_col].dropna().nunique()
        return {"ok": False, "error": f"Outcome column '{success_col}' must have exactly 2 values (found {n_vals})."}
    sub = sub.assign(_success=success_binary)

    variant_stats = {}
    for label, value in (("control", control_value), ("treatment", treatment_value)):
        vsub = sub[sub[variant_col] == value]
        trials = int(len(vsub))
        if trials < min_trials_per_variant:
            return {
                "ok": False,
                "error": f"Not enough rows for variant '{value}': {trials} (need >= {min_trials_per_variant}).",
            }
        successes = int(vsub["_success"].sum())
        alpha, beta = beta_posterior(successes, trials, prior_alpha, prior_beta)
        variant_stats[label] = {
            "value": value,
            "trials": trials,
            "successes": successes,
            "observed_rate": successes / trials,
            "posterior_alpha": alpha,
            "posterior_beta": beta,
            "summary": posterior_summary(alpha, beta, credible_level),
        }

    ctrl, trt = variant_stats["control"], variant_stats["treatment"]
    p_b_beats_a = prob_b_beats_a(
        ctrl["posterior_alpha"], ctrl["posterior_beta"], trt["posterior_alpha"], trt["posterior_beta"],
        random_state=random_state,
    )
    loss = expected_loss(
        ctrl["posterior_alpha"], ctrl["posterior_beta"], trt["posterior_alpha"], trt["posterior_beta"],
        random_state=random_state,
    )
    lift = lift_distribution(
        ctrl["posterior_alpha"], ctrl["posterior_beta"], trt["posterior_alpha"], trt["posterior_beta"],
        credible_level, random_state=random_state,
    )

    p = p_b_beats_a["value"]
    if p >= _STRONG_EVIDENCE:
        recommendation = f"Strong evidence '{treatment_value}' beats '{control_value}' (P = {p:.1%})."
    elif p <= 1 - _STRONG_EVIDENCE:
        recommendation = f"Strong evidence '{control_value}' beats '{treatment_value}' (P = {1 - p:.1%})."
    else:
        recommendation = (
            f"Not enough evidence yet to call a winner (P('{treatment_value}' beats '{control_value}') = {p:.1%}). "
            "Keep collecting data, or weigh the expected-loss numbers below if a decision is needed now."
        )

    return {
        "ok": True,
        "variant_col": variant_col,
        "success_col": success_col,
        "control_value": control_value,
        "treatment_value": treatment_value,
        "control": ctrl,
        "treatment": trt,
        "prob_treatment_beats_control": p_b_beats_a,
        "expected_loss": loss,
        "lift": lift,
        "recommendation": recommendation,
        "warnings": warnings,
    }


def narrate_bayesian_ab(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one bayesian_ab_test() result in plain English.
    Returns (narration, error) — never raises. Callers should cache the
    result rather than re-calling this on every rerun, same convention as
    modules.survival.narrate_survival.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    ctrl, trt = result["control"], result["treatment"]
    p = result["prob_treatment_beats_control"]["value"]
    lift = result["lift"]
    rel_lift_txt = f"{lift['relative_mean']:.1%}" if lift["relative_mean"] is not None else "n/a"

    prompt = (
        f"A Bayesian A/B test on '{result['variant_col']}' ({result['success_col']} as the outcome) compared "
        f"'{result['control_value']}' (control: {ctrl['successes']}/{ctrl['trials']} = {ctrl['observed_rate']:.2%}) "
        f"against '{result['treatment_value']}' (treatment: {trt['successes']}/{trt['trials']} = "
        f"{trt['observed_rate']:.2%}).\n"
        f"P(treatment beats control) = {p:.1%}.\n"
        f"Expected loss of choosing treatment if wrong: {result['expected_loss']['choose_treatment']:.4f}; "
        f"of choosing control if wrong: {result['expected_loss']['choose_control']:.4f}.\n"
        f"Estimated relative lift: {rel_lift_txt}.\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what this means, whether "
        "there's a clear winner yet, and how confident we should be. Do not repeat the raw numbers verbatim — "
        "focus on the practical decision."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
