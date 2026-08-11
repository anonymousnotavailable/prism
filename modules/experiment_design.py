"""
Experiment Design — A/B test sample-size/power calculator, and post-hoc
power checks for a hypothesis test result already on hand.

Two audiences, one set of formulas:

1. **Before an experiment runs**: "how many users do I need per variant to
   reliably detect a lift this size?" — `sample_size_two_proportions()` for
   conversion-rate tests, `sample_size_two_means()` for continuous-metric
   tests (revenue, time-on-page, etc.).
2. **After a test already exists in the data** (e.g. a Hypothesis Sweep
   result, or historical A/B data someone hands you): "was this test even
   capable of detecting an effect this size, given how few rows it had?" —
   `power_check_ttest()`. This is the check most take-home data-analyst
   assignments skip and most interviewers ask about directly: a
   non-significant result from an underpowered test proves nothing, and a
   significant result from a tiny sample is exactly the kind of thing that
   fails to replicate.

Built on statsmodels' `NormalIndPower` (two-proportion z-test, via Cohen's h)
and `TTestIndPower` (two-sample t-test, via Cohen's d) rather than
hand-rolled formulas — these are the same primitives R's `pwr` package and
most commercial A/B calculators use, so results should match what a
stakeholder gets from Optimizely/Evan Miller's calculator to within
rounding. Every public function returns a plain dict (`{"error": "..."}`
on invalid input) rather than raising, matching `stats_lab`'s contract, so
a Streamlit caller never needs a try/except around these.
"""

from __future__ import annotations

import math
from typing import Optional

from statsmodels.stats.power import GofChisquarePower, NormalIndPower, TTestIndPower
from statsmodels.stats.proportion import proportion_effectsize

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.8

# Above this, solve_power's root-finder for "what n reaches this power" can
# run away toward infinity (e.g. a near-zero effect size) rather than
# converging — cap the search so a bad input fails fast with a clear
# "no finite sample size" answer instead of hanging or returning nonsense.
_MAX_SOLVABLE_N = 1_000_000


def _round_up(n: float) -> int:
    return int(math.ceil(n))


def sample_size_two_proportions(
    baseline_rate: float,
    mde: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> dict:
    """Required sample size per group for a two-proportion z-test (the
    standard "conversion rate A vs B" experiment).

    `mde` is the minimum detectable effect as an absolute rate difference
    (e.g. baseline_rate=0.20, mde=0.05 means "can we detect a move from 20%
    to 25%?"). `ratio` is group_b_n / group_a_n (1.0 = equal split).

    Returns {baseline_rate, variant_rate, mde, effect_size (Cohen's h),
    alpha, power, ratio, n_group_a, n_group_b, n_per_group, total_n} or
    {"error": "..."} on invalid input.
    """
    if not (0.0 < baseline_rate < 1.0):
        return {"error": "Baseline rate must be strictly between 0 and 1."}
    if mde == 0:
        return {"error": "Minimum detectable effect (mde) must be non-zero."}
    variant_rate = baseline_rate + mde
    if not (0.0 < variant_rate < 1.0):
        return {
            "error": (
                f"Baseline rate ({baseline_rate:.0%}) + mde ({mde:+.0%}) = "
                f"{variant_rate:.0%}, which isn't a valid probability."
            )
        }
    if ratio <= 0:
        return {"error": "ratio must be positive."}

    effect_size = proportion_effectsize(baseline_rate, variant_rate)
    try:
        n1 = NormalIndPower().solve_power(
            effect_size=abs(effect_size), alpha=alpha, power=power, ratio=ratio,
            alternative=alternative,
        )
    except Exception as exc:  # statsmodels raises on degenerate inputs
        return {"error": f"Could not solve for sample size: {exc}"}

    n_group_a = _round_up(n1)
    n_group_b = _round_up(n1 * ratio)
    return {
        "baseline_rate": baseline_rate,
        "variant_rate": variant_rate,
        "mde": mde,
        "effect_size": float(effect_size),
        "effect_size_name": "Cohen's h",
        "alpha": alpha,
        "power": power,
        "ratio": ratio,
        "n_group_a": n_group_a,
        "n_group_b": n_group_b,
        "n_per_group": n_group_a,  # convenience alias for the common ratio=1 case
        "total_n": n_group_a + n_group_b,
    }


def sample_size_two_means(
    mean_diff: float,
    std_dev: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> dict:
    """Required sample size per group for a two-sample (Welch/independent)
    t-test on a continuous metric — e.g. "can we detect a $5 lift in average
    order value, given a standard deviation of $10?".

    Returns {mean_diff, std_dev, cohens_d, alpha, power, ratio, n_group_a,
    n_group_b, n_per_group, total_n} or {"error": "..."}.
    """
    if std_dev <= 0:
        return {"error": "std_dev must be positive."}
    if mean_diff == 0:
        return {"error": "mean_diff must be non-zero."}
    if ratio <= 0:
        return {"error": "ratio must be positive."}

    cohens_d = mean_diff / std_dev
    try:
        n1 = TTestIndPower().solve_power(
            effect_size=abs(cohens_d), alpha=alpha, power=power, ratio=ratio,
            alternative=alternative,
        )
    except Exception as exc:
        return {"error": f"Could not solve for sample size: {exc}"}

    n_group_a = _round_up(n1)
    n_group_b = _round_up(n1 * ratio)
    return {
        "mean_diff": mean_diff,
        "std_dev": std_dev,
        "cohens_d": round(float(cohens_d), 6),
        "alpha": alpha,
        "power": power,
        "ratio": ratio,
        "n_group_a": n_group_a,
        "n_group_b": n_group_b,
        "n_per_group": n_group_a,
        "total_n": n_group_a + n_group_b,
    }


def achieved_power_ttest(cohens_d: float, n1: int, n2: int, alpha: float = DEFAULT_ALPHA) -> float:
    """Post-hoc (observed) power of a two-sample t-test that already ran,
    given the effect size it found and the group sizes it had. Answers
    "given the sample sizes we actually had, what were our odds of detecting
    an effect this size at all?" — distinct from p-value, which only says
    whether *this* result was significant.
    """
    if n1 < 2 or n2 < 2:
        return 0.0
    ratio = n2 / n1
    power = TTestIndPower().power(
        effect_size=abs(cohens_d), nobs1=n1, ratio=ratio, alpha=alpha, alternative="two-sided"
    )
    return float(min(max(power, 0.0), 1.0))


def power_check_ttest(
    cohens_d: float,
    n1: int,
    n2: int,
    alpha: float = DEFAULT_ALPHA,
    target_power: float = DEFAULT_POWER,
) -> dict:
    """Full post-hoc power verdict for a t-test result: achieved power, a
    pass/fail flag against `target_power`, and — if underpowered — the
    sample size per group that *would* reach `target_power` for this same
    effect size (so a follow-up study has a concrete number to design
    around, not just a warning).

    Returns {achieved_power, target_power, alpha, underpowered,
    recommended_n_per_group, recommended_total_n}. When the effect size is
    (near) zero, no finite sample size reaches target_power —
    `recommended_n_per_group` is `None` in that case rather than a
    misleadingly huge or infinite number.
    """
    achieved = achieved_power_ttest(cohens_d, n1, n2, alpha=alpha)
    underpowered = achieved < target_power

    recommended_n_per_group: Optional[int] = None
    if abs(cohens_d) > 1e-9:
        try:
            n_needed = TTestIndPower().solve_power(
                effect_size=abs(cohens_d), alpha=alpha, power=target_power, ratio=1.0,
                alternative="two-sided",
            )
            if n_needed and n_needed <= _MAX_SOLVABLE_N:
                recommended_n_per_group = _round_up(n_needed)
        except Exception:
            recommended_n_per_group = None

    return {
        "test": "ttest",
        "achieved_power": achieved,
        "target_power": target_power,
        "alpha": alpha,
        "n1": n1,
        "n2": n2,
        "cohens_d": cohens_d,
        "underpowered": underpowered,
        "recommended_n_per_group": recommended_n_per_group,
        "recommended_total_n": (
            recommended_n_per_group * 2 if recommended_n_per_group is not None else None
        ),
    }


def achieved_power_chi2(cramers_v: float, n: int, rows: int, cols: int, alpha: float = DEFAULT_ALPHA) -> float:
    """Post-hoc power of a chi-square test of independence that already ran,
    given the effect size it found (Cramer's V), its sample size, and the
    contingency table's shape.

    Cramer's V alone isn't enough to size a chi-square power calculation —
    unlike Cohen's d for a t-test, V is normalized by `min(rows, cols) - 1`,
    which erases the table's actual degrees of freedom whenever it isn't
    square. This recovers Cohen's w (the effect-size measure
    `GofChisquarePower` expects) via `w = V * sqrt(min(rows, cols) - 1)` —
    algebraically the inverse of how `stats_lab.run_chi2` derives V from w
    in the first place — and passes `n_bins = dof + 1` (`dof =
    (rows-1)*(cols-1)`), which is how statsmodels' goodness-of-fit power
    function is documented to encode a contingency table's degrees of
    freedom for an independence test.
    """
    if n < 1 or rows < 2 or cols < 2:
        return 0.0
    min_dim = min(rows, cols) - 1
    dof = (rows - 1) * (cols - 1)
    cohens_w = abs(cramers_v) * math.sqrt(min_dim)
    power = GofChisquarePower().power(effect_size=cohens_w, nobs=n, alpha=alpha, n_bins=dof + 1)
    return float(min(max(power, 0.0), 1.0))


def power_check_chi2(
    cramers_v: float,
    n: int,
    rows: int,
    cols: int,
    alpha: float = DEFAULT_ALPHA,
    target_power: float = DEFAULT_POWER,
) -> dict:
    """Full post-hoc power verdict for a chi-square test of independence —
    the chi-square counterpart to `power_check_ttest()`. Same contract:
    achieved power, a pass/fail flag against `target_power`, and — if
    underpowered — the total sample size that would reach `target_power`
    for this same effect size and table shape.

    Returns {test: "chi2", achieved_power, target_power, alpha, n, rows,
    cols, dof, cramers_v, cohens_w, underpowered, recommended_n}.
    `recommended_n` is `None` when the effect size is (near) zero, same
    "no finite sample size" convention as `power_check_ttest`.
    """
    if rows < 2 or cols < 2:
        return {"error": f"Need at least a 2x2 table, got {rows}x{cols}."}

    achieved = achieved_power_chi2(cramers_v, n, rows, cols, alpha=alpha)
    underpowered = achieved < target_power

    min_dim = min(rows, cols) - 1
    dof = (rows - 1) * (cols - 1)
    cohens_w = abs(cramers_v) * math.sqrt(min_dim)

    recommended_n: Optional[int] = None
    if cohens_w > 1e-9:
        try:
            n_needed = GofChisquarePower().solve_power(
                effect_size=cohens_w, alpha=alpha, power=target_power, n_bins=dof + 1
            )
            if n_needed and n_needed <= _MAX_SOLVABLE_N:
                recommended_n = _round_up(n_needed)
        except Exception:
            recommended_n = None

    return {
        "test": "chi2",
        "achieved_power": achieved,
        "target_power": target_power,
        "alpha": alpha,
        "n": n,
        "rows": rows,
        "cols": cols,
        "dof": dof,
        "cramers_v": cramers_v,
        "cohens_w": cohens_w,
        "underpowered": underpowered,
        "recommended_n": recommended_n,
    }


def _interpret_power_check_ttest(check: dict) -> str:
    pct = f"{check['achieved_power']:.0%}"
    n1, n2 = check["n1"], check["n2"]
    n_desc = f"{n1} vs {n2}" if n1 != n2 else str(n1)

    if not check["underpowered"]:
        return (
            f"✅ Well-powered: with {n_desc} samples per group, this test had "
            f"{pct} power to detect an effect this size (target: "
            f"{check['target_power']:.0%})."
        )

    if check["recommended_n_per_group"] is None:
        return (
            f"⚠️ Underpowered: with {n_desc} samples per group, this test had only "
            f"{pct} power to detect an effect this size — the effect size is too "
            "close to zero for any finite sample size to reliably detect."
        )

    return (
        f"⚠️ Underpowered: with {n_desc} samples per group, this test had only "
        f"{pct} power to detect an effect this size — a follow-up study should use "
        f"~{check['recommended_n_per_group']:,} samples per group to reach "
        f"{check['target_power']:.0%} power."
    )


def _interpret_power_check_chi2(check: dict) -> str:
    pct = f"{check['achieved_power']:.0%}"
    table_desc = f"{check['rows']}x{check['cols']} table, n={check['n']}"

    if not check["underpowered"]:
        return (
            f"✅ Well-powered: with a {table_desc}, this test had "
            f"{pct} power to detect an association this strong (target: "
            f"{check['target_power']:.0%})."
        )

    if check["recommended_n"] is None:
        return (
            f"⚠️ Underpowered: with a {table_desc}, this test had only "
            f"{pct} power to detect an association this strong — the effect size is too "
            "close to zero for any finite sample size to reliably detect."
        )

    return (
        f"⚠️ Underpowered: with a {table_desc}, this test had only "
        f"{pct} power to detect an association this strong — a follow-up study should "
        f"collect ~{check['recommended_n']:,} rows total to reach "
        f"{check['target_power']:.0%} power."
    )


def interpret_power_check(check: dict) -> str:
    """Plain-English verdict for any `power_check_*()` result — dispatches
    on the `"test"` key (`power_check_ttest()` sets `"ttest"`,
    `power_check_chi2()` sets `"chi2"`) so a caller rendering a mixed sweep
    result (t-test and chi-square rows side by side) can call this one
    function regardless of which test produced the check. E.g.
    "⚠️ Underpowered: with 15 samples per group, this test had only 18%
    power to detect an effect this size — a follow-up would need ~176
    samples per group for 80% power." Never raises on a missing
    recommendation (zero/near-zero effect size).
    """
    if check.get("error"):
        return check["error"]
    if check.get("test") == "chi2":
        return _interpret_power_check_chi2(check)
    return _interpret_power_check_ttest(check)


def interpret_sample_size_proportions(result: dict) -> str:
    """Plain-English readout of a `sample_size_two_proportions()` result."""
    if result.get("error"):
        return result["error"]
    return (
        f"To detect a move from {result['baseline_rate']:.1%} to "
        f"{result['variant_rate']:.1%} with {result['power']:.0%} power at "
        f"α={result['alpha']}, you need **~{result['n_per_group']:,} users per "
        f"group** (~{result['total_n']:,} total)."
    )


def interpret_sample_size_means(result: dict) -> str:
    """Plain-English readout of a `sample_size_two_means()` result."""
    if result.get("error"):
        return result["error"]
    return (
        f"To detect a mean difference of {result['mean_diff']:g} (Cohen's d = "
        f"{result['cohens_d']:.2f}) with {result['power']:.0%} power at "
        f"α={result['alpha']}, you need **~{result['n_per_group']:,} samples per "
        f"group** (~{result['total_n']:,} total)."
    )
