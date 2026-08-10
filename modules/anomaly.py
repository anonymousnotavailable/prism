"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged row.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# Cap how many individual row reasons go into the Gemini prompt — a wide
# anomaly set (hundreds of flagged rows) would otherwise blow up the request
# for no narration benefit; the model only needs enough examples to spot
# the pattern, not the full list.
_MAX_ROWS_IN_NARRATION_PROMPT = 15

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


def format_anomalies_text(flagged: pd.DataFrame, total_rows: int) -> str:
    """Render flagged anomaly rows as a compact text block for Gemini
    narration input — count, share of the dataset, and each row's reason
    (capped, see _MAX_ROWS_IN_NARRATION_PROMPT). Never includes raw cell
    values, only the already-computed plain-English reason string, so no
    extra PII surface is opened up beyond what find_anomalies already returns.
    """
    if flagged.empty:
        return "No anomalies were flagged."
    pct = len(flagged) / total_rows * 100 if total_rows else 0.0
    lines = [f"{len(flagged)} of {total_rows} rows flagged as anomalous ({pct:.1f}%)."]
    for i, reason in enumerate(flagged["anomaly_reason"].head(_MAX_ROWS_IN_NARRATION_PROMPT), 1):
        lines.append(f"{i}. {reason}")
    remaining = len(flagged) - _MAX_ROWS_IN_NARRATION_PROMPT
    if remaining > 0:
        lines.append(f"...and {remaining} more row(s) with similar flags.")
    return "\n".join(lines)


_NARRATION_PROMPT = (
    "You are a senior data analyst. An automated anomaly detector (IsolationForest) "
    "just flagged some rows in a dataset as statistical outliers. Below is a summary of "
    "what it found. Write a 2-4 sentence plain-English narration for a non-technical "
    "stakeholder: what pattern the flagged rows share (if any), how concerning it looks, "
    "and one concrete suggested next action (e.g. investigate a specific column, exclude "
    "the rows, or treat it as expected). Do not invent numbers not given below.\n\n"
    "{findings_text}"
)


def narrate_anomalies(model, flagged: pd.DataFrame, total_rows: int) -> tuple[str, Optional[str]]:
    """Ask Gemini to narrate the flagged anomaly rows in plain English with a
    suggested next action — the agentic-EDA layer on top of find_anomalies()'s
    deterministic detection.

    Returns (narration, error). Never calls Gemini when there's nothing to
    narrate (empty flagged set) or when no model is available — both are
    handled with a deterministic message instead, same fallback shape as
    modules.auto_insights.narrate_insights().
    """
    if flagged.empty:
        return "No anomalies were flagged — this dataset looks clean.", None
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    findings_text = format_anomalies_text(flagged, total_rows)
    prompt = _NARRATION_PROMPT.format(findings_text=findings_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
