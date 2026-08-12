"""
Hypothesis Sweep — the agentic version of Stats Lab. Where Stats Lab tests
one manually-picked pair of columns at a time, this generates and runs
*every* statistically viable pairwise hypothesis test across the dataset
automatically, then applies Benjamini-Hochberg false-discovery-rate (FDR)
correction across the whole sweep before ranking what's left by effect size.

Reuses `stats_lab.suggest_test` / `stats_lab.run_test` for the actual test
dispatch, so a given pair type always resolves to exactly the same test
Stats Lab's manual flow would pick (Pearson for numeric/numeric, Welch's
t-test or one-way ANOVA for numeric/categorical depending on group count,
chi-square for categorical/categorical) — this module's only job is the
"run many, then correct for running many" part.

Why the correction matters: running N independent tests at a raw alpha of
0.05 produces roughly 0.05*N false positives by chance alone, even when
nothing in the data is really related. A dataset with 10 numeric columns
already has 45 possible pairs — reporting every p<0.05 pair from that
sweep without correction is implicit p-hacking. Benjamini-Hochberg controls
the expected proportion of false discoveries among the flagged pairs
instead, which is what makes an automated multi-test sweep a defensible
exploratory-analysis technique.
"""

from __future__ import annotations

import hashlib
from itertools import combinations
from typing import Optional

import pandas as pd

from modules import experiment_design, stats_lab

# Hard cap on pairs tested in one sweep so a very wide dataset (hundreds of
# columns) can't blow up runtime — C(200, 2) is already ~20k combinations,
# so this caps *columns considered*, not raw pair count, keeping the sweep
# proportional to what a human could plausibly review anyway.
DEFAULT_MAX_PAIRS = 200
DEFAULT_ALPHA = 0.05


def _viable_pairs(column_types: dict[str, str]) -> list[tuple[str, str]]:
    cols = [c for c, t in column_types.items() if t in ("numeric", "categorical")]
    return list(combinations(cols, 2))


def sweep_hypotheses(
    df: pd.DataFrame,
    column_types: dict[str, str],
    alpha: float = DEFAULT_ALPHA,
    max_pairs: int = DEFAULT_MAX_PAIRS,
) -> dict:
    """Run every viable pairwise hypothesis test and FDR-correct the results.

    Returns {
      "tested": [ {col_a, col_b, test, test_label, statistic, p_value,
                   p_adj, significant, effect_size, effect_size_name,
                   effect_size_label, n}, ... ] sorted by p_adj ascending,
                 ties broken by |effect_size| descending,
      "n_pairs_available": int,  # viable pairs before the max_pairs cap
      "n_pairs_skipped": int,    # dropped by the cap or unusable (e.g. a
                                  # categorical column with only 1 category)
      "n_tests_run": int,        # tests actually executed and scored
      "n_significant": int,      # significant *after* FDR correction
      "alpha": alpha,
    }

    An empty or all-unusable dataset returns a result with "tested": []
    and zeroed counts rather than raising — a sweep that finds nothing
    viable to test is a valid outcome, not a failure.
    """
    all_pairs = _viable_pairs(column_types)
    n_pairs_available = len(all_pairs)
    pairs = all_pairs[:max_pairs]
    n_skipped = n_pairs_available - len(pairs)

    rows = []
    for col_a, col_b in pairs:
        suggestion = stats_lab.suggest_test(df, column_types, col_a, col_b)
        if suggestion.get("error"):
            n_skipped += 1
            continue
        result = stats_lab.run_test(df, suggestion)
        if result.get("error") or result.get("p_value") is None:
            n_skipped += 1
            continue
        n = len(df[[col_a, col_b]].dropna())
        rows.append(
            {
                "col_a": col_a,
                "col_b": col_b,
                "test": result["test"],
                "test_label": stats_lab.TEST_LABELS[result["test"]],
                "statistic": result["statistic"],
                "p_value": result["p_value"],
                "effect_size": result["effect_size"],
                "effect_size_name": result["effect_size_name"],
                "effect_size_label": result["effect_size_label"],
                "n": n,
                # Per-group n for ttest/anova rows (needed for a post-hoc power
                # check — see annotate_power() below); None for pearson (no
                # groups) and chi2 (a contingency table, not per-group counts).
                "group_sizes": (
                    dict(result["groups"]) if result["test"] in ("ttest", "anova") else None
                ),
                # Degrees of freedom, chi2 rows only (also for annotate_power()
                # below — chi-square power needs dof, not just Cramer's V).
                "dof": result.get("dof"),
            }
        )

    if not rows:
        return {
            "tested": [],
            "n_pairs_available": n_pairs_available,
            "n_pairs_skipped": n_skipped,
            "n_tests_run": 0,
            "n_significant": 0,
            "alpha": alpha,
        }

    from statsmodels.stats.multitest import multipletests

    p_values = [r["p_value"] for r in rows]
    reject, p_adj, _, _ = multipletests(p_values, alpha=alpha, method="fdr_bh")
    for row, adj, sig in zip(rows, p_adj, reject):
        row["p_adj"] = float(adj)
        row["significant"] = bool(sig)

    rows.sort(key=lambda r: (r["p_adj"], -abs(r["effect_size"])))

    return {
        "tested": rows,
        "n_pairs_available": n_pairs_available,
        "n_pairs_skipped": n_skipped,
        "n_tests_run": len(rows),
        "n_significant": int(sum(reject)),
        "alpha": alpha,
    }


def annotate_power(result: dict, target_power: float = experiment_design.DEFAULT_POWER) -> dict:
    """Attach a post-hoc power check to every significant row in a sweep
    result, across all three test families that have a well-defined power
    formula: t-test (`experiment_design.power_check_ttest`), chi-square
    (`power_check_chi2`), and one-way ANOVA (`power_check_anova`).

    A significant result only tells you *this* sample showed an effect —
    it says nothing about whether the test had enough power to reliably
    find one in the first place. A "significant" result from 8 rows per
    group is far less trustworthy than the same p-value from 800, and this
    surfaces that distinction automatically rather than making the user
    reason about sample size themselves.

    Pearson (correlation) rows get `power_check: None` — correlation power
    needs a Fisher z-transform noncentral distribution family, a genuinely
    different approach than the noncentral-chi-square family the other
    three share, and is left as a real, separate follow-on rather than
    approximated here (see `experiment_design`'s module docstring).

    Non-mutating: returns a new dict with a new `tested` list; the input
    `result` (and its row dicts) are left untouched.
    """
    if not result or not result.get("tested"):
        return result

    alpha = result.get("alpha", DEFAULT_ALPHA)
    annotated_rows = []
    for row in result["tested"]:
        row = dict(row)
        test = row.get("test")
        group_sizes = row.get("group_sizes")
        dof = row.get("dof")

        if (
            test == "ttest"
            and row.get("significant")
            and group_sizes
            and len(group_sizes) == 2
            and all(n >= 2 for n in group_sizes.values())
        ):
            n1, n2 = list(group_sizes.values())
            row["power_check"] = experiment_design.power_check_ttest(
                row["effect_size"], n1, n2, alpha=alpha, target_power=target_power
            )
        elif (
            test == "anova"
            and row.get("significant")
            and group_sizes
            and len(group_sizes) >= 2
            and all(n >= 2 for n in group_sizes.values())
        ):
            k_groups = len(group_sizes)
            nobs_total = sum(group_sizes.values())
            row["power_check"] = experiment_design.power_check_anova(
                row["effect_size"], k_groups, nobs_total, alpha=alpha, target_power=target_power
            )
        elif (
            test == "chi2"
            and row.get("significant")
            and dof
            and dof >= 1
            and row.get("n", 0) >= 2
        ):
            cohens_w = experiment_design.cohens_w_from_chi2(row["statistic"], row["n"])
            row["power_check"] = experiment_design.power_check_chi2(
                cohens_w, row["n"], dof, alpha=alpha, target_power=target_power
            )
        else:
            row["power_check"] = None
        annotated_rows.append(row)

    annotated = dict(result)
    annotated["tested"] = annotated_rows
    return annotated


