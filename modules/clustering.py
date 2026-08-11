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

import pandas as pd
import plotly.express as px
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from modules.ai_analyst import call_gemini, parse_numbered_bullets

# Below this many rows, clustering results are shown but flagged as unreliable.
MIN_ROWS_FOR_CLUSTERING = 50
MAX_K = 10

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
