"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged row.
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


def fingerprint_flagged(flagged: Optional[pd.DataFrame]) -> str:
    """A short, stable hash of a `find_anomalies()` result — used to cache
    the AI narration below so re-viewing the same flagged set (e.g. after
    switching tabs and back, with no re-detection) doesn't re-spend a
    Gemini call. Changes whenever the row count or the specific rows/reasons
    flagged change; index order doesn't matter (sorted first).
    """
    if flagged is None or flagged.empty:
        return "empty"
    reasons = flagged["anomaly_reason"] if "anomaly_reason" in flagged.columns else pd.Series(dtype=str)
    parts = sorted(f"{idx}:{reasons.get(idx, '')}" for idx in flagged.index)
    key = f"{len(flagged)}|" + "|".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data analyst explaining an anomaly-detection result (from an "
    "IsolationForest model) to a stakeholder who isn't technical. {n} row(s) out of the "
    "dataset were flagged as unusual. Here are the most common reasons they were flagged, "
    "with counts:\n\n{reasons_text}\n\n"
    "In 3-4 sentences: explain in plain English what pattern of anomalies this suggests "
    "(e.g. data-entry errors vs. genuine rare events), and suggest one concrete next action "
    "(e.g. spot-check a few rows, exclude them, or investigate a specific column further). "
    "Do not simply restate the numbers back."
)


def narrate_anomalies(model, flagged: Optional[pd.DataFrame]) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn a `find_anomalies()` result into a short plain-
    English explanation + suggested next action.

    Returns (narration, error). Callers should cache the result keyed by
    `fingerprint_flagged(flagged)` to avoid re-calling Gemini for a result
    the user has already seen narrated (this function itself makes no
    caching decision — it always calls Gemini when given a model and a
    non-empty flagged set, same as the rest of the app's narration
    helpers).
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if flagged is None or flagged.empty:
        return "No anomalies were flagged — nothing to narrate.", None
    if "anomaly_reason" not in flagged.columns:
        return "", "This result has no anomaly_reason column to narrate."

    from modules.ai_analyst import call_gemini

    reason_counts = flagged["anomaly_reason"].value_counts().head(8)
    reasons_text = "\n".join(f"- {reason} ({count} row(s))" for reason, count in reason_counts.items())
    prompt = _NARRATION_PROMPT.format(n=len(flagged), reasons_text=reasons_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
