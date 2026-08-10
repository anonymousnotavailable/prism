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


# ---------------------------------------------------------------------------
# Anomaly narration — an agentic upgrade on top of the templated reasons
# above: ask Gemini to explain the flagged set in plain English and suggest
# a concrete next action. Deterministic and free when there's nothing to
# narrate (no Gemini call for an empty result), and callers are expected to
# cache the result per `anomaly_fingerprint()` so re-rendering the page
# doesn't re-spend a free-tier request on an unchanged detection run.
# ---------------------------------------------------------------------------

_NARRATION_PROMPT = (
    "You are a senior data analyst. Below is a summary of rows an anomaly-detection model "
    "flagged as unusual. In 2-4 sentences, explain in plain English what these anomalies "
    "likely mean for this dataset, and suggest ONE concrete next action (e.g. investigate a "
    "specific column, exclude the rows, or treat them as a valid rare segment). Be specific "
    "to the reasons given, not generic. Write in second person ('your data').\n\n{summary}"
)


def format_anomalies_text(flagged_df: Optional[pd.DataFrame], total_rows: int) -> str:
    """Compact plain-text summary of flagged anomalies, for a Gemini prompt.

    Also used directly by the UI as a fallback description when Gemini isn't
    available.
    """
    if flagged_df is None or flagged_df.empty:
        return "No anomalies were flagged."

    pct = 100 * len(flagged_df) / total_rows if total_rows else 0.0
    lines = [f"{len(flagged_df)} of {total_rows} rows ({pct:.1f}%) were flagged as anomalous by IsolationForest."]
    if "anomaly_reason" in flagged_df.columns:
        reason_counts = flagged_df["anomaly_reason"].value_counts().head(5)
        lines.append("Most common reasons:")
        for reason, count in reason_counts.items():
            lines.append(f"- ({count}x) {reason}")
    return "\n".join(lines)


def narrate_anomalies(model, flagged_df: Optional[pd.DataFrame], total_rows: int) -> tuple[str, Optional[str]]:
    """Ask Gemini to narrate the flagged anomalies in plain English with a
    suggested next action.

    Returns (narration, error). Short-circuits without a Gemini call when
    there's no result yet or nothing was flagged.
    """
    if flagged_df is None:
        return "", "No anomaly results to narrate yet — run detection first."
    if flagged_df.empty:
        return "No anomalies were flagged, so there's nothing to investigate.", None
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    prompt = _NARRATION_PROMPT.format(summary=format_anomalies_text(flagged_df, total_rows))
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None


def anomaly_fingerprint(flagged_df: Optional[pd.DataFrame]) -> str:
    """Stable fingerprint for a flagged-anomaly result set.

    Callers cache narration keyed on this so switching tabs / Streamlit
    reruns doesn't re-spend a Gemini call on an unchanged detection result —
    only a fresh "Find Anomalies" click (which changes the flagged index or
    empties it) invalidates the cache.
    """
    if flagged_df is None or flagged_df.empty:
        return "empty"
    return f"{len(flagged_df)}:{hash(tuple(flagged_df.index.tolist()))}"
