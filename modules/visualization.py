"""
Visualization — the smart chart picker. Every function returns a Plotly
figure (or None when the chart doesn't apply) so app.py and report.py can
both consume the same chart-building logic without duplicating it.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from modules import theme

# Registering the dark/cyan template here (module import time) — rather than
# only in app.py — means every chart is themed even when this module is used
# standalone, e.g. by the AI Analyst sandbox or a script/test that never
# touches app.py.
theme.apply_plotly_theme()

# Pie charts only read well with a handful of slices; beyond this, a bar chart
# of the top categories communicates the distribution more clearly.
PIE_CHART_MAX_CATEGORIES = 8
TOP_N_CATEGORIES = 10

# User-facing chart types offered in the Visualize tab's manual mode.
MANUAL_CHART_TYPES = ["Histogram", "Box", "Bar", "Pie", "Scatter", "Line"]
# Chart types where a Y-axis column is mandatory (not just an optional grouping).
MANUAL_CHART_TYPES_REQUIRING_Y = {"Scatter", "Line"}


def get_overview_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return df.describe() across all dtypes, transposed for easier table display."""
    return df.describe(include="all").transpose()


def _cyan_gradient_color(norm_value: float) -> str:
    """Blend from the app's card background (#111827) to accent cyan (#00e5ff)."""
    start, end = (17, 24, 39), (0, 229, 255)
    norm_value = max(0.0, min(1.0, norm_value))
    r, g, b = (int(s + (e - s) * norm_value) for s, e in zip(start, end))
    return f"rgb({r}, {g}, {b})"


def style_describe_table(stats_df: pd.DataFrame):
    """Apply a cyan gradient to the numeric cells of a describe() table.

    `df.describe(include="all").transpose()` mixes numeric stats (mean, std, ...)
    with categorical ones (top, freq, ...) in the same table, which pandas
    stores as `object` dtype per column — so a plain `select_dtypes` misses
    everything. Instead we coerce each column with `pd.to_numeric(errors=
    "coerce")` and color whatever comes out numeric, cell by cell.

    Built without matplotlib (which pandas' built-in .background_gradient()
    requires) — just a manual per-column min/max blend — to keep the app's
    dependency footprint small. Returns a pandas Styler, which st.dataframe()
    renders natively.
    """

    def _gradient(col: pd.Series):
        numeric_vals = pd.to_numeric(col, errors="coerce")
        if numeric_vals.notna().sum() == 0:
            return [""] * len(col)
        col_min, col_max = numeric_vals.min(), numeric_vals.max()
        span = col_max - col_min
        styles = []
        for v in numeric_vals:
            if pd.isna(v):
                styles.append("")
                continue
            norm = (v - col_min) / span if span else 0.5
            text_color = "#05070d" if norm > 0.6 else "#e0f7fa"
            styles.append(f"background-color: {_cyan_gradient_color(norm)}; color: {text_color}")
        return styles

    return stats_df.style.apply(_gradient, axis=0).format(precision=2)


def plot_categorical(df: pd.DataFrame, column: str):
    """Pie chart for low-cardinality categoricals, bar chart (top N) otherwise."""
    counts = df[column].value_counts(dropna=True)
    if counts.empty:
        return None

    if counts.shape[0] <= PIE_CHART_MAX_CATEGORIES:
        fig = px.pie(values=counts.values, names=counts.index.astype(str), title=f"Distribution of {column}")
    else:
        top = counts.head(TOP_N_CATEGORIES)
        fig = px.bar(
            x=top.index.astype(str),
            y=top.values,
            title=f"Top {TOP_N_CATEGORIES} categories in {column}",
            labels={"x": column, "y": "Count"},
        )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def plot_numeric(df: pd.DataFrame, column: str) -> tuple[go.Figure, go.Figure]:
    """Histogram + boxplot pair for a numeric column."""
    hist = px.histogram(df, x=column, nbins=30, title=f"Distribution of {column}")
    box = px.box(df, y=column, title=f"Spread & outliers in {column}", points="outliers")
    for fig in (hist, box):
        fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return hist, box


def plot_datetime_trend(df: pd.DataFrame, datetime_col: str, numeric_col: str) -> go.Figure:
    """Line chart of a numeric column over time."""
    series = df.dropna(subset=[datetime_col, numeric_col]).sort_values(datetime_col)
    fig = px.line(series, x=datetime_col, y=numeric_col, title=f"{numeric_col} over {datetime_col}")
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def plot_scatter(df: pd.DataFrame, col_x: str, col_y: str) -> go.Figure:
    """Scatter plot between two numeric columns with an OLS trendline."""
    try:
        fig = px.scatter(df, x=col_x, y=col_y, trendline="ols", title=f"{col_y} vs {col_x}")
    except Exception:
        # statsmodels missing or the trendline fit failed — fall back to a plain scatter
        fig = px.scatter(df, x=col_x, y=col_y, title=f"{col_y} vs {col_x}")
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def get_top_correlations(corr: pd.DataFrame, n: int = 3) -> list[tuple[str, str, float]]:
    """Return the n strongest |correlation| pairs, excluding self-pairs and duplicates."""
    pairs = []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            value = corr.iloc[i, j]
            if pd.notna(value):
                pairs.append((cols[i], cols[j], float(value)))
    pairs.sort(key=lambda p: abs(p[2]), reverse=True)
    return pairs[:n]


def describe_correlation(value: float) -> str:
    """Turn a raw correlation coefficient into a plain-English label, e.g. 'strong positive: 0.87'."""
    magnitude = abs(value)
    if magnitude >= 0.9:
        strength = "very strong"
    elif magnitude >= 0.7:
        strength = "strong"
    elif magnitude >= 0.4:
        strength = "moderate"
    else:
        strength = "weak"
    direction = "positive" if value >= 0 else "negative"
    return f"{strength} {direction}: {value:.2f}"


def plot_correlation_heatmap(df: pd.DataFrame):
    """Correlation heatmap over numeric columns, plus the top strongest pairs.

    Returns (figure_or_None, top_correlations_list).
    """
    numeric_df = df.select_dtypes(include=np.number)
    if numeric_df.shape[1] < 2:
        return None, []

    corr = numeric_df.corr()
    fig = px.imshow(
        corr,
        text_auto=".2f",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        title="Correlation Heatmap",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig, get_top_correlations(corr)


def auto_generate_charts(df: pd.DataFrame, column_types: dict[str, str]):
    """Build the full auto-chart set (used by both the Visualize tab and the HTML export).

    Returns (charts_dict, top_correlations_list) where charts_dict maps a
    human-readable title to a Plotly figure.
    """
    charts: dict[str, go.Figure] = {}

    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    datetime_cols = [c for c, t in column_types.items() if t == "datetime"]

    for col in categorical_cols:
        fig = plot_categorical(df, col)
        if fig is not None:
            charts[f"{col} (categorical)"] = fig

    for col in numeric_cols:
        hist, box = plot_numeric(df, col)
        charts[f"{col} — histogram"] = hist
        charts[f"{col} — boxplot"] = box

    # Cap datetime x numeric trends so a wide dataset doesn't generate dozens of charts.
    if datetime_cols and numeric_cols:
        dt_col = datetime_cols[0]
        for num_col in numeric_cols[:3]:
            charts[f"{num_col} over {dt_col}"] = plot_datetime_trend(df, dt_col, num_col)

    heatmap, top_corr = plot_correlation_heatmap(df)
    if heatmap is not None:
        charts["Correlation Heatmap"] = heatmap
        # Scatter the most strongly correlated pairs — more informative than
        # an arbitrary combination of numeric columns.
        for col_x, col_y, _ in top_corr:
            charts[f"Scatter: {col_x} vs {col_y}"] = plot_scatter(df, col_x, col_y)

    return charts, top_corr


def build_manual_chart(df: pd.DataFrame, chart_type: str, col_x: str, col_y: Optional[str] = None) -> go.Figure:
    """Build a chart from explicit user picks — the manual escape hatch next to
    the automatic per-dtype chart picker above.

    chart_type: one of MANUAL_CHART_TYPES ("Histogram", "Box", "Bar", "Pie", "Scatter", "Line").
    col_y is required for "Scatter"/"Line" and optional (used as a grouping) for "Box"/"Bar".
    Raises ValueError for an invalid combination, so callers can surface it as a friendly message.
    """
    if chart_type in MANUAL_CHART_TYPES_REQUIRING_Y and not col_y:
        raise ValueError(f"{chart_type} needs a Y-axis column.")

    if chart_type == "Histogram":
        fig = px.histogram(df, x=col_x, nbins=30, title=f"Histogram of {col_x}")
    elif chart_type == "Box":
        if col_y:
            fig = px.box(df, x=col_x, y=col_y, title=f"{col_y} by {col_x}")
        else:
            fig = px.box(df, y=col_x, title=f"Spread of {col_x}", points="outliers")
    elif chart_type == "Pie":
        counts = df[col_x].value_counts(dropna=True).head(TOP_N_CATEGORIES)
        fig = px.pie(values=counts.values, names=counts.index.astype(str), title=f"Distribution of {col_x}")
    elif chart_type == "Bar":
        if col_y and pd.api.types.is_numeric_dtype(df[col_y]):
            grouped = df.groupby(col_x)[col_y].mean().sort_values(ascending=False).head(TOP_N_CATEGORIES)
            fig = px.bar(
                x=grouped.index.astype(str), y=grouped.values,
                title=f"Mean {col_y} by {col_x}", labels={"x": col_x, "y": f"Mean {col_y}"},
            )
        else:
            counts = df[col_x].value_counts(dropna=True).head(TOP_N_CATEGORIES)
            fig = px.bar(
                x=counts.index.astype(str), y=counts.values,
                title=f"Top {TOP_N_CATEGORIES} values in {col_x}", labels={"x": col_x, "y": "Count"},
            )
    elif chart_type == "Scatter":
        fig = plot_scatter(df, col_x, col_y)
    elif chart_type == "Line":
        subset = df[[col_x, col_y]].dropna().sort_values(col_x)
        fig = px.line(subset, x=col_x, y=col_y, title=f"{col_y} over {col_x}")
    else:
        raise ValueError(f"Unknown chart type: {chart_type}")

    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig
