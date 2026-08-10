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


# ==========================================================================
# Anomaly Narration — agentic layer on top of the flagging above. Gemini
# turns the flagged rows + their deterministic reasons into a short
# plain-English narrative with a suggested next action. The evidence
# (flagged rows, reasons) is always computed by find_anomalies() above,
# never by the model — this function only narrates evidence that already
# exists, the same "structured evidence -> narration" split the rest of
# Prism's agentic features (Auto-Insight Engine, Insight Verifier) use.
# ==========================================================================

_NARRATION_PROMPT = (
    "You are a senior data analyst. Below is a list of rows an anomaly-detection "
    "model (IsolationForest) flagged as unusual, each with the deterministic reason "
    "it was flagged. Write a short 2-4 sentence narrative for a stakeholder: "
    "summarize what kind of rows stand out and why, then suggest ONE concrete next "
    "action (e.g. investigate a specific column, exclude the rows, or check for a "
    "data-entry error). Do not invent numbers not present below. Write in second "
    "person ('your data').\n\n"
    "{n_flagged} row(s) flagged:\n{reasons_text}"
)

MAX_REASONS_IN_PROMPT = 20


def anomaly_fingerprint(flagged_df: pd.DataFrame) -> str:
    """A short deterministic hash of a flagged-rows result, used to cache
    narration in st.session_state so re-rendering the same result (or a
    user re-clicking the same button) never triggers a second Gemini call
    for identical input — keeps repeat use inside the free-tier rate limit.
    """
    if flagged_df is None or flagged_df.empty:
        basis = "empty"
    else:
        reasons = flagged_df["anomaly_reason"].astype(str).tolist() if "anomaly_reason" in flagged_df.columns else []
        basis = f"{len(flagged_df)}|" + "|".join(sorted(reasons))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def narrate_anomalies(model, flagged_df: pd.DataFrame) -> tuple[str, Optional[str]]:
    """Ask Gemini to narrate an already-computed anomaly result.

    Returns (narration, error). Callers should cache the result keyed by
    anomaly_fingerprint(flagged_df) and only call this once per distinct
    flagged set (see app.py's Anomaly Detection panel).
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if flagged_df is None or flagged_df.empty:
        return "Your data looks clean — no anomalies were flagged.", None

    from modules.ai_analyst import call_gemini

    reasons = flagged_df["anomaly_reason"].astype(str).tolist() if "anomaly_reason" in flagged_df.columns else []
    reasons_text = "\n".join(f"- {r}" for r in reasons[:MAX_REASONS_IN_PROMPT])
    if len(reasons) > MAX_REASONS_IN_PROMPT:
        reasons_text += f"\n- ...and {len(reasons) - MAX_REASONS_IN_PROMPT} more."

    prompt = _NARRATION_PROMPT.format(n_flagged=len(flagged_df), reasons_text=reasons_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
