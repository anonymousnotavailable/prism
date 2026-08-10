"""
Feature Selection Engine — ranks candidate features against a chosen target
by mutual information, flags redundant near-duplicate pairs by pairwise
correlation, and flags multicollinearity via VIF (variance inflation
factor). Complements ML Lab's Feature Engineering Assistant (which suggests
encodings/scalings for features you keep) by answering the earlier
question: which features are actually worth keeping in the first place.

Mutual information (not correlation) drives the primary ranking because it
also catches non-linear relationships a correlation coefficient would miss
entirely — a feature can score 0 correlation with the target and still be
highly informative. VIF is the standard statistical multicollinearity
diagnostic (a value above ~10 signals a feature is redundant with a *linear
combination* of others, which a pairwise correlation check alone can miss —
see test_flags_high_multicollinearity_via_vif).
"""

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
    from sklearn.preprocessing import LabelEncoder
except ImportError:  # the app should still load even if the package isn't installed yet
    mutual_info_classif = mutual_info_regression = LabelEncoder = None

try:
    from statsmodels.stats.outliers_influence import variance_inflation_factor
except ImportError:
    variance_inflation_factor = None

MIN_ROWS_REQUIRED = 20
HIGH_CORRELATION_THRESHOLD = 0.85
HIGH_VIF_THRESHOLD = 10.0
MAX_VIF_CANDIDATE_COLUMNS = 30  # VIF is O(n_cols^2); guard against pathologically wide datasets


def is_available() -> bool:
    """Whether scikit-learn and statsmodels are both installed."""
    return mutual_info_classif is not None and variance_inflation_factor is not None


def _encode_for_mi(series: pd.Series, column_types: dict[str, str], col: str) -> tuple[np.ndarray, bool]:
    """Return (encoded_values, is_discrete) for one candidate/target column.

    Numeric columns pass through with NaNs filled by the median. Everything
    else (categorical/text/datetime) is label-encoded — mutual_info_*
    needs numeric input either way, and marks it 'discrete' so sklearn
    treats it as categorical rather than assuming an ordinal scale.
    """
    if column_types.get(col) == "numeric":
        values = pd.to_numeric(series, errors="coerce")
        values = values.fillna(values.median())
        return values.to_numpy(dtype=float), False

    filled = series.astype(str).fillna("__missing__")
    encoded = LabelEncoder().fit_transform(filled)
    return encoded, True


def rank_features(
    df: pd.DataFrame, column_types: dict[str, str], target_col: str
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Rank every non-target column by mutual information with `target_col`,
    flag redundant near-duplicate pairs, and flag multicollinearity via VIF.

    Returns (ranking_df, error). ranking_df has one row per candidate
    feature, columns: Feature, MI Score, Correlation Peak, VIF,
    Recommendation ("Keep" | "Redundant" | "High multicollinearity").
    Sorted by MI Score descending. error is set only when ranking couldn't
    run at all (missing deps, missing target, too few rows, no candidates).
    """
    if not is_available():
        return None, "scikit-learn and statsmodels are required. Run `pip install -r requirements.txt` and restart."

    if target_col not in df.columns:
        return None, f"'{target_col}' is not a column in this dataset."

    candidate_cols = [c for c in df.columns if c != target_col]
    if not candidate_cols:
        return None, "No candidate feature columns — the dataset has only the target column."

    valid_rows = df[target_col].notna()
    if valid_rows.sum() < MIN_ROWS_REQUIRED:
        return None, f"Not enough non-missing target rows to rank features (need at least {MIN_ROWS_REQUIRED})."

    work = df.loc[valid_rows]

    is_classification = column_types.get(target_col) != "numeric"
    y, _ = _encode_for_mi(work[target_col], column_types, target_col)

    X_cols, discrete_mask = [], []
    for col in candidate_cols:
        encoded, is_discrete = _encode_for_mi(work[col], column_types, col)
        X_cols.append(encoded)
        discrete_mask.append(is_discrete)
    X = np.column_stack(X_cols)

    mi_func = mutual_info_classif if is_classification else mutual_info_regression
    try:
        mi_scores = mi_func(X, y, discrete_features=discrete_mask, random_state=42)
    except ValueError as e:
        return None, f"Couldn't compute mutual information: {e}"

    # Pairwise correlation among numeric candidates only — used to flag
    # near-duplicate features (a categorical-vs-numeric or categorical-vs-
    # categorical "correlation" isn't a well-defined single number here,
    # so redundancy flagging is scoped to numeric pairs, same convention
    # ML Lab's Feature Engineering Assistant already uses for interactions).
    numeric_candidates = [c for c in candidate_cols if column_types.get(c) == "numeric"]
    redundant_partner: dict[str, tuple[str, float]] = {}
    if len(numeric_candidates) >= 2:
        corr_matrix = work[numeric_candidates].corr().abs()
        mi_by_col = dict(zip(candidate_cols, mi_scores))
        for i, col_a in enumerate(numeric_candidates):
            for col_b in numeric_candidates[i + 1 :]:
                value = corr_matrix.loc[col_a, col_b]
                if pd.isna(value) or value < HIGH_CORRELATION_THRESHOLD:
                    continue
                # the lower-MI column of the pair is the redundant one
                loser = col_a if mi_by_col[col_a] < mi_by_col[col_b] else col_b
                winner, value_f = (col_b, float(value)) if loser == col_a else (col_a, float(value))
                prev = redundant_partner.get(loser)
                if prev is None or value_f > prev[1]:
                    redundant_partner[loser] = (winner, value_f)

    vif_by_col: dict[str, Optional[float]] = {c: None for c in candidate_cols}
    if 2 <= len(numeric_candidates) <= MAX_VIF_CANDIDATE_COLUMNS:
        vif_matrix = work[numeric_candidates].fillna(work[numeric_candidates].median())
        # constant columns (zero variance) make VIF singular/undefined — drop them from the design matrix
        vif_matrix = vif_matrix.loc[:, vif_matrix.nunique(dropna=True) > 1]
        if vif_matrix.shape[1] >= 2:
            try:
                for i, col in enumerate(vif_matrix.columns):
                    vif_by_col[col] = float(variance_inflation_factor(vif_matrix.to_numpy(dtype=float), i))
            except (np.linalg.LinAlgError, ValueError):
                pass  # singular design matrix — leave VIF as None for all rather than fail the whole ranking

    rows = []
    for col, mi_score in zip(candidate_cols, mi_scores):
        vif = vif_by_col.get(col)
        redundancy = redundant_partner.get(col)
        if redundancy is not None:
            recommendation = "Redundant"
        elif vif is not None and vif > HIGH_VIF_THRESHOLD:
            recommendation = "High multicollinearity"
        else:
            recommendation = "Keep"
        rows.append(
            {
                "Feature": col,
                "MI Score": round(float(mi_score), 4),
                "Correlation Peak": f"{redundancy[0]} ({redundancy[1]:.2f})" if redundancy else "—",
                "VIF": round(vif, 2) if vif is not None else None,
                "Recommendation": recommendation,
            }
        )

    ranking = pd.DataFrame(rows).sort_values("MI Score", ascending=False).reset_index(drop=True)
    return ranking, None


def recommended_features(ranking: Optional[pd.DataFrame]) -> list[str]:
    """The subset of ranked features worth keeping — excludes anything
    flagged Redundant, keeps everything else (High multicollinearity is
    still surfaced to the user, not silently dropped, since VIF alone
    doesn't say which of several collinear features to cut).
    """
    if ranking is None or ranking.empty:
        return []
    return ranking.loc[ranking["Recommendation"] != "Redundant", "Feature"].tolist()


def fingerprint_ranking(ranking: Optional[pd.DataFrame], target_col: str) -> str:
    """Stable hash of a rank_features() result, for caching the AI
    narration below the same way anomaly.fingerprint_flagged() does.
    """
    if ranking is None or ranking.empty:
        return f"empty|{target_col}"
    # dict records, not itertuples — itertuples renames non-identifier column
    # names like "MI Score" to positional fields (_1, _2, ...), so r['MI Score']
    # raises TypeError: tuple indices must be integers or slices, not str.
    parts = sorted(f"{r['Feature']}:{r['MI Score']}:{r['Recommendation']}" for r in ranking.to_dict("records"))
    key = f"{target_col}|" + "|".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data scientist explaining a feature-selection result to a colleague. "
    "The target column is '{target}'. Features were ranked by mutual information against it, "
    "with redundant/multicollinear features flagged. Top features by score:\n\n{table_text}\n\n"
    "In 3-4 sentences: explain which features look most worth keeping and why, call out any "
    "redundant or multicollinear ones worth dropping, and suggest one concrete next step. "
    "Do not simply restate the numbers back."
)


def narrate_selection(model, ranking: Optional[pd.DataFrame], target_col: str) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn a rank_features() result into a short plain-
    English explanation + suggested next step.

    Returns (narration, error), same contract as anomaly.narrate_anomalies —
    callers should cache the result keyed by fingerprint_ranking() to avoid
    re-spending a Gemini call on a result already narrated.
    """
    if ranking is None or ranking.empty:
        return f"No features were ranked against '{target_col}' — nothing to narrate.", None
    if model is None:
        return "", "No Gemini model available for narration."

    from modules.ai_analyst import call_gemini

    top = ranking.head(8)
    table_text = "\n".join(
        f"- {r['Feature']}: MI={r['MI Score']}, {r['Recommendation']}"
        + (f", correlated with {r['Correlation Peak']}" if r["Recommendation"] == "Redundant" else "")
        for r in top.to_dict("records")
    )
    prompt = _NARRATION_PROMPT.format(target=target_col, table_text=table_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
