"""
Geo Lens — detects a state/UT column in the active dataset (fuzzy-matched
against the canonical 28 states + 8 union territories in modules.india),
and builds an India choropleth + top/bottom-5 bar chart from a user-chosen
metric column. The map geometry is data/india_states.geojson (36 features,
"ST_NM" property) — a small, widely-used simplified boundary set, not a
full-precision survey file, since Prism only needs shape-level accuracy
for a dashboard map, not GIS work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
from rapidfuzz import fuzz, process

from modules.india import INDIAN_STATES_AND_UTS

GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "india_states.geojson"
GEOJSON_STATE_KEY = "ST_NM"

# Fuzzy-match threshold for "this column value is probably an Indian state name".
MATCH_THRESHOLD = 80


def is_geojson_available() -> bool:
    return GEOJSON_PATH.exists()


def load_geojson() -> Optional[dict]:
    """The India states/UTs GeoJSON, or None if the bundled file is
    missing — callers use this to show a friendly empty state instead of
    crashing (see app.py's Geo Lens tab).
    """
    if not GEOJSON_PATH.exists():
        return None
    try:
        with open(GEOJSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _geojson_state_names() -> list[str]:
    geojson = load_geojson()
    if not geojson:
        return []
    return [feat["properties"].get(GEOJSON_STATE_KEY, "") for feat in geojson.get("features", [])]


def detect_state_columns(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Find columns whose values look like Indian state/UT names.

    Returns [{"column", "match_pct", "sample_matches"}, ...] for every
    categorical/text column where at least half the distinct values
    fuzzy-match a canonical state/UT name at MATCH_THRESHOLD or better.
    """
    candidates = []
    for col, ctype in column_types.items():
        if ctype not in ("categorical", "text"):
            continue
        distinct = df[col].dropna().astype(str).unique()
        if len(distinct) == 0 or len(distinct) > 60:  # a real state column has <= 36 distinct values
            continue
        matched = 0
        for value in distinct:
            best = process.extractOne(value.strip(), INDIAN_STATES_AND_UTS, scorer=fuzz.ratio)
            if best and best[1] >= MATCH_THRESHOLD:
                matched += 1
        match_pct = 100 * matched / len(distinct)
        if match_pct >= 50:
            candidates.append({"column": col, "match_pct": round(match_pct, 1), "n_distinct": len(distinct)})

    candidates.sort(key=lambda c: -c["match_pct"])
    return candidates


def match_state_names(values: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map each distinct raw value to its best-matching canonical
    geojson state name. Returns (mapping, unmatched) — unmatched lists
    values that didn't clear MATCH_THRESHOLD against either the canonical
    list or the geojson's own names, with no fix applied automatically.
    """
    geo_names = _geojson_state_names()
    pool = geo_names or INDIAN_STATES_AND_UTS
    mapping: dict[str, str] = {}
    unmatched: list[str] = []
    for value in values:
        best = process.extractOne(str(value).strip(), pool, scorer=fuzz.ratio)
        if best and best[1] >= MATCH_THRESHOLD:
            mapping[value] = best[0]
        else:
            unmatched.append(value)
    return mapping, unmatched


def build_choropleth(df: pd.DataFrame, state_col: str, metric_col: str, agg: str = "sum"):
    """Aggregate `metric_col` by matched state name and render an India
    choropleth. Returns (fig, unmatched_values, state_totals_df) —
    unmatched_values lists raw values that couldn't be mapped to a state
    (excluded from the map, surfaced separately so nothing is silently
    dropped without the user knowing).
    """
    geojson = load_geojson()
    if geojson is None:
        return None, [], pd.DataFrame()

    raw_values = df[state_col].dropna().astype(str).unique().tolist()
    mapping, unmatched = match_state_names(raw_values)

    work = df.copy()
    work["_matched_state"] = work[state_col].astype(str).map(mapping)
    work = work.dropna(subset=["_matched_state"])

    grouped = work.groupby("_matched_state")[metric_col].agg(agg).reset_index()
    grouped.columns = ["state", "value"]

    fig = px.choropleth(
        grouped, geojson=geojson, featureidkey=f"properties.{GEOJSON_STATE_KEY}",
        locations="state", color="value", color_continuous_scale="Tealgrn",
        hover_name="state", hover_data={"value": ":,.2f", "state": False},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), coloraxis_colorbar_title=metric_col)

    return fig, unmatched, grouped.sort_values("value", ascending=False).reset_index(drop=True)


def top_bottom_chart(state_totals: pd.DataFrame, metric_col: str, n: int = 5):
    """A grouped top-N / bottom-N bar chart alongside the choropleth."""
    if state_totals.empty:
        return None
    top = state_totals.head(n).assign(group=f"Top {n}")
    bottom = state_totals.tail(n).assign(group=f"Bottom {n}")
    combined = pd.concat([top, bottom]).drop_duplicates(subset="state")
    fig = px.bar(
        combined.sort_values("value"), x="value", y="state", color="group", orientation="h",
        labels={"value": metric_col, "state": "", "group": ""},
    )
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig
