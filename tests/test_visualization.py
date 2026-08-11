"""Tests for modules.visualization's Manual Chart Builder — the grammar-of-
graphics-style "pick your own encoding" escape hatch next to the automatic
per-dtype chart picker. Covers build_manual_chart()'s color/aggregation
encoding channels plus the Facet (small-multiples) channel added this run
— the next encoding-channel slice toward a PyGWalker-style builder — and
the pre-existing X/Y/type behavior all of it must stay backward compatible
with.
"""
from __future__ import annotations

import pandas as pd
import pytest

from modules.visualization import (
    MANUAL_CHART_AGG_FUNCS,
    MANUAL_CHART_TYPES,
    MANUAL_CHART_TYPES_REQUIRING_Y,
    MANUAL_CHART_TYPES_SUPPORTING_COLOR,
    MANUAL_CHART_TYPES_SUPPORTING_FACET,
    MAX_FACET_CATEGORIES,
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


@pytest.fixture
def df_wide_facet():
    # 10 distinct facet categories, well above MAX_FACET_CATEGORIES (6) —
    # for exercising the top-N capping behavior.
    import itertools

    groups = [f"g{i}" for i in range(10)]
    rows = list(itertools.chain.from_iterable([g] * 5 for g in groups))
    # Make the first 6 groups appear more often than the rest, so "top N by
    # frequency" is unambiguous.
    extra = ["g0", "g1", "g2", "g3", "g4", "g5"] * 3
    all_rows = rows + extra
    n = len(all_rows)
    return pd.DataFrame(
        {
            "value": list(range(n)),
            "metric": [i % 5 for i in range(n)],
            "grp": all_rows,
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
# Facet (small-multiples) encoding
# ─────────────────────────────────────────────────────────────────────────


def test_histogram_with_facet_creates_one_subplot_per_category(df):
    fig = build_manual_chart(df, "Histogram", "spend", facet="channel")
    # Plotly express annotates each facet subplot's title in fig.layout.annotations.
    annotation_text = {a.text for a in fig.layout.annotations}
    assert any("online" in t for t in annotation_text)
    assert any("retail" in t for t in annotation_text)


def test_scatter_with_facet(df):
    fig = build_manual_chart(df, "Scatter", "spend", "revenue", facet="region")
    annotation_text = {a.text for a in fig.layout.annotations}
    assert any("north" in t for t in annotation_text)
    assert any("south" in t for t in annotation_text)


def test_bar_with_facet_and_agg(df):
    fig = build_manual_chart(df, "Bar", "region", "revenue", facet="channel", agg="sum")
    annotation_text = {a.text for a in fig.layout.annotations}
    assert any("online" in t for t in annotation_text)
    assert any("retail" in t for t in annotation_text)


def test_line_with_facet(df):
    fig = build_manual_chart(df, "Line", "spend", "revenue", facet="region")
    annotation_text = {a.text for a in fig.layout.annotations}
    assert any("north" in t for t in annotation_text)


def test_box_with_facet(df):
    fig = build_manual_chart(df, "Box", "region", "revenue", facet="channel")
    annotation_text = {a.text for a in fig.layout.annotations}
    assert any("online" in t for t in annotation_text)


def test_facet_same_as_x_is_silently_ignored(df):
    # No self-encoding — facet == x just gets dropped, no error, no crash.
    fig = build_manual_chart(df, "Histogram", "region", facet="region")
    assert fig.data


def test_facet_same_as_color_is_silently_ignored(df):
    fig = build_manual_chart(df, "Histogram", "spend", color="channel", facet="channel")
    assert fig.data


def test_facet_same_as_y_is_silently_ignored(df):
    fig = build_manual_chart(df, "Scatter", "spend", "revenue", facet="revenue")
    assert fig.data


def test_unknown_facet_column_raises(df):
    with pytest.raises(ValueError):
        build_manual_chart(df, "Histogram", "spend", facet="nonexistent_col")


def test_pie_ignores_facet_without_error(df):
    fig = build_manual_chart(df, "Pie", "region", facet="channel")
    assert fig.data


def test_facet_caps_to_max_categories_by_frequency(df_wide_facet):
    fig = build_manual_chart(df_wide_facet, "Histogram", "value", facet="grp")
    annotation_text = {a.text for a in fig.layout.annotations}
    facet_groups_shown = {t.split("=")[-1] for t in annotation_text if "grp" in t}
    assert len(facet_groups_shown) <= MAX_FACET_CATEGORIES
    # The 6 most frequent groups (g0-g5, boosted by the `extra` rows) should
    # be the ones kept, not an arbitrary/alphabetical subset.
    assert facet_groups_shown <= {"g0", "g1", "g2", "g3", "g4", "g5"}


def test_facet_without_color_or_agg_still_works(df):
    fig = build_manual_chart(df, "Box", "region", "revenue", facet="channel", color=None)
    assert fig.data


def test_facet_none_is_backward_compatible(df):
    # Omitting facet entirely must render identically to before this feature.
    fig = build_manual_chart(df, "Bar", "region", "revenue")
    assert fig.data
    assert not fig.layout.annotations


# ─────────────────────────────────────────────────────────────────────────
# Constants sanity
# ─────────────────────────────────────────────────────────────────────────


def test_manual_chart_types_supporting_color_is_subset_of_all_types():
    assert MANUAL_CHART_TYPES_SUPPORTING_COLOR <= set(MANUAL_CHART_TYPES)


def test_manual_chart_types_supporting_facet_is_subset_of_all_types():
    assert MANUAL_CHART_TYPES_SUPPORTING_FACET <= set(MANUAL_CHART_TYPES)


def test_scatter_and_line_still_require_y():
    assert {"Scatter", "Line"} <= MANUAL_CHART_TYPES_REQUIRING_Y
