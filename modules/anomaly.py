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


# ── Anomaly narration — agentic layer on top of the deterministic flags ────
# find_anomalies() above already explains *which* column drove each flag
# (via anomaly_reason). Narration turns that row-by-row table into a single
# plain-English paragraph: what pattern connects the flagged rows, and what
# to do about it. Mirrors modules.auto_insights.narrate_insights — same
# call_gemini() plumbing (shared rate limit, quota/safety error handling),
# same (text, error) contract, same "caller decides what to show on error"
# convention. A deterministic, non-LLM fallback covers the case where no
# key is configured or the call fails, so the feature still says *something*
# useful rather than just an error banner.

_NARRATION_PROMPT = (
    "You are a senior data analyst explaining an automated anomaly scan to a colleague. "
    "An IsolationForest model flagged {n_flagged} of {n_total} rows ({pct:.1f}%) as unusual. "
    "Below is, for each flagged row, which column deviated most from its median and by how "
    "much. Write 2-4 sentences: (1) name the pattern connecting the flags, if there is a "
    "shared driver column or direction, or say the flags look scattered/independent if not; "
    "(2) end with one concrete suggested next action (e.g. investigate a specific column, "
    "treat as genuine outliers worth a closer look, or check for a data-entry/unit error). "
    "Do not repeat the raw numbers back verbatim — synthesize.\n\n"
    "Flagged rows:\n{reasons_text}"
)


def _format_reasons_text(flagged_df: pd.DataFrame, max_rows: int = 25) -> str:
    """Render anomaly_reason values as a compact numbered list for the prompt.

    Capped at max_rows so a large flagged set (e.g. 5% of a 50K-row
    dataset = 2500 rows) doesn't blow the prompt token budget — the reason
    strings are usually highly repetitive across rows anyway.
    """
    reasons = flagged_df["anomaly_reason"].tolist()
    shown = reasons[:max_rows]
    lines = [f"{i}. {r}" for i, r in enumerate(shown, 1)]
    if len(reasons) > max_rows:
        lines.append(f"...and {len(reasons) - max_rows} more with similar reasons.")
    return "\n".join(lines)


def deterministic_narration(flagged_df: pd.DataFrame, n_total: int) -> str:
    """A template-based summary used when Gemini isn't available or fails.

    Picks the most common driver column out of each row's anomaly_reason
    (parsed back out of the "'{col}' is Nx above/below..." string produced
    by _reason_for_row) so the fallback is still specific, not just
    "some rows looked unusual."
    """
    if flagged_df is None or flagged_df.empty:
        return "No anomalies were flagged."

    n_flagged = len(flagged_df)
    pct = 100 * n_flagged / n_total if n_total else 0.0

    driver_counts: dict[str, int] = {}
    for reason in flagged_df["anomaly_reason"]:
        col = reason.split(" is ", 1)[0].strip("'") if " is " in reason else None
        if col:
            driver_counts[col] = driver_counts.get(col, 0) + 1

    if driver_counts:
        top_col, top_count = max(driver_counts.items(), key=lambda kv: kv[1])
        share = 100 * top_count / n_flagged
        if share >= 60:
            driver_sentence = (
                f"Most of these ({top_count}/{n_flagged}) are driven primarily by '{top_col}' — "
                f"worth checking that column for data-entry errors or a genuine unit/scale issue."
            )
        else:
            driver_sentence = (
                f"The flags are spread across several columns, most often '{top_col}' "
                f"({top_count}/{n_flagged}) — likely independent unusual rows rather than one shared cause."
            )
    else:
        driver_sentence = "No single driver column stood out."

    return (
        f"IsolationForest flagged {n_flagged} of {n_total} rows ({pct:.1f}%) as anomalous. "
        f"{driver_sentence} Suggested next step: review the flagged rows below before deciding "
        f"whether to exclude them or investigate further."
    )


def narrate_anomalies(model, flagged_df: pd.DataFrame, n_total: int) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn the flagged-rows table into a short plain-English narrative.

    Returns (narration, error) — same contract as auto_insights.narrate_insights.
    On any failure (no model, rate limit, quota, safety filter) the caller
    should fall back to deterministic_narration() rather than show a dead end.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if flagged_df is None or flagged_df.empty:
        return "No anomalies were flagged — nothing to narrate.", None
    if "anomaly_reason" not in flagged_df.columns:
        return "", "flagged_df is missing the 'anomaly_reason' column."

    from modules.ai_analyst import call_gemini

    n_flagged = len(flagged_df)
    pct = 100 * n_flagged / n_total if n_total else 0.0
    prompt = _NARRATION_PROMPT.format(
        n_flagged=n_flagged, n_total=n_total, pct=pct,
        reasons_text=_format_reasons_text(flagged_df),
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
