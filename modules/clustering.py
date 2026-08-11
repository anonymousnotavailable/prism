"""
Clustering & Segmentation — pick numeric columns, standardize them, run
KMeans with a hybrid elbow + silhouette-score suggestion for K, project to
2D via PCA for a scatter colored by cluster, and (optionally) ask Gemini to
name and describe each resulting segment in one line.

K selection follows the standard hybrid practice: the elbow method (inertia
drop-off) narrows candidates to a small window, then the silhouette score
— which unlike inertia actually measures how well-separated the resulting
clusters are, not just how tight they are — picks the winner within that
window. Silhouette alone can be noisy at the boundaries of K search ranges;
elbow alone can't tell a genuinely good K from an arbitrary one, since
inertia decreases monotonically with K by construction. Combining them is
cheap (both come from the same KMeans fits) and avoids both failure modes.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
from scipy.cluster.hierarchy import linkage as scipy_linkage
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from modules.ai_analyst import call_gemini, parse_numbered_bullets

# Below this many rows, clustering results are shown but flagged as unreliable.
MIN_ROWS_FOR_CLUSTERING = 50
MAX_K = 10

# Algorithms offered in the Clustering tab's algorithm picker.
CLUSTER_ALGORITHMS = ["KMeans", "DBSCAN", "Hierarchical (Agglomerative)"]

# Linkage criteria offered for Agglomerative/hierarchical clustering. Ward
# (minimizes within-cluster variance, the standard default) requires
# Euclidean distance, which is what StandardScaler-ed data already gives us.
HIERARCHICAL_LINKAGE_METHODS = ["ward", "complete", "average", "single"]

# Dendrograms with too many leaves are unreadable and slow to render; sample
# down to this many rows for the dendrogram plot only (cluster assignments
# elsewhere are computed on the full clean data, unaffected by this cap).
MAX_DENDROGRAM_ROWS = 300

# How many candidate Ks on either side of the elbow's pick to compare by
# silhouette score before settling on a final suggestion.
_ELBOW_WINDOW = 1

_SEGMENT_NAMING_PROMPT_TEMPLATE = (
    "The following table shows per-cluster mean values (from KMeans clustering on standardized "
    "numeric columns), plus each cluster's size and share of the data:\n\n{stats_text}\n\n"
    "You are a senior data analyst. For each cluster (in the row order given), write ONE short, "
    "descriptive segment name (2-5 words) followed by a colon and a one-sentence description "
    "that references at least one concrete number from the table. Format your response as exactly "
    "{n} lines, each starting with '1. ' through '{n}. ', with no other text before or after."
)


def compute_silhouette_scores(df: pd.DataFrame, numeric_cols: list[str], max_k: int = MAX_K) -> dict[int, float]:
    """Fit KMeans for k=2..max_k on standardized data and score each with the
    mean silhouette coefficient — how well-separated the resulting clusters
    are (near +1: dense, well-separated; near 0: overlapping; negative:
    likely mis-assigned points).

    Returns {} if there isn't enough clean data to try even k=2.
    """
    clean = df[numeric_cols].dropna()
    usable_max_k = min(max_k, len(clean) - 1)
    if usable_max_k < 2:
        return {}

    scaled = StandardScaler().fit_transform(clean)
    scores = {}
    for k in range(2, usable_max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(scaled)
        scores[k] = float(silhouette_score(scaled, labels))
    return scores


def suggest_k(
    df: pd.DataFrame, numeric_cols: list[str], max_k: int = MAX_K
) -> tuple[int, dict[int, float], dict[int, float]]:
    """Hybrid elbow + silhouette K suggestion: fit KMeans for k=2..max_k on
    standardized data, use the elbow method (sharpest inertia drop-off) to
    find a rough candidate, then pick the final K as whichever candidate in
    a small window around the elbow has the best silhouette score.

    Returns (suggested_k, inertias_by_k, silhouettes_by_k). Both dicts are
    empty if there isn't enough data to try more than one k.
    """
    clean = df[numeric_cols].dropna()
    usable_max_k = min(max_k, len(clean) - 1)
    if usable_max_k < 2:
        return 2, {}, {}

    scaled = StandardScaler().fit_transform(clean)
    inertias = {}
    silhouettes = {}
    for k in range(2, usable_max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(scaled)
        inertias[k] = km.inertia_
        silhouettes[k] = float(silhouette_score(scaled, labels))

    ks = sorted(inertias)
    if len(ks) < 3:
        elbow_k = ks[0]
    else:
        drops = [
            (
                (inertias[ks[i - 1]] - inertias[ks[i]]) - (inertias[ks[i]] - inertias[ks[i + 1]]),
                ks[i],
            )
            for i in range(1, len(ks) - 1)
        ]
        elbow_k = max(drops)[1] if drops else ks[0]

    # Pick the best silhouette score within a small window around the
    # elbow's pick, rather than trusting either signal in isolation.
    window = [k for k in range(elbow_k - _ELBOW_WINDOW, elbow_k + _ELBOW_WINDOW + 1) if k in silhouettes]
    best_k = max(window, key=lambda k: silhouettes[k]) if window else elbow_k
    return best_k, inertias, silhouettes


def run_clustering(df: pd.DataFrame, numeric_cols: list[str], k: int) -> dict:
    """Standardize numeric_cols, fit KMeans(k), and project to 2D via PCA.

    Returns a dict with "cluster_stats" (per-cluster mean of each column plus
    size/pct), "scatter_df" (PC1/PC2/cluster, ready to plot), and
    "pca_explained_variance" — or "error" if there isn't enough clean data.
    """
    clean = df[numeric_cols].dropna()
    if len(clean) < k:
        return {"error": f"Only {len(clean)} complete rows available — need at least {k} to form {k} clusters."}

    scaled = StandardScaler().fit_transform(clean)

    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(scaled)

    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(scaled)

    scatter_df = pd.DataFrame(coords, columns=["PC1", "PC2"], index=clean.index)
    scatter_df["cluster"] = labels.astype(str)

    stats_source = clean.copy()
    stats_source["cluster"] = labels
    cluster_stats = stats_source.groupby("cluster")[numeric_cols].mean()
    cluster_stats["size"] = stats_source.groupby("cluster").size()
    cluster_stats["pct"] = (cluster_stats["size"] / len(clean) * 100).round(1)

    # silhouette_score requires 2 <= n_labels <= n_samples - 1; k=1 (all one
    # cluster) or a degenerate fit where KMeans collapses to fewer than k
    # distinct labels can't be scored, so fall back to None rather than
    # raising — the caller shows "not available" in that case.
    n_unique_labels = len(set(labels))
    sil_score = (
        float(silhouette_score(scaled, labels)) if 2 <= n_unique_labels <= len(clean) - 1 else None
    )

    return {
        "cluster_stats": cluster_stats,
        "scatter_df": scatter_df,
        "pca_explained_variance": pca.explained_variance_ratio_,
        "k": k,
        "n_rows": len(clean),
        "silhouette_score": sil_score,
    }


def _elbow_index(values: list[float]) -> int:
    """Kneedle-style elbow finder: the index of the point on `values` (a
    monotonic curve) furthest from the straight line connecting its first
    and last point. Used for the DBSCAN eps k-distance plot, the same way
    `suggest_k` already finds an elbow in KMeans inertia — an unattended
    version of what a human would eyeball on the curve.
    """
    n = len(values)
    if n < 3:
        return 0
    y = np.asarray(values, dtype=float)
    x = np.arange(n, dtype=float)
    x_range = x[-1] - x[0]
    y_range = y.max() - y.min()
    x_norm = (x - x[0]) / x_range if x_range > 0 else np.zeros(n)
    y_norm = (y - y.min()) / y_range if y_range > 0 else np.zeros(n)

    x1, y1 = x_norm[0], y_norm[0]
    x2, y2 = x_norm[-1], y_norm[-1]
    denom = float(np.hypot(y2 - y1, x2 - x1))
    if denom == 0:
        return 0
    distances = np.abs((y2 - y1) * x_norm - (x2 - x1) * y_norm + x2 * y1 - y2 * x1) / denom
    return int(np.argmax(distances))


def suggest_eps(
    df: pd.DataFrame, numeric_cols: list[str], min_samples: int = 5
) -> tuple[Optional[float], list[float]]:
    """DBSCAN needs an `eps` (neighborhood radius). The standard way to pick
    one (Ester et al. 1996) is the "k-distance plot": for every point, find
    the distance to its `min_samples`-th nearest neighbor, sort those
    distances ascending, and look for the "knee" where the curve bends
    sharply upward — points past the knee are in sparse regions (noise
    candidates), points before it are in dense regions (core points).

    Returns (suggested_eps, sorted_k_distances). Both are the empty/None
    case if there isn't enough clean data to compute `min_samples` nearest
    neighbors for every point.
    """
    clean = df[numeric_cols].dropna()
    if len(clean) < min_samples + 1:
        return None, []

    scaled = StandardScaler().fit_transform(clean)
    nn = NearestNeighbors(n_neighbors=min_samples).fit(scaled)
    distances, _ = nn.kneighbors(scaled)
    k_distances = np.sort(distances[:, -1])

    elbow_idx = _elbow_index(k_distances.tolist())
    suggested_eps = float(k_distances[elbow_idx])
    return (suggested_eps if suggested_eps > 0 else 0.5), k_distances.tolist()


def _pca_scatter(clean: pd.DataFrame, scaled, labels) -> tuple[pd.DataFrame, "np.ndarray"]:
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(scaled)
    scatter_df = pd.DataFrame(coords, columns=["PC1", "PC2"], index=clean.index)
    scatter_df["cluster"] = ["Noise" if lbl == -1 else str(lbl) for lbl in labels]
    return scatter_df, pca.explained_variance_ratio_


def run_dbscan(df: pd.DataFrame, numeric_cols: list[str], eps: float, min_samples: int) -> dict:
    """Density-based clustering: finds arbitrary-shaped clusters and
    explicitly labels points that don't belong to any dense region as noise
    (-1), unlike KMeans which forces every point into some cluster and
    assumes roughly spherical shapes. No K to pick — density
    (eps/min_samples) implicitly determines the cluster count.

    Returns the same shape as run_clustering (cluster_stats, scatter_df,
    pca_explained_variance, silhouette_score) plus n_clusters (excluding
    noise), noise_count, and noise_pct — or "error" if there isn't enough
    clean data, or if every point was classified as noise (eps too small).
    """
    clean = df[numeric_cols].dropna()
    if len(clean) < min_samples + 1:
        return {
            "error": (
                f"Only {len(clean)} complete rows available — need at least "
                f"{min_samples + 1} for min_samples={min_samples}."
            )
        }

    scaled = StandardScaler().fit_transform(clean)
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(scaled)

    n_clusters = len({lbl for lbl in labels if lbl != -1})
    noise_count = int((labels == -1).sum())
    if n_clusters == 0:
        return {
            "error": (
                f"DBSCAN found no clusters at eps={eps:.3g}, min_samples={min_samples} — "
                "every point was treated as noise. Try a larger eps."
            )
        }

    scatter_df, explained_variance = _pca_scatter(clean, scaled, labels)

    stats_source = clean.copy()
    stats_source["cluster"] = ["Noise" if lbl == -1 else str(lbl) for lbl in labels]
    cluster_stats = stats_source.groupby("cluster")[numeric_cols].mean()
    cluster_stats["size"] = stats_source.groupby("cluster").size()
    cluster_stats["pct"] = (cluster_stats["size"] / len(clean) * 100).round(1)

    # Silhouette score only makes sense over real (non-noise) cluster
    # assignments — noise points have no cluster to be "well-separated" from.
    non_noise_mask = labels != -1
    non_noise_labels = labels[non_noise_mask]
    n_unique_non_noise = len(set(non_noise_labels))
    sil_score = (
        float(silhouette_score(scaled[non_noise_mask], non_noise_labels))
        if 2 <= n_unique_non_noise <= non_noise_mask.sum() - 1
        else None
    )

    return {
        "cluster_stats": cluster_stats,
        "scatter_df": scatter_df,
        "pca_explained_variance": explained_variance,
        "n_rows": len(clean),
        "silhouette_score": sil_score,
        "n_clusters": n_clusters,
        "noise_count": noise_count,
        "noise_pct": round(noise_count / len(clean) * 100, 1),
        "eps": eps,
        "min_samples": min_samples,
    }


def run_hierarchical(
    df: pd.DataFrame, numeric_cols: list[str], k: int, linkage_method: str = "ward"
) -> dict:
    """Agglomerative hierarchical clustering: starts with every point as its
    own cluster and repeatedly merges the closest pair (by `linkage_method`)
    until `k` clusters remain. Unlike KMeans, it makes no upfront assumption
    about cluster shape and its merge history can be inspected as a
    dendrogram (see build_dendrogram_chart) — useful when the "right" K
    isn't obvious and you want to see the merge structure, not just guess.

    Returns the same shape as run_clustering plus "linkage_method" — or
    "error" if there isn't enough clean data to form k clusters.
    """
    clean = df[numeric_cols].dropna()
    if len(clean) < k:
        return {"error": f"Only {len(clean)} complete rows available — need at least {k} to form {k} clusters."}

    scaled = StandardScaler().fit_transform(clean)
    agg = AgglomerativeClustering(n_clusters=k, linkage=linkage_method)
    labels = agg.fit_predict(scaled)

    scatter_df, explained_variance = _pca_scatter(clean, scaled, labels)

    stats_source = clean.copy()
    stats_source["cluster"] = labels.astype(str)
    cluster_stats = stats_source.groupby("cluster")[numeric_cols].mean()
    cluster_stats["size"] = stats_source.groupby("cluster").size()
    cluster_stats["pct"] = (cluster_stats["size"] / len(clean) * 100).round(1)

    n_unique_labels = len(set(labels))
    sil_score = (
        float(silhouette_score(scaled, labels)) if 2 <= n_unique_labels <= len(clean) - 1 else None
    )

    return {
        "cluster_stats": cluster_stats,
        "scatter_df": scatter_df,
        "pca_explained_variance": explained_variance,
        "k": k,
        "n_rows": len(clean),
        "silhouette_score": sil_score,
        "linkage_method": linkage_method,
    }


def build_dbscan_eps_chart(k_distances: list[float], suggested_eps: Optional[float]) -> px.Figure:
    """The k-distance plot behind suggest_eps: sorted nearest-neighbor
    distances with the suggested eps marked, so the "knee" the heuristic
    picked is visible rather than just a bare number.
    """
    if not k_distances:
        fig = px.line(title="K-Distance Plot (DBSCAN eps selection)")
        fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
        return fig

    fig = px.line(
        x=list(range(len(k_distances))), y=k_distances,
        labels={"x": "Points, sorted by distance", "y": "Distance to k-th nearest neighbor"},
        title="K-Distance Plot (DBSCAN eps selection)",
    )
    if suggested_eps is not None:
        fig.add_hline(
            y=suggested_eps, line_dash="dash", line_color="red",
            annotation_text=f"Suggested eps ≈ {suggested_eps:.3g}",
        )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_dendrogram_chart(
    df: pd.DataFrame, numeric_cols: list[str], linkage_method: str = "ward", max_rows: int = MAX_DENDROGRAM_ROWS
) -> px.Figure:
    """Dendrogram of the hierarchical merge structure, via plotly's
    figure_factory (which wraps scipy's linkage/dendrogram under the hood —
    we pass our own linkagefun so it uses the same linkage_method as
    run_hierarchical, on the same standardized data).

    Sampled down to `max_rows` rows for readability/speed if the dataset is
    larger — this affects only the dendrogram's shape, not any cluster
    assignment (run_hierarchical always uses the full clean data).
    """
    clean = df[numeric_cols].dropna()
    if len(clean) > max_rows:
        clean = clean.sample(n=max_rows, random_state=42)
    scaled = StandardScaler().fit_transform(clean)

    fig = ff.create_dendrogram(
        scaled, linkagefun=lambda x: scipy_linkage(x, method=linkage_method)
    )
    fig.update_layout(
        title=f"Dendrogram ({linkage_method} linkage)"
        + (f" — sampled {max_rows} of {len(df[numeric_cols].dropna())} rows" if len(df[numeric_cols].dropna()) > max_rows else ""),
        margin=dict(t=50, b=10, l=10, r=10),
        xaxis_title="Rows (leaf order)",
        yaxis_title="Merge distance",
    )
    return fig


def build_elbow_chart(inertias: dict[int, float]) -> px.Figure:
    ks = sorted(inertias)
    fig = px.line(
        x=ks, y=[inertias[k] for k in ks], markers=True,
        labels={"x": "K (number of clusters)", "y": "Inertia"}, title="Elbow Method",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_silhouette_chart(silhouettes: dict[int, float]) -> px.Figure:
    """Bar chart of mean silhouette score per K, so the tradeoff behind the
    hybrid elbow+silhouette suggestion is visible, not just its final pick.
    """
    if not silhouettes:
        fig = px.bar(title="Silhouette Score by K")
        fig.update_layout(margin=dict(t=50, b=10, l=10, r=10), yaxis_range=[-1, 1])
        return fig

    ks = sorted(silhouettes)
    fig = px.bar(
        x=ks, y=[silhouettes[k] for k in ks],
        labels={"x": "K (number of clusters)", "y": "Mean silhouette score"}, title="Silhouette Score by K",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10), yaxis_range=[-1, 1])
    return fig


def silhouette_verdict(score: Optional[float]) -> str:
    """Plain-English read of a mean silhouette score, using the standard
    Kaufman & Rousseeuw interpretation bands.
    """
    if score is None:
        return "Silhouette score not available for this clustering (too few distinct clusters to score)."
    if score > 0.7:
        return f"Silhouette score {score:.2f} — strong, well-separated cluster structure."
    if score > 0.5:
        return f"Silhouette score {score:.2f} — reasonable cluster structure; segments are distinguishable."
    if score > 0.25:
        return f"Silhouette score {score:.2f} — weak structure; clusters overlap noticeably. Treat segments as directional, not sharply defined."
    return f"Silhouette score {score:.2f} — little to no real cluster structure detected. Consider a different K, different columns, or that this data may not have natural clusters."


def build_scatter(scatter_df: pd.DataFrame, explained_variance) -> px.Figure:
    fig = px.scatter(
        scatter_df, x="PC1", y="PC2", color="cluster",
        title=(
            f"Clusters (PCA projection — {explained_variance[0] * 100:.0f}% + "
            f"{explained_variance[1] * 100:.0f}% variance explained)"
        ),
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def name_segments(model, cluster_stats: pd.DataFrame) -> tuple[list[str], Optional[str]]:
    """Ask Gemini to name and describe each cluster in one line.

    Returns (descriptions, error) — descriptions is ordered to match
    cluster_stats' row order (cluster 0, 1, 2, ...).
    """
    if model is None:
        return [], "No Gemini model available."

    n = len(cluster_stats)
    prompt = _SEGMENT_NAMING_PROMPT_TEMPLATE.format(stats_text=cluster_stats.round(2).to_string(), n=n)

    text, error = call_gemini(model, prompt)
    if error:
        return [], error
    return parse_numbered_bullets(text)[:n], None
