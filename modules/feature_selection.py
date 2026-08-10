"""
Feature Selection Engine — ranks ML Lab's candidate feature columns using
three independent, complementary signals instead of trusting any single
method:

- **Mutual information** — a model-free, nonlinear dependency measure
  between each feature and the target (sklearn's `mutual_info_classif` /
  `mutual_info_regression`).
- **L1-regularized linear model** — which features a sparse linear model
  (L1-logistic for classification, Lasso for regression) keeps a non-zero
  coefficient for, after standardizing every feature onto the same scale.
- **Recursive Feature Elimination (RFE)** with a Random Forest estimator —
  which features a tree ensemble treats as load-bearing when forced to
  drop half the candidates.

Each signal is min-max normalized to [0, 1] and averaged into a single
composite_score. This is standard pre-modeling feature triage practice:
no one method is reliable alone (MI misses interactions with regularization
context, L1 misses nonlinear relationships, RFE is estimator-dependent) —
agreement across all three is a much stronger signal than any one score.

This module only *ranks* candidates; it never mutates the caller's
dataframe or the model-training pipeline in mllab.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

MIN_FEATURES_REQUIRED = 2


def _encode_matrix(df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    """Numeric matrix for sklearn's feature-selection estimators: numeric
    columns pass through median-imputed, categorical columns get
    ordinal-encoded (category codes, median-imputed for any NaN codes).
    Mirrors mllab.suggest_features' own encoding choices closely enough for
    ranking purposes, without touching the caller's data.
    """
    columns = []
    for col in feature_cols:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            filled = series.astype(float)
            filled = filled.fillna(filled.median())
        else:
            codes = series.astype("category").cat.codes.astype(float)
            codes = codes.replace(-1, np.nan)  # -1 = NaN's own code in pandas' categorical
            fill_value = codes.median() if not codes.dropna().empty else 0.0
            filled = codes.fillna(fill_value)
        columns.append(filled.to_numpy())
    return np.column_stack(columns)


def _normalize(arr: np.ndarray) -> np.ndarray:
    """Min-max scale to [0, 1]; an all-equal array (every method agrees, or
    every method failed) normalizes to all-zero rather than dividing by zero.
    """
    arr = np.nan_to_num(np.asarray(arr, dtype=float))
    span = arr.max() - arr.min()
    if span == 0:
        return np.zeros_like(arr)
    return (arr - arr.min()) / span


def rank_features(df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str) -> pd.DataFrame:
    """Rank feature_cols by mutual information, L1 coefficient magnitude,
    and RFE selection, combined into composite_score.

    Returns a DataFrame sorted by composite_score descending, with columns:
    feature, mutual_info (raw score), l1_score (|coefficient|, 0 if the L1
    model zeroed it out), rfe_selected (bool — kept in RFE's top half),
    composite_score (0-1).

    Raises ValueError with fewer than MIN_FEATURES_REQUIRED columns —
    ranking is meaningless with 0-1 candidates. Each individual method
    degrades to a neutral (zero / all-selected) score rather than raising,
    so one flaky estimator never takes down the whole ranking — matching
    this app's "never crash the demo" failure-handling stance.
    """
    if len(feature_cols) < MIN_FEATURES_REQUIRED:
        raise ValueError(f"Need at least {MIN_FEATURES_REQUIRED} feature columns to rank, got {len(feature_cols)}.")

    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.feature_selection import RFE, mutual_info_classif, mutual_info_regression
    from sklearn.linear_model import Lasso, LogisticRegression
    from sklearn.preprocessing import StandardScaler

    data = df[feature_cols + [target_col]].dropna(subset=[target_col])
    X = _encode_matrix(data, feature_cols)
    is_classification = task_type == "classification"
    y = data[target_col].astype("category").cat.codes.to_numpy() if is_classification else pd.to_numeric(
        data[target_col], errors="coerce"
    ).to_numpy()

    try:
        mi_func = mutual_info_classif if is_classification else mutual_info_regression
        mi_scores = mi_func(X, y, random_state=42)
    except Exception:
        mi_scores = np.zeros(len(feature_cols))

    X_scaled = StandardScaler().fit_transform(X)
    try:
        if is_classification:
            l1_model = LogisticRegression(penalty="l1", solver="liblinear", max_iter=1000, random_state=42)
            l1_model.fit(X_scaled, y)
            coefs = np.abs(l1_model.coef_)
            l1_scores = coefs.max(axis=0) if coefs.ndim > 1 else coefs.ravel()
        else:
            l1_model = Lasso(alpha=0.01, random_state=42, max_iter=5000)
            l1_model.fit(X_scaled, y)
            l1_scores = np.abs(l1_model.coef_)
    except Exception:
        l1_scores = np.zeros(len(feature_cols))

    try:
        n_select = max(1, len(feature_cols) // 2)
        estimator = (
            RandomForestClassifier(n_estimators=100, random_state=42)
            if is_classification
            else RandomForestRegressor(n_estimators=100, random_state=42)
        )
        rfe = RFE(estimator, n_features_to_select=n_select)
        rfe.fit(X, y)
        rfe_selected = rfe.support_
    except Exception:
        rfe_selected = np.ones(len(feature_cols), dtype=bool)

    composite = (_normalize(mi_scores) + _normalize(l1_scores) + rfe_selected.astype(float)) / 3.0

    result = pd.DataFrame(
        {
            "feature": feature_cols,
            "mutual_info": mi_scores,
            "l1_score": l1_scores,
            "rfe_selected": rfe_selected,
            "composite_score": composite,
        }
    )
    return result.sort_values("composite_score", ascending=False, kind="stable").reset_index(drop=True)


def select_top_k(ranked: pd.DataFrame, k: int) -> list[str]:
    """Top-k feature names by composite_score, capped at however many were ranked."""
    k = min(k, len(ranked))
    top = ranked.sort_values("composite_score", ascending=False, kind="stable").head(k)
    return list(top["feature"])


def build_ranking_chart(ranked: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of composite_score per feature, weakest at the bottom."""
    ordered = ranked.sort_values("composite_score", ascending=True)
    fig = px.bar(
        ordered, x="composite_score", y="feature", orientation="h",
        labels={"composite_score": "Composite Score", "feature": "Feature"},
        title="Composite Feature Ranking",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig
