"""
Anomaly Detection — flags unusual rows via three independent scikit-learn
detectors (IsolationForest, Local Outlier Factor, DBSCAN) over the dataset's
numeric columns, with a plain-English reason per flagged row.

Three algorithms rather than one because each catches a different failure
mode: IsolationForest is fast and handles high dimensions well but assumes
a global contamination rate; LOF catches *local* density anomalies (a point
that's normal globally but unusual within its neighborhood) that IsolationForest
can miss; DBSCAN needs no contamination assumption at all — it just marks
whatever doesn't fit in a dense region as noise. `run_ensemble_detection()`
runs all three and ranks rows by how many methods agree, which is a much
stronger anomaly signal than any single method's raw output — a row flagged
by all three is far more likely to be a genuine data-quality problem than
one flagged by a single sensitive detector.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler
except ImportError:  # the app should still load even if the package isn't installed yet
    IsolationForest = None
    LocalOutlierFactor = None
    NearestNeighbors = None
    DBSCAN = None
    StandardScaler = None

MIN_ROWS_REQUIRED = 10
_NOT_INSTALLED_ERROR = "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."


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


def _prepare_numeric(df: pd.DataFrame, column_types: dict[str, str]) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Shared validation + cleanup for every detector below.

    Returns (numeric_df, error). numeric_df has NaNs filled with the column
    median (detectors can't handle NaNs) and all-empty columns dropped; the
    caller still indexes back into the original `df` for the returned rows,
    so original values (including NaNs) are never lost.
    """
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    if not numeric_cols:
        return None, "No numeric columns available for anomaly detection."

    if len(df) < MIN_ROWS_REQUIRED:
        return None, f"Not enough rows to reliably detect anomalies (need at least {MIN_ROWS_REQUIRED})."

    numeric_df = df[numeric_cols].copy()
    numeric_df = numeric_df.fillna(numeric_df.median(numeric_only=True))
    numeric_df = numeric_df.dropna(axis=1, how="all")
    if numeric_df.shape[1] == 0:
        return None, "All numeric columns are entirely empty — nothing to analyze."
    return numeric_df, None


def _flag_rows(df: pd.DataFrame, numeric_df: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    """Turn a -1/1 (or -1/cluster-id) prediction array into a flagged-rows frame
    with a plain-English 'anomaly_reason' column. Always returns a DataFrame
    (possibly empty) — "nothing flagged" is a valid result, not an error.
    """
    flagged_idx = df.index[predictions == -1]
    if len(flagged_idx) == 0:
        return df.iloc[0:0].copy()

    medians = numeric_df.median()
    flagged = df.loc[flagged_idx].copy()
    flagged["anomaly_reason"] = [
        _reason_for_row(numeric_df.loc[idx], list(numeric_df.columns), medians) for idx in flagged_idx
    ]
    return flagged


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
        return None, _NOT_INSTALLED_ERROR

    numeric_df, error = _prepare_numeric(df, column_types)
    if error:
        return None, error

    model = IsolationForest(contamination=contamination, random_state=42)
    predictions = model.fit_predict(numeric_df)  # -1 = anomaly, 1 = normal
    return _flag_rows(df, numeric_df, predictions), None


def find_anomalies_lof(
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = 0.05
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run Local Outlier Factor over numeric columns — catches points that are
    unusual relative to their *local* neighborhood density, which a global
    detector like IsolationForest can miss (e.g. a moderate value that's
    normal for the dataset overall but out of place within its cluster).
    """
    if LocalOutlierFactor is None:
        return None, _NOT_INSTALLED_ERROR

    numeric_df, error = _prepare_numeric(df, column_types)
    if error:
        return None, error

    n_neighbors = max(1, min(20, len(numeric_df) - 1))
    model = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    predictions = model.fit_predict(numeric_df)  # -1 = anomaly, 1 = normal
    return _flag_rows(df, numeric_df, predictions), None


def _estimate_dbscan_eps(scaled: np.ndarray, min_samples: int) -> float:
    """Heuristic eps for DBSCAN: the 90th percentile of each point's distance
    to its k-th nearest neighbor (k = min_samples), the standard "k-distance
    elbow" approach. Returns 0.0 for degenerate inputs (e.g. every row
    identical after scaling) so the caller can treat that as "no anomalies"
    instead of dividing by zero or picking an arbitrary eps.
    """
    n = scaled.shape[0]
    k = min(min_samples, n - 1)
    if k < 1:
        return 0.0
    neighbors = NearestNeighbors(n_neighbors=k + 1)  # +1: a point is its own nearest neighbor
    neighbors.fit(scaled)
    distances, _ = neighbors.kneighbors(scaled)
    kth_distances = distances[:, -1]
    finite = kth_distances[np.isfinite(kth_distances)]
    if finite.size == 0:
        return 0.0
    return float(np.percentile(finite, 90))


def find_anomalies_dbscan(
    df: pd.DataFrame, column_types: dict[str, str]
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run DBSCAN over standardized numeric columns — flags points density-based
    clustering can't assign to any dense region ("noise") as anomalies. Unlike
    IsolationForest/LOF, this needs no contamination assumption: it's a pure
    function of how dense the data actually is.
    """
    if DBSCAN is None or NearestNeighbors is None or StandardScaler is None:
        return None, _NOT_INSTALLED_ERROR

    numeric_df, error = _prepare_numeric(df, column_types)
    if error:
        return None, error

    scaled = StandardScaler().fit_transform(numeric_df)
    min_samples = max(2, min(5, len(numeric_df) // 5))
    eps = _estimate_dbscan_eps(scaled, min_samples)
    if eps <= 0:
        # Every row is identical (or near-identical) after scaling — DBSCAN has
        # no basis to call anything "noise", so there's nothing to flag.
        return df.iloc[0:0].copy(), None

    model = DBSCAN(eps=eps, min_samples=min_samples)
    predictions = model.fit_predict(scaled)  # -1 = noise (anomaly), >=0 = cluster id
    return _flag_rows(df, numeric_df, predictions), None


def run_ensemble_detection(
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = 0.05
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run all three detectors and rank flagged rows by how many agree.

    Returns (result_df, error). result_df has one row per row flagged by at
    least one method, columns 'isolation_forest'/'lof'/'dbscan' (bool),
    'agreement_count' (0-3), and 'anomaly_reason', sorted by agreement_count
    descending — the rows most likely to be genuine problems (flagged by all
    three independent methods) surface first.
    """
    if not is_available():
        return None, _NOT_INSTALLED_ERROR

    numeric_df, error = _prepare_numeric(df, column_types)
    if error:
        return None, error

    if_flagged, if_error = find_anomalies(df, column_types, contamination=contamination)
    lof_flagged, lof_error = find_anomalies_lof(df, column_types, contamination=contamination)
    dbscan_flagged, dbscan_error = find_anomalies_dbscan(df, column_types)
    first_error = if_error or lof_error or dbscan_error
    if first_error:
        return None, first_error

    flags = pd.DataFrame(index=df.index)
    flags["isolation_forest"] = df.index.isin(if_flagged.index)
    flags["lof"] = df.index.isin(lof_flagged.index)
    flags["dbscan"] = df.index.isin(dbscan_flagged.index)
    flags["agreement_count"] = flags[["isolation_forest", "lof", "dbscan"]].sum(axis=1)

    flagged_idx = flags.index[flags["agreement_count"] > 0]
    if len(flagged_idx) == 0:
        return df.iloc[0:0].copy(), None

    medians = numeric_df.median()
    result = df.loc[flagged_idx].copy()
    for col in ("isolation_forest", "lof", "dbscan", "agreement_count"):
        result[col] = flags.loc[flagged_idx, col]
    result["anomaly_reason"] = [
        _reason_for_row(numeric_df.loc[idx], list(numeric_df.columns), medians) for idx in flagged_idx
    ]
    return result.sort_values("agreement_count", ascending=False), None


# ── Gemini narration ─────────────────────────────────────────────────────────

_ANOMALY_NARRATION_PROMPT = (
    "You are a senior data analyst explaining an automated ensemble anomaly scan "
    "(IsolationForest + Local Outlier Factor + DBSCAN) to a non-technical stakeholder. "
    "Below are the rows flagged by at least one method, ranked by how many of the three "
    "independent methods agreed. Write a 3-4 sentence plain-English summary of what these "
    "anomalies have in common, how severe they look, and what to do next. Do not list every "
    "row — synthesize the pattern.\n\n"
    "Flagged rows:\n{summary_text}"
)


def _format_ensemble_text(result: pd.DataFrame, top_n: int = 15) -> str:
    lines = []
    for i, (idx, row) in enumerate(result.head(top_n).iterrows(), 1):
        lines.append(f"{i}. row {idx} — agreement {int(row['agreement_count'])}/3 — {row['anomaly_reason']}")
    remaining = len(result) - min(top_n, len(result))
    if remaining > 0:
        lines.append(f"...and {remaining} more row(s) flagged.")
    return "\n".join(lines)


def narrate_anomalies(model, result: Optional[pd.DataFrame]) -> tuple[str, Optional[str]]:
    """Ask Gemini to summarize the ensemble result in plain English.

    Returns (narration, error). Short-circuits (no Gemini call) when there's
    nothing to narrate. Falls back gracefully if Gemini is unavailable —
    matches the rate-limit/quota/auth handling already shared by every other
    Gemini call in the app via `ai_analyst.call_gemini`.
    """
    if result is None or result.empty:
        return "No anomalies detected across any method — this dataset looks clean.", None
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    summary_text = _format_ensemble_text(result)
    prompt = _ANOMALY_NARRATION_PROMPT.format(summary_text=summary_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
