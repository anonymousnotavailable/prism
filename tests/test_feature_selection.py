"""Tests for modules.feature_selection — mutual-information feature ranking,
pairwise-correlation redundancy pruning, and VIF multicollinearity flagging
for the ML Lab tab's Feature Selection Engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import feature_selection


def _rng():
    return np.random.default_rng(0)


def test_is_available_true_when_deps_installed():
    # sklearn + statsmodels are both in requirements.txt / requirements-dev.txt
    assert feature_selection.is_available() is True


def test_ranks_informative_feature_above_pure_noise():
    rng = _rng()
    n = 300
    x_informative = rng.normal(size=n)
    target = x_informative * 3 + rng.normal(scale=0.2, size=n)
    df = pd.DataFrame(
        {
            "informative": x_informative,
            "noise": rng.normal(size=n),
            "target": target,
        }
    )
    column_types = {"informative": "numeric", "noise": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    assert ranking is not None
    informative_score = ranking.loc[ranking["Feature"] == "informative", "MI Score"].iloc[0]
    noise_score = ranking.loc[ranking["Feature"] == "noise", "MI Score"].iloc[0]
    assert informative_score > noise_score


def test_flags_redundant_correlated_pair():
    rng = _rng()
    n = 300
    base = rng.normal(size=n)
    target = base * 2 + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame(
        {
            "original": base,
            # near-duplicate of 'original' — should be flagged redundant against it
            "duplicate": base + rng.normal(scale=0.01, size=n),
            "target": target,
        }
    )
    column_types = {"original": "numeric", "duplicate": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    redundant_rows = ranking[ranking["Recommendation"] == "Redundant"]
    assert len(redundant_rows) == 1
    assert redundant_rows.iloc[0]["Feature"] in {"original", "duplicate"}


def test_flags_high_multicollinearity_via_vif():
    rng = _rng()
    n = 300
    a = rng.normal(size=n)
    b = rng.normal(size=n)
    # 'combo' is (almost) an exact linear combination of a and b — classic
    # multicollinearity case that a pairwise-correlation check alone would miss
    # (it need not be highly correlated with EITHER a or b individually).
    combo = a * 0.5 + b * 0.5 + rng.normal(scale=0.001, size=n)
    target = a + b + rng.normal(scale=0.5, size=n)
    df = pd.DataFrame({"a": a, "b": b, "combo": combo, "target": target})
    column_types = {"a": "numeric", "b": "numeric", "combo": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    vif_values = ranking.set_index("Feature")["VIF"]
    assert vif_values.notna().any()
    assert (vif_values.dropna() > feature_selection.HIGH_VIF_THRESHOLD).any()


def test_works_with_categorical_target_classification():
    rng = _rng()
    n = 200
    x = rng.normal(size=n)
    target = pd.Series(np.where(x > 0, "yes", "no"))
    df = pd.DataFrame({"x": x, "noise": rng.normal(size=n), "target": target})
    column_types = {"x": "numeric", "noise": "numeric", "target": "categorical"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    assert ranking is not None
    x_score = ranking.loc[ranking["Feature"] == "x", "MI Score"].iloc[0]
    noise_score = ranking.loc[ranking["Feature"] == "noise", "MI Score"].iloc[0]
    assert x_score > noise_score


def test_categorical_candidate_features_are_encoded_and_ranked():
    rng = _rng()
    n = 200
    cat = pd.Series(rng.choice(["a", "b", "c"], size=n))
    target = cat.map({"a": 1.0, "b": 5.0, "c": 9.0}) + rng.normal(scale=0.1, size=n)
    df = pd.DataFrame({"cat": cat, "target": target})
    column_types = {"cat": "categorical", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    assert "cat" in ranking["Feature"].tolist()


def test_returns_error_for_too_few_rows():
    df = pd.DataFrame({"x": [1, 2, 3], "target": [1, 2, 3]})
    column_types = {"x": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert ranking is None
    assert error is not None


def test_returns_error_when_no_candidate_features():
    df = pd.DataFrame({"target": list(range(50))})
    column_types = {"target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert ranking is None
    assert error is not None


def test_returns_error_for_missing_target():
    df = pd.DataFrame({"x": list(range(50)), "y": list(range(50))})
    column_types = {"x": "numeric", "y": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "not_a_column")
    assert ranking is None
    assert error is not None


def test_recommended_features_excludes_redundant_and_low_mi():
    rng = _rng()
    n = 300
    base = rng.normal(size=n)
    target = base * 2 + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame(
        {
            "original": base,
            "duplicate": base + rng.normal(scale=0.01, size=n),
            "noise": rng.normal(size=n),
            "target": target,
        }
    )
    column_types = {"original": "numeric", "duplicate": "numeric", "noise": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    recommended = feature_selection.recommended_features(ranking)
    assert "duplicate" not in recommended
    assert "original" in recommended


def test_narrate_selection_requires_model():
    df = pd.DataFrame({"Feature": ["x"], "MI Score": [0.5], "Recommendation": ["Keep"]})
    text, error = feature_selection.narrate_selection(None, df, "target")
    assert text == ""
    assert error is not None


def test_narrate_selection_handles_empty_ranking():
    text, error = feature_selection.narrate_selection(object(), pd.DataFrame(), "target")
    assert error is None
    assert "target" in text.lower() or text


def _sample_ranking():
    """A realistic rank_features()-shaped DataFrame — columns include ones
    with spaces ("MI Score", "Correlation Peak"), the exact shape that
    broke itertuples-based row access (r['MI Score'] on a namedtuple).
    """
    return pd.DataFrame(
        [
            {"Feature": "a", "MI Score": 0.91, "Correlation Peak": "b (0.90)", "VIF": 12.3, "Recommendation": "Redundant"},
            {"Feature": "b", "MI Score": 0.85, "Correlation Peak": "—", "VIF": None, "Recommendation": "Keep"},
        ]
    )


def test_fingerprint_ranking_handles_real_column_names_with_spaces():
    # Regression test: itertuples() renames non-identifier column names
    # ("MI Score") to positional fields, so r['MI Score'] used to raise
    # TypeError: tuple indices must be integers or slices, not str.
    fp = feature_selection.fingerprint_ranking(_sample_ranking(), "target")
    assert isinstance(fp, str) and len(fp) == 40  # sha1 hexdigest length
    # same input -> same fingerprint (order-independent to row reordering isn't required, but stable for same df)
    assert fp == feature_selection.fingerprint_ranking(_sample_ranking(), "target")


def test_excludes_id_like_columns_from_ranking():
    # Regression test for a Codex review finding: label-encoding a
    # near-unique identifier column and scoring it as an ordinary discrete
    # feature lets mutual information assign it close to the target's full
    # entropy (it "predicts" the target as well as memorizing the row
    # does) — reads as maximally informative and would get recommended
    # straight into the model. customer_id should never appear at all.
    rng = _rng()
    n = 200
    x = rng.normal(size=n)
    target = x * 2 + rng.normal(scale=0.3, size=n)
    df = pd.DataFrame(
        {
            "customer_id": [f"CUST-{i:05d}" for i in range(n)],
            "x": x,
            "target": target,
        }
    )
    column_types = {"customer_id": "categorical", "x": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    assert "customer_id" not in ranking["Feature"].tolist()
    assert "x" in ranking["Feature"].tolist()


def test_returns_error_when_only_id_like_candidates_remain():
    n = 200
    df = pd.DataFrame({"customer_id": [f"CUST-{i:05d}" for i in range(n)], "target": list(range(n))})
    column_types = {"customer_id": "categorical", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert ranking is None
    assert error is not None


def test_vif_not_inflated_by_uncentered_positive_mean_columns():
    # Regression test for a Codex review finding: variance_inflation_factor
    # needs an intercept in the design matrix. Two independent columns with
    # large positive means (not centered near zero) get wildly inflated
    # VIFs without one, despite having near-zero correlation once centered.
    rng = _rng()
    n = 300
    a = 100 + rng.normal(size=n)
    b = 100 + rng.normal(size=n)
    target = rng.normal(size=n)  # unrelated to a/b — VIF is about the FEATURES' relationship to each other
    df = pd.DataFrame({"a": a, "b": b, "target": target})
    column_types = {"a": "numeric", "b": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    vif_values = ranking.set_index("Feature")["VIF"]
    assert vif_values.notna().all()
    assert (vif_values < feature_selection.HIGH_VIF_THRESHOLD).all()
    assert not (ranking["Recommendation"] == "High multicollinearity").any()


def test_uses_classification_mi_for_low_cardinality_numeric_target():
    # Regression test for a Codex review finding: a numeric column with a
    # handful of distinct values (e.g. a 0/1/2 class code) is a
    # classification target even though data_engine types it "numeric" —
    # mutual_info_regression should not be used for it.
    calls = []
    original_classif = feature_selection.mutual_info_classif
    original_regression = feature_selection.mutual_info_regression

    def spy_classif(*args, **kwargs):
        calls.append("classif")
        return original_classif(*args, **kwargs)

    def spy_regression(*args, **kwargs):
        calls.append("regression")
        return original_regression(*args, **kwargs)

    feature_selection.mutual_info_classif = spy_classif
    feature_selection.mutual_info_regression = spy_regression
    try:
        rng = _rng()
        n = 200
        x = rng.normal(size=n)
        target = pd.Series(np.where(x > 0, 1, 0))  # numeric-coded binary class, low cardinality
        df = pd.DataFrame({"x": x, "target": target})
        column_types = {"x": "numeric", "target": "numeric"}  # data_engine would type this "numeric"
        ranking, error = feature_selection.rank_features(df, column_types, "target")
    finally:
        feature_selection.mutual_info_classif = original_classif
        feature_selection.mutual_info_regression = original_regression

    assert error is None
    assert calls == ["classif"]


def test_excludes_zero_mi_constant_column_from_recommendation():
    # Regression test for a Codex review finding: a feature with zero
    # relevance to the target (no variation at all, in this case) is
    # neither Redundant nor High-multicollinearity, so it used to fall
    # through to "Keep" and get handed straight to the model by
    # recommended_features() — exactly what this engine exists to screen out.
    rng = _rng()
    n = 200
    x = rng.normal(size=n)
    target = x * 2 + rng.normal(scale=0.2, size=n)
    df = pd.DataFrame({"x": x, "constant_col": [5.0] * n, "target": target})
    column_types = {"x": "numeric", "constant_col": "numeric", "target": "numeric"}
    ranking, error = feature_selection.rank_features(df, column_types, "target")
    assert error is None
    constant_row = ranking.loc[ranking["Feature"] == "constant_col"].iloc[0]
    assert constant_row["MI Score"] <= feature_selection.LOW_RELEVANCE_MI_THRESHOLD
    assert constant_row["Recommendation"] == "Low relevance"
    assert "constant_col" not in feature_selection.recommended_features(ranking)


def test_narrate_selection_builds_table_text_with_real_ranking():
    calls = {}

    def fake_call_gemini(model, prompt):
        calls["prompt"] = prompt
        return "Feature b looks strongest; a is redundant with b.", None

    import modules.ai_analyst as ai_analyst_module

    original = ai_analyst_module.call_gemini
    ai_analyst_module.call_gemini = fake_call_gemini
    try:
        text, error = feature_selection.narrate_selection(object(), _sample_ranking(), "target")
    finally:
        ai_analyst_module.call_gemini = original

    assert error is None
    assert "strongest" in text
    assert "correlated with b (0.90)" in calls["prompt"]
