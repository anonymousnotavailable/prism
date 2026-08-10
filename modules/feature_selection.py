"""
Feature Selection Engine — rank-aggregated feature importance for ML Lab.

Combines three independent, complementary signals so no single method's
blind spot dominates the ranking:

  - Mutual information (mutual_info_classif / mutual_info_regression):
    captures any dependency, linear or not, between a feature and the
    target. Model-free.
  - Univariate statistical test (ANOVA F-test / f_regression): the
    classical "is this feature's relationship with the target unlikely
    to be chance" signal, cheap and well understood.
  - L1-regularized linear model (LogisticRegression(penalty='l1') /
    Lasso): captures which features a sparse linear model keeps once it
    can trade features off against each other, unlike the two univariate
    methods above which score each feature in isolation.

Each method produces its own per-feature score; features are ranked
1..N *within* each method, and the combined score is the mean rank across
all three (Borda-count style rank aggregation) — a standard technique for
combining heterogeneous feature-importance signals without needing to
normalize wildly different scales (bits of mutual information vs.
F-statistics vs. regression coefficients) onto one axis.

Categorical feature columns are label-encoded (pd.factorize) purely for
this ranking — the caller's actual training pipeline (mllab.run_baseline_models)
does its own proper one-hot encoding downstream. This module only answers
"which columns are worth including," not "how to encode them."
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.feature_selection import (
        f_classif,
        f_regression,
        mutual_info_classif,
        mutual_info_regression,
    )
    from sklearn.linear_model import Lasso, LogisticRegression
    from sklearn.preprocessing import StandardScaler
except ImportError:  # pragma: no cover — app should still import if sklearn is missing
    f_classif = f_regression = mutual_info_classif = mutual_info_regression = None
    Lasso = LogisticRegression = StandardScaler = None

MIN_ROWS_REQUIRED = 20
_ELBOW_CUMULATIVE_SHARE = 0.8  # recommend features covering ~80% of total combined weight


def is_available() -> bool:
    """Whether scikit-learn is installed."""
    return mutual_info_classif is not None


def _encode_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Label-encode any non-numeric feature columns for ranking purposes only."""
    encoded = pd.DataFrame(index=df.index)
    for col in feature_cols:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            encoded[col] = series
        else:
            codes, _ = pd.factorize(series, sort=True)
            encoded[col] = codes.astype(float)
            encoded.loc[series.isna(), col] = np.nan
    return encoded


def rank_features(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str
) -> dict:
    """Rank candidate feature columns by combined importance to target_col.

    Returns a dict with keys:
      error               — set (str) and every other list/field empty if ranking couldn't run
      ranked              — list of {feature, mutual_info, stat_test, lasso_importance, combined_rank}
                             sorted best-first (lowest combined_rank = strongest)
      recommended_k        — suggested number of top features to keep
      recommended_features — the top recommended_k feature names, in ranked order
    """
    empty_result = {"error": None, "ranked": [], "recommended_k": 0, "recommended_features": []}

    if not is_available():
        return {**empty_result, "error": "scikit-learn isn't installed."}
    if not feature_cols:
        return {**empty_result, "error": "No feature columns given."}
    if target_col not in df.columns:
        return {**empty_result, "error": f"Target column '{target_col}' not found."}

    feature_cols = [c for c in feature_cols if c in df.columns and c != target_col]
    if not feature_cols:
        return {**empty_result, "error": "No usable feature columns given."}

    encoded = _encode_features(df, feature_cols)
    # Drop feature columns that are entirely missing — nothing to rank there.
    all_null_cols = [c for c in encoded.columns if encoded[c].isna().all()]
    usable_cols = [c for c in feature_cols if c not in all_null_cols]
    if not usable_cols:
        return {**empty_result, "error": "All requested feature columns are entirely empty."}

    work = encoded[usable_cols].copy()
    work[target_col] = df[target_col]
    work = work.dropna()

    if len(work) < MIN_ROWS_REQUIRED:
        return {
            **empty_result,
            "error": f"Not enough complete rows to rank features (need at least {MIN_ROWS_REQUIRED}, have {len(work)}).",
        }

    X = work[usable_cols].values
    y = work[target_col]

    if task_type == "classification":
        if y.nunique() < 2:
            return {**empty_result, "error": "Target has only one class — nothing to rank features against."}
        y_enc, _ = pd.factorize(y)
        mi = mutual_info_classif(X, y_enc, random_state=42)
        f_stat, _ = f_classif(X, y_enc)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        lasso_model = LogisticRegression(penalty="l1", solver="liblinear", C=1.0, random_state=42)
        lasso_model.fit(X_scaled, y_enc)
        coefs = lasso_model.coef_
        lasso_importance = np.abs(coefs).mean(axis=0) if coefs.ndim > 1 else np.abs(coefs[0])
    elif task_type == "regression":
        y_num = pd.to_numeric(y, errors="coerce")
        if y_num.isna().any():
            return {**empty_result, "error": "Target column isn't fully numeric — can't rank for a regression task."}
        mi = mutual_info_regression(X, y_num, random_state=42)
        f_stat, _ = f_regression(X, y_num)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        lasso_model = Lasso(alpha=0.01, random_state=42, max_iter=5000)
        lasso_model.fit(X_scaled, y_num)
        lasso_importance = np.abs(lasso_model.coef_)
    else:
        return {**empty_result, "error": f"Unknown task type '{task_type}'."}

    f_stat = np.nan_to_num(f_stat, nan=0.0)

    def _ranks(values: np.ndarray) -> np.ndarray:
        """1 = best (highest value). Ties get the same (average) rank."""
        order = pd.Series(values).rank(ascending=False, method="average")
        return order.values

    mi_ranks = _ranks(mi)
    f_ranks = _ranks(f_stat)
    lasso_ranks = _ranks(lasso_importance)
    combined = (mi_ranks + f_ranks + lasso_ranks) / 3.0

    rows = []
    for i, col in enumerate(usable_cols):
        rows.append({
            "feature": col,
            "mutual_info": round(float(mi[i]), 4),
            "stat_test": round(float(f_stat[i]), 4),
            "lasso_importance": round(float(lasso_importance[i]), 4),
            "combined_rank": round(float(combined[i]), 2),
        })
    rows.sort(key=lambda r: r["combined_rank"])

    recommended_k = _recommend_k([r["combined_rank"] for r in rows])
    return {
        "error": None,
        "ranked": rows,
        "recommended_k": recommended_k,
        "recommended_features": [r["feature"] for r in rows[:recommended_k]],
    }


def _recommend_k(combined_ranks: list[float]) -> int:
    """Pick how many top-ranked features to recommend keeping.

    Converts combined rank (lower=better) to a positive "weight" via
    inversion, then keeps the smallest prefix whose cumulative weight
    covers _ELBOW_CUMULATIVE_SHARE of the total — an elbow heuristic so a
    dataset with one dominant feature recommends just that one, while a
    dataset where importance is spread evenly recommends most of them.
    Always keeps at least 1, never more than all features.
    """
    n = len(combined_ranks)
    if n <= 1:
        return max(n, 1)
    # invert: best (lowest) rank -> highest weight. +1 avoids a zero weight for the worst feature.
    max_rank = max(combined_ranks)
    weights = [(max_rank - r) + 1 for r in combined_ranks]
    total = sum(weights)
    if total <= 0:
        return n
    cumulative = 0.0
    for k, w in enumerate(weights, 1):
        cumulative += w
        if cumulative / total >= _ELBOW_CUMULATIVE_SHARE:
            return k
    return n
