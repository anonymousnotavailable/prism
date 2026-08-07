"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged
row, plus an optional Gemini-written narrative summarizing the flagged set
as a whole (narrate_anomalies).
"""

from __future__ import annotations

import hashlib
from typing import Optional

import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
except ImportError:  # the app should still load even if the package isn't installed yet
    IsolationForest = None

MIN_ROWS_REQUIRED = 10


def is_available() -> bool:
    """Whether scikit-learn is installed."""
    return IsolationForest is not None


def _reason_for_row(row: pd.Series, numeric_cols: list[str], medians: pd.Series) -> str:
    """Pick the numeric column with the largest relative deviation from its
    median as the human-readable reason a row was flagged.
    """
    best_col, best_ratio = None, 0.0
    for col in numeric_cols:
        median = medians[col]
        value = row[col]
        if pd.isna(value) or pd.isna(median) or median == 0:
            continue
        ratio = abs(value / median)
        if ratio > best_ratio:
            best_ratio, best_col = ratio, col

    if best_col is None:
        return "Unusual combination of values across numeric columns."
    direction = "above" if row[best_col] > medians[best_col] else "below"
    return f"{best_col} is {best_ratio:.1f}x {direction} the column median."


def find_anomalies(
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = 0.05
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run IsolationForest over numeric columns and return flagged rows with reasons.

    Returns (flagged_df, error). flagged_df carries an added 'anomaly_reason'
    column and may be empty (0 rows) if nothing was flagged — that's a valid
    "no anomalies found" result, not an error. error is set only when
    detection couldn't run at all (no numeric columns, missing dependency,
    or too few rows).
    """
    if IsolationForest is None:
        return None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."

    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    if not numeric_cols:
        return None, "No numeric columns available for anomaly detection."

    if len(df) < MIN_ROWS_REQUIRED:
        return None, f"Not enough rows to reliably detect anomalies (need at least {MIN_ROWS_REQUIRED})."

    numeric_df = df[numeric_cols].copy()
    # IsolationForest can't handle NaNs — fill with the column median for
    # detection purposes only; the returned rows still carry their original values.
    numeric_df = numeric_df.fillna(numeric_df.median(numeric_only=True))
    numeric_df = numeric_df.dropna(axis=1, how="all")
    if numeric_df.shape[1] == 0:
        return None, "All numeric columns are entirely empty — nothing to analyze."

    model = IsolationForest(contamination=contamination, random_state=42)
    predictions = model.fit_predict(numeric_df)  # -1 = anomaly, 1 = normal

    flagged_idx = df.index[predictions == -1]
    if len(flagged_idx) == 0:
        return df.iloc[0:0].copy(), None  # empty frame — a valid "no anomalies" result

    medians = numeric_df.median()
    flagged = df.loc[flagged_idx].copy()
    flagged["anomaly_reason"] = [
        _reason_for_row(numeric_df.loc[idx], list(numeric_df.columns), medians) for idx in flagged_idx
    ]
    return flagged, None


# In-process cache of narration text keyed by a hash of the flagged set's
# content, so re-rendering or re-clicking "Narrate" on the same result
# doesn't re-hit the Gemini API — Gemini's free-tier quota is a shared,
# per-session budget (see modules.ai_analyst._check_rate_limit) and a
# narration of an unchanged anomaly set will always come out the same way.
_narration_cache: dict[str, str] = {}


def _anomaly_cache_key(flagged: pd.DataFrame) -> str:
    reasons = "|".join(flagged["anomaly_reason"].astype(str).tolist())
    payload = f"{len(flagged)}::{reasons}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def narrate_anomalies(model, flagged: pd.DataFrame, numeric_cols: list[str]) -> tuple[str, Optional[str]]:
    """One short LLM paragraph explaining the flagged rows as a group:
    what pattern dominates, which column(s) drive it, and whether it reads
    more like data-entry errors or a genuine outlier signal worth digging into.

    Returns (narration, error). narration is "" with error=None when there's
    nothing to narrate (no flagged rows) — that's a valid no-op, not a failure.
    Uses modules.ai_analyst.call_gemini for the same quota/error handling as
    every other Gemini call in the app.
    """
    from modules.ai_analyst import call_gemini  # local import: avoids a module-load-time cycle

    if model is None:
        return "", "No Gemini model available."
    if flagged is None or flagged.empty:
        return "", None

    cache_key = _anomaly_cache_key(flagged)
    if cache_key in _narration_cache:
        return _narration_cache[cache_key], None

    reason_counts = flagged["anomaly_reason"].value_counts().head(8)
    reason_summary = "\n".join(f"- {reason} ({count}x)" for reason, count in reason_counts.items())
    prompt = (
        "You are a senior data analyst. An IsolationForest model flagged "
        f"{len(flagged)} anomalous row(s) out of a dataset. Here are the most common "
        f"reasons rows were flagged:\n\n{reason_summary}\n\n"
        "In 2-4 sentences: (1) summarize what kind of anomaly this looks like, "
        "(2) name the column(s) driving it most, and (3) say whether this reads more like "
        "likely data-entry/measurement errors or a genuine outlier signal worth investigating, "
        "with one concrete next step. Plain English, no headers, no bullet points."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error

    narration = text.strip()
    _narration_cache[cache_key] = narration
    return narration, None
