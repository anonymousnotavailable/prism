"""
Dashboard Builder — Gemini inspects the dataset's schema and returns a JSON
dashboard spec (a handful of KPI cards + 4-6 charts, each with a one-line
reason). Falls back to a sensible default spec, built from column_types
alone, whenever Gemini is unavailable or its JSON can't be parsed.
"""

from __future__ import annotations

import json
import re

import pandas as pd
import plotly.express as px

from modules.ai_analyst import build_data_context, call_gemini

DASHBOARD_SYSTEM_PROMPT = (
    "You are a senior data analyst designing a dashboard for a pandas DataFrame called `df`. "
    "Given the dataframe's schema, a sample, and summary statistics, return a JSON object with "
    "two keys:\n"
    '- "kpis": a list of 3-4 objects, each {"label": str, "column": str, "agg": one of '
    '"sum"/"mean"/"count"/"nunique"} — simple, business-relevant summary numbers.\n'
    '- "charts": a list of 4-6 objects, each {"chart_type": one of "bar"/"line"/"scatter"/'
    '"histogram"/"box", "x": column name, "y": column name or null, "reason": a one-line '
    "explanation of why this chart is useful}.\n\n"
    "Only reference columns that exist in the schema below. Return ONLY the JSON object, no prose, "
    "no markdown code fences."
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_CHART_TYPE_ROTATION = ["bar", "line", "histogram", "box", "scatter"]


def _default_spec(df: pd.DataFrame, column_types: dict[str, str]) -> dict:
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]
    datetime_cols = [c for c, t in column_types.items() if t == "datetime"]

    kpis = [{"label": "Rows", "column": df.columns[0], "agg": "count"}]
    for col in numeric_cols[:3]:
        kpis.append({"label": f"Average {col}", "column": col, "agg": "mean"})

    charts = []
    if datetime_cols and numeric_cols:
        charts.append(
            {
                "chart_type": "line", "x": datetime_cols[0], "y": numeric_cols[0],
                "reason": "Shows the trend of the main numeric metric over time.",
            }
        )
    for col in categorical_cols[:2]:
        y = numeric_cols[0] if numeric_cols else None
        charts.append(
            {
                "chart_type": "bar", "x": col, "y": y,
                "reason": f"Compares {y or 'counts'} across '{col}' categories.",
            }
        )
    for col in numeric_cols[:2]:
        charts.append({"chart_type": "histogram", "x": col, "y": None, "reason": f"Shows the distribution of '{col}'."})
    if len(numeric_cols) >= 2:
        charts.append(
            {
                "chart_type": "scatter", "x": numeric_cols[0], "y": numeric_cols[1],
                "reason": f"Shows the relationship between '{numeric_cols[0]}' and '{numeric_cols[1]}'.",
            }
        )

    return {"kpis": kpis[:4], "charts": charts[:6]}


def generate_dashboard_spec(model, df: pd.DataFrame, column_types: dict[str, str]) -> dict:
    """Ask Gemini for a dashboard spec. Always returns something renderable —
    falls back to _default_spec() on any failure, bad JSON, or a spec that
    references columns that don't exist.
    """
    if model is None:
        return _default_spec(df, column_types)

    context = build_data_context(df, column_types)
    prompt = f"{DASHBOARD_SYSTEM_PROMPT}\n\nData context:\n{context}"
    text, error = call_gemini(model, prompt)
    if error:
        return _default_spec(df, column_types)

    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return _default_spec(df, column_types)

    try:
        spec = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _default_spec(df, column_types)

    kpis = [k for k in spec.get("kpis", []) if isinstance(k, dict) and k.get("column") in df.columns]
    charts = [
        c for c in spec.get("charts", [])
        if isinstance(c, dict) and c.get("x") in df.columns and (c.get("y") is None or c.get("y") in df.columns)
    ]

    if not kpis and not charts:
        return _default_spec(df, column_types)
    return {"kpis": kpis, "charts": charts}


def compute_kpi(df: pd.DataFrame, kpi: dict):
    """Evaluate one KPI spec entry against the live dataframe. Returns None on failure."""
    agg = kpi.get("agg", "count")
    col = kpi.get("column")
    try:
        series = df[col]
        if agg == "sum":
            return float(series.sum())
        if agg == "mean":
            return float(series.mean())
        if agg == "nunique":
            return int(series.nunique())
        return int(series.count())
    except Exception:
        return None


def build_dashboard_chart(df: pd.DataFrame, chart: dict):
    """Build a Plotly figure for one chart spec entry. Returns None if it can't be built."""
    chart_type = chart.get("chart_type")
    x, y = chart.get("x"), chart.get("y")
    try:
        if chart_type == "bar":
            if y:
                grouped = df.groupby(x)[y].mean().sort_values(ascending=False).head(15)
                fig = px.bar(x=grouped.index.astype(str), y=grouped.values, labels={"x": x, "y": f"Average {y}"})
            else:
                counts = df[x].value_counts().head(15)
                fig = px.bar(x=counts.index.astype(str), y=counts.values, labels={"x": x, "y": "Count"})
        elif chart_type == "line":
            grouped = df.groupby(x)[y].mean().sort_index() if y else df[x].value_counts().sort_index()
            fig = px.line(x=grouped.index, y=grouped.values, labels={"x": x, "y": y or "Count"})
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x)
        elif chart_type == "box":
            fig = px.box(df, x=x, y=y) if y else px.box(df, y=x)
        else:
            return None
        fig.update_layout(margin=dict(t=40, b=10, l=10, r=10))
        return fig
    except Exception:
        return None


def swap_chart_type(chart: dict) -> dict:
    """Cycle to the next chart type for the same x/y columns (the "swap" action)."""
    current = chart.get("chart_type", "bar")
    idx = _CHART_TYPE_ROTATION.index(current) if current in _CHART_TYPE_ROTATION else -1
    next_type = _CHART_TYPE_ROTATION[(idx + 1) % len(_CHART_TYPE_ROTATION)]
    new_chart = dict(chart)
    new_chart["chart_type"] = next_type
    if next_type == "histogram":
        new_chart["y"] = None
    return new_chart
