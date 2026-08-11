"""
Anomaly Detection — flags unusual rows via scikit-learn's IsolationForest
over the dataset's numeric columns, with a plain-English reason per flagged row.
"""

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.cluster import DBSCAN
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler
except ImportError:  # the app should still load even if the package isn't installed yet
    IsolationForest = None
    DBSCAN = None
    LocalOutlierFactor = None
    StandardScaler = None

MIN_ROWS_REQUIRED = 10

# SHAP TreeExplainer attribution upgrades the naive single-feature reason
# below into real multi-feature ranking, but it costs one explainer pass per
# flagged row — bounded so a dataset with a huge flagged set (large N,
# generous contamination) can't turn a detection click into a multi-second
# hang. Above the cap, find_anomalies() silently keeps the naive reason
# rather than partially explaining an arbitrary subset.
SHAP_MAX_ROWS_TO_EXPLAIN = 300

# Multi-method ensemble — three detectors with genuinely different
# assumptions, so a row every method agrees on is a much stronger signal
# than any single model's opinion:
#   isolation_forest — global isolation via random recursive splits (same
#                       model as find_anomalies() above)
#   lof               — local density: flags points whose neighborhood is
#                       much sparser than their neighbors' neighborhoods,
#                       catching local outliers a global method can miss
#   dbscan            — density-based clustering: anything that doesn't
#                       fall in any dense cluster (label -1) is an outlier
# Needs more rows than the single-method detector above (LOF/DBSCAN need
# enough neighbors to estimate local density meaningfully) and needs at
# least two numeric columns (a distance/density notion on a single axis
# degenerates to "how far from the median", which IsolationForest already
# covers on its own).
ENSEMBLE_METHODS = ("isolation_forest", "lof", "dbscan")
ENSEMBLE_MIN_ROWS = 20


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


def shap_is_available() -> bool:
    """Whether the `shap` package can be imported. Checked lazily (not at
    module import time) since it's a heavier optional dependency than
    scikit-learn — anomaly detection itself must keep working without it.
    """
    try:
        import shap  # noqa: F401
    except ImportError:
        return False
    return True


def _shap_matrix_for_rows(model, numeric_df: pd.DataFrame) -> Optional["np.ndarray"]:
    """Per-feature SHAP attribution for every row in numeric_df, using
    shap's TreeExplainer against the fitted IsolationForest.

    Returns an (n_rows, n_features) array, or None if shap isn't installed
    or the explanation fails for any reason (version mismatch, degenerate
    input, ...) — this is a best-effort enrichment, never a hard dependency,
    so any failure here must fall back to the naive median-ratio reason
    rather than propagate.
    """
    try:
        import shap

        explainer = shap.TreeExplainer(model)
        values = explainer.shap_values(numeric_df)
        values = np.asarray(values)
        if values.ndim != 2 or values.shape != (len(numeric_df), numeric_df.shape[1]):
            return None
        return values
    except Exception:
        return None


def _shap_reason_and_drivers(
    shap_row: "np.ndarray", columns: list[str], row: pd.Series, medians: pd.Series, top_k: int = 3
) -> tuple[str, list[dict]]:
    """Turn one row's SHAP vector into (reason string, ranked driver list).

    Ranks features by |SHAP value| — how much each one actually pushed this
    row's anomaly score, not just which is numerically furthest from the
    median (the naive heuristic conflates "far from median" with "why the
    model flagged it," which are the same thing only when a single feature
    dominates). Direction (above/below median) is still reported the same
    way as the naive reason for readability.
    """
    order = np.argsort(-np.abs(shap_row))[:top_k]
    drivers: list[dict] = []
    parts: list[str] = []
    for i in order:
        col = columns[i]
        value, median = row[col], medians[col]
        shap_abs = float(abs(shap_row[i]))
        if pd.isna(value) or pd.isna(median) or median == 0:
            direction = "unusual"
            parts.append(f"{col} (unusual value)")
        else:
            direction = "above" if value > median else "below"
            ratio = abs(value / median)
            parts.append(f"{col} is {ratio:.1f}x {direction} median")
        drivers.append({"feature": col, "shap_abs": shap_abs, "direction": direction})
    reason = "; ".join(parts) if parts else "Unusual combination of values across numeric columns."
    return reason, drivers


def find_anomalies(
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = 0.05
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Run IsolationForest over numeric columns and return flagged rows with reasons.

    Returns (flagged_df, error). flagged_df carries an added 'anomaly_reason'
    column and may be empty (0 rows) if nothing was flagged — that's a valid
    "no anomalies found" result, not an error. error is set only when
    detection couldn't run at all (no numeric columns, missing dependency,
    or too few rows).

    When `shap` is installed and the flagged set is within
    SHAP_MAX_ROWS_TO_EXPLAIN, 'anomaly_reason' is upgraded from a naive
    single-feature heuristic to real multi-feature SHAP attribution, and an
    'anomaly_top_drivers' column is added (ranked [{feature, shap_abs,
    direction}, ...] per row) for the aggregate driver chart. Falls back to
    the naive reason with no extra column when shap is unavailable, the
    flagged set is too large, or the explanation fails for any reason.
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
    columns = list(numeric_df.columns)
    flagged = df.loc[flagged_idx].copy()
    flagged["anomaly_reason"] = [
        _reason_for_row(numeric_df.loc[idx], columns, medians) for idx in flagged_idx
    ]

    if len(flagged_idx) <= SHAP_MAX_ROWS_TO_EXPLAIN:
        shap_matrix = _shap_matrix_for_rows(model, numeric_df.loc[flagged_idx])
        if shap_matrix is not None:
            reasons, drivers_col = [], []
            for pos, idx in enumerate(flagged_idx):
                reason, drivers = _shap_reason_and_drivers(
                    shap_matrix[pos], columns, numeric_df.loc[idx], medians
                )
                reasons.append(reason)
                drivers_col.append(drivers)
            flagged["anomaly_reason"] = reasons
            flagged["anomaly_top_drivers"] = drivers_col

    return flagged, None


def aggregate_top_drivers(flagged: Optional[pd.DataFrame], top_n: int = 8) -> list[dict]:
    """Roll up per-row SHAP driver lists (from `find_anomalies`'s
    'anomaly_top_drivers' column) into "which features drive anomalies
    across this whole flagged set" — how many rows named this feature as a
    top driver, and its average |SHAP value| when it did.

    Returns [] if the column is missing (SHAP enrichment wasn't available
    for this result) rather than raising — the aggregate chart is optional
    polish, not a hard requirement of anomaly detection.
    """
    if flagged is None or "anomaly_top_drivers" not in flagged.columns:
        return []

    counts: dict[str, int] = {}
    magnitude_sums: dict[str, float] = {}
    for drivers in flagged["anomaly_top_drivers"]:
        if not isinstance(drivers, list) or not drivers:
            continue
        top = drivers[0]  # each row's single strongest driver
        feature = top["feature"]
        counts[feature] = counts.get(feature, 0) + 1
        magnitude_sums[feature] = magnitude_sums.get(feature, 0.0) + top["shap_abs"]

    rows = [
        {"feature": feature, "count": count, "avg_abs_shap": magnitude_sums[feature] / count}
        for feature, count in counts.items()
    ]
    rows.sort(key=lambda r: (r["count"], r["avg_abs_shap"]), reverse=True)
    return rows[:top_n]


