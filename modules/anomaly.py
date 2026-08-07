"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged
row, plus an optional Gemini narration that summarizes the flagged rows as
a whole (what's really going on, not just which column deviated most).
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
except ImportError:  # the app should still load even if the package isn't installed yet
    IsolationForest = None

MIN_ROWS_REQUIRED = 10
MIN_CONTAMINATION = 0.01
MAX_CONTAMINATION = 0.25
DEFAULT_CONTAMINATION = 0.05


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
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = DEFAULT_CONTAMINATION
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run IsolationForest over numeric columns and return flagged rows with reasons.

    Returns (flagged_df, error). flagged_df carries an added 'anomaly_reason'
    column and may be empty (0 rows) if nothing was flagged — that's a valid
    "no anomalies found" result, not an error. error is set only when
    detection couldn't run at all (no numeric columns, missing dependency,
    or too few rows). `contamination` (roughly, the expected anomaly rate)
    is clamped to [MIN_CONTAMINATION, MAX_CONTAMINATION] — IsolationForest
    itself accepts (0, 0.5], but values outside this band tend to flag
    either near-nothing or a third of the dataset, neither of which reads
    as a useful "anomaly" result.
    """
    if IsolationForest is None:
        return None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."

    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    if not numeric_cols:
        return None, "No numeric columns available for anomaly detection."

    if len(df) < MIN_ROWS_REQUIRED:
        return None, f"Not enough rows to reliably detect anomalies (need at least {MIN_ROWS_REQUIRED})."

    contamination = max(MIN_CONTAMINATION, min(MAX_CONTAMINATION, contamination))

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


def _default_narration(flagged: pd.DataFrame, total_rows: int) -> str:
    """Deterministic fallback narration, built from the per-row reasons
    without any LLM call — used when Gemini is unavailable or fails.
    """
    if len(flagged) == 0:
        return "No rows were flagged as anomalies at the current sensitivity."

    pct = 100 * len(flagged) / total_rows if total_rows else 0.0
    culprit_cols = Counter(reason.split(" is ")[0].strip("'") for reason in flagged["anomaly_reason"])
    top_col, top_count = culprit_cols.most_common(1)[0]
    return (
        f"{len(flagged)} row(s) ({pct:.1f}% of the dataset) were flagged as unusual. "
        f"'{top_col}' was the most common driver, involved in {top_count} of the flagged row(s) — "
        "worth a closer look before deciding whether these are data-entry errors or genuine outliers."
    )


def narrate_anomalies(model, flagged: pd.DataFrame, total_rows: int) -> tuple[str, Optional[str]]:
    """Plain-English, 2-3 sentence summary of the flagged rows as a whole —
    what's really going on, not just "column X deviated most" per row.

    Always returns usable text (falls back to _default_narration on any
    error) — narration is a nice-to-have, never a blocker. Returns
    (narration, error); error is only informational (e.g. rate limit hit),
    the narration field is always populated regardless.
    """
    if len(flagged) == 0:
        return _default_narration(flagged, total_rows), None
    if model is None:
        return _default_narration(flagged, total_rows), None

    from modules.ai_analyst import call_gemini  # local import: keep anomaly.py Gemini-optional

    reasons_sample = flagged["anomaly_reason"].head(10).tolist()
    pct = 100 * len(flagged) / total_rows if total_rows else 0.0
    prompt = (
        "An IsolationForest anomaly detector flagged the following rows in a dataset as unusual. "
        f"{len(flagged)} of {total_rows} rows ({pct:.1f}%) were flagged. Here are up to 10 sample "
        f"reasons, one per flagged row:\n{chr(10).join(f'- {r}' for r in reasons_sample)}\n\n"
        "In 2-3 plain-English sentences, summarize what's likely going on across these anomalies as "
        "a group (a common pattern, a likely data-quality issue, or a genuinely interesting outlier "
        "segment) — not a restatement of each reason. No markdown, no bullet points, just prose."
    )
    text, error = call_gemini(model, prompt)
    if error or not text.strip():
        return _default_narration(flagged, total_rows), error
    return text.strip(), None
