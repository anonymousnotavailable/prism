"""
ML Lab — the data-science bridge: a feature engineering assistant that
suggests (and one-click applies) encoding/scaling/datetime-expansion/
interaction features, a baseline model runner (Logistic/Linear Regression
vs. Random Forest, auto-detecting classification vs. regression), and a
class-imbalance detector with optional SMOTE resampling on the training set.

This is explicitly a *baseline exploration* tool, not a model-deployment
pipeline — every result the UI shows should be paired with that framing.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

SMOTE_TEST_SET_NOTE = (
    "SMOTE is applied only to the training set, after the train/test split — the test set stays "
    "exactly as collected, since evaluating against synthetic data would give a falsely optimistic score."
)

# ==========================================================================
# 9. Feature Engineering Assistant
# ==========================================================================

ONE_HOT_CARDINALITY_THRESHOLD = 10


def suggest_features(df: pd.DataFrame, column_types: dict[str, str], target_col: str) -> list[dict]:
    """For every non-target column, suggest an encoding/scaling/expansion
    treatment, plus up to 3 candidate numeric interaction features.

    Returns a list of suggestion dicts:
    {"type": "encode", "column", "method": "one-hot"|"ordinal", "reason"}
    {"type": "scale", "column", "method": "standard", "reason"}
    {"type": "datetime_expand", "column", "reason"}
    {"type": "interaction", "columns": [a, b], "method": "product", "reason"}
    """
    suggestions = []
    feature_cols = [c for c in df.columns if c != target_col]
    numeric_cols = []

    for col in feature_cols:
        ctype = column_types.get(col)
        if ctype == "categorical":
            nunique = df[col].nunique()
            if nunique <= ONE_HOT_CARDINALITY_THRESHOLD:
                suggestions.append(
                    {
                        "type": "encode", "column": col, "method": "one-hot",
                        "reason": f"Low cardinality ({nunique} unique values) — one-hot keeps each category independent without implying order.",
                    }
                )
            else:
                suggestions.append(
                    {
                        "type": "encode", "column": col, "method": "ordinal",
                        "reason": f"High cardinality ({nunique} unique values) — one-hot would create too many columns; ordinal encoding is more compact.",
                    }
                )
        elif ctype == "numeric":
            numeric_cols.append(col)
            suggestions.append(
                {
                    "type": "scale", "column": col, "method": "standard",
                    "reason": "Numeric feature — standardizing helps distance-based and linear models treat it fairly alongside other features.",
                }
            )
        elif ctype == "datetime":
            suggestions.append(
                {
                    "type": "datetime_expand", "column": col,
                    "reason": "Datetime column — expanding into year/month/day/weekday lets models use seasonality patterns directly.",
                }
            )

    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr().abs()
        pairs = []
        for i, col_a in enumerate(numeric_cols):
            for col_b in numeric_cols[i + 1 :]:
                value = corr_matrix.loc[col_a, col_b]
                if pd.notna(value):
                    pairs.append((col_a, col_b, value))
        pairs.sort(key=lambda p: -p[2])
        for col_a, col_b, value in pairs[:3]:
            suggestions.append(
                {
                    "type": "interaction", "columns": [col_a, col_b], "method": "product",
                    "reason": (
                        f"'{col_a}' and '{col_b}' are correlated ({value:.2f}) — their product may capture "
                        "a combined effect a linear model would otherwise miss."
                    ),
                }
            )

    return suggestions


def apply_suggestion(df: pd.DataFrame, suggestion: dict) -> tuple[pd.DataFrame, str, str]:
    """Apply one feature-engineering suggestion. Returns (new_df, description, code)."""
    new_df = df.copy()
    kind = suggestion["type"]

    if kind == "encode":
        col = suggestion["column"]
        if suggestion["method"] == "one-hot":
            dummies = pd.get_dummies(new_df[col], prefix=col)
            new_df = pd.concat([new_df.drop(columns=[col]), dummies], axis=1)
            description = f"One-hot encoded '{col}' into {dummies.shape[1]} column(s)"
            code = (
                f"df = pd.concat([df.drop(columns=[{col!r}]), "
                f"pd.get_dummies(df[{col!r}], prefix={col!r})], axis=1)"
            )
        else:
            categories = new_df[col].astype("category").cat.categories
            new_df[col] = new_df[col].astype("category").cat.codes
            description = f"Ordinal-encoded '{col}' ({len(categories)} categories)"
            code = f"df[{col!r}] = df[{col!r}].astype('category').cat.codes"

    elif kind == "scale":
        col = suggestion["column"]
        from sklearn.preprocessing import StandardScaler

        new_df[col] = StandardScaler().fit_transform(new_df[[col]])
        description = f"Standardized '{col}' (mean 0, std 1)"
        code = f"from sklearn.preprocessing import StandardScaler\ndf[{col!r}] = StandardScaler().fit_transform(df[[{col!r}]])"

    elif kind == "datetime_expand":
        col = suggestion["column"]
        dt_series = pd.to_datetime(new_df[col], errors="coerce")
        new_df[f"{col}_year"] = dt_series.dt.year
        new_df[f"{col}_month"] = dt_series.dt.month
        new_df[f"{col}_day"] = dt_series.dt.day
        new_df[f"{col}_weekday"] = dt_series.dt.weekday
        description = f"Expanded '{col}' into year/month/day/weekday columns"
        code = (
            f"_dt = pd.to_datetime(df[{col!r}], errors='coerce')\n"
            f"df[{col + '_year'!r}] = _dt.dt.year\n"
            f"df[{col + '_month'!r}] = _dt.dt.month\n"
            f"df[{col + '_day'!r}] = _dt.dt.day\n"
            f"df[{col + '_weekday'!r}] = _dt.dt.weekday"
        )

    elif kind == "interaction":
        col_a, col_b = suggestion["columns"]
        new_col = f"{col_a}_x_{col_b}"
        new_df[new_col] = new_df[col_a] * new_df[col_b]
        description = f"Added interaction feature '{new_col}' ({col_a} * {col_b})"
        code = f"df[{new_col!r}] = df[{col_a!r}] * df[{col_b!r}]"

    else:
        return df, "Unknown suggestion type", "# unknown suggestion type"

    return new_df, description, code


# ==========================================================================
# 10. Baseline Model Runner
# ==========================================================================


def detect_task_type(series: pd.Series) -> str:
    """"classification" if the target looks categorical/low-cardinality
    relative to the row count, else "regression"."""
    if pd.api.types.is_numeric_dtype(series):
        nunique = series.nunique()
        if nunique <= 15 and nunique / max(len(series), 1) < 0.05:
            return "classification"
        return "regression"
    return "classification"


def run_baseline_models(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, task_type: str, use_smote: bool = False
) -> dict:
    """Train/test split (80/20, stratified for classification), a
    ColumnTransformer preprocessing pipeline (impute + one-hot for
    categoricals, impute + StandardScaler for numerics), and two baseline
    models (Logistic/Linear Regression + Random Forest) compared side by side.

    Returns {"task_type", "results": {model_name: metrics}, "confusion_matrix",
    "confusion_labels", "feature_importances", "n_train", "n_test",
    "smote_before_after"}.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    data = df[feature_cols + [target_col]].dropna(subset=[target_col])
    X = data[feature_cols]
    y = data[target_col]

    categorical_features = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(X[c])]
    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]

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

    stratify = y if task_type == "classification" else None
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=stratify)

    X_train_transformed = preprocessor.fit_transform(X_train)
    X_test_transformed = preprocessor.transform(X_test)
    feature_names = [name.split("__", 1)[-1] for name in preprocessor.get_feature_names_out()]

    smote_before_after = None
    if task_type == "classification" and use_smote:
        from imblearn.over_sampling import SMOTE

        before_counts = y_train.value_counts().to_dict()
        try:
            X_train_transformed, y_train = SMOTE(random_state=42).fit_resample(X_train_transformed, y_train)
            smote_before_after = {"before": before_counts, "after": pd.Series(y_train).value_counts().to_dict()}
        except ValueError as e:
            smote_before_after = {"error": str(e)}

    if task_type == "classification":
        baseline_model = LogisticRegression(max_iter=1000)
        rf_model = RandomForestClassifier(n_estimators=200, random_state=42)
    else:
        baseline_model = LinearRegression()
        rf_model = RandomForestRegressor(n_estimators=200, random_state=42)

    fitted_models = {}
    results = {}
    for name, model in [("Baseline", baseline_model), ("Random Forest", rf_model)]:
        model.fit(X_train_transformed, y_train)
        preds = model.predict(X_test_transformed)
        if task_type == "classification":
            metrics = {
                "accuracy": round(accuracy_score(y_test, preds), 4),
                "f1": round(f1_score(y_test, preds, average="weighted"), 4),
            }
        else:
            metrics = {
                "rmse": round(mean_squared_error(y_test, preds) ** 0.5, 4),
                "r2": round(r2_score(y_test, preds), 4),
            }
        fitted_models[name] = model
        results[name] = metrics

    confusion, confusion_labels = None, None
    if task_type == "classification":
        confusion_labels = sorted(y.unique().tolist())
        rf_preds = fitted_models["Random Forest"].predict(X_test_transformed)
        confusion = confusion_matrix(y_test, rf_preds, labels=confusion_labels)

    importances = None
    if hasattr(fitted_models["Random Forest"], "feature_importances_"):
        importances = pd.Series(
            fitted_models["Random Forest"].feature_importances_, index=feature_names
        ).sort_values(ascending=False)

    return {
        "task_type": task_type,
        "results": results,
        "confusion_matrix": confusion,
        "confusion_labels": confusion_labels,
        "feature_importances": importances,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "smote_before_after": smote_before_after,
        # Kept for SHAP explainability (see explain_with_shap below) — the
        # Random Forest specifically, since it's the model feature_importances_
        # already covers; re-fitting a second time just to explain it would
        # waste both compute and the point of reusing this same run.
        "fitted_rf_model": fitted_models["Random Forest"],
        # Kept for ROC/PR curves (see compute_roc_pr_curves below) — both
        # fitted models plus the actual test labels, so curves can be built
        # without a second fit.
        "fitted_models": fitted_models,
        "y_test": y_test,
        "X_train_transformed": X_train_transformed,
        "X_test_transformed": X_test_transformed,
        "feature_names": feature_names,
    }