def build_driver_chart(agg_drivers: list[dict]):
    """Horizontal bar chart: how often each feature was a flagged row's
    top SHAP driver. None when there's nothing to show — callers should
    skip rendering the chart entirely rather than showing an empty plot.
    """
    if not agg_drivers:
        return None

    import plotly.express as px

    ordered = sorted(agg_drivers, key=lambda r: r["count"])
    fig = px.bar(
        x=[r["count"] for r in ordered],
        y=[r["feature"] for r in ordered],
        orientation="h",
        labels={"x": "Rows where this was the top driver", "y": "Feature"},
        title="Anomaly Detection — top contributing features (SHAP)",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


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


def _dbscan_eps(scaled: "np.ndarray", min_samples: int) -> float:
    """Heuristic eps for DBSCAN: the 90th percentile of each point's
    distance to its min_samples-th nearest neighbor (a simplified k-distance
    "elbow" — the full elbow-plot method needs a human eyeballing a curve,
    which has no place in an unattended pipeline call).
    """
    from sklearn.neighbors import NearestNeighbors

    n_neighbors = min(min_samples + 1, len(scaled))  # +1: a point is its own nearest neighbor
    nn = NearestNeighbors(n_neighbors=n_neighbors).fit(scaled)
    distances, _ = nn.kneighbors(scaled)
    kth_distances = distances[:, -1]
    eps = float(np.percentile(kth_distances, 90))
    return eps if eps > 0 else 0.5


def find_anomalies_ensemble(
    df: pd.DataFrame, column_types: dict[str, str], contamination: float = 0.05
) -> tuple[Optional[pd.DataFrame], Optional[dict], Optional[str]]:
    """Run three anomaly detectors with different assumptions (see
    ENSEMBLE_METHODS above) over the same numeric columns and return their
    consensus — the self-verifying-agent pattern applied to anomaly
    detection: instead of trusting one model's opinion, cross-check it
    against others built on different assumptions and surface how much
    they agree.

    Returns (consensus_df, methods_summary, error):
      consensus_df — union of every row flagged by at least one method,
        with 'consensus_count' (how many of the 3 methods flagged it,
        1-3) and 'anomaly_reason' (which methods + the largest numeric
        deviation, reusing _reason_for_row's logic), sorted by
        consensus_count descending. May be empty (valid "nothing flagged
        by any method" result).
      methods_summary — {method: {"flagged_count": int, "pct": float}}
        per-method counts, for the UI to show e.g. "LOF flagged 8 (13%),
        DBSCAN flagged 3 (5%)".
      error — set only when detection couldn't run at all.
    """
    if IsolationForest is None or DBSCAN is None or LocalOutlierFactor is None:
        return None, None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."

    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    if len(numeric_cols) < 2:
        return None, None, "Ensemble mode needs at least 2 numeric columns (LOF/DBSCAN rely on distance between them)."

    if len(df) < ENSEMBLE_MIN_ROWS:
        return None, None, f"Not enough rows for the ensemble detector (need at least {ENSEMBLE_MIN_ROWS})."

    numeric_df = df[numeric_cols].copy()
    numeric_df = numeric_df.fillna(numeric_df.median(numeric_only=True))
    numeric_df = numeric_df.dropna(axis=1, how="all")
    if numeric_df.shape[1] < 2:
        return None, None, "Fewer than 2 usable numeric columns after dropping fully-empty ones."

    scaled = StandardScaler().fit_transform(numeric_df.values)
    n = len(numeric_df)
    min_samples = max(5, round(0.02 * n))

    flags: dict[str, "np.ndarray"] = {}

    iso = IsolationForest(contamination=contamination, random_state=42)
    flags["isolation_forest"] = iso.fit_predict(numeric_df) == -1

    lof = LocalOutlierFactor(n_neighbors=min(min_samples, n - 1), contamination=contamination)
    flags["lof"] = lof.fit_predict(scaled) == -1

    eps = _dbscan_eps(scaled, min_samples)
    dbscan_labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(scaled)
    flags["dbscan"] = dbscan_labels == -1

    methods_summary = {
        method: {"flagged_count": int(mask.sum()), "pct": round(100 * mask.sum() / n, 2)}
        for method, mask in flags.items()
    }

    consensus_count = np.zeros(n, dtype=int)
    for mask in flags.values():
        consensus_count += mask.astype(int)

    flagged_positions = np.where(consensus_count > 0)[0]
    if len(flagged_positions) == 0:
        return df.iloc[0:0].copy(), methods_summary, None

    medians = numeric_df.median()
    flagged_idx = numeric_df.index[flagged_positions]
    consensus = df.loc[flagged_idx].copy()
    consensus["consensus_count"] = consensus_count[flagged_positions]

    reasons = []
    for pos, idx in zip(flagged_positions, flagged_idx):
        flagged_by = [m for m, mask in flags.items() if mask[pos]]
        base_reason = _reason_for_row(numeric_df.loc[idx], list(numeric_df.columns), medians)
        method_label = ", ".join(m.replace("_", " ") for m in flagged_by)
        reasons.append(f"Flagged by {len(flagged_by)}/{len(ENSEMBLE_METHODS)} methods ({method_label}). {base_reason}")
    consensus["anomaly_reason"] = reasons

    consensus = consensus.sort_values("consensus_count", ascending=False)
    return consensus, methods_summary, None


_ENSEMBLE_NARRATION_PROMPT = (
    "You are a senior data analyst explaining a multi-method anomaly-detection result to a "
    "stakeholder who isn't technical. Three different anomaly detectors were run over the same "
    "data, each with different assumptions: Isolation Forest (global isolation via random "
    "splits), LOF/Local Outlier Factor (local density — flags points in sparser neighborhoods "
    "than their neighbors), and DBSCAN (density-based clustering — anything outside a dense "
    "cluster). Here's how many rows each method flagged, out of {n_rows} total rows:\n\n"
    "{summary_text}\n\n"
    "{agreement_text}\n\n"
    "In 3-4 sentences: explain in plain English what the level of agreement or disagreement "
    "between the methods suggests about the kind of anomalies present (e.g. a few extreme "
    "global outliers vs. local pockets of unusual density), and suggest one concrete next "
    "action. Do not simply restate the numbers back."
)


def narrate_ensemble_disagreement(model, consensus: Optional[pd.DataFrame], methods_summary: Optional[dict]) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain what the ensemble's agreement/disagreement
    pattern suggests — the interpretive step of the self-verifying-agent
    pattern: the detection itself stays deterministic and auditable
    (three independent sklearn models), Gemini's only job is turning
    "IsoForest flagged 12, LOF flagged 8, only 3 rows overlap" into an
    explanation a stakeholder can act on.

    Returns (narration, error). Callers should cache by
    fingerprint_flagged(consensus) same as narrate_anomalies().
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if consensus is None or consensus.empty or not methods_summary:
        return "No anomalies were flagged by any method — nothing to narrate.", None

    n_rows = len(consensus)
    summary_text = "\n".join(
        f"- {method.replace('_', ' ').title()}: {stats['flagged_count']} row(s) ({stats['pct']}%)"
        for method, stats in methods_summary.items()
    )
    full_agreement = int((consensus["consensus_count"] == len(ENSEMBLE_METHODS)).sum()) if "consensus_count" in consensus.columns else 0
    agreement_text = (
        f"{full_agreement} row(s) were flagged by all {len(ENSEMBLE_METHODS)} methods "
        f"(strong consensus); the rest were flagged by only 1-2 methods."
    )
    prompt = _ENSEMBLE_NARRATION_PROMPT.format(n_rows=n_rows, summary_text=summary_text, agreement_text=agreement_text)

    from modules.ai_analyst import call_gemini

    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
