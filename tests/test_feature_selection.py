"""Tests for modules/feature_selection.py — mutual info / Lasso / RFE
consensus ranking, aggregation of one-hot columns back to parent features,
and edge-case guardrails (too few features, too few rows)."""

import numpy as np
import pandas as pd
import pytest

from modules import feature_selection


@pytest.fixture
def classification_df():
    rng = np.random.default_rng(42)
    n = 300
    signal = rng.normal(size=n)
    noise1 = rng.normal(size=n)
    noise2 = rng.uniform(size=n)
    category = rng.choice(["A", "B", "C"], size=n)
    # target driven almost entirely by `signal`, weakly by category
    target = (signal + 0.05 * (category == "A").astype(int) > 0).astype(int)
    return pd.DataFrame(
        {"signal": signal, "noise1": noise1, "noise2": noise2, "category": category, "target": target}
    )


@pytest.fixture
def regression_df():
    rng = np.random.default_rng(7)
    n = 300
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    noise = rng.normal(size=n)
    y = 5 * x1 - 0.01 * x2 + rng.normal(scale=0.1, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "noise": noise, "y": y})


class TestMutualInfoRanking:
    def test_strong_predictor_ranks_first(self, classification_df):
        scores = feature_selection.mutual_info_ranking(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        assert scores.index[0] == "signal"
        assert scores.iloc[0] == pytest.approx(1.0)

    def test_scores_normalized_0_to_1(self, classification_df):
        scores = feature_selection.mutual_info_ranking(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        assert scores.max() <= 1.0 + 1e-9
        assert scores.min() >= 0.0

    def test_regression_target(self, regression_df):
        scores = feature_selection.mutual_info_ranking(regression_df, ["x1", "x2", "noise"], "y", "regression")
        assert scores.index[0] == "x1"


class TestLassoRanking:
    def test_weak_regression_feature_near_zero(self, regression_df):
        scores = feature_selection.lasso_ranking(regression_df, ["x1", "x2", "noise"], "y", "regression")
        assert scores["x1"] == pytest.approx(1.0)
        assert scores["x2"] < 0.1  # coefficient ~0, should be driven near-zero by L1

    def test_classification_l1(self, classification_df):
        scores = feature_selection.lasso_ranking(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        assert scores.index[0] == "signal"


class TestRfeSelection:
    def test_selects_requested_count_of_parents(self, classification_df):
        flags = feature_selection.rfe_selection(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification", n_features_to_select=1
        )
        assert flags["signal"] is True
        assert sum(flags.values()) >= 1

    def test_all_features_selected_when_n_equals_total(self, regression_df):
        flags = feature_selection.rfe_selection(regression_df, ["x1", "x2", "noise"], "y", "regression", n_features_to_select=3)
        assert all(flags.values())


class TestBuildFeatureSelectionReport:
    def test_full_report_shape(self, classification_df):
        report = feature_selection.build_feature_selection_report(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        assert "error" not in report
        assert list(report["table"].columns) == ["feature", "mutual_info", "lasso_importance", "rfe_selected", "consensus_score"]
        assert len(report["table"]) == 4
        assert report["table"].iloc[0]["feature"] == "signal"
        assert "signal" in report["recommended_features"]
        assert len(report["narrative"]) >= 1

    def test_too_few_features_errors(self, classification_df):
        report = feature_selection.build_feature_selection_report(classification_df, ["signal"], "target", "classification")
        assert "error" in report

    def test_too_few_rows_errors(self):
        tiny = pd.DataFrame({"a": range(5), "b": range(5), "y": [0, 1, 0, 1, 0]})
        report = feature_selection.build_feature_selection_report(tiny, ["a", "b"], "y", "classification")
        assert "error" in report

    def test_flags_zero_signal_features(self, regression_df):
        report = feature_selection.build_feature_selection_report(regression_df, ["x1", "x2", "noise"], "y", "regression")
        assert any("noise" in line or "x2" in line for line in report["narrative"])

    def test_consensus_score_sorted_descending(self, classification_df):
        report = feature_selection.build_feature_selection_report(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        scores = report["table"]["consensus_score"].tolist()
        assert scores == sorted(scores, reverse=True)


class TestBuildConsensusChart:
    def test_returns_figure(self, classification_df):
        report = feature_selection.build_feature_selection_report(
            classification_df, ["signal", "noise1", "noise2", "category"], "target", "classification"
        )
        fig = feature_selection.build_consensus_chart(report["table"])
        assert fig is not None
        assert len(fig.data) >= 1