def build_verdict(baseline_result: dict) -> str:
    """Plain-English comparison of Baseline vs. Random Forest, naming the top feature."""
    task_type = baseline_result["task_type"]
    metric_key = "f1" if task_type == "classification" else "r2"
    metric_label = "F1 score" if task_type == "classification" else "R²"

    baseline_score = baseline_result["results"]["Baseline"][metric_key]
    rf_score = baseline_result["results"]["Random Forest"][metric_key]
    better_name = "Random Forest" if rf_score >= baseline_score else "Baseline"
    pct_diff = abs(rf_score - baseline_score) / abs(baseline_score) * 100 if baseline_score else 0.0
    direction = "higher" if rf_score >= baseline_score else "lower"

    verdict = (
        f"{better_name} wins on {metric_label} ({max(rf_score, baseline_score):.3f} vs "
        f"{min(rf_score, baseline_score):.3f}, {pct_diff:.0f}% {direction} than the other model)."
    )

    importances = baseline_result.get("feature_importances")
    if importances is not None and not importances.empty:
        verdict += f" Top driver: {importances.index[0]}."
    return verdict


def build_confusion_matrix_chart(confusion: np.ndarray, labels: list) -> go.Figure:
    str_labels = [str(label) for label in labels]
    fig = px.imshow(
        confusion, text_auto=True, x=str_labels, y=str_labels, color_continuous_scale="Tealgrn",
        labels=dict(x="Predicted", y="Actual", color="Count"),
    )
    fig.update_layout(title="Confusion Matrix (Random Forest)", margin=dict(t=50, b=10, l=10, r=10))
    return fig


# ==========================================================================
# Reproducible script export — turns one ML Lab baseline-model run into a
# standalone, runnable .py file, mirroring the existing pattern in
# cleaning.export_script() (which only replays cleaning steps). This closes
# the gap where the model-training pipeline itself — preprocessing,
# train/test split, optional SMOTE, both baseline models — could only ever
# be reproduced by re-clicking through the app, not handed to a colleague
# or checked into a repo. Deliberately mirrors run_baseline_models() line
# for line so the exported script's results should match the in-app run
# (same random_state=42 everywhere).
# ==========================================================================


def export_baseline_script(
    feature_cols: list[str], target_col: str, task_type: str, use_smote: bool = False,
    original_filename: Optional[str] = None,
) -> str:
    """Generate a standalone .py script that reproduces this ML Lab
    baseline-model run against a fresh CSV/Excel load: the same
    ColumnTransformer preprocessing, 80/20 train/test split, optional SMOTE
    resampling, and both baseline models (Logistic/Linear Regression +
    Random Forest), printing the same accuracy/F1 or RMSE/R² metrics.
    """
    source = original_filename or "your_file.csv"
    reader = "read_excel" if source.lower().endswith((".xlsx", ".xls")) else "read_csv"

    is_classification = task_type == "classification"
    model_import = "LogisticRegression" if is_classification else "LinearRegression"
    rf_import = "RandomForestClassifier" if is_classification else "RandomForestRegressor"
    baseline_ctor = "LogisticRegression(max_iter=1000)" if is_classification else "LinearRegression()"
    rf_ctor = f"{rf_import}(n_estimators=200, random_state=42)"

    lines = [
        '"""Auto-generated by Prism — reproduces the ML Lab baseline model run for this session."""',
        "import pandas as pd",
        "import numpy as np",
        "from sklearn.compose import ColumnTransformer",
        f"from sklearn.ensemble import {rf_import}",
        "from sklearn.impute import SimpleImputer",
        f"from sklearn.linear_model import {model_import}",
        "from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_squared_error, r2_score",
        "from sklearn.model_selection import train_test_split",
        "from sklearn.pipeline import Pipeline",
        "from sklearn.preprocessing import OneHotEncoder, StandardScaler",
        "",
        f"df = pd.{reader}({source!r})  # replace with your actual file path",
        "",
        f"feature_cols = {feature_cols!r}",
        f"target_col = {target_col!r}",
        "",
        "data = df[feature_cols + [target_col]].dropna(subset=[target_col])",
        "X = data[feature_cols]",
        "y = data[target_col]",
        "",
        "categorical_features = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(X[c])]",
        "numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]",
        "",
        "preprocessor = ColumnTransformer(",
        "    transformers=[",
        '        ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric_features),',
        "        (",
        '            "cat",',
        '            Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]),',
        "            categorical_features,",
        "        ),",
        "    ],",
        '    remainder="drop",',
        ")",
        "",
        f"stratify = y if {is_classification!r} else None",
        "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=stratify)",
        "",
        "X_train_transformed = preprocessor.fit_transform(X_train)",
        "X_test_transformed = preprocessor.transform(X_test)",
        "",
    ]

    if is_classification and use_smote:
        lines += [
            "# --- SMOTE (training set only, applied after the split) ---",
            "from imblearn.over_sampling import SMOTE",
            "try:",
            "    X_train_transformed, y_train = SMOTE(random_state=42).fit_resample(X_train_transformed, y_train)",
            '    print("SMOTE resampling applied to the training set.")',
            "except ValueError as e:",
            '    print(f"SMOTE could not be applied: {e}")',
            "",
        ]

    lines += [
        f"baseline_model = {baseline_ctor}",
        f"rf_model = {rf_ctor}",
        "",
        'for name, model in [("Baseline", baseline_model), ("Random Forest", rf_model)]:',
        "    model.fit(X_train_transformed, y_train)",
        "    preds = model.predict(X_test_transformed)",
    ]
    if is_classification:
        lines += [
            '    print(f"{name}: accuracy={accuracy_score(y_test, preds):.4f}, '
            'f1={f1_score(y_test, preds, average=\'weighted\'):.4f}")',
        ]
    else:
        lines += [
            '    print(f"{name}: rmse={mean_squared_error(y_test, preds) ** 0.5:.4f}, '
            'r2={r2_score(y_test, preds):.4f}")',
        ]

    if is_classification:
        lines += [
            "",
            "rf_preds = rf_model.predict(X_test_transformed)",
            "labels = sorted(y.unique().tolist())",
            'print("Confusion matrix (Random Forest, rows=actual, cols=predicted):")',
            "print(confusion_matrix(y_test, rf_preds, labels=labels))",
        ]

    return "\n".join(lines)


# ==========================================================================
# ROC-AUC / Precision-Recall curves (binary classification)
# ==========================================================================
# Accuracy alone is misleading whenever classes are imbalanced — exactly
# the case ML Lab's own check_class_imbalance()/SMOTE flow already handles
# — since a model can score high accuracy just by favoring the majority
# class. ROC-AUC is the standard threshold-independent quality measure, but
# it can look deceptively good even for a model that performs poorly on the
# minority class; the Precision-Recall curve (and its summary, average
# precision / PR-AUC) is the standard complement for skewed data, since it
# ignores true negatives and focuses on the class that actually matters.
# Multiclass targets (3+ classes) are handled via the standard one-vs-rest
# (OvR) scheme: each class gets its own binary "this class vs. everything
# else" ROC and PR curve, plus a macro-average (unweighted mean across
# classes) AUC/AP as the single headline number. This mirrors scikit-learn's
# own documented approach to multiclass ROC-AUC and keeps the same
# per-model structure as the binary case, just nested one level deeper by
# class. compute_roc_pr_curves() returns {"mode": "binary" | "multiclass",
# ...} so callers can branch on shape; it returns None only when there's
# truly nothing to compute (not classification, only one class present, or
# no fitted model exposes predict_proba).

_ROC_AUC_BANDS = [
    (0.9, "outstanding"),
    (0.8, "excellent"),
    (0.7, "acceptable"),
    (0.6, "poor"),
    (0.5, "no better than random guessing"),
]


