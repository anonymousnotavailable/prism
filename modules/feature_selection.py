"""
Feature Selection Engine — ranks candidate features by predictive value for
a chosen target using three complementary, well-established methods, then
synthesizes a consensus ranking. Answers "which features actually matter"
*before* a baseline model is even run, and flags likely-redundant features.

Methods (each catches failure modes the others miss — the standard reason
a real feature-selection pass never relies on a single method):

1. Mutual Information (`sklearn.feature_selection.mutual_info_classif` /
   `mutual_info_regression`) — a non-parametric, model-free measure of
   statistical dependence. Catches non-linear relationships a linear model
   would miss entirely.
2. L1-regularized linear model coefficients (`LogisticRegression(penalty="l1")`
   for classification, `LassoCV` for regression) — the classic embedded
   method; L1 drives redundant/weak feature coefficients to exactly zero,
   directly surfacing multicollinearity. `LassoCV` picks its regularization
   strength via 5-fold cross-validation rather than a hardcoded alpha.
3. Recursive Feature Elimination (`sklearn.feature_selection.RFE`) — a
   wrapper method: repeatedly fits a model and prunes the weakest feature,
   so importance reflects features *in combination*, not in isolation.

One-hot encoded categorical columns are aggregated back to their parent
feature (max for MI, sum-of-abs for Lasso, "any selected" for RFE) so the
ranking stays interpretable at the level the user actually picked columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

MIN_FEATURES = 2
MIN_ROWS = 20  # below this, CV folds / train-test splits get unstable
RFE_MAX_ITERATIONS = 15  # bounds RFE's step size regardless of one-hot width
HIGH_CARDINALITY_RATIO = 0.5  # nunique/nrows above this in a candidate -> likely an ID column, flag it


def _encode(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str
) -> tuple[np.ndarray, pd.Series, list[str]]:
    """Impute + scale numeric columns, impute + one-hot encode categoricals.
    Returns (X_transformed, y, parent_feature_per_transformed_column)."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    data = df[feature_cols + [target_col]].dropna(subset=[target_col])
    X, y = data[feature_cols], data[target_col]

    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]
    categorical_features = [c for c in feature_cols if c not in numeric_features]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric_features),
            (
                "cat",
                Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]),
                categorical_features,
            ),
        ],
        remainder="drop",
    )
    X_transformed = preprocessor.fit_transform(X)
    if hasattr(X_transformed, "toarray"):
        X_transformed = X_transformed.toarray()

    transformed_names = preprocessor.get_feature_names_out()
    # sklearn names transformed columns like "num__age" / "cat__city_Mumbai" —
    # map each back to its original ("num"/"cat" stripped) parent feature.
    parent_of = []
    for name in transformed_names:
        stripped = name.split("__", 1)[-1]
        matched = max((c for c in feature_cols if stripped == c or stripped.startswith(c + "_")), key=len, default=stripped)
        parent_of.append(matched)

    return X_transformed, y.reset_index(drop=True), parent_of


def _aggregate_by_parent(scores: np.ndarray, parent_of: list[str], feature_cols: list[str], how: str) -> pd.Series:
    frame = pd.DataFrame({"parent": parent_of, "score": np.abs(scores)})
    if how == "max":
        agg = frame.groupby("parent")["score"].max()
    else:  # "sum"
        agg = frame.groupby("parent")["score"].sum()
    return agg.reindex(feature_cols, fill_value=0.0)


def _normalize(series: pd.Series) -> pd.Series:
    max_val = series.max()
    if max_val <= 0:
        return series * 0.0
    return series / max_val


def mutual_info_ranking(df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str) -> pd.Series:
    """Parent-feature MI scores, normalized 0-1 by the strongest feature."""
    from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

    X, y, parent_of = _encode(df, feature_cols, target_col, task_type)
    scorer = mutual_info_classif if task_type == "classification" else mutual_info_regression
    raw = scorer(X, y, random_state=42)
    return _normalize(_aggregate_by_parent(raw, parent_of, feature_cols, how="max")).sort_values(ascending=False)


