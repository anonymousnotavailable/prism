"""Tests for modules.visualization's Manual Chart Builder — the grammar-of-
graphics-style "pick your own encoding" escape hatch next to the automatic
per-dtype chart picker. Focused on build_manual_chart()'s color/aggregation
encoding channels (the competitor-parity slice toward a PyGWalker-style
builder), plus the pre-existing X/Y/type behavior it must stay backward
compatible with.
"""
from __future__ import annotations

import pandas as pd
import pytest

from modules.visualization import (
    MANUAL_CHART_AGG_FUNCS,
    MANUAL_CHART_TYPES,
    MANUAL_CHART_TYPES_REQUIRING_Y,
    MANUAL_CHART_TYPES_SUPPORTING_COLOR,
    build_manual_chart,
)


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "spend": [10, 20, 30, 40, 50, 60, 70, 80],
            "revenue": [12, 18, 33, 41, 48, 65, 68, 85],
            "region": ["north", "north", "south", "south", "north", "south", "north", "south"],
            "channel": ["online", "retail", "online", "retail", "online", "retail", "online", "retail"],
        }
    )


# ─────────────────────────────────────────────────────────────────────────
# Backward-compatible base behavior (no color/agg passed)
# ─────────────────────────────────────────────────────────────────────────


def test_histogram_basic(df):
    fig = build_manual_chart(df, "Histogram", "spend")
    assert fig.data


def test_scatter_requires_y(df):
    with pytest.raises(ValueError):
        build_manual_chart(df, "Scatter", "spend")


def test_bar_default_agg_is_mean(df):
    fig = build_manual_chart(df, "Bar", "region", "revenue")
    assert "Mean" in fig.layout.title.text


def test_unknown_chart_type_raises(df):
    with pytest.raises(ValueError):
        build_manual_chart(df, "Sankey", "spend")


# ─────────────────────────────────────────────────────────────────────────
# Color encoding
# ─────────────────────────────────────────────────────────────────────────


def test_scatter_with_color_splits_by_group(df):
    fig = build_manual_chart(df, "Scatter", "spend", "revenue", color="region")
    trace_names = {t.name for t in fig.data if t.name}
    assert "north" in trace_names and "south" in trace_names


def test_histogram_with_color(df):
    fig = build_manual_chart(df, "Histogram", "spend", color="channel")
    assert len({t.name for t in fig.data if t.name}) == 2


def test_line_with_color(df):
    fig = build_manual_chart(df, "Line", "spend", "revenue", color="region")
    assert len({t.name for t in fig.data if t.name}) == 2


def test_color_same_as_x_is_silently_ignored(df):
    # Encoding a column against itself doesn't error — it's just dropped.
    fig = build_manual_chart(df, "Histogram", "region", color="region")
    assert fig.data


def test_unknown_color_column_raises(df):
    with pytest.raises(ValueError):
        build_manual_chart(df, "Bar", "region", "revenue", color="nonexistent_col")


def test_pie_ignores_color_without_error(df):
    # Pie has no meaningful color channel of its own (it already encodes
    # category via slices) — must not raise even if a color is passed.
    fig = build_manual_chart(df, "Pie", "region", color="channel")
    assert fig.data


# ─────────────────────────────────────────────────────────────────────────
# Aggregation encoding (Bar only)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("agg_label", list(MANUAL_CHART_AGG_FUNCS.keys()))
def test_bar_every_agg_func_runs(df, agg_label):
    fig = build_manual_chart(df, "Bar", "region", "revenue", agg=MANUAL_CHART_AGG_FUNCS[agg_label])
    assert fig.data
    assert agg_label in fig.layout.title.text


def test_bar_sum_differs_from_mean(df):
    fig_mean = build_manual_chart(df, "Bar", "region", "revenue", agg="mean")
    fig_sum = build_manual_chart(df, "Bar", "region", "revenue", agg="sum")
    assert list(fig_mean.data[0].y) != list(fig_sum.data[0].y)


def test_bar_with_color_and_agg_groups_both(df):
    fig = build_manual_chart(df, "Bar", "region", "revenue", color="channel", agg="sum")
    trace_names = {t.name for t in fig.data if t.name}
    assert trace_names == {"online", "retail"}


# ─────────────────────────────────────────────────────────────────────────
# Constants sanity
# ─────────────────────────────────────────────────────────────────────────


def test_manual_chart_types_supporting_color_is_subset_of_all_types():
    assert MANUAL_CHART_TYPES_SUPPORTING_COLOR <= set(MANUAL_CHART_TYPES)


def test_scatter_and_line_still_require_y():
    assert {"Scatter", "Line"} <= MANUAL_CHART_TYPES_REQUIRING_Y
