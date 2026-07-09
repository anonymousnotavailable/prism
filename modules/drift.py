"""
Drift — compares the active dataset (A) against a second uploaded dataset
(B, e.g. "last month") column by column: mean/median shifts for numeric
columns, new/missing categories for categorical columns, and a distribution
overlap chart for each shared column. An overall drift score highlights
which columns changed the most.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def _compare_numeric(series_a: pd.Series, series_b: pd.Series, col: str) -> dict:
    a, b = series_a.dropna(), series_b.dropna()
    mean_a, mean_b = float(a.mean()), float(b.mean())
    std_a = float(a.std())

    mean_shift_pct = None if mean_a == 0 else round((mean_b - mean_a) / mean_a * 100, 1)
    # Mean shift measured in units of dataset A's std dev; a 2-std shift maxes the score out.
    z_shift = abs(mean_b - mean_a) / std_a if std_a > 0 else 0.0
    drift_score = round(min(100.0, z_shift * 50), 1)

    return {
        "column": col,
        "type": "numeric",
        "mean_a": mean_a,
        "mean_b": mean_b,
        "median_a": float(a.median()),
        "median_b": float(b.median()),
        "mean_shift_pct": mean_shift_pct,
        "drift_score": drift_score,
        "series_a": a,
        "series_b": b,
    }


def _compare_categorical(series_a: pd.Series, series_b: pd.Series, col: str) -> dict:
    a, b = series_a.dropna(), series_b.dropna()
    cats_a, cats_b = set(a.unique()), set(b.unique())
    new_categories = sorted((cats_b - cats_a), key=str)
    missing_categories = sorted((cats_a - cats_b), key=str)

    freq_a = a.value_counts(normalize=True)
    freq_b = b.value_counts(normalize=True)
    all_cats = cats_a | cats_b
    # Total variation distance: half the sum of absolute frequency differences.
    tvd = sum(abs(freq_a.get(c, 0.0) - freq_b.get(c, 0.0)) for c in all_cats) / 2
    drift_score = round(min(100.0, tvd * 100), 1)

    return {
        "column": col,
        "type": "categorical",
        "new_categories": new_categories,
        "missing_categories": missing_categories,
        "freq_a": freq_a,
        "freq_b": freq_b,
        "drift_score": drift_score,
    }


def compare_datasets(df_a: pd.DataFrame, df_b: pd.DataFrame, column_types_a: dict[str, str]) -> dict:
    """Column-by-column drift report between df_a (baseline) and df_b (comparison).

    Returns "column_reports" (sorted by drift_score descending), an
    "overall_drift_score" (0-100 average across shared numeric/categorical
    columns), and which columns exist in only one of the two datasets.
    """
    shared_cols = [c for c in df_a.columns if c in df_b.columns]
    reports = []
    for col in shared_cols:
        col_type = column_types_a.get(col)
        if col_type == "numeric":
            reports.append(_compare_numeric(df_a[col], df_b[col], col))
        elif col_type == "categorical":
            reports.append(_compare_categorical(df_a[col], df_b[col], col))

    reports.sort(key=lambda r: r["drift_score"], reverse=True)
    overall = round(sum(r["drift_score"] for r in reports) / len(reports), 1) if reports else 0.0

    return {
        "column_reports": reports,
        "overall_drift_score": overall,
        "columns_only_in_a": [c for c in df_a.columns if c not in df_b.columns],
        "columns_only_in_b": [c for c in df_b.columns if c not in df_a.columns],
    }


def describe_drift(report: dict) -> str:
    """One-line plain-English summary of a single column's drift report."""
    if report["type"] == "numeric":
        shift = report["mean_shift_pct"]
        if shift is None:
            return f"Mean changed from {report['mean_a']:.2f} to {report['mean_b']:.2f}."
        direction = "up" if shift > 0 else "down"
        return f"Mean shifted {direction} {abs(shift):.1f}% ({report['mean_a']:.2f} -> {report['mean_b']:.2f})."

    parts = []
    if report["new_categories"]:
        n = len(report["new_categories"])
        parts.append(f"{n} new categor{'y' if n == 1 else 'ies'}")
    if report["missing_categories"]:
        n = len(report["missing_categories"])
        parts.append(f"{n} missing categor{'y' if n == 1 else 'ies'}")
    if not parts:
        parts.append("category set unchanged")
    return "; ".join(parts) + "."


def build_overlap_chart(report: dict) -> go.Figure:
    """Distribution overlap chart — overlaid histograms for numeric columns,
    grouped frequency bars for categorical columns.
    """
    fig = go.Figure()
    if report["type"] == "numeric":
        fig.add_trace(go.Histogram(x=report["series_a"], name="Dataset A", opacity=0.6, histnorm="probability"))
        fig.add_trace(go.Histogram(x=report["series_b"], name="Dataset B", opacity=0.6, histnorm="probability"))
        fig.update_layout(barmode="overlay")
    else:
        cats = sorted(set(report["freq_a"].index) | set(report["freq_b"].index), key=str)
        fig.add_trace(go.Bar(x=[str(c) for c in cats], y=[report["freq_a"].get(c, 0) for c in cats], name="Dataset A"))
        fig.add_trace(go.Bar(x=[str(c) for c in cats], y=[report["freq_b"].get(c, 0) for c in cats], name="Dataset B"))
        fig.update_layout(barmode="group")

    fig.update_layout(title=f"{report['column']} — distribution comparison", margin=dict(t=50, b=10, l=10, r=10))
    return fig
