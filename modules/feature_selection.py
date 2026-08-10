"""
Feature Selection Engine — ranks candidate feature columns for a chosen
target using three methods with genuinely different assumptions, then
reports a consensus. Same self-verifying-ensemble idea as
anomaly.find_anomalies_ensemble(): no single method's opinion is trusted
alone, and a feature every method agrees matters is a much stronger
signal than any one method's score.

  mutual_info — nonparametric, captures any statistical dependency
                (linear or not) between a feature and the target
  l1          — a linear model (Lasso for regression, L1-penalized
                logistic regression for classification) whose
                regularization drives irrelevant coefficients toward
                zero; only linear relationships are visible to it
  rfe         — recursive feature elimination with a linear estimator,
                which ranks features by how much removing each one hurts
                the fitted model, capturing simple feature interactions
                the other two score independently

If one method's fit fails outright (small/degenerate data, a class with
too few members, etc.) the other methods still produce a result — a
demo-breaking crash is worse than a ranking built from two methods
instead of three, so failures are caught per-method and recorded in
`method_errors` rather than aborting the whole ranking.
"""

from __future__ import annotations

import hashlib
import math
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

try:
    from sklearn.feature_selection import RFE, mutual_info_classif, mutual_info_regression
    from sklearn.linear_model import Lasso, LogisticRegression
    from sklearn.preprocessing import OrdinalEncoder, StandardScaler
except ImportError:  # the app should still load even if the package isn't installed yet
    RFE = None
    mutual_info_classif = mutual_info_regression = None
    Lasso = LogisticRegression = None
    OrdinalEncoder = StandardScaler = None

MIN_ROWS_REQUIRED = 30
MIN_FEATURES_REQUIRED = 2
HIGH_CARDINALITY_THRESHOLD = 50  # id-like categorical columns carry no ranking signal and blow up ordinal encoding noise
TOP_K_DEFAULT = 5

METHODS = ("mutual_info", "l1", "rfe")


def is_available() -> bool:
    """Whether scikit-learn is installed."""
    return mutual_info_classif is not None


def _encode_column(series: pd.Series, ctype: str) -> Optional[pd.Series]:
    """Encode a single feature column to numeric for ranking purposes.
    Returns None if the column carries no usable signal (constant,
    entirely null, or too-high-cardinality categorical/text)."""
    if ctype == "numeric":
        col = series.astype(float)
        if col.notna().sum() == 0:
            return None
        col = col.fillna(col.median())
    else:
        # categorical, datetime-as-string, or anything else: ordinal-encode.
        # Fine for ranking (unlike one-hot, it doesn't multiply column count),
        # even though it implies an arbitrary category order the model itself
        # doesn't rely on for anything beyond a relative importance score.
        nunique = series.nunique(dropna=True)
        if nunique > HIGH_CARDINALITY_THRESHOLD:
            return None
        filled = series.astype(str).fillna("__missing__")
        encoder = OrdinalEncoder()
        col = pd.Series(encoder.fit_transform(filled.to_numpy().reshape(-1, 1)).ravel(), index=series.index)

    if col.nunique(dropna=True) <= 1:
        return None
    return col


