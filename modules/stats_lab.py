"""
Stats Lab — guided statistical testing. Given two columns, suggest_test()
picks the right test based on their detected types (independent t-test,
one-way ANOVA, chi-square test of independence, or Pearson correlation
significance) with a one-line reason, run_test() executes it via
scipy.stats, and interpret_result()/normality_warnings() turn the raw
numbers into a plain-English verdict plus assumption-check warnings.

normality_warnings() has always been able to tell a user their data isn't
normal — but until now that was a dead end: a warning with no valid next
step. NONPARAMETRIC_ALTERNATIVE and run_nonparametric_alternative() close
that gap: Mann-Whitney U (rank-based two-group comparison, replacing the
t-test), Kruskal-Wallis (rank-based k-group comparison, replacing ANOVA),
and Spearman's rho (rank-based monotonic association, replacing Pearson) —
the standard non-parametric counterpart to each parametric test this module
already runs, sharing its dispatch/interpret/effect-size machinery rather
than bolting on a separate code path. Chi-square has no such counterpart
here: it's already distribution-free (it tests category-count independence,
not a mean/correlation that assumes normality), so it isn't in the map.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# Beyond this many categories, a group comparison stops being meaningful
# (too many tiny groups) — the UI should ask the user to pick a different column.
MAX_GROUPS_FOR_TEST = 10

# scipy.stats.shapiro is only validated up to a few thousand points; beyond
# that we test a fixed random subsample rather than the full column.
SHAPIRO_MAX_N = 5000

TEST_LABELS = {
    "ttest": "Independent t-test",
    "anova": "One-way ANOVA",
    "chi2": "Chi-square test of independence",
    "pearson": "Pearson correlation significance",
    "mannwhitney": "Mann-Whitney U test",
    "kruskal": "Kruskal-Wallis H test",
    "spearman": "Spearman rank correlation",
}

_EFFECT_SIZE_THRESHOLDS = {
    "ttest": [(0.2, "small"), (0.5, "medium"), (0.8, "large")],
    "anova": [(0.01, "small"), (0.06, "medium"), (0.14, "large")],
    "chi2": [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
    "pearson": [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
    # Rank-biserial r (Mann-Whitney) and Spearman's rho share Pearson's
    # conventional correlation-strength bands; epsilon-squared (Kruskal-
    # Wallis) shares ANOVA's eta-squared bands — both are the standard
    # analogues cited for these statistics (e.g. Tomczak & Tomczak 2014).
    "mannwhitney": [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
    "kruskal": [(0.01, "small"), (0.06, "medium"), (0.14, "large")],
    "spearman": [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
}

# Which non-parametric test replaces which parametric one when its normality
# assumption looks shaky. Chi-square deliberately has no entry — it's
# already distribution-free.
NONPARAMETRIC_ALTERNATIVE = {
    "ttest": "mannwhitney",
    "anova": "kruskal",
    "pearson": "spearman",
}


def has_nonparametric_alternative(test: str) -> bool:
    return test in NONPARAMETRIC_ALTERNATIVE


def _effect_size_label(test: str, value: float) -> str:
    """Conventional small/medium/large label for a test's effect-size statistic."""
    magnitude = abs(value)
    label = "negligible"
    for cutoff, name in _EFFECT_SIZE_THRESHOLDS[test]:
        if magnitude >= cutoff:
            label = name
    return label


def _shapiro_check(values: np.ndarray) -> dict:
    """Shapiro-Wilk normality check. Returns {p_value, is_normal, note}."""
    n = len(values)
    if n < 3:
        return {"p_value": None, "is_normal": None, "note": "Too few values to test normality."}

    note = ""
    sample = values
    if n > SHAPIRO_MAX_N:
        sample = np.random.RandomState(0).choice(values, SHAPIRO_MAX_N, replace=False)
        note = f"Sampled {SHAPIRO_MAX_N:,} of {n:,} values for the normality check."

    try:
        _, p = stats.shapiro(sample)
    except Exception:
        return {"p_value": None, "is_normal": None, "note": "Normality test failed to run."}

    return {"p_value": float(p), "is_normal": bool(p >= 0.05), "note": note}


def suggest_test(df: pd.DataFrame, column_types: dict[str, str], col_a: str, col_b: str) -> dict:
    """Pick the right test for two columns based on their detected types.

    Returns a dict always containing "col_a"/"col_b". On success it also has
    "test" (one of "ttest"/"anova"/"chi2"/"pearson") and "reason" (a one-line
    explanation of why that test fits). On failure it has "error" instead.
    """
    type_a = column_types.get(col_a)
    type_b = column_types.get(col_b)
    base = {"col_a": col_a, "col_b": col_b}

    if type_a == "numeric" and type_b == "numeric":
        return {
            **base,
            "test": "pearson",
            "reason": f"Both '{col_a}' and '{col_b}' are numeric — testing whether they're linearly correlated.",
        }

    if {type_a, type_b} == {"numeric", "categorical"}:
        numeric_col, cat_col = (col_a, col_b) if type_a == "numeric" else (col_b, col_a)
        n_groups = df[cat_col].dropna().nunique()
        if n_groups < 2:
            return {**base, "error": f"'{cat_col}' needs at least 2 distinct categories to compare groups."}
        if n_groups > MAX_GROUPS_FOR_TEST:
            return {
                **base,
                "error": (
                    f"'{cat_col}' has {n_groups} categories — too many for a meaningful group "
                    f"comparison (max {MAX_GROUPS_FOR_TEST}). Pick a lower-cardinality column."
                ),
            }
        if n_groups == 2:
            return {
                **base,
                "test": "ttest",
                "numeric_col": numeric_col,
                "cat_col": cat_col,
                "reason": f"'{cat_col}' splits the data into exactly 2 groups — comparing '{numeric_col}' means with a t-test.",
            }
        return {
            **base,
            "test": "anova",
            "numeric_col": numeric_col,
            "cat_col": cat_col,
            "reason": f"'{cat_col}' splits the data into {n_groups} groups — comparing '{numeric_col}' means with one-way ANOVA.",
        }

    if type_a == "categorical" and type_b == "categorical":
        return {
            **base,
            "test": "chi2",
            "reason": f"Both '{col_a}' and '{col_b}' are categorical — testing whether they're independent with a chi-square test.",
        }

    return {
        **base,
        "error": f"No suitable test for a '{type_a}' column and a '{type_b}' column. Pick two numeric or categorical columns.",
    }


def run_ttest(df: pd.DataFrame, numeric_col: str, cat_col: str) -> dict:
    """Welch's independent t-test (doesn't assume equal group variances)."""
    clean = df[[numeric_col, cat_col]].dropna()
    levels = sorted(clean[cat_col].unique(), key=str)
    if len(levels) != 2:
        return {"error": f"'{cat_col}' must have exactly 2 categories for a t-test (found {len(levels)})."}

    group1 = clean.loc[clean[cat_col] == levels[0], numeric_col].to_numpy()
    group2 = clean.loc[clean[cat_col] == levels[1], numeric_col].to_numpy()
    if len(group1) < 2 or len(group2) < 2:
        return {"error": "Each group needs at least 2 values to run a t-test."}

    stat, p_value = stats.ttest_ind(group1, group2, equal_var=False)

    pooled_std = np.sqrt((group1.std(ddof=1) ** 2 + group2.std(ddof=1) ** 2) / 2)
    cohens_d = (group1.mean() - group2.mean()) / pooled_std if pooled_std > 0 else 0.0

    label1, label2 = str(levels[0]), str(levels[1])
    return {
        "test": "ttest",
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(cohens_d),
        "effect_size_name": "Cohen's d",
        "effect_size_label": _effect_size_label("ttest", cohens_d),
        "groups": {label1: len(group1), label2: len(group2)},
        "means": {label1: float(group1.mean()), label2: float(group2.mean())},
        "normality": {label1: _shapiro_check(group1), label2: _shapiro_check(group2)},
    }


def run_anova(df: pd.DataFrame, numeric_col: str, cat_col: str) -> dict:
    """One-way ANOVA across the categorical column's groups."""
    clean = df[[numeric_col, cat_col]].dropna()
    groups = {str(name): g[numeric_col].to_numpy() for name, g in clean.groupby(cat_col) if len(g) >= 2}
    if len(groups) < 2:
        return {"error": f"Need at least 2 groups with 2+ values each in '{cat_col}'."}

    stat, p_value = stats.f_oneway(*groups.values())

    grand_mean = clean[numeric_col].mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups.values())
    ss_total = ((clean[numeric_col] - grand_mean) ** 2).sum()
    eta_sq = ss_between / ss_total if ss_total > 0 else 0.0

    return {
        "test": "anova",
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(eta_sq),
        "effect_size_name": "eta-squared",
        "effect_size_label": _effect_size_label("anova", eta_sq),
        "groups": {name: len(g) for name, g in groups.items()},
        "means": {name: float(g.mean()) for name, g in groups.items()},
        "normality": {name: _shapiro_check(g) for name, g in groups.items()},
    }


def run_chi2(df: pd.DataFrame, col_a: str, col_b: str) -> dict:
    """Chi-square test of independence between two categorical columns."""
    clean = df[[col_a, col_b]].dropna()
    table = pd.crosstab(clean[col_a], clean[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {"error": f"Need at least 2 categories in both '{col_a}' and '{col_b}'."}

    stat, p_value, dof, expected = stats.chi2_contingency(table)

    n = table.to_numpy().sum()
    min_dim = min(table.shape) - 1
    cramers_v = np.sqrt((stat / n) / min_dim) if n > 0 and min_dim > 0 else 0.0

    return {
        "test": "chi2",
        "statistic": float(stat),
        "p_value": float(p_value),
        "dof": int(dof),
        "effect_size": float(cramers_v),
        "effect_size_name": "Cramer's V",
        "effect_size_label": _effect_size_label("chi2", cramers_v),
        "contingency_table": table,
        "low_expected_pct": float((expected < 5).mean() * 100),
    }


def run_pearson(df: pd.DataFrame, col_a: str, col_b: str) -> dict:
    """Pearson correlation coefficient with a significance test."""
    clean = df[[col_a, col_b]].dropna()
    if len(clean) < 3:
        return {"error": "Need at least 3 paired values to test correlation significance."}

    r, p_value = stats.pearsonr(clean[col_a], clean[col_b])

    return {
        "test": "pearson",
        "statistic": float(r),
        "p_value": float(p_value),
        "effect_size": float(r),
        "effect_size_name": "Pearson r",
        "effect_size_label": _effect_size_label("pearson", r),
        "n": len(clean),
        "normality": {
            col_a: _shapiro_check(clean[col_a].to_numpy()),
            col_b: _shapiro_check(clean[col_b].to_numpy()),
        },
    }


def run_mannwhitney(df: pd.DataFrame, numeric_col: str, cat_col: str) -> dict:
    """Mann-Whitney U test — the rank-based, no-normality-assumed
    counterpart to run_ttest() for exactly 2 groups. Effect size is the
    rank-biserial correlation, computed from U itself (r = 2U/(n1*n2) - 1):
    +1 means every value in group 1 outranks every value in group 2, -1 the
    reverse, 0 means the groups' ranks are fully interleaved.
    """
    clean = df[[numeric_col, cat_col]].dropna()
    levels = sorted(clean[cat_col].unique(), key=str)
    if len(levels) != 2:
        return {"error": f"'{cat_col}' must have exactly 2 categories for a Mann-Whitney U test (found {len(levels)})."}

    group1 = clean.loc[clean[cat_col] == levels[0], numeric_col].to_numpy()
    group2 = clean.loc[clean[cat_col] == levels[1], numeric_col].to_numpy()
    if len(group1) < 1 or len(group2) < 1:
        return {"error": "Each group needs at least 1 value to run a Mann-Whitney U test."}

    stat, p_value = stats.mannwhitneyu(group1, group2, alternative="two-sided")
    # scipy's U (`stat`) counts group1-over-group2 "wins" among all pairs;
    # r = 2U/(n1*n2) - 1 rescales that win-rate to [-1, 1] so positive means
    # group1 tends to rank higher than group2, negative the reverse — the
    # sign convention matches the "medians" reported below (Kerby 2014).
    rank_biserial = (2 * stat) / (len(group1) * len(group2)) - 1

    label1, label2 = str(levels[0]), str(levels[1])
    return {
        "test": "mannwhitney",
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(rank_biserial),
        "effect_size_name": "rank-biserial r",
        "effect_size_label": _effect_size_label("mannwhitney", rank_biserial),
        "groups": {label1: len(group1), label2: len(group2)},
        "medians": {label1: float(np.median(group1)), label2: float(np.median(group2))},
    }


def run_kruskal(df: pd.DataFrame, numeric_col: str, cat_col: str) -> dict:
    """Kruskal-Wallis H test — the rank-based, no-normality-assumed
    counterpart to run_anova() for 3+ groups. Effect size is epsilon-
    squared, (H - k + 1) / (n - k): ANOVA's eta-squared, adapted for ranks.
    """
    clean = df[[numeric_col, cat_col]].dropna()
    groups = {str(name): g[numeric_col].to_numpy() for name, g in clean.groupby(cat_col) if len(g) >= 1}
    if len(groups) < 2:
        return {"error": f"Need at least 2 groups with 1+ value each in '{cat_col}'."}

    stat, p_value = stats.kruskal(*groups.values())

    n = sum(len(g) for g in groups.values())
    k = len(groups)
    epsilon_sq = (stat - k + 1) / (n - k) if n > k else 0.0
    epsilon_sq = max(0.0, epsilon_sq)  # can dip slightly negative near the null; floor at 0

    return {
        "test": "kruskal",
        "statistic": float(stat),
        "p_value": float(p_value),
        "effect_size": float(epsilon_sq),
        "effect_size_name": "epsilon-squared",
        "effect_size_label": _effect_size_label("kruskal", epsilon_sq),
        "groups": {name: len(g) for name, g in groups.items()},
        "medians": {name: float(np.median(g)) for name, g in groups.items()},
    }


def run_spearman(df: pd.DataFrame, col_a: str, col_b: str) -> dict:
    """Spearman rank correlation — the rank-based, no-normality-assumed
    counterpart to run_pearson(). Measures monotonic (not necessarily
    linear) association.
    """
    clean = df[[col_a, col_b]].dropna()
    if len(clean) < 3:
        return {"error": "Need at least 3 paired values to test correlation significance."}

    rho, p_value = stats.spearmanr(clean[col_a], clean[col_b])

    return {
        "test": "spearman",
        "statistic": float(rho),
        "p_value": float(p_value),
        "effect_size": float(rho),
        "effect_size_name": "Spearman rho",
        "effect_size_label": _effect_size_label("spearman", rho),
        "n": len(clean),
    }


def run_nonparametric_alternative(df: pd.DataFrame, suggestion: dict) -> dict:
    """Run whichever non-parametric test replaces suggestion['test'], reusing
    the same column choices suggest_test() already made. Returns
    {"error": ...} if suggestion['test'] has no alternative (chi2) or is
    missing/unrecognized — never raises.
    """
    test = suggestion.get("test")
    alternative = NONPARAMETRIC_ALTERNATIVE.get(test)
    if alternative is None:
        return {"error": f"No non-parametric alternative for '{test}'."}
    if alternative == "mannwhitney":
        return run_mannwhitney(df, suggestion["numeric_col"], suggestion["cat_col"])
    if alternative == "kruskal":
        return run_kruskal(df, suggestion["numeric_col"], suggestion["cat_col"])
    if alternative == "spearman":
        return run_spearman(df, suggestion["col_a"], suggestion["col_b"])
    return {"error": f"No non-parametric alternative for '{test}'."}  # pragma: no cover — unreachable while the map above stays in sync


def run_test(df: pd.DataFrame, suggestion: dict) -> dict:
    """Dispatch to the right run_* function based on a suggest_test() result."""
    test = suggestion.get("test")
    if test == "ttest":
        return run_ttest(df, suggestion["numeric_col"], suggestion["cat_col"])
    if test == "anova":
        return run_anova(df, suggestion["numeric_col"], suggestion["cat_col"])
    if test == "chi2":
        return run_chi2(df, suggestion["col_a"], suggestion["col_b"])
    if test == "pearson":
        return run_pearson(df, suggestion["col_a"], suggestion["col_b"])
    return {"error": suggestion.get("error", "No test selected.")}


def interpret_result(result: dict) -> str:
    """Plain-English verdict, e.g. 'Significant difference between the two
    group means detected (p=0.0030, large effect, Cohen's d=0.82).'
    """
    if result.get("error"):
        return result["error"]

    p_value = result["p_value"]
    significant = p_value < 0.05
    subject = {
        "ttest": "difference between the two group means",
        "anova": "difference among the group means",
        "chi2": "association between the two columns",
        "pearson": "correlation",
        "mannwhitney": "difference between the two group distributions",
        "kruskal": "difference among the group distributions",
        "spearman": "monotonic correlation",
    }[result["test"]]

    headline = f"Significant {subject} detected" if significant else f"No significant {subject} detected"
    p_str = f"p={p_value:.4f}" if p_value >= 0.0001 else "p<0.0001"
    effect = f"{result['effect_size_label']} effect, {result['effect_size_name']}={result['effect_size']:.2f}"
    return f"{headline} ({p_str}, {effect})."


def normality_warnings(result: dict) -> list[str]:
    """Turn a result's assumption checks into plain-English warning strings."""
    warnings: list[str] = []
    for name, check in result.get("normality", {}).items():
        if check.get("is_normal") is False:
            warnings.append(
                f"'{name}' does not look normally distributed (Shapiro-Wilk p={check['p_value']:.4f}) — "
                "this test assumes roughly normal data, so treat the result with some caution."
            )
        if check.get("note"):
            warnings.append(f"'{name}': {check['note']}")

    if "low_expected_pct" in result and result["low_expected_pct"] > 20:
        warnings.append(
            f"{result['low_expected_pct']:.0f}% of expected cell counts are below 5 — the chi-square "
            "approximation may be unreliable here; consider grouping rare categories together."
        )
    return warnings


_SMALL_GROUP_N = 5  # below this, a rank test's p-value is too coarse to trust


def nonparametric_notes(result: dict) -> list[str]:
    """Plain-English caveats for a run_mannwhitney()/run_kruskal()/
    run_spearman() result — the rank-test counterpart to normality_warnings()
    above (those checks don't apply here: rank tests don't assume
    normality, which is the whole point of reaching for one)."""
    if result.get("error") or result.get("test") not in ("mannwhitney", "kruskal"):
        return []
    small = [name for name, n in result.get("groups", {}).items() if n < _SMALL_GROUP_N]
    if not small:
        return []
    joined = ", ".join(f"'{name}' (n={result['groups'][name]})" for name in small)
    return [
        f"{joined} {'has' if len(small) == 1 else 'have'} fewer than {_SMALL_GROUP_N} values — "
        "with so few observations, even a real difference may not reach significance; treat the "
        "p-value as indicative rather than conclusive."
    ]
