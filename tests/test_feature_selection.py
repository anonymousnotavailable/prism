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
