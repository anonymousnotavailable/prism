"""
Profiling — deeper statistical diagnostics beyond the basic quality report:
skewness/kurtosis in plain English, cardinality flags (probable ID columns),
constant/near-constant detection, and a per-column health badge. Used by the
Overview tab's Column Health section and the Column Drill-Down mini-report.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# A column where >90% of non-null values are unique reads like an identifier
# (order ID, primary key) rather than an analytical variable — worth flagging
# and excluding from auto-charts, which would otherwise render a useless
# giant bar chart with one bar per row.
ID_LIKE_UNIQUE_RATIO = 0.9

# A column where one value accounts for >=95% of rows carries almost no
# signal — usually a candidate for dropping.
NEAR_CONSTANT_RATIO = 0.95


def describe_skewness(skew: float) -> str:
    """Turn a raw skewness coefficient into a plain-English label."""
    if pd.isna(skew):
        return "not enough data"
    direction = "right" if skew > 0 else "left"
    magnitude = abs(skew)
    if magnitude < 0.5:
        return "approximately symmetric"
    if magnitude < 1:
        return f"moderately {direction}-skewed"
    return f"highly {direction}-skewed"


def describe_kurtosis(kurt: float) -> str:
    """Turn a raw excess-kurtosis coefficient (0 = normal) into plain English."""
    if pd.isna(kurt):
        return "not enough data"
    if kurt > 3:
        return "heavy-tailed (prone to extreme outliers)"
    if kurt < -1:
        return "light-tailed (unusually flat distribution)"
    return "close to normal tail weight"


def is_id_like(series: pd.Series) -> bool:
    """True if this column's non-null values are almost all unique.

    Only meaningful for discrete, identifier-shaped columns. Continuous
    float measurements (revenue, temperature, ...) and datetime columns are
    naturally near-100% unique without being identifiers — both are excluded
    here so they don't get wrongly flagged (and excluded from auto-charts).
    """
    if pd.api.types.is_float_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        return False
    non_null = series.dropna()
    if non_null.empty:
        return False
    return non_null.nunique() / len(non_null) > ID_LIKE_UNIQUE_RATIO


def get_id_like_columns(df: pd.DataFrame) -> list[str]:
    """All columns that look like identifiers — used to exclude them from auto-charts."""
    return [c for c in df.columns if is_id_like(df[c])]


def constant_status(series: pd.Series) -> Optional[str]:
    """Returns 'constant', 'near_constant', or None.

    Requires at least 2 non-null values — with only 1, every column is
    trivially "100% one value" without that meaning anything (there's
    nothing to compare it against), so it isn't a real signal worth flagging.
    """
    non_null = series.dropna()
    if len(non_null) < 2:
        return None
    top_ratio = non_null.value_counts(normalize=True).iloc[0]
    if top_ratio >= 1.0:
        return "constant"
    if top_ratio >= NEAR_CONSTANT_RATIO:
        return "near_constant"
    return None


def profile_column(df: pd.DataFrame, column: str, column_types: dict[str, str], quality_report: dict) -> dict:
    """Assemble one column's full diagnostic profile — the shared building
    block behind both the Column Health table and the Column Drill-Down tab.
    """
    ctype = column_types.get(column, "text")
    series = df[column]
    missing_pct = quality_report["missing_by_column"].get(column, 0.0)
    issues: list[str] = []
    warnings: list[str] = []

    if ctype == "all_null":
        issues.append("Column is entirely empty.")

    const_status = constant_status(series)
    if const_status == "constant":
        issues.append("Column has a single constant value — consider dropping it.")
    elif const_status == "near_constant":
        warnings.append("Column is >95% one value (near-constant) — consider dropping it.")

    id_like = is_id_like(series)
    if id_like and ctype != "all_null":
        warnings.append("Looks like an ID column (>90% unique values) — excluded from auto-charts.")

    skew_label = kurt_label = None
    if ctype == "numeric":
        skew_label = describe_skewness(series.skew())
        kurt_label = describe_kurtosis(series.kurt())
        if "highly" in skew_label:
            warnings.append(f"Distribution is {skew_label}.")

    if missing_pct >= 50:
        issues.append(f"{missing_pct}% of values are missing.")
    elif missing_pct >= 10:
        warnings.append(f"{missing_pct}% of values are missing.")

    outlier_info = quality_report["outliers"].get(column)
    if outlier_info and outlier_info["pct"] >= 10:
        warnings.append(f"{outlier_info['pct']}% of values are outliers (IQR method).")

    if issues:
        health = "issue"
    elif warnings:
        health = "warning"
    else:
        health = "good"

    return {
        "column": column,
        "type": ctype,
        "health": health,
        "issues": issues,
        "warnings": warnings,
        "skew_label": skew_label,
        "kurt_label": kurt_label,
        "id_like": id_like,
        "constant_status": const_status,
        "missing_pct": missing_pct,
    }


def profile_all_columns(df: pd.DataFrame, column_types: dict[str, str], quality_report: dict) -> list[dict]:
    """Profile every column — the full Column Health table."""
    return [profile_column(df, col, column_types, quality_report) for col in df.columns]