def _drop_reason(series: pd.Series, ctype: str) -> str:
    if series.notna().sum() == 0:
        return "entirely empty — no values to rank"
    if ctype != "numeric" and series.nunique(dropna=True) > HIGH_CARDINALITY_THRESHOLD:
        return f"too many unique values ({series.nunique(dropna=True)}) — looks like an identifier, not a feature"
    return "constant column — no variation, so it can't explain variation in the target"


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a {feature: raw_score} dict to 0-1 so methods on
    different native scales (MI nats, model coefficients, rank position)
    can be averaged meaningfully."""
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return {k: 1.0 for k in scores}  # all tied — treat as equally informative rather than dividing by ~0
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def rank_features(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    column_types: dict[str, str],
    task_type: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Rank feature_cols by relevance to target_col using the 3-method
    consensus described above.

    Returns (result, error). result = {
      "task_type", "n_rows_used",
      "ranking": [{"feature", "mutual_info", "l1", "rfe", "consensus_score", "votes"}, ...]
                 sorted descending by consensus_score, each sub-score 0-1 normalized,
      "dropped_features": [{"feature", "reason"}, ...],
      "top_k": [feature names, up to TOP_K_DEFAULT, from the ranking above],
      "method_errors": {method_name: error_message} for any method that
                        failed outright and was excluded from the consensus,
    }
    """
    if mutual_info_classif is None:
        return None, "scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app."

    working = df[list(feature_cols) + [target_col]].copy()
    working = working.dropna(subset=[target_col])
    if len(working) < MIN_ROWS_REQUIRED:
        return None, (
            f"Not enough rows with a non-missing target to rank features reliably "
            f"(need at least {MIN_ROWS_REQUIRED}, have {len(working)})."
        )

    encoded = {}
    dropped = []
    for col in feature_cols:
        ctype = column_types.get(col, "categorical")
        enc = _encode_column(working[col], ctype)
        if enc is None:
            dropped.append({"feature": col, "reason": _drop_reason(working[col], ctype)})
        else:
            encoded[col] = enc

    if len(encoded) < MIN_FEATURES_REQUIRED:
        return None, (
            f"Fewer than {MIN_FEATURES_REQUIRED} usable feature columns after dropping constant/"
            f"empty/too-high-cardinality columns — nothing left to rank."
        )

    X = pd.DataFrame(encoded)
    feature_names = list(X.columns)
    X_scaled = StandardScaler().fit_transform(X.to_numpy())

    if task_type == "classification":
        y_raw = working[target_col].astype(str)
        y = OrdinalEncoder().fit_transform(y_raw.to_numpy().reshape(-1, 1)).ravel()
    else:
        y = working[target_col].astype(float).to_numpy()

    method_errors: dict[str, str] = {}
    raw_scores: dict[str, dict[str, float]] = {}

    # 1. Mutual information — nonparametric, catches nonlinear dependence.
    try:
        mi_fn = mutual_info_classif if task_type == "classification" else mutual_info_regression
        mi_values = mi_fn(X_scaled, y, random_state=42)
        raw_scores["mutual_info"] = dict(zip(feature_names, mi_values))
    except Exception as e:
        method_errors["mutual_info"] = str(e)

    # 2. L1-regularized linear model — coefficient magnitude after regularization.
    try:
        if task_type == "classification":
            l1_model = LogisticRegression(penalty="l1", solver="liblinear", C=1.0, random_state=42, max_iter=1000)
            l1_model.fit(X_scaled, y)
            coefs = np.abs(l1_model.coef_).mean(axis=0)  # average across classes for multiclass OVR
        else:
            l1_model = Lasso(alpha=0.01, random_state=42, max_iter=5000)
            l1_model.fit(X_scaled, y)
            coefs = np.abs(l1_model.coef_)
        raw_scores["l1"] = dict(zip(feature_names, coefs))
    except Exception as e:
        method_errors["l1"] = str(e)

    # 3. Recursive feature elimination — ranks by how much removing each
    #    feature hurts a fitted linear estimator, one feature at a time.
    try:
        n_select = max(1, min(TOP_K_DEFAULT, len(feature_names) - 1)) if len(feature_names) > 1 else 1
        rfe_estimator = (
            LogisticRegression(max_iter=1000, random_state=42)
            if task_type == "classification"
            else Lasso(alpha=0.01, random_state=42, max_iter=5000)
        )
        rfe = RFE(rfe_estimator, n_features_to_select=n_select)
        rfe.fit(X_scaled, y)
        max_rank = max(rfe.ranking_)
        # rank 1 = most important; invert so higher = more important, like the other two methods
        rfe_scores = {
            name: (1.0 if max_rank <= 1 else 1.0 - (rank - 1) / (max_rank - 1))
            for name, rank in zip(feature_names, rfe.ranking_)
        }
        raw_scores["rfe"] = rfe_scores
    except Exception as e:
        method_errors["rfe"] = str(e)

    if not raw_scores:
        return None, "All three ranking methods failed on this data — try a different target or feature set."

    normalized = {method: _normalize(scores) for method, scores in raw_scores.items()}

    # "votes" — how many of the methods that ran place this feature in
    # their own top TOP_K_DEFAULT, mirroring anomaly ensemble's consensus_count.
    top_sets = {}
    for method, scores in raw_scores.items():
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_sets[method] = {name for name, _ in ranked[:TOP_K_DEFAULT]}

    ranking = []
    for name in feature_names:
        per_method = {method: normalized[method].get(name, 0.0) for method in raw_scores}
        consensus_score = sum(per_method.values()) / len(per_method)
        votes = sum(1 for method in raw_scores if name in top_sets[method])
        row = {"feature": name, "consensus_score": round(consensus_score, 4), "votes": votes}
        for method in METHODS:
            row[method] = round(per_method[method], 4) if method in per_method else None
        ranking.append(row)

    ranking.sort(key=lambda r: (r["consensus_score"], r["votes"]), reverse=True)

    result = {
        "task_type": task_type,
        "n_rows_used": len(working),
        "ranking": ranking,
        "dropped_features": dropped,
        "top_k": [r["feature"] for r in ranking[:TOP_K_DEFAULT]],
        "method_errors": method_errors,
    }
    return result, None


def fingerprint_ranking(result: Optional[dict]) -> str:
    """A short, stable hash of a rank_features() result — used to cache
    the AI narration so re-viewing the same ranking doesn't re-spend a
    Gemini call."""
    if result is None:
        return "empty"
    parts = [f"{r['feature']}:{r['consensus_score']}" for r in result["ranking"]]
    key = f"{result['task_type']}|{result['n_rows_used']}|" + "|".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data scientist explaining a feature-selection result to a "
    "stakeholder who isn't technical. For a {task_type} target, three independent ranking "
    "methods (mutual information, L1-regularized model coefficients, and recursive feature "
    "elimination) were run and combined into a consensus score. The top-ranked features "
    "are, in order:\n\n{ranking_text}\n\n"
    "In 3-4 sentences: explain in plain English why the top feature(s) likely matter for "
    "predicting the target, note if any lower-ranked feature might still be worth keeping for "
    "a business reason even with a weak statistical score, and suggest whether it's safe to "
    "drop the bottom-ranked features from a first modeling pass. Do not simply restate the numbers back."
)


def narrate_feature_ranking(model, result: Optional[dict]) -> tuple[str, Optional[str]]:
    """Ask Gemini to interpret a rank_features() result. Detection/scoring
    stays entirely deterministic (three sklearn models) — the LLM's job is
    strictly to interpret already-computed numbers, same division of
    labor as anomaly.narrate_ensemble_disagreement().

    Returns (narration, error). Callers should cache the result keyed by
    fingerprint_ranking(result) to avoid re-calling Gemini for a ranking
    the user has already seen narrated.
    """
    if result is None or not result.get("ranking"):
        return "", "No feature ranking to narrate yet — run feature ranking first."
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    ranking_text = "\n".join(
        f"- {r['feature']} (consensus score {r['consensus_score']:.2f}, agreed on by {r['votes']}/{len(METHODS)} methods)"
        for r in result["ranking"]
    )
    prompt = _NARRATION_PROMPT.format(task_type=result["task_type"], ranking_text=ranking_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None


def build_ranking_chart(result: dict) -> go.Figure:
    """Grouped bar chart: one group per feature, one bar per method's
    normalized score, features ordered by consensus rank."""
    features = [r["feature"] for r in result["ranking"]]
    fig = go.Figure()
    for method in METHODS:
        values = [r[method] if r[method] is not None else 0 for r in result["ranking"]]
        fig.add_trace(go.Bar(name=method.replace("_", " ").title(), x=features, y=values))
    fig.update_layout(
        barmode="group",
        xaxis_title="Feature",
        yaxis_title="Normalized score (0-1)",
        legend_title="Method",
        margin=dict(t=30, b=10),
    )
    return fig
