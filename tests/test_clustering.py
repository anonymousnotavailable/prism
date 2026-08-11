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


class TestSuggestEps:
    def test_returns_positive_float_and_curve_for_blobs(self):
        df = _blob_df(n_samples=150, centers=3, cluster_std=0.4)
        suggested_eps, k_distances = clustering.suggest_eps(df, ["a", "b", "c"], min_samples=5)
        assert suggested_eps is not None
        assert suggested_eps > 0
        assert len(k_distances) == 150
        # k-distances are returned sorted ascending (the standard k-distance plot).
        assert k_distances == sorted(k_distances)

    def test_too_few_rows_returns_none_and_empty(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        suggested_eps, k_distances = clustering.suggest_eps(df, ["a", "b"], min_samples=5)
        assert suggested_eps is None
        assert k_distances == []


class TestRunDbscan:
    def test_recovers_true_cluster_count_on_well_separated_blobs(self):
        df = _blob_df(n_samples=150, centers=3, cluster_std=0.4)
        eps, _ = clustering.suggest_eps(df, ["a", "b", "c"], min_samples=5)
        result = clustering.run_dbscan(df, ["a", "b", "c"], eps=eps, min_samples=5)
        assert "error" not in result
        assert result["n_clusters"] == 3
        assert result["noise_count"] >= 0
        assert "cluster" in result["scatter_df"].columns

    def test_too_small_eps_yields_all_noise_error(self):
        df = _blob_df(n_samples=60, centers=2, cluster_std=0.4)
        result = clustering.run_dbscan(df, ["a", "b", "c"], eps=1e-6, min_samples=5)
        assert "error" in result

    def test_too_few_rows_returns_error(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 4.0, 5.0]})
        result = clustering.run_dbscan(df, ["a", "b"], eps=0.5, min_samples=5)
        assert "error" in result

    def test_noise_points_labeled_and_excluded_from_silhouette_bookkeeping(self):
        # A tight blob plus a handful of far-flung scattered points should
        # get flagged as noise by DBSCAN with a modest eps.
        rng = np.random.RandomState(0)
        core = rng.normal(loc=0, scale=0.2, size=(80, 2))
        scatter_pts = rng.uniform(low=-20, high=20, size=(8, 2))
        X = np.vstack([core, scatter_pts])
        df = pd.DataFrame(X, columns=["a", "b"])
        result = clustering.run_dbscan(df, ["a", "b"], eps=0.6, min_samples=5)
        assert "error" not in result
        assert result["noise_count"] >= 1
        assert result["n_clusters"] >= 1

    def test_cluster_stats_has_size_and_pct_columns(self):
        df = _blob_df(n_samples=120, centers=3, cluster_std=0.4)
        eps, _ = clustering.suggest_eps(df, ["a", "b", "c"], min_samples=5)
        result = clustering.run_dbscan(df, ["a", "b", "c"], eps=eps, min_samples=5)
        assert "size" in result["cluster_stats"].columns
        assert "pct" in result["cluster_stats"].columns


class TestRunHierarchical:
    def test_recovers_true_cluster_count_on_well_separated_blobs(self):
        df = _blob_df(n_samples=150, centers=3, cluster_std=0.4)
        result = clustering.run_hierarchical(df, ["a", "b", "c"], k=3)
        assert "error" not in result
        assert result["k"] == 3
        assert result["silhouette_score"] > 0.4

    def test_too_few_rows_returns_error(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        result = clustering.run_hierarchical(df, ["a", "b"], k=5)
        assert "error" in result

    @pytest.mark.parametrize("linkage_method", ["ward", "complete", "average", "single"])
    def test_accepts_every_supported_linkage_method(self, linkage_method):
        df = _blob_df(n_samples=60, centers=2, cluster_std=0.4)
        result = clustering.run_hierarchical(df, ["a", "b", "c"], k=2, linkage_method=linkage_method)
        assert "error" not in result
        assert result["linkage_method"] == linkage_method

    def test_cluster_stats_shape_matches_kmeans_convention(self):
        df = _blob_df(n_samples=120, centers=3, cluster_std=0.4)
        result = clustering.run_hierarchical(df, ["a", "b", "c"], k=3)
        assert "size" in result["cluster_stats"].columns
        assert "pct" in result["cluster_stats"].columns
        assert "scatter_df" in result
        assert "pca_explained_variance" in result


class TestBuildDbscanEpsChart:
    def test_builds_figure_without_error(self):
        k_distances = sorted(np.random.RandomState(0).uniform(0, 5, size=50).tolist())
        fig = clustering.build_dbscan_eps_chart(k_distances, suggested_eps=1.2)
        assert fig is not None

    def test_empty_curve_still_returns_figure(self):
        fig = clustering.build_dbscan_eps_chart([], suggested_eps=None)
        assert fig is not None


class TestBuildDendrogramChart:
    def test_builds_figure_without_error(self):
        df = _blob_df(n_samples=60, centers=3, cluster_std=0.4)
        fig = clustering.build_dendrogram_chart(df, ["a", "b", "c"])
        assert fig is not None

    def test_samples_down_large_datasets(self):
        df = _blob_df(n_samples=500, centers=3, cluster_std=0.4)
        fig = clustering.build_dendrogram_chart(df, ["a", "b", "c"], max_rows=100)
        assert fig is not None


class TestClusterAlgorithms:
    def test_algorithm_list_includes_all_three(self):
        assert "KMeans" in clustering.CLUSTER_ALGORITHMS
        assert "DBSCAN" in clustering.CLUSTER_ALGORITHMS
        assert any("Hierarchical" in a for a in clustering.CLUSTER_ALGORITHMS)
