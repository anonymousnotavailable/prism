"""
Clustering & Segmentation — pick numeric columns, standardize them, run
KMeans with an elbow-method suggestion for K, project to 2D via PCA for a
scatter colored by cluster, and (optionally) ask Gemini to name and
describe each resulting segment in one line.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from modules.ai_analyst import call_gemini, parse_numbered_bullets

# Below this many rows, clustering results are shown but flagged as unreliable.
MIN_ROWS_FOR_CLUSTERING = 50
MAX_K = 10

_SEGMENT_NAMING_PROMPT_TEMPLATE = (
    "The following table shows per-cluster mean values (from KMeans clustering on standardized "
    "numeric columns), plus each cluster's size and share of the data:\n\n{stats_text}\n\n"
    "You are a senior data analyst. For each cluster (in the row order given), write ONE short, "
    "descriptive segment name (2-5 words) followed by a colon and a one-sentence description "
    "that references at least one concrete number from the table. Format your response as exactly "
    "{n} lines, each starting with '1. ' through '{n}. ', with no other text before or after."
)


def suggest_k(df: pd.DataFrame, numeric_cols: list[str], max_k: int = MAX_K) -> tuple[int, dict[int, float]]:
    """Elbow-method K suggestion: fit KMeans for k=2..max_k on standardized
    data and pick the k with the sharpest drop-off in inertia (the "elbow").

    Returns (suggested_k, inertias_by_k). inertias_by_k is empty if there
    isn't enough data to try more than one k.
    """
    clean = df[numeric_cols].dropna()
    usable_max_k = min(max_k, len(clean) - 1)
    if usable_max_k < 2:
        return 2, {}

    scaled = StandardScaler().fit_transform(clean)
    inertias = {}
    for k in range(2, usable_max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(scaled)
        inertias[k] = km.inertia_

    ks = sorted(inertias)
    if len(ks) < 3:
        return ks[0], inertias

    drops = [
        (
            (inertias[ks[i - 1]] - inertias[ks[i]]) - (inertias[ks[i]] - inertias[ks[i + 1]]),
            ks[i],
        )
        for i in range(1, len(ks) - 1)
    ]
    best_k = max(drops)[1] if drops else ks[0]
    return best_k, inertias


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

    return {
        "cluster_stats": cluster_stats,
        "scatter_df": scatter_df,
        "pca_explained_variance": pca.explained_variance_ratio_,
        "k": k,
        "n_rows": len(clean),
    }


def build_elbow_chart(inertias: dict[int, float]) -> px.Figure:
    ks = sorted(inertias)
    fig = px.line(
        x=ks, y=[inertias[k] for k in ks], markers=True,
        labels={"x": "K (number of clusters)", "y": "Inertia"}, title="Elbow Method",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


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
