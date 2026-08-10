"""
Anomaly Detection — flags unusual rows over the dataset's numeric columns via
a selectable scikit-learn method (tree-based Isolation Forest or density-based
Local Outlier Factor), with a plain-English reason per flagged row and an
optional Gemini narration pass that explains the flagged set in plain English.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
except ImportError:  # the app should still load even if the package isn't installed yet
    IsolationForest = None

try:
    from sklearn.neighbors import LocalOutlierFactor
except ImportError:
    LocalOutlierFactor = None

MIN_ROWS_REQUIRED = 10

# Detection methods, keyed by the value used everywhere else in the app
# (find_anomalies' `method` arg, session state, the UI selectbox).
METHODS = {
    "isolation_forest": "Isolation Forest (tree-based, fast, good default)",
    "lof": "Local Outlier Factor (density-based, flags local outliers a global method misses)",
}


def is_available() -> bool:
    """Whether scikit-learn's IsolationForest is installed."""
    return IsolationForest is not None


def lof_available() -> bool:
    """Whether scikit-learn's LocalOutlierFactor is installed."""
    return LocalOutlierFactor is not None


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


def _build_model(method: str, contamination: float, n_rows: int):
    """Instantiate the requested detector. Returns (model, error)."""
    if method == "isolation_forest":
        if IsolationForest is None:
            return None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."
        return IsolationForest(contamination=contamination, random_state=42), None

    if method == "lof":
        if LocalOutlierFactor is None:
            return None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."
        # LOF requires n_neighbors < n_samples; the sklearn default (20) breaks
        # on small datasets, so cap it to what the data actually supports.
        n_neighbors = max(1, min(20, n_rows - 1))
        return LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination), None

    return None, f"Unknown detection method: '{method}'. Choose one of: {', '.join(METHODS)}."


def find_anomalies(
    df: pd.DataFrame,
    column_types: dict[str, str],
    contamination: float = 0.05,
    method: str = "isolation_forest",
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Flag unusual rows over numeric columns and return them with reasons.

    `method` selects the detector: "isolation_forest" (tree-based, the
    default) or "lof" (Local Outlier Factor, density-based — catches local
    outliers that look normal against the global distribution but stand out
    against their nearest neighbors).

    Returns (flagged_df, error). flagged_df carries an added 'anomaly_reason'
    column and may be empty (0 rows) if nothing was flagged — that's a valid
    "no anomalies found" result, not an error. error is set only when
    detection couldn't run at all (no numeric columns, missing dependency,
    unknown method, or too few rows).
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    if not numeric_cols:
        return None, "No numeric columns available for anomaly detection."

    if len(df) < MIN_ROWS_REQUIRED:
        return None, f"Not enough rows to reliably detect anomalies (need at least {MIN_ROWS_REQUIRED})."

    numeric_df = df[numeric_cols].copy()
    # Neither detector handles NaNs — fill with the column median for
    # detection purposes only; the returned rows still carry their original values.
    numeric_df = numeric_df.fillna(numeric_df.median(numeric_only=True))
    numeric_df = numeric_df.dropna(axis=1, how="all")
    if numeric_df.shape[1] == 0:
        return None, "All numeric columns are entirely empty — nothing to analyze."

    model, build_error = _build_model(method, contamination, len(numeric_df))
    if build_error:
        return None, build_error

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


# --------------------------------------------------------------------------
# Gemini narration — turns the already-flagged rows into a plain-English
# explanation + suggested next action. Mirrors modules.auto_insights.
# narrate_insights: same call_gemini() shared rate limiter, same graceful
# no-model/empty-result short-circuit, no extra Gemini call surface.
# --------------------------------------------------------------------------

_ANOMALY_NARRATION_PROMPT = (
    "You are a senior data analyst explaining anomaly-detection results to a "
    "colleague who isn't a statistician. A {method} model flagged {n} unusual "
    "row(s) in this dataset. Here are the reasons each row was flagged:\n\n"
    "{reasons_text}\n\n"
    "In 3-5 sentences: (1) describe the common pattern among these anomalies in "
    "plain English, (2) suggest one plausible real-world cause (data entry error, "
    "genuine rare event, a different population/segment, etc.), and (3) recommend "
    "one concrete next step (investigate further, exclude from analysis, verify "
    "against source data). Do not invent numbers not shown above."
)


def narrate_anomalies(
    model, flagged_df: Optional[pd.DataFrame], method: str = "isolation_forest"
) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain the flagged anomalous rows in plain English.

    Returns (narration, error). Falls back gracefully if Gemini is
    unavailable, and short-circuits (no Gemini call) when there's nothing to
    narrate — an empty/None flagged_df is a valid "no anomalies" state.
    """
    if flagged_df is None or flagged_df.empty:
        return "No anomalies were flagged — nothing to narrate.", None
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    reasons = flagged_df["anomaly_reason"] if "anomaly_reason" in flagged_df.columns else []
    reasons_text = "\n".join(f"- {r}" for r in reasons[:15]) or "- (no per-row reason available)"
    prompt = _ANOMALY_NARRATION_PROMPT.format(
        method=METHODS.get(method, method), n=len(flagged_df), reasons_text=reasons_text
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
