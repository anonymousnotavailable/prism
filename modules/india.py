"""
India Mode — fiscal-year intelligence, Indian number formatting, day-first
date parsing, and festival-date awareness for time-series charts. Every
function here is a pure helper with no Streamlit dependency, so it's usable
from app.py, autocleaner.py, geo.py, and the Plotly chart builders alike.

Toggled from the sidebar (default ON) — when off, callers fall back to
calendar-year labels and Western number formatting, but nothing here is
destructive: it only ever affects *display* formatting and *which* fiscal
label a date maps to, never the underlying data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

FESTIVALS_PATH = Path(__file__).resolve().parent.parent / "data" / "festivals.csv"

# 28 states + 8 union territories, canonical spelling — used by geo.py for
# fuzzy-matching a user's state column, but lives here since it's general
# "India reference data" alongside festivals.
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
]
INDIAN_UNION_TERRITORIES = [
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
INDIAN_STATES_AND_UTS = INDIAN_STATES + INDIAN_UNION_TERRITORIES


# ==========================================================================
# Number formatting — Indian digit grouping (1,20,000) + compact ₹ labels.
# ==========================================================================
def indian_comma_group(n: float) -> str:
    """Format an integer with Indian-style comma grouping: the last 3 digits
    as one group, then groups of 2 (1,20,000 not 120,000). Sign-aware.
    """
    negative = n < 0
    n = abs(int(round(n)))
    s = str(n)
    if len(s) <= 3:
        grouped = s
    else:
        last3, rest = s[-3:], s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return f"-{grouped}" if negative else grouped


def format_inr(value: Optional[float], compact: bool = True, decimals: int = 1) -> str:
    """The one INR formatter every chart/KPI card in India Mode uses.

    compact=True: "₹1.2L" / "₹3.4Cr" / "₹85.0K" for large values, plain
    "₹450" below 1,000. compact=False: full Indian-grouped value, e.g.
    "₹1,20,000". Returns "—" for None/NaN so callers never need a None-check
    of their own.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"

    negative = value < 0
    abs_value = abs(value)

    if not compact:
        return f"{'-' if negative else ''}₹{indian_comma_group(abs_value)}"

    if abs_value >= 1_00_00_000:
        label = f"{abs_value / 1_00_00_000:.{decimals}f}Cr"
    elif abs_value >= 1_00_000:
        label = f"{abs_value / 1_00_000:.{decimals}f}L"
    elif abs_value >= 1_000:
        label = f"{abs_value / 1_000:.{decimals}f}K"
    else:
        label = f"{abs_value:.0f}"
    return f"{'-' if negative else ''}₹{label}"


# ==========================================================================
# Fiscal year — Apr-Mar, quarters Q1=Apr-Jun ... Q4=Jan-Mar.
# ==========================================================================
def fiscal_year_label(date) -> Optional[str]:
    """"FY2025-26" for any date from 2025-04-01 through 2026-03-31."""
    ts = pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date
    if pd.isna(ts):
        return None
    start_year = ts.year if ts.month >= 4 else ts.year - 1
    return f"FY{start_year}-{str(start_year + 1)[-2:]}"


def fiscal_quarter_label(date) -> Optional[str]:
    """"Q1 FY2025-26" (Apr-Jun) through "Q4 FY2025-26" (Jan-Mar)."""
    ts = pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date
    if pd.isna(ts):
        return None
    quarter = ((ts.month - 4) % 12) // 3 + 1
    return f"Q{quarter} {fiscal_year_label(ts)}"


def add_fiscal_columns(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Add `<date_col>_fiscal_year` and `<date_col>_fiscal_quarter` columns,
    derived from an existing datetime column. Non-destructive — the source
    column is untouched.
    """
    new_df = df.copy()
    dt = pd.to_datetime(new_df[date_col], errors="coerce")
    new_df[f"{date_col}_fiscal_year"] = dt.apply(fiscal_year_label)
    new_df[f"{date_col}_fiscal_quarter"] = dt.apply(fiscal_quarter_label)
    return new_df


def fiscal_columns_code(date_col: str) -> str:
    return (
        f"from modules.india import fiscal_year_label, fiscal_quarter_label\n"
        f"_dt = pd.to_datetime(df[{date_col!r}], errors='coerce')\n"
        f"df[{date_col + '_fiscal_year'!r}] = _dt.apply(fiscal_year_label)\n"
        f"df[{date_col + '_fiscal_quarter'!r}] = _dt.apply(fiscal_quarter_label)"
    )


# ==========================================================================
# Festival calendar — subtle chart markers + AI-insight context.
# ==========================================================================
def load_festivals() -> pd.DataFrame:
    """Read data/festivals.csv. Returns an empty DataFrame (not an error) if
    the file is missing, so callers can skip markers silently rather than
    branch on file existence themselves.
    """
    if not FESTIVALS_PATH.exists():
        return pd.DataFrame(columns=["date", "festival"])
    try:
        df = pd.read_csv(FESTIVALS_PATH, parse_dates=["date"])
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "festival"])


def festivals_in_range(start, end) -> pd.DataFrame:
    """Festivals falling within [start, end] (inclusive), for annotating a
    time-series chart's x-axis span. Empty DataFrame if none fall in range
    or the festival calendar is unavailable.
    """
    festivals = load_festivals()
    if festivals.empty:
        return festivals
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    return festivals[(festivals["date"] >= start_ts) & (festivals["date"] <= end_ts)].reset_index(drop=True)


def add_festival_markers(fig, start, end) -> None:
    """Add subtle vertical dashed lines + hover-visible labels for every
    festival in [start, end] to an existing Plotly figure, in place. A
    no-op if the festival calendar is missing or nothing falls in range —
    callers never need to check first.
    """
    festivals = festivals_in_range(start, end)
    if festivals.empty:
        return
    for _, row in festivals.iterrows():
        fig.add_vline(
            x=row["date"], line_width=1, line_dash="dot", line_color="rgba(251,191,36,0.45)",
            annotation_text=row["festival"], annotation_position="top",
            annotation_font_size=9, annotation_font_color="rgba(251,191,36,0.85)",
        )


def festival_context_for_prompt(start, end) -> str:
    """One line of festival context to fold into an AI-insight prompt, e.g.
    "Festivals in this period: Diwali (2025-10-20), Holi (2025-03-14)." —
    empty string if none, so callers can always append it safely.
    """
    festivals = festivals_in_range(start, end)
    if festivals.empty:
        return ""
    parts = [f"{row['festival']} ({row['date'].date()})" for _, row in festivals.iterrows()]
    return f"Festivals in this period: {', '.join(parts)}."
