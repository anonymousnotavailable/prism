"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged row.

Also includes an optional Gemini narration layer (`narrate_anomalies`) that
turns the aggregated flagged-row reasons into a short, stakeholder-readable
paragraph with a suggested next action — the deterministic detect/reason
step above never changes; only the final language is delegated to the LLM,
and only ever from aggregated reason strings (never raw row values), so the
narration path is PII-safe by construction. Callers should cache the result
keyed by `anomaly_fingerprint()` to avoid re-calling Gemini on an unchanged
flagged set (e.g. across Streamlit reruns).
"""

from __future__ import annotations

import hashlib
from collections import Counter
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


# ---------------------------------------------------------------------------
# Narration layer — deterministic aggregation + optional Gemini narration.
# ---------------------------------------------------------------------------

def _driving_column(reason: str) -> Optional[str]:
    """Pull the column name back out of a `_reason_for_row` string, or None
    for the "unusual combination" fallback (no single driving column).
    """
    if " is " not in reason or "column median" not in reason:
        return None
    return reason.split(" is ", 1)[0]


def summarize_flagged(flagged_df: pd.DataFrame) -> dict:
    """Aggregate a flagged-rows frame into counts, never raw values —
    this summary is what gets sent to Gemini for narration, so it must
    never carry actual cell contents (PII-safety by construction).
    """
    if flagged_df is None or flagged_df.empty or "anomaly_reason" not in flagged_df.columns:
        return {"n_flagged": 0, "top_columns": []}

    counter: Counter[str] = Counter()
    for reason in flagged_df["anomaly_reason"]:
        col = _driving_column(reason)
        if col:
            counter[col] += 1

    return {"n_flagged": len(flagged_df), "top_columns": counter.most_common()}


def anomaly_fingerprint(flagged_df: pd.DataFrame, total_rows: int) -> str:
    """Deterministic fingerprint of a flagged-rows result, for caching a
    Gemini narration across Streamlit reruns without re-calling the API
    when nothing about the flagged set has changed.
    """
    if flagged_df is None or flagged_df.empty or "anomaly_reason" not in flagged_df.columns:
        reasons: tuple = ()
        n_flagged = 0
    else:
        reasons = tuple(sorted(flagged_df["anomaly_reason"].astype(str)))
        n_flagged = len(flagged_df)

    payload = f"{total_rows}|{n_flagged}|{reasons}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


_NARRATION_PROMPT = (
    "You are a senior data analyst explaining an automated anomaly scan to a "
    "non-technical stakeholder. {n_flagged} out of {total_rows} rows ({pct}%) "
    "were flagged as statistically unusual by an IsolationForest model. The "
    "column(s) most often responsible for a flag, in order: {top_columns_text}. "
    "In 2-3 sentences, explain in plain English what kind of rows are being "
    "flagged and suggest one concrete next action (manual review, exclude "
    "from analysis, or investigate a possible data-entry issue). Do not "
    "invent specific values you were not given."
)


def narrate_anomalies(model, flagged_df: pd.DataFrame, total_rows: int) -> tuple[str, Optional[str]]:
    """Ask Gemini to narrate the flagged-row summary into plain English with
    a suggested next action. Returns (narration, error).

    Never sends raw row values — only the aggregated reason-column counts
    from `summarize_flagged`. Short-circuits (no Gemini call at all) when
    nothing was flagged, since that case needs no LLM to describe.
    """
    summary = summarize_flagged(flagged_df)
    if summary["n_flagged"] == 0:
        return "No anomalies were flagged — this data looks clean.", None

    if model is None:
        return "", "No Gemini model available for anomaly narration."

    top_columns_text = ", ".join(
        f"{col} ({count} row{'s' if count != 1 else ''})" for col, count in summary["top_columns"][:5]
    ) or "no single dominant column"
    pct = round(100 * summary["n_flagged"] / total_rows, 1) if total_rows else 0.0

    prompt = _NARRATION_PROMPT.format(
        n_flagged=summary["n_flagged"], total_rows=total_rows, pct=pct, top_columns_text=top_columns_text
    )

    from modules import ai_analyst

    text, error = ai_analyst.call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