def compute_roc_pr_curves(baseline_result: dict) -> Optional[dict]:
    """ROC and Precision-Recall curves for every model in baseline_result
    that supports predict_proba, for classification tasks of any class
    count.

    Returns None if the task isn't classification, no model in the result
    supports probability predictions, or the test set has fewer than 2
    classes present (curves are undefined). Otherwise returns one of two
    shapes depending on class count:

    Binary (exactly 2 classes) — {"mode": "binary",
        "roc": {model_name: {"fpr", "tpr", "auc"}},
        "pr": {model_name: {"precision", "recall", "ap"}},
        "positive_label": the class treated as positive,
        "baseline_rate": share of the test set that is the positive class
                          (the PR curve's "no-skill" reference line)}

    Multiclass (3+ classes, one-vs-rest) — {"mode": "multiclass",
        "classes": sorted list of class labels,
        "roc": {model_name: {class_label: {"fpr", "tpr", "auc"}}},
        "pr": {model_name: {class_label: {"precision", "recall", "ap"}}},
        "macro_auc": {model_name: unweighted mean AUC across classes},
        "macro_ap": {model_name: unweighted mean AP across classes}}
    """
    from sklearn.metrics import auc, average_precision_score, precision_recall_curve, roc_curve

    if baseline_result.get("task_type") != "classification":
        return None

    confusion_labels = baseline_result.get("confusion_labels")
    if not confusion_labels or len(confusion_labels) < 2:
        return None

    y_test = baseline_result.get("y_test")
    X_test_transformed = baseline_result.get("X_test_transformed")
    fitted_models = baseline_result.get("fitted_models") or {}
    if y_test is None or X_test_transformed is None or not fitted_models:
        return None

    if len(confusion_labels) == 2:
        # Convention: the second label in sorted order (confusion_labels is
        # already sorted, see run_baseline_models) is treated as "positive"
        # — matches the diagonal ordering already used by the confusion
        # matrix.
        positive_label = confusion_labels[-1]
        y_true_binary = (y_test == positive_label).astype(int).to_numpy()
        if y_true_binary.sum() == 0 or y_true_binary.sum() == len(y_true_binary):
            return None  # test set only has one class present — curves are undefined

        roc_data: dict[str, dict] = {}
        pr_data: dict[str, dict] = {}
        for name, model in fitted_models.items():
            if not hasattr(model, "predict_proba"):
                continue
            classes = list(model.classes_)
            if positive_label not in classes:
                continue
            pos_idx = classes.index(positive_label)
            y_scores = model.predict_proba(X_test_transformed)[:, pos_idx]

            fpr, tpr, _ = roc_curve(y_true_binary, y_scores)
            roc_data[name] = {"fpr": fpr, "tpr": tpr, "auc": float(auc(fpr, tpr))}

            precision, recall, _ = precision_recall_curve(y_true_binary, y_scores)
            pr_data[name] = {
                "precision": precision,
                "recall": recall,
                "ap": float(average_precision_score(y_true_binary, y_scores)),
            }

        if not roc_data:
            return None

        return {
            "mode": "binary",
            "roc": roc_data,
            "pr": pr_data,
            "positive_label": positive_label,
            "baseline_rate": float(y_true_binary.mean()),
        }

    # Multiclass: one-vs-rest. Each class present in *both* the label set
    # and the test set gets its own binary curve; classes absent from the
    # test set (curves undefined for them) are silently skipped rather than
    # failing the whole computation.
    classes_sorted = list(confusion_labels)
    roc_mc: dict[str, dict[str, dict]] = {}
    pr_mc: dict[str, dict[str, dict]] = {}
    macro_auc: dict[str, float] = {}
    macro_ap: dict[str, float] = {}

    for name, model in fitted_models.items():
        if not hasattr(model, "predict_proba"):
            continue
        model_classes = list(model.classes_)
        proba = model.predict_proba(X_test_transformed)

        roc_by_class: dict[str, dict] = {}
        pr_by_class: dict[str, dict] = {}
        for cls in classes_sorted:
            if cls not in model_classes:
                continue
            y_true_ovr = (y_test == cls).astype(int).to_numpy()
            if y_true_ovr.sum() == 0 or y_true_ovr.sum() == len(y_true_ovr):
                continue  # this class isn't present (or is everything) in the test set
            cls_idx = model_classes.index(cls)
            y_scores = proba[:, cls_idx]

            fpr, tpr, _ = roc_curve(y_true_ovr, y_scores)
            roc_by_class[cls] = {"fpr": fpr, "tpr": tpr, "auc": float(auc(fpr, tpr))}

            precision, recall, _ = precision_recall_curve(y_true_ovr, y_scores)
            pr_by_class[cls] = {
                "precision": precision,
                "recall": recall,
                "ap": float(average_precision_score(y_true_ovr, y_scores)),
            }

        if not roc_by_class:
            continue
        roc_mc[name] = roc_by_class
        pr_mc[name] = pr_by_class
        macro_auc[name] = float(np.mean([d["auc"] for d in roc_by_class.values()]))
        macro_ap[name] = float(np.mean([d["ap"] for d in pr_by_class.values()]))

    if not roc_mc:
        return None

    # "classes" reflects only the classes that actually got a curve for at
    # least one model, preserving the caller-visible sorted order.
    curve_classes = [c for c in classes_sorted if any(c in d for d in roc_mc.values())]

    return {
        "mode": "multiclass",
        "classes": curve_classes,
        "roc": roc_mc,
        "pr": pr_mc,
        "macro_auc": macro_auc,
        "macro_ap": macro_ap,
    }