def fingerprint_sweep(result: Optional[dict]) -> str:
    """A short, stable hash of a `sweep_hypotheses()` result's significant
    findings — used to cache a Gemini narration call keyed to output that's
    actually different, same pattern as `anomaly.fingerprint_flagged`.
    """
    if not result or not result.get("tested"):
        return "empty"
    significant = [r for r in result["tested"] if r["significant"]]
    key = "|".join(
        f"{r['col_a']}:{r['col_b']}:{r['test']}:{r['p_adj']:.6f}" for r in significant
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


_SWEEP_NARRATION_PROMPT = (
    "You are a senior data analyst explaining the results of an automated statistical "
    "hypothesis sweep to a stakeholder who isn't technical. {n_tests} pairwise statistical "
    "tests were run automatically across the dataset's columns (correlation tests for "
    "numeric/numeric pairs, t-test/ANOVA for numeric/categorical pairs, chi-square for "
    "categorical/categorical pairs), then corrected for the multiple-comparisons problem "
    "with Benjamini-Hochberg false-discovery-rate correction so random noise doesn't get "
    "reported as a real finding. {n_significant} pair(s) stayed significant after correction. "
    "Here are the top findings, ranked by effect size:\n\n{findings_text}\n\n"
    "In 3-4 sentences: explain in plain English what these relationships suggest about the "
    "data, and recommend one concrete next step (e.g. investigate a specific relationship "
    "further in Stats Lab, or treat it as a candidate feature in ML Lab). Do not simply "
    "restate the numbers back."
)


def narrate_sweep(model, result: Optional[dict]) -> tuple[str, Optional[str]]:
    """Ask Gemini to interpret a hypothesis sweep's significant findings.

    Returns (narration, error). Callers should cache the result keyed by
    `fingerprint_sweep(result)` to avoid re-calling Gemini for a sweep the
    user has already seen narrated — same caching contract as every other
    narration helper in the app (see `anomaly.narrate_anomalies`).
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result or not result.get("tested"):
        return "No column pairs were viable to test in this sweep — nothing to narrate.", None

    significant = [r for r in result["tested"] if r["significant"]]
    if not significant:
        return (
            f"None of the {result['n_tests_run']} test(s) run stayed significant after "
            "false-discovery-rate correction — no reliable relationships were found in this sweep.",
            None,
        )

    from modules.ai_analyst import call_gemini

    top = significant[:8]
    findings_text = "\n".join(
        f"- '{r['col_a']}' vs '{r['col_b']}' ({r['test_label']}): {r['effect_size_label']} effect "
        f"({r['effect_size_name']}={r['effect_size']:.2f}, p_adj={r['p_adj']:.4f})"
        for r in top
    )
    prompt = _SWEEP_NARRATION_PROMPT.format(
        n_tests=result["n_tests_run"], n_significant=result["n_significant"], findings_text=findings_text
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None


# ═══════════════════════════════════════════════════════════════════════
# NARRATION FACT-CHECK — the same "plausible but wrong number" safety net
# insight_verifier applies to Auto Analyst's Gemini findings (see that
# module's docstring), extended here to narrate_sweep()'s prose. The
# reference numbers don't need recomputing from the DataFrame the way
# insight_verifier.compute_reference_numbers() does — sweep_hypotheses()
# already produced every statistic narrate_sweep() could plausibly cite
# (p-values, adjusted p-values, effect sizes, sample sizes, test counts),
# so the ground truth here is exact, not a reference-set approximation.
# ═══════════════════════════════════════════════════════════════════════
def sweep_reference_numbers(result: Optional[dict]) -> set[float]:
    """Ground-truth numbers straight from a sweep result's own already-
    computed statistics. Never raises — a malformed result just yields an
    empty (or partial) reference set, which verify_narration() degrades to
    "unverifiable" for, same non-blocking contract as insight_verifier.
    """
    if not result:
        return set()
    numbers: set[float] = set()
    try:
        numbers.add(float(result.get("n_tests_run", 0)))
        numbers.add(float(result.get("n_significant", 0)))
        for row in result.get("tested") or []:
            for key in ("p_value", "p_adj", "effect_size", "n"):
                value = row.get(key)
                if value is None:
                    continue
                numbers.add(round(float(value), 4))
                numbers.add(round(float(value), 2))
                numbers.add(round(float(value) * 100, 2))  # p/effect sizes often quoted as %
    except (TypeError, ValueError, AttributeError):
        pass
    return numbers


def verify_narration(narration: str, result: Optional[dict]) -> dict:
    """Fact-check narrate_sweep()'s prose against the sweep's own numbers.
    Reuses insight_verifier.verify_finding() — same {"status": "confirmed"
    | "flagged" | "unverifiable", ...} contract as every other verified
    surface in the app, just backed by exact sweep statistics instead of a
    DataFrame recomputation. Never raises.
    """
    from modules import insight_verifier

    try:
        reference_numbers = sweep_reference_numbers(result)
    except Exception:
        reference_numbers = set()
    return insight_verifier.verify_finding(narration or "", reference_numbers)


# ═══════════════════════════════════════════════════════════════════════
# CONFOUNDER CROSS-CHECK — the sweep's own agentic follow-up question.
# Auto-Insights' strong correlations already get stress-tested by
# modules.confounder_detection ("...but does it hold up once you control
# for a third variable?" — see that module's docstring for why this
# matters, Simpson's Paradox in particular). A sweep finding that survives
# FDR correction across dozens of tests is a *stronger* claim than a single
# eyeballed correlation, which makes it more likely to get taken at face
# value — exactly the kind of finding worth auto-questioning, not less.
# ═══════════════════════════════════════════════════════════════════════
def cross_check_confounders(
    df: pd.DataFrame, column_types: dict[str, str], result: Optional[dict], top_k: int = 3
) -> list[dict]:
    """For the sweep's strongest significant findings, auto-run the same
    paradox/attenuation check Auto-Insights' correlations get:

    - numeric/numeric (Pearson) pairs, via `confounder_detection.
      auto_scan_for_confounding`'s `correlation_pairs=` hook — the pair's
      already-computed r is reused directly, nothing recomputed.
    - binary-categorical/numeric (Welch's t-test) pairs, via
      `confounder_detection.auto_scan_for_group_diff_confounding`'s
      `ttest_pairs=` hook — same reuse, but for Cohen's d instead of r
      (see that module's "GROUP-DIFFERENCE CONFOUNDER CROSS-CHECK" section
      for why a categorical relationship is just as susceptible to
      Simpson's Paradox as a correlation is).

    One-way ANOVA (>2 groups) and chi-square pairs are still out of scope —
    neither has a single signed effect size for a confounder to flip.
    Deterministic, no Gemini call. Returns a list of scans tagged with
    `"relationship"` ("correlation" or "group_diff") so callers can render
    each appropriately — each scan is otherwise its source function's own
    shape ({x, y, overall_r, findings: [...]} or {x, y, overall_d,
    findings: [...]}). Empty when nothing significant survived FDR
    correction or every candidate confounder came back "robust". Never
    raises: a malformed `result` just yields an empty list, same
    non-blocking contract as `sweep_reference_numbers`.
    """
    try:
        tested = result.get("tested") if result else None
        if not tested:
            return []
        significant_pearson = [
            r for r in tested
            if r.get("significant") and r.get("test") == "pearson" and r.get("effect_size") is not None
        ]
        significant_ttest = [
            r for r in tested
            if r.get("significant") and r.get("test") == "ttest" and r.get("effect_size") is not None
        ]
    except (TypeError, AttributeError, KeyError):
        return []

    if not significant_pearson and not significant_ttest:
        return []

    from modules import confounder_detection

    scans = []
    if significant_pearson:
        pairs = [(r["col_a"], r["col_b"], float(r["effect_size"])) for r in significant_pearson[:top_k]]
        for scan in confounder_detection.auto_scan_for_confounding(
            df, column_types, correlation_pairs=pairs, top_k_pairs=top_k
        ):
            scan["relationship"] = "correlation"
            scans.append(scan)

    if significant_ttest:
        ttest_pairs = []
        for r in significant_ttest[:top_k]:
            col_a, col_b = r["col_a"], r["col_b"]
            if column_types.get(col_a) == "categorical":
                cat_col, num_col = col_a, col_b
            else:
                cat_col, num_col = col_b, col_a
            ttest_pairs.append((cat_col, num_col, float(r["effect_size"])))
        for scan in confounder_detection.auto_scan_for_group_diff_confounding(
            df, column_types, ttest_pairs=ttest_pairs, top_k_pairs=top_k
        ):
            scan["relationship"] = "group_diff"
            scans.append(scan)

    return scans


def build_sweep_chart(result: dict, top_n: int = 15):
    """Horizontal bar chart of the top significant findings by |effect size|."""
    import plotly.express as px

    significant = [r for r in result.get("tested", []) if r["significant"]][:top_n]
    if not significant:
        return None

    significant = sorted(significant, key=lambda r: abs(r["effect_size"]))
    labels = [f"{r['col_a']} vs {r['col_b']}" for r in significant]
    values = [abs(r["effect_size"]) for r in significant]
    fig = px.bar(
        x=values, y=labels, orientation="h",
        labels={"x": "|Effect size|", "y": "Column pair"},
        title="Hypothesis Sweep — significant findings by effect size",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig
