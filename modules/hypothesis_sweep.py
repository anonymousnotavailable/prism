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

from modules import stats_lab

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
