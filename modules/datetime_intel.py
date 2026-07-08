"""
Datetime Intelligence — one-click calendar feature extraction and time-series
gap detection for datetime columns.
"""

from __future__ import annotations

import pandas as pd


def extract_datetime_features(df: pd.DataFrame, column: str) -> tuple[pd.DataFrame, list[str]]:
    """Add year/month/day/weekday/quarter columns derived from `column`.

    Returns (new_df, added_column_names). Existing columns with the same
    generated names are overwritten rather than duplicated.
    """
    new_df = df.copy()
    series = pd.to_datetime(new_df[column], errors="coerce")

    feature_map = {
        "year": series.dt.year,
        "month": series.dt.month,
        "day": series.dt.day,
        "weekday": series.dt.day_name(),
        "quarter": series.dt.quarter,
    }
    added = []
    for suffix, values in feature_map.items():
        new_col = f"{column}_{suffix}"
        new_df[new_col] = values
        added.append(new_col)
    return new_df, added


def _build_gap(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    days = (end - start).days + 1
    return {
        "start": start.strftime("%b %d, %Y"),
        "end": end.strftime("%b %d, %Y"),
        "days_missing": days,
    }


def detect_gaps(df: pd.DataFrame, column: str, freq: str = "D") -> list[dict]:
    """Detect missing periods in a datetime column, assuming a regular
    frequency (daily by default).

    Returns a list of {"start": str, "end": str, "days_missing": int} — one
    entry per contiguous run of missing expected dates. Empty list if the
    column has fewer than 2 distinct dates or no gaps are found.
    """
    series = pd.to_datetime(df[column], errors="coerce").dropna()
    unique_dates = pd.DatetimeIndex(sorted(series.unique()))
    if len(unique_dates) < 2:
        return []

    full_range = pd.date_range(start=unique_dates.min(), end=unique_dates.max(), freq=freq)
    missing = full_range.difference(unique_dates)
    if len(missing) == 0:
        return []

    step = pd.Timedelta(pd.tseries.frequencies.to_offset(freq))
    missing_sorted = sorted(missing)

    gaps = []
    gap_start = prev = missing_sorted[0]
    for ts in missing_sorted[1:]:
        if (ts - prev) > step * 1.5:  # a jump larger than one step starts a new gap
            gaps.append(_build_gap(gap_start, prev))
            gap_start = ts
        prev = ts
    gaps.append(_build_gap(gap_start, prev))
    return gaps
