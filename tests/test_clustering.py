"""Tests for modules/clustering.py — elbow method, silhouette-score cluster
validation, KMeans + PCA clustering, and chart builders.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_blobs

from modules import clustering


def _blob_df(n_samples=180, centers=3, cluster_std=0.6, random_state=42) -> pd.DataFrame:
    """Well-separated synthetic blobs — silhouette score should be high and
    the elbow/silhouette-suggested K should recover the true center count.
    """
    X, _ = make_blobs(
        n_samples=n_samples, centers=centers, n_features=3, cluster_std=cluster_std, random_state=random_state
    )
    return pd.DataFrame(X, columns=["a", "b", "c"])


def _overlapping_df(n_samples=120, random_state=7) -> pd.DataFrame:
    """One big blob with huge spread — no real cluster structure, silhouette
    scores should be low/mediocre for every K.
    """
    rng = np.random.RandomState(random_state)
    return pd.DataFrame(rng.normal(size=(n_samples, 3)), columns=["a", "b", "c"])


class TestComputeSilhouetteScores:
    def test_returns_scores_for_every_k_in_range(self):
        df = _blob_df()
        scores = clustering.compute_silhouette_scores(df, ["a", "b", "c"], max_k=6)
        assert set(scores.keys()) == set(range(2, 7))
        for score in scores.values():
            assert -1.0 <= score <= 1.0

    def test_well_separated_blobs_score_high_at_true_k(self):
        df = _blob_df(centers=3)
        scores = clustering.compute_silhouette_scores(df, ["a", "b", "c"], max_k=6)
        # True cluster count (3) should have a strong silhouette score, and
        # should be at or near the best score across all tried K.
        assert scores[3] > 0.5
        assert scores[3] == max(scores.values())

    def test_handles_nan_rows_by_dropping(self):
        df = _blob_df(n_samples=60, centers=2)
        df.loc[0, "a"] = np.nan
        scores = clustering.compute_silhouette_scores(df, ["a", "b", "c"], max_k=4)
        assert set(scores.keys()) == set(range(2, 5))

    def test_too_few_rows_returns_empty(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        scores = clustering.compute_silhouette_scores(df, ["a", "b"], max_k=6)
        assert scores == {}


class TestSuggestK:
    def test_returns_three_tuple(self):
        df = _blob_df()
        result = clustering.suggest_k(df, ["a", "b", "c"])
        assert len(result) == 3
        suggested_k, inertias, silhouettes = result
        assert isinstance(suggested_k, int)
        assert isinstance(inertias, dict)
        assert isinstance(silhouettes, dict)

    def test_recovers_true_k_on_well_separated_blobs(self):
        df = _blob_df(centers=4, n_samples=240)
        suggested_k, inertias, silhouettes = clustering.suggest_k(df, ["a", "b", "c"], max_k=8)
        assert suggested_k == 4
        assert inertias  # populated
        assert silhouettes  # populated

    def test_tiny_dataset_falls_back_to_two_with_empty_dicts(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        suggested_k, inertias, silhouettes = clustering.suggest_k(df, ["a", "b"])
        assert suggested_k == 2
        assert inertias == {}
        assert silhouettes == {}

    def test_suggested_k_is_within_silhouette_candidate_window(self):
        # Suggested K should always be one that was actually scored.
        df = _blob_df(centers=3, n_samples=200)
        suggested_k, inertias, silhouettes = clustering.suggest_k(df, ["a", "b", "c"], max_k=8)
        assert suggested_k in silhouettes


class TestRunClustering:
    def test_includes_silhouette_score_in_result(self):
        df = _blob_df(centers=3)
        result = clustering.run_clustering(df, ["a", "b", "c"], k=3)
        assert "silhouette_score" in result
        assert -1.0 <= result["silhouette_score"] <= 1.0
        assert result["silhouette_score"] > 0.4  # well-separated blobs

    def test_error_case_has_no_silhouette_key_crash(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        result = clustering.run_clustering(df, ["a", "b"], k=5)
        assert "error" in result
        assert "silhouette_score" not in result

    def test_single_cluster_k1_silhouette_is_none(self):
        # k=1 is not selectable via the UI slider (min_value=2) but the
        # function itself should not blow up if ever called with it.
        df = _blob_df(n_samples=30, centers=1)
        result = clustering.run_clustering(df, ["a", "b", "c"], k=1)
        assert result.get("silhouette_score") is None


class TestSilhouetteVerdict:
    @pytest.mark.parametrize(
        "score,expected_fragment",
        [
            (0.85, "strong"),
            (0.6, "reasonable"),
            (0.35, "weak"),
            (0.1, "little"),
            (-0.2, "little"),
        ],
    )
    def test_verdict_matches_score_band(self, score, expected_fragment):
        verdict = clustering.silhouette_verdict(score)
        assert expected_fragment in verdict.lower()

    def test_verdict_none_handled_gracefully(self):
        verdict = clustering.silhouette_verdict(None)
        assert isinstance(verdict, str)
        assert verdict  # non-empty


class TestBuildSilhouetteChart:
    def test_builds_figure_without_error(self):
        scores = {2: 0.3, 3: 0.6, 4: 0.55, 5: 0.4}
        fig = clustering.build_silhouette_chart(scores)
        assert fig is not None

    def test_empty_scores_still_returns_figure(self):
        fig = clustering.build_silhouette_chart({})
        assert fig is not None
