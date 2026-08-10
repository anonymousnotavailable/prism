"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged row.
"""

from __future__ import annotations

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


# ── Gemini narration ─────────────────────────────────────────────────────
#
# find_anomalies() above already gives each flagged row a templated
# `anomaly_reason` string ("X is 3.2x above the median") — useful, but it
# reads like a debug log, not an analyst's judgment call. narrate_anomalies()
# turns the flagged set into a short plain-English paragraph plus one
# concrete suggested next action, the same "raw findings -> Gemini
# synthesis" shape as modules.auto_insights.narrate_insights. Deliberately
# a single bounded call per flagged set (the caller in app.py only invokes
# this on an explicit button click and caches the result in session_state
# until the next "Find Anomalies" run or dataset swap resets it) — this
# is what keeps it inside Gemini's free-tier rate limits.

MAX_REASONS_IN_PROMPT = 20  # cap prompt size on a large flagged set

_NARRATION_PROMPT = (
    "You are a senior data analyst reviewing rows an anomaly-detection model "
    "(IsolationForest, unsupervised) flagged as statistical outliers. Below is a "
    "summary of what was flagged and why. Write a 2-4 sentence plain-English "
    "narration for a non-technical stakeholder: describe what stands out about "
    "the flagged rows, then end with exactly ONE concrete suggested next action "
    "(e.g. verify against the source system, exclude before modeling, or "
    "investigate a specific column). Do not list every row individually — "
    "synthesize the pattern.\n\n{summary}"
)


def format_anomalies_text(flagged: Optional[pd.DataFrame], max_rows: int = MAX_REASONS_IN_PROMPT) -> str:
    """Compact text summary of a flagged-anomaly set, for use as Gemini
    narration input. Deliberately caps at max_rows distinct reasons so a
    large flagged set doesn't blow up the prompt's token count — mirrors
    modules.auto_insights.format_insights_text.
    """
    if flagged is None or flagged.empty:
        return "No anomalies were flagged."

    total = len(flagged)
    lines = [f"{total} row(s) flagged as anomalies out of the dataset."]
    if "anomaly_reason" in flagged.columns:
        reason_counts = flagged["anomaly_reason"].value_counts().head(max_rows)
        if not reason_counts.empty:
            lines.append("Most common reasons:")
            for reason, count in reason_counts.items():
                lines.append(f"- {reason} ({count} row(s))")
    return "\n".join(lines)


def narrate_anomalies(model, flagged: Optional[pd.DataFrame]) -> tuple[str, Optional[str]]:
    """Ask Gemini to narrate a flagged-anomaly set in plain English with one
    suggested next action.

    Returns (narration, error) — same shape and same non-blocking failure
    mode as auto_insights.narrate_insights: a missing model or a Gemini
    error never raises, it just surfaces as `error` for the caller to show
    alongside the (still fully usable) flagged-rows table. An empty flagged
    set short-circuits before ever calling Gemini — nothing to narrate, and
    no reason to spend a free-tier request on it.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if flagged is None or flagged.empty:
        return "No anomalies were flagged in this pass — nothing to narrate.", None

    from modules.ai_analyst import call_gemini

    prompt = _NARRATION_PROMPT.format(summary=format_anomalies_text(flagged))
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