def build_roc_chart(curves: dict) -> go.Figure:
    fig = go.Figure()
    for name, d in curves["roc"].items():
        fig.add_trace(go.Scatter(x=d["fpr"], y=d["tpr"], mode="lines", name=f"{name} (AUC={d['auc']:.3f})"))
    fig.add_trace(
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dash", color="gray"), name="Random (AUC=0.500)")
    )
    fig.update_layout(
        title="ROC Curve", xaxis_title="False Positive Rate", yaxis_title="True Positive Rate",
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def build_pr_chart(curves: dict) -> go.Figure:
    fig = go.Figure()
    for name, d in curves["pr"].items():
        fig.add_trace(go.Scatter(x=d["recall"], y=d["precision"], mode="lines", name=f"{name} (AP={d['ap']:.3f})"))
    baseline_rate = curves.get("baseline_rate", 0.0)
    fig.add_trace(
        go.Scatter(
            x=[0, 1], y=[baseline_rate, baseline_rate], mode="lines",
            line=dict(dash="dash", color="gray"), name=f"No-skill baseline ({baseline_rate:.3f})",
        )
    )
    fig.update_layout(
        title="Precision-Recall Curve", xaxis_title="Recall", yaxis_title="Precision",
        margin=dict(t=50, b=10, l=10, r=10), yaxis_range=[0, 1.02],
    )
    return fig


def _roc_auc_band(score: float) -> str:
    for threshold, label in _ROC_AUC_BANDS:
        if score >= threshold:
            return label
    return "worse than random guessing"


def roc_pr_verdict(curves: Optional[dict]) -> str:
    """Plain-English read of the ROC-AUC / PR-AUC for the Random Forest
    model (falls back to whichever model is present), flagging when the
    positive class is rare enough that the Precision-Recall curve should be
    trusted over ROC-AUC alone.
    """
    if not curves or not curves.get("roc"):
        return ""

    model_name = "Random Forest" if "Random Forest" in curves["roc"] else next(iter(curves["roc"]))
    roc_auc = curves["roc"][model_name]["auc"]
    band = _roc_auc_band(roc_auc)
    ap = curves.get("pr", {}).get(model_name, {}).get("ap")
    baseline_rate = curves.get("baseline_rate", 0.5)

    parts = [f"{model_name}: ROC-AUC {roc_auc:.3f} ({band})."]
    if ap is not None:
        parts.append(f"Precision-Recall AUC (average precision) {ap:.3f} vs. a no-skill baseline of {baseline_rate:.3f}.")
    if baseline_rate < 0.3 or baseline_rate > 0.7:
        parts.append(
            "The positive class is imbalanced in the test set — ROC-AUC can look better than the model really "
            "performs on the minority class here, so weight the Precision-Recall curve more heavily than ROC-AUC alone."
        )
    return " ".join(parts)


def build_multiclass_roc_chart(curves: dict, model_name: str) -> go.Figure:
    """One-vs-rest ROC curves, one line per class, for a single model.
    Raises KeyError if model_name isn't in curves["roc"] (caller error)."""
    class_curves = curves["roc"][model_name]
    fig = go.Figure()
    for cls, d in class_curves.items():
        fig.add_trace(go.Scatter(x=d["fpr"], y=d["tpr"], mode="lines", name=f"{cls} (AUC={d['auc']:.3f})"))
    fig.add_trace(
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dash", color="gray"), name="Random (AUC=0.500)")
    )
    macro = curves.get("macro_auc", {}).get(model_name)
    title = f"ROC Curves ({model_name}, one-vs-rest)"
    if macro is not None:
        title += f" — macro-AUC {macro:.3f}"
    fig.update_layout(
        title=title, xaxis_title="False Positive Rate", yaxis_title="True Positive Rate",
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def build_multiclass_pr_chart(curves: dict, model_name: str) -> go.Figure:
    """One-vs-rest Precision-Recall curves, one line per class, for a
    single model. Raises KeyError if model_name isn't in curves["pr"]."""
    class_curves = curves["pr"][model_name]
    fig = go.Figure()
    for cls, d in class_curves.items():
        fig.add_trace(go.Scatter(x=d["recall"], y=d["precision"], mode="lines", name=f"{cls} (AP={d['ap']:.3f})"))
    macro = curves.get("macro_ap", {}).get(model_name)
    title = f"Precision-Recall Curves ({model_name}, one-vs-rest)"
    if macro is not None:
        title += f" — macro-AP {macro:.3f}"
    fig.update_layout(
        title=title, xaxis_title="Recall", yaxis_title="Precision",
        margin=dict(t=50, b=10, l=10, r=10), yaxis_range=[0, 1.02],
    )
    return fig


def multiclass_roc_pr_verdict(curves: Optional[dict]) -> str:
    """Plain-English read of the one-vs-rest macro-AUC for the Random
    Forest model (falls back to whichever model is present), naming the
    single worst-performing class by per-class AUC — the class most likely
    to be getting confused with the others, and the one worth digging into
    first via the confusion matrix.
    """
    if not curves or not curves.get("roc"):
        return ""

    model_name = "Random Forest" if "Random Forest" in curves["roc"] else next(iter(curves["roc"]))
    per_class_auc = {cls: d["auc"] for cls, d in curves["roc"][model_name].items()}
    macro_auc = curves.get("macro_auc", {}).get(model_name)
    if macro_auc is None or not per_class_auc:
        return ""

    band = _roc_auc_band(macro_auc)
    worst_class = min(per_class_auc, key=per_class_auc.get)
    worst_auc = per_class_auc[worst_class]

    parts = [f"{model_name}: macro-average ROC-AUC {macro_auc:.3f} across {len(per_class_auc)} classes ({band})."]
    parts.append(f"Weakest class: '{worst_class}' (AUC {worst_auc:.3f}) — most likely to be confused with the others.")
    return " ".join(parts)


def build_feature_importance_chart(importances: pd.Series, top_n: int = 15) -> go.Figure:
    top = importances.head(top_n).sort_values(ascending=True)
    fig = px.bar(
        x=top.values, y=top.index, orientation="h",
        labels={"x": "Importance", "y": "Feature"}, title="Feature Importance (Random Forest)",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


# ==========================================================================
# 11. Class Imbalance Detector
# ==========================================================================

IMBALANCE_MINORITY_THRESHOLD_PCT = 20.0


def check_class_imbalance(y: pd.Series) -> dict:
    """Class distribution + whether the minority class is under the imbalance threshold."""
    counts = y.value_counts()
    proportions = (counts / counts.sum() * 100).round(1)
    minority_pct = float(proportions.min())
    return {
        "counts": counts.to_dict(),
        "proportions_pct": proportions.to_dict(),
        "minority_pct": minority_pct,
        "is_imbalanced": minority_pct < IMBALANCE_MINORITY_THRESHOLD_PCT,
    }


def imbalance_explanation(imbalance_info: dict) -> str:
    return (
        f"The minority class is only {imbalance_info['minority_pct']}% of the data — a model that "
        "always predicts the majority class would still score high on accuracy without learning "
        "anything useful. F1/recall are shown as the headline metric instead, since they penalize "
        "ignoring the minority class."
    )


def build_class_distribution_chart(imbalance_info: dict) -> go.Figure:
    counts = imbalance_info["counts"]
    fig = px.bar(
        x=[str(k) for k in counts.keys()], y=list(counts.values()),
        labels={"x": "Class", "y": "Count"}, title="Class Distribution",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


# ==========================================================================
# 12. SHAP Explainability
# ==========================================================================

# SHAP's max_display default (10) hides features past the top handful even
# on datasets with many columns — 15 matches the Feature Importance chart
# above so the two views describe the same set of columns.
SHAP_MAX_DISPLAY = 15


def explain_with_shap(model, X_background: np.ndarray, X_explain: np.ndarray, feature_names: list[str]):
    """Build a SHAP Explainer for `model` and compute SHAP values for
    X_explain (the test set) using X_background (the training set) as the
    reference distribution for perturbation. shap.Explainer auto-selects
    the right algorithm per model type (TreeExplainer for Random Forest —
    fast and exact; LinearExplainer for Logistic/Linear Regression).

    Raises on incompatible models/inputs rather than swallowing the error —
    callers should wrap this in try/except, since SHAP's supported-model
    surface and output shape genuinely vary by algorithm, and a raised
    exception with the real message is more useful than this function
    guessing at a fallback.
    """
    import shap
    from scipy import sparse

    # run_baseline_models' preprocessing pipeline one-hot-encodes categorical
    # features as a sparse matrix — fine for sklearn's own fit/predict, but
    # SHAP's TreeExplainer C extension raises a low-level array error on
    # sparse input for its background-data perturbation path. Densifying
    # here (SHAP's own input, not the model pipeline's) keeps this local to
    # explainability instead of changing memory behavior for every model run.
    if sparse.issparse(X_background):
        X_background = X_background.toarray()
    if sparse.issparse(X_explain):
        X_explain = X_explain.toarray()

    explainer = shap.Explainer(model, X_background, feature_names=feature_names)
    try:
        return explainer(X_explain)
    except shap.utils._exceptions.ExplainerError:
        # TreeExplainer's additivity check (SHAP values should sum to the
        # model's output) is a known false-positive on RandomForest: summing
        # many trees' averaged predictions accumulates floating-point error
        # past the check's tolerance even when the SHAP values themselves
        # are computed correctly. Confirmed by reproducing it directly
        # against this app's own sample data — not a real inconsistency,
        # just an overly strict sanity check for ensemble averaging.
        return explainer(X_explain, check_additivity=False)


def shap_for_display(shap_values):
    """Collapse a multi-class SHAP Explanation (shape: samples x features x
    classes) down to the single class SHAP's own plotting functions expect
    (samples x features) — picks the class with the largest mean |SHAP
    value|, i.e. the class the model's decisions hinge on most. Binary
    classification and regression Explanations are already 2D and pass
    through unchanged.
    """
    values = getattr(shap_values, "values", None)
    if values is not None and values.ndim == 3:
        class_idx = int(np.abs(values).mean(axis=(0, 1)).argmax())
        return shap_values[:, :, class_idx]
    return shap_values


# ==========================================================================
# 13. Feature Selection Engine
# ==========================================================================

# Same self-verifying-ensemble pattern already used for anomaly detection
# (see `modules.anomaly.find_anomalies_ensemble`) applied to feature
# selection: cross-check three methods built on different assumptions
# instead of trusting any single one's ranking.
FEATURE_SELECTION_MIN_FEATURES = 2


def run_feature_selection(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    task_type: str,
    top_k: Optional[int] = None,
) -> dict:
    """Cross-check three independent feature-selection methods over the same
    preprocessed feature matrix:

    - **Mutual Information** — a nonlinear, model-free measure of
      dependency between each feature and the target (catches
      relationships a linear method would miss).
    - **L1-regularized linear model** (Lasso for regression,
      L1-penalized Logistic Regression for classification) — sparsity-
      inducing coefficients that zero out weak features outright.
    - **Recursive Feature Elimination** with a Random Forest estimator —
      a wrapper method that accounts for feature interactions a filter
      method can't see.

    Each method ranks every (preprocessed) feature; a feature's
    `consensus_votes` (0-3) counts how many methods place it in their own
    top `top_k`, and `consensus_rank` is the mean of the three individual
    ranks — so a feature no single method rates highly still gets a fair
    composite score if the others agree on it.

    Returns {
      "task_type", "top_k", "n_features",
      "ranking": DataFrame indexed by preprocessed feature name (one-hot
        columns are expanded, same as `run_baseline_models`'
        `feature_importances`) with columns [mutual_info,
        mutual_info_rank, l1_coef_abs, l1_rank, rfe_selected, rfe_rank,
        consensus_votes, consensus_rank], sorted by consensus_votes desc
        then consensus_rank asc,
      "recommended_features": list[str],  # top_k feature names by that sort
    }
    or {"error": ...} if there aren't enough usable features.
    """
    if len(feature_cols) < FEATURE_SELECTION_MIN_FEATURES:
        return {"error": f"Feature Selection needs at least {FEATURE_SELECTION_MIN_FEATURES} feature columns."}

    from scipy import sparse
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.feature_selection import RFE, mutual_info_classif, mutual_info_regression
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Lasso, LassoCV, LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    data = df[feature_cols + [target_col]].dropna(subset=[target_col])
    X = data[feature_cols]
    y = data[target_col]

    categorical_features = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(X[c])]
    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]

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
    # Mutual info / Lasso / RFE all need a dense matrix for consistent
    # behavior across sklearn versions — same reasoning as SHAP's
    # densify-before-explaining step above; these feature sets are small
    # (Feature Selection is run over a hand-picked subset, not the raw
    # dataset), so the memory cost is negligible.
    if sparse.issparse(X_transformed):
        X_transformed = X_transformed.toarray()
    feature_names = [name.split("__", 1)[-1] for name in preprocessor.get_feature_names_out()]
    n_features = len(feature_names)

    if n_features < FEATURE_SELECTION_MIN_FEATURES:
        return {"error": "Fewer than 2 usable features after preprocessing (check for all-null columns)."}

    k = top_k if top_k is not None else max(1, n_features // 2)
    k = min(k, n_features)

    y_values = y.to_numpy()
    n_samples = X_transformed.shape[0]

    # --- Mutual Information -------------------------------------------
    mi_func = mutual_info_classif if task_type == "classification" else mutual_info_regression
    try:
        mi_scores = mi_func(X_transformed, y_values, random_state=42)
    except ValueError:
        mi_scores = np.zeros(n_features)
    mi_series = pd.Series(mi_scores, index=feature_names)
    mi_rank = mi_series.rank(ascending=False, method="min")

    # --- L1-regularized linear model -----------------------------------
    if task_type == "classification":
        l1_model = LogisticRegression(penalty="l1", solver="liblinear", C=1.0, max_iter=2000)
        l1_model.fit(X_transformed, y_values)
        coefs = np.abs(l1_model.coef_)
        l1_scores = coefs.max(axis=0) if coefs.ndim > 1 else coefs
    else:
        cv_folds = min(5, max(2, n_samples // 5))
        try:
            l1_model = LassoCV(cv=cv_folds, random_state=42, max_iter=10000)
            l1_model.fit(X_transformed, y_values)
        except ValueError:
            # too few samples for the requested CV split — fall back to a
            # single fixed-alpha fit rather than failing the whole run
            l1_model = Lasso(alpha=0.01, max_iter=10000)
            l1_model.fit(X_transformed, y_values)
        l1_scores = np.abs(l1_model.coef_)
    l1_series = pd.Series(l1_scores, index=feature_names)
    l1_rank = l1_series.rank(ascending=False, method="min")

    # --- Recursive Feature Elimination (Random Forest) ------------------
    rf_estimator = (
        RandomForestClassifier(n_estimators=100, random_state=42)
        if task_type == "classification"
        else RandomForestRegressor(n_estimators=100, random_state=42)
    )
    rfe = RFE(estimator=rf_estimator, n_features_to_select=k)
    rfe.fit(X_transformed, y_values)
    rfe_selected = pd.Series(rfe.support_, index=feature_names)
    rfe_rank = pd.Series(rfe.ranking_, index=feature_names)

    ranking = pd.DataFrame(
        {
            "mutual_info": mi_series,
            "mutual_info_rank": mi_rank,
            "l1_coef_abs": l1_series,
            "l1_rank": l1_rank,
            "rfe_selected": rfe_selected,
            "rfe_rank": rfe_rank,
        }
    )
    ranking["consensus_votes"] = (
        (ranking["mutual_info_rank"] <= k).astype(int)
        + (ranking["l1_rank"] <= k).astype(int)
        + ranking["rfe_selected"].astype(int)
    )
    ranking["consensus_rank"] = ranking[["mutual_info_rank", "l1_rank", "rfe_rank"]].mean(axis=1)
    ranking = ranking.sort_values(["consensus_votes", "consensus_rank"], ascending=[False, True])

    return {
        "task_type": task_type,
        "top_k": k,
        "n_features": n_features,
        "ranking": ranking,
        "recommended_features": ranking.head(k).index.tolist(),
    }


def build_feature_selection_chart(ranking: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Horizontal bar chart of consensus votes (0-3) for the top-ranked features."""
    top = ranking.sort_values("consensus_rank", ascending=True).head(top_n)
    top = top.sort_values("consensus_votes", ascending=True)
    fig = px.bar(
        x=top["consensus_votes"], y=top.index, orientation="h",
        labels={"x": "Methods agreeing (of 3)", "y": "Feature"},
        title="Feature Selection Consensus (Mutual Info + L1 + RFE)",
        range_x=[0, 3],
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


# ==========================================================================
# 14. Conformal Prediction — regression uncertainty quantification
# ==========================================================================

# Split-conformal prediction (Lei et al., "Distribution-Free Predictive
# Inference"): fit a model on a training fold, score its residuals on a
# *separate* held-out calibration fold, then widen every future point
# prediction by the (1-alpha) empirical quantile of those calibration
# residuals. Unlike the parametric confidence bands statsmodels gives
# `regression_diagnostics`/`forecasting`, this makes no distributional
# assumption about the residuals (no normality requirement) — it only
# assumes the calibration and test data are exchangeable, which is why
# the calibration split has to come from the same fit-time data rather
# than being computed in-sample. The resulting interval width is
# constant across test points (absolute-residual nonconformity, the
# simplest and most standard split-conformal scorer); that's a real
# limitation — it doesn't adapt to points with wider true uncertainty —
# but it comes with a genuine finite-sample marginal coverage guarantee,
# which parametric bands only get exactly right when their distributional
# assumptions hold.
CONFORMAL_MIN_ROWS = 60  # need enough rows split three ways (train/calib/test) for the quantile to be meaningful


def run_conformal_regression(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    alpha: float = 0.1,
    random_state: int = 42,
) -> dict:
    """Fit a Random Forest regressor and compute split-conformal prediction
    intervals at the (1-alpha) coverage level.

    Returns {"alpha", "target_coverage", "empirical_coverage",
    "mean_interval_width", "quantile", "n_train", "n_calib", "n_test",
    "predictions": DataFrame[actual, predicted, lower, upper] sorted by
    predicted value} on success, or {"error": str} on any failure
    (non-numeric target, all-null target, too few usable rows, or an
    invalid alpha) — never raises.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    if not (0.0 < alpha < 1.0):
        return {"error": f"alpha must be between 0 and 1 (exclusive), got {alpha}."}

    if target_col not in df.columns or not pd.api.types.is_numeric_dtype(df[target_col]):
        return {"error": "Conformal prediction intervals require a numeric target column."}

    data = df[feature_cols + [target_col]].dropna()
    if len(data) < CONFORMAL_MIN_ROWS:
        return {
            "error": (
                f"Need at least {CONFORMAL_MIN_ROWS} complete rows to split into train/calibration/test "
                f"sets for conformal prediction — only {len(data)} available after dropping missing values."
            )
        }

    X = data[feature_cols]
    y = data[target_col]

    categorical_features = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(X[c])]
    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]

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

    # 60/20/20 train/calibration/test — the calibration split must be held
    # out from *training*, not carved from the test set, so the residual
    # quantile is computed on data the model never saw fitting-wise.
    X_trainfull, X_test, y_trainfull, y_test = train_test_split(X, y, test_size=0.2, random_state=random_state)
    X_train, X_calib, y_train, y_calib = train_test_split(X_trainfull, y_trainfull, test_size=0.25, random_state=random_state)

    X_train_t = preprocessor.fit_transform(X_train)
    X_calib_t = preprocessor.transform(X_calib)
    X_test_t = preprocessor.transform(X_test)

    model = RandomForestRegressor(n_estimators=200, random_state=random_state)
    model.fit(X_train_t, y_train)

    calib_preds = model.predict(X_calib_t)
    nonconformity = np.abs(y_calib.to_numpy() - calib_preds)

    n_calib = len(nonconformity)
    # Finite-sample-corrected quantile level (Romano/Candès): ceil((n+1)(1-alpha))/n,
    # clipped to 1.0 for small calibration sets where that would exceed 1.
    q_level = min(1.0, np.ceil((n_calib + 1) * (1 - alpha)) / n_calib)
    quantile = float(np.quantile(nonconformity, q_level, method="higher"))

    test_preds = model.predict(X_test_t)
    lower = test_preds - quantile
    upper = test_preds + quantile
    empirical_coverage = float(np.mean((y_test.to_numpy() >= lower) & (y_test.to_numpy() <= upper)))

    predictions = pd.DataFrame(
        {"actual": y_test.to_numpy(), "predicted": test_preds, "lower": lower, "upper": upper},
        index=y_test.index,
    ).sort_values("predicted")

    return {
        "alpha": alpha,
        "target_coverage": round(1 - alpha, 4),
        "empirical_coverage": round(empirical_coverage, 4),
        "mean_interval_width": round(2 * quantile, 4),
        "quantile": quantile,
        "n_train": len(X_train),
        "n_calib": n_calib,
        "n_test": len(X_test),
        "predictions": predictions,
    }


def build_conformal_chart(result: dict) -> go.Figure:
    """Predictions sorted by predicted value, with the constant-width
    conformal interval as a shaded band and actual values overlaid as
    points — makes it easy to see at a glance how many actuals fall
    outside the band (roughly `alpha` fraction, by construction).
    """
    preds = result["predictions"]
    x = list(range(len(preds)))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x + x[::-1],
            y=list(preds["upper"]) + list(preds["lower"])[::-1],
            fill="toself",
            fillcolor="rgba(0, 229, 255, 0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name=f"{int(result['target_coverage'] * 100)}% interval",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(x=x, y=preds["predicted"], mode="lines", name="Predicted", line=dict(color="#00e5ff")))
    fig.add_trace(
        go.Scatter(
            x=x, y=preds["actual"], mode="markers", name="Actual",
            marker=dict(size=5, color="#ff6b9d", opacity=0.7),
        )
    )
    fig.update_layout(
        title="Conformal Prediction Intervals — test set, sorted by predicted value",
        xaxis_title="Test row (sorted by predicted value)",
        yaxis_title="Target",
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def conformal_verdict(result: dict) -> str:
    """Plain-English summary of a conformal prediction run — target vs.
    empirical coverage, and interval width. Handles an error result
    gracefully instead of raising, since UI code can call this without
    checking "error" first.
    """
    if "error" in result:
        return f"Couldn't compute prediction intervals: {result['error']}"

    target_pct = result["target_coverage"] * 100
    empirical_pct = result["empirical_coverage"] * 100
    gap = abs(empirical_pct - target_pct)
    quality = "closely matches" if gap <= 5 else ("is reasonably close to" if gap <= 10 else "diverges notably from")

    return (
        f"Targeting {target_pct:.0f}% coverage, the actual test-set coverage was {empirical_pct:.1f}% — "
        f"this {quality} the target (small gaps are expected on a single test split; conformal prediction's "
        f"guarantee is on average across repeated splits, not exact on any one). Each prediction gets a "
        f"fixed-width interval of ±{result['quantile']:.3g} ({result['mean_interval_width']:.3g} total width), "
        f"built from {result['n_train']} training rows and calibrated on {result['n_calib']} held-out rows."
    )


# ==========================================================================
# 15. K-Fold Cross-Validation — replaces the noisy single 80/20 split
# ==========================================================================

# `run_baseline_models()` above reports metrics off exactly one train/test
# split; on a small-to-medium dataset that single split's metrics can swing
# noticeably depending on which rows happened to land in the test fold.
# This runs the same two baseline models through proper k-fold
# cross-validation instead — a fresh preprocessing fit *inside every fold*
# (via a single sklearn Pipeline passed to `cross_validate`, never fit
# once up front) so there's no leakage between folds — and reports mean
# +/- std per metric, which is the actual standard a hiring-panel-caliber
# reviewer expects before trusting a single-split number.
CV_MIN_ROWS = 20
CV_MIN_K = 2


def run_cross_validation(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    task_type: str,
    k: int = 5,
    random_state: int = 42,
) -> dict:
    """K-fold (StratifiedKFold for classification, KFold for regression)
    cross-validation of the same Baseline (Logistic/Linear Regression) and
    Random Forest models `run_baseline_models` compares, scored via
    `sklearn.model_selection.cross_validate` over a single Pipeline so
    preprocessing is refit inside every fold.

    Returns {"task_type", "k" (the k actually used, after any reduction),
    "k_requested", "k_reduced" (bool), "n_samples", "results": {model_name:
    {metric_name: {"mean", "std", "scores": [per-fold values]}}}} on
    success, or {"error": str} on any failure — never raises. For
    classification, k is silently reduced to the rarest class's member
    count when the requested k exceeds it (StratifiedKFold's own
    requirement), flagged via "k_reduced".
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.model_selection import KFold, StratifiedKFold, cross_validate
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    if not feature_cols:
        return {"error": "Pick at least one feature column to cross-validate."}
    if k < CV_MIN_K:
        return {"error": f"k must be at least {CV_MIN_K}."}
    if target_col not in df.columns:
        return {"error": f"Target column '{target_col}' not found."}

    data = df[feature_cols + [target_col]].dropna()
    if len(data) < CV_MIN_ROWS:
        return {
            "error": (
                f"Need at least {CV_MIN_ROWS} complete rows for cross-validation — "
                f"only {len(data)} available after dropping missing values."
            )
        }

    X = data[feature_cols]
    y = data[target_col]

    k_requested = k
    k_reduced = False

    if task_type == "classification":
        class_counts = y.value_counts()
        if len(class_counts) < 2:
            return {"error": "The target has only one class — nothing to cross-validate."}
        min_class_count = int(class_counts.min())
        if min_class_count < CV_MIN_K:
            return {
                "error": (
                    f"The rarest class in the target has only {min_class_count} row(s) — each class needs "
                    f"at least {CV_MIN_K} for cross-validation."
                )
            }
        if k > min_class_count:
            k = min_class_count
            k_reduced = True
        splitter = StratifiedKFold(n_splits=k, shuffle=True, random_state=random_state)
    else:
        if len(data) < 2 * k:
            return {"error": f"Need at least {2 * k} rows to run {k}-fold cross-validation ({len(data)} available)."}
        splitter = KFold(n_splits=k, shuffle=True, random_state=random_state)

    categorical_features = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(X[c])]
    numeric_features = [c for c in feature_cols if pd.api.types.is_numeric_dtype(X[c])]

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

    if task_type == "classification":
        models = {
            "Baseline": LogisticRegression(max_iter=1000),
            "Random Forest": RandomForestClassifier(n_estimators=200, random_state=random_state),
        }
        scoring = {"accuracy": "accuracy", "f1": "f1_weighted"}
    else:
        models = {
            "Baseline": LinearRegression(),
            "Random Forest": RandomForestRegressor(n_estimators=200, random_state=random_state),
        }
        scoring = {"rmse": "neg_root_mean_squared_error", "r2": "r2"}

    results = {}
    try:
        for model_name, model in models.items():
            pipeline = Pipeline([("preprocess", preprocessor), ("model", model)])
            cv_scores = cross_validate(pipeline, X, y, cv=splitter, scoring=list(scoring.values()))
            model_results = {}
            for display_name, sklearn_name in scoring.items():
                raw_scores = cv_scores[f"test_{sklearn_name}"]
                # neg_root_mean_squared_error comes back negative by sklearn convention
                # (so "higher is better" holds uniformly across all scorers) — flip sign for display.
                scores = -raw_scores if sklearn_name.startswith("neg_") else raw_scores
                model_results[display_name] = {
                    "mean": round(float(np.mean(scores)), 4),
                    "std": round(float(np.std(scores)), 4),
                    "scores": [round(float(s), 4) for s in scores],
                }
            results[model_name] = model_results
    except Exception as e:
        return {"error": f"Cross-validation failed: {e}"}

    return {
        "task_type": task_type,
        "k": k,
        "k_requested": k_requested,
        "k_reduced": k_reduced,
        "n_samples": len(data),
        "results": results,
    }


def build_cv_score_chart(result: dict, metric: str) -> go.Figure:
    """Box plot of per-fold scores for `metric`, one box per model — makes
    fold-to-fold spread (the whole point of cross-validating) visible
    instead of collapsing straight to a mean.
    """
    fig = go.Figure()
    for model_name, model_results in result["results"].items():
        if metric in model_results:
            fig.add_trace(go.Box(y=model_results[metric]["scores"], name=model_name, boxpoints="all"))
    fig.update_layout(
        title=f"{result['k']}-Fold Cross-Validation — {metric}",
        yaxis_title=metric,
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def cv_verdict(result: dict) -> str:
    """Plain-English mean +/- std comparison for the primary metric
    (accuracy for classification, R² for regression). Handles an error
    result gracefully instead of raising.
    """
    if "error" in result:
        return f"Couldn't run cross-validation: {result['error']}"

    primary_metric = "accuracy" if result["task_type"] == "classification" else "r2"
    metric_label = "accuracy" if primary_metric == "accuracy" else "R²"

    lines = [
        f"{model_name}: {model_results[primary_metric]['mean']:.4f} ± {model_results[primary_metric]['std']:.4f} {metric_label}"
        for model_name, model_results in result["results"].items()
    ]
    reduction_note = (
        f" (k reduced from {result['k_requested']} to {result['k']} — the rarest class doesn't have enough "
        f"members for {result['k_requested']}-fold stratification)"
        if result.get("k_reduced")
        else ""
    )
    return (
        f"{result['k']}-fold cross-validation on {result['n_samples']} rows{reduction_note}: " + "; ".join(lines) +
        ". A mean +/- std across folds is a far more reliable estimate of real-world performance than any "
        "single train/test split, which can swing significantly just from which rows happened to land in "
        "the test set."
    )