def lasso_ranking(df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str) -> pd.Series:
    """Parent-feature |coefficient| from an L1-regularized linear model,
    normalized 0-1. Zero means the regularizer dropped every transformed
    column belonging to that feature — a direct redundancy signal."""
    from sklearn.linear_model import LassoCV, LogisticRegression

    X, y, parent_of = _encode(df, feature_cols, target_col, task_type)
    if task_type == "classification":
        model = LogisticRegression(penalty="l1", solver="liblinear", max_iter=1000, random_state=42)
        model.fit(X, y)
        coefs = model.coef_
        raw = np.abs(coefs).max(axis=0) if coefs.ndim > 1 else np.abs(coefs[0])
    else:
        n_folds = min(5, max(2, len(y) // 5))
        model = LassoCV(cv=n_folds, random_state=42, max_iter=5000)
        model.fit(X, y)
        raw = np.abs(model.coef_)
    return _normalize(_aggregate_by_parent(raw, parent_of, feature_cols, how="sum")).sort_values(ascending=False)


def rfe_selection(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str, n_features_to_select: int
) -> dict[str, bool]:
    """{parent_feature: selected} from Recursive Feature Elimination — a
    parent is "selected" if RFE kept any of its transformed columns."""
    from sklearn.feature_selection import RFE
    from sklearn.linear_model import LinearRegression, LogisticRegression

    X, y, parent_of = _encode(df, feature_cols, target_col, task_type)
    n_select = max(1, min(n_features_to_select, X.shape[1]))
    estimator = (
        LogisticRegression(max_iter=1000, random_state=42) if task_type == "classification" else LinearRegression()
    )
    # RFE's default step=1 removes one transformed column per iteration —
    # fine for a handful of numeric features, but a single high-cardinality
    # ID-like categorical (e.g. a column with one distinct value per row)
    # one-hot expands into as many columns as there are rows, turning that
    # into hundreds of sequential model fits. Bounding the step keeps this
    # to roughly a fixed number of iterations regardless of how wide the
    # one-hot encoding gets, so ranking a poorly-chosen candidate column
    # degrades gracefully instead of stalling the UI.
    step = max(1, X.shape[1] // RFE_MAX_ITERATIONS)
    rfe = RFE(estimator, n_features_to_select=n_select, step=step)
    rfe.fit(X, y)

    selected_parents: set[str] = {parent_of[i] for i, keep in enumerate(rfe.support_) if keep}
    return {feature: (feature in selected_parents) for feature in feature_cols}


def build_feature_selection_report(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str, n_features_to_select: int | None = None
) -> dict:
    """Runs all three methods and synthesizes a consensus ranking.

    Returns {"table": DataFrame[feature, mutual_info, lasso_importance,
    rfe_selected, consensus_score], "recommended_features": list[str],
    "narrative": list[str]} or {"error": str} if the input can't support
    feature selection (too few features/rows, no variance in target, etc.).
    """
    valid_rows = df[feature_cols + [target_col]].dropna(subset=[target_col]).shape[0]
    if len(feature_cols) < MIN_FEATURES:
        return {"error": f"Pick at least {MIN_FEATURES} feature columns to rank them against each other."}
    if valid_rows < MIN_ROWS:
        return {"error": f"Only {valid_rows} rows have a non-missing target — need at least {MIN_ROWS} for stable rankings."}

    if n_features_to_select is None:
        # Leave at least one feature eliminated when there's more than one to
        # choose from, otherwise RFE can't actually narrow anything down.
        cap = len(feature_cols) - 1 if len(feature_cols) > 1 else 1
        n_features_to_select = max(1, min(cap, round(len(feature_cols) ** 0.5) + 1))

    try:
        mi_scores = mutual_info_ranking(df, feature_cols, target_col, task_type)
        lasso_scores = lasso_ranking(df, feature_cols, target_col, task_type)
        rfe_flags = rfe_selection(df, feature_cols, target_col, task_type, n_features_to_select)
    except ValueError as e:
        return {"error": f"Feature selection couldn't run on this target/feature combination: {e}"}

    table = pd.DataFrame(
        {
            "feature": feature_cols,
            "mutual_info": [round(mi_scores.get(f, 0.0), 4) for f in feature_cols],
            "lasso_importance": [round(lasso_scores.get(f, 0.0), 4) for f in feature_cols],
            "rfe_selected": [rfe_flags.get(f, False) for f in feature_cols],
        }
    )
    table["consensus_score"] = round(
        (table["mutual_info"] + table["lasso_importance"] + table["rfe_selected"].astype(float)) / 3, 4
    )
    table = table.sort_values("consensus_score", ascending=False).reset_index(drop=True)

    recommended = table.head(n_features_to_select)["feature"].tolist()

    narrative = []
    high_cardinality = [
        c for c in feature_cols
        if not pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() / max(len(df), 1) > HIGH_CARDINALITY_RATIO
    ]
    if high_cardinality:
        narrative.append(
            f"{', '.join(high_cardinality)} look like ID columns (nearly one distinct value per row) — "
            "ranking them rarely means anything and one-hot encoding them slows every method down. Consider excluding them."
        )

    if not table.empty:
        top = table.iloc[0]
        narrative.append(f"**{top['feature']}** ranks highest across all three methods (consensus {top['consensus_score']:.2f}) — the strongest single predictor.")

    unanimous = table[(table["mutual_info"] > 0.3) & (table["lasso_importance"] > 0.3) & table["rfe_selected"]]["feature"].tolist()
    if len(unanimous) > 1:
        narrative.append(f"{len(unanimous)} features agree across MI, Lasso, and RFE: {', '.join(unanimous)} — safe to prioritize these.")

    zero_signal = table[(table["mutual_info"] < 0.05) & (table["lasso_importance"] < 0.05) & ~table["rfe_selected"]]["feature"].tolist()
    if zero_signal:
        narrative.append(f"{len(zero_signal)} feature(s) show near-zero signal on every method — candidates to drop: {', '.join(zero_signal)}.")

    disagreement = table[(table["lasso_importance"] < 0.05) & (table["mutual_info"] > 0.4)]["feature"].tolist()
    if disagreement:
        narrative.append(
            f"{', '.join(disagreement)} score high on Mutual Information but near-zero on Lasso — likely a non-linear "
            "relationship a linear baseline model won't capture, or redundant with another selected feature."
        )

    return {
        "table": table,
        "recommended_features": recommended,
        "n_features_to_select": n_features_to_select,
        "narrative": narrative,
    }


def build_consensus_chart(table: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Horizontal bar chart of consensus_score, colored by whether RFE kept the feature."""
    top = table.head(top_n).sort_values("consensus_score", ascending=True)
    fig = px.bar(
        top, x="consensus_score", y="feature", orientation="h", color="rfe_selected",
        color_discrete_map={True: "#00e5ff", False: "#5c6b7a"},
        labels={"consensus_score": "Consensus Score", "feature": "Feature", "rfe_selected": "RFE selected"},
        title="Feature Selection — Consensus Ranking",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig
