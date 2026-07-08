"""
Join Engine — combine two DataFrames on a detected or user-chosen key.
Pure functions; app.py owns all Streamlit widgets and session state.
"""

from __future__ import annotations

import pandas as pd

JOIN_TYPE_DESCRIPTIONS = {
    "inner": "Keeps only rows where the key exists in both files.",
    "left": "Keeps every row from the active dataset, filling in matches from the second file where found.",
    "right": "Keeps every row from the second file, filling in matches from the active dataset where found.",
    "outer": "Keeps every row from both files, leaving blanks wherever there's no match.",
}


def detect_candidate_join_keys(df1: pd.DataFrame, df2: pd.DataFrame) -> list[dict]:
    """Find columns present (by name) in both frames and measure how much
    their values overlap.

    Returns a list of dicts, sorted by overlap % descending:
    [{"column": str, "overlap_pct": float, "left_unique": int, "right_unique": int}]

    overlap_pct is a Jaccard-style measure — |shared values| / |union of
    values| * 100 — so it rewards keys that actually line up, not just keys
    that happen to share a column name.
    """
    candidates = []
    shared_names = [c for c in df1.columns if c in df2.columns]

    for col in shared_names:
        left_vals = set(df1[col].dropna().unique().tolist())
        right_vals = set(df2[col].dropna().unique().tolist())
        if not left_vals or not right_vals:
            continue
        union = left_vals | right_vals
        overlap_pct = 100 * len(left_vals & right_vals) / len(union) if union else 0.0
        candidates.append(
            {
                "column": col,
                "overlap_pct": round(overlap_pct, 1),
                "left_unique": len(left_vals),
                "right_unique": len(right_vals),
            }
        )

    candidates.sort(key=lambda c: c["overlap_pct"], reverse=True)
    return candidates


def join_dataframes(
    df1: pd.DataFrame, df2: pd.DataFrame, left_on: str, right_on: str, how: str
) -> tuple[pd.DataFrame, dict]:
    """Join df2 onto df1 on the given key columns.

    Returns (joined_df, stats) where stats is:
    {"rows_before": int, "rows_after": int, "columns_gained": int, "match_pct": float}

    match_pct is the share of df1's key values that have at least one match in
    df2 — a data-quality signal for the chosen key, independent of `how`
    (an inner join with a low match_pct will simply drop most rows; an outer
    join will keep them all but leave the joined columns blank).
    """
    joined = df1.merge(df2, how=how, left_on=left_on, right_on=right_on, suffixes=("", "_2"))

    left_keys = df1[left_on].dropna()
    right_key_set = set(df2[right_on].dropna().unique().tolist())
    match_pct = round(100 * left_keys.isin(right_key_set).mean(), 1) if len(left_keys) else 0.0

    stats = {
        "rows_before": len(df1),
        "rows_after": len(joined),
        "columns_gained": joined.shape[1] - df1.shape[1],
        "match_pct": match_pct,
    }
    return joined, stats
