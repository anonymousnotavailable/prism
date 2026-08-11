"""Tests for visualization.suggest_chart_encoding — the "explore mode"
auto-suggestion slice toward a PyGWalker/Tableau-style chart builder that
Runs 13/14 explicitly left as the remaining scope after shipping the
Color/Aggregation/Facet encoding channels. Looks at the loaded data
directly (deterministic, no Gemini call) and recommends a chart type +
axis/color/facet encoding, the same "read the data, not the LLM's prose"
pattern auto_analyst.suggest_followup_hypothesis already established for
Stats Lab.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.visualization import (
    MANUAL_CHART_TYPES,
    build_manual_chart,
    suggest_chart_encoding,
)


def test_suggests_scatter_for_strongest_numeric_correlation():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    df = pd.DataFrame(
        {
            "x": x,
            "y_strong": x * 2 + rng.normal(scale=0.1, size=200),
            "z_noise": rng.normal(size=200),
        }
    )
    column_types = {"x": "numeric", "y_strong": "numeric", "z_noise": "numeric"}
    suggestion = suggest_chart_encoding(df, column_types)
    assert suggestion is not None
    assert suggestion["chart_type"] == "Scatter"
    assert {suggestion["col_x"], suggestion["col_y"]} == {"x", "y_strong"}
    assert "reason" in suggestion and suggestion["reason"]


def test_scatter_suggestion_colors_by_low_cardinality_categorical():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    df = pd.DataFrame(
        {
            "x": x,
            "y": x * 2 + rng.normal(scale=0.1, size=200),
            "segment": ["a", "b"] * 100,
        }
    )
    column_types = {"x": "numeric", "y": "numeric", "segment": "categorical"}
    suggestion = suggest_chart_encoding(df, column_types)
    assert suggestion is not None
    assert suggestion["color"] == "segment"


def test_suggests_bar_for_numeric_categorical_group_difference():
    df = pd.DataFrame(
        {
            "value": [10, 11, 9, 10, 100, 101, 99, 102],
            "group": ["low"] * 4 + ["high"] * 4,
        }
    )
    column_types = {"value": "numeric", "group": "categorical"}
    suggestion = suggest_chart_encoding(df, column_types)
    assert suggestion is not None
    assert suggestion["chart_type"] == "Bar"
    assert suggestion["col_x"] == "group"
    assert suggestion["col_y"] == "value"
    assert suggestion["agg"] == "mean"


def test_suggests_line_for_datetime_and_numeric_when_no_stronger_signal():
    rng = np.random.default_rng(2)
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=60, freq="D"),
            "sales": rng.normal(loc=100, scale=1, size=60),
        }
    )
    column_types = {"date": "datetime", "sales": "numeric"}
    suggestion = suggest_chart_encoding(df, column_types)
    assert suggestion is not None
    assert suggestion["chart_type"] == "Line"
    assert suggestion["col_x"] == "date"
    assert suggestion["col_y"] == "sales"


def test_suggests_histogram_for_lone_numeric_column():
    df = pd.DataFrame({"amount": range(50)})
    suggestion = suggest_chart_encoding(df, {"amount": "numeric"})
    assert suggestion is not None
    assert suggestion["chart_type"] == "Histogram"
    assert suggestion["col_x"] == "amount"


def test_suggests_bar_of_counts_for_lone_categorical_column():
    df = pd.DataFrame({"region": ["north", "south", "north", "east"] * 5})
    suggestion = suggest_chart_encoding(df, {"region": "categorical"})
    assert suggestion is not None
    assert suggestion["chart_type"] == "Bar"
    assert suggestion["col_x"] == "region"
    assert suggestion["col_y"] is None


def test_returns_none_for_empty_dataframe():
    assert suggest_chart_encoding(pd.DataFrame(), {}) is None


def test_returns_none_for_all_null_columns():
    df = pd.DataFrame({"a": [None, None, None], "b": [None, None, None]})
    column_types = {"a": "numeric", "b": "numeric"}
    assert suggest_chart_encoding(df, column_types) is None


def test_never_raises_on_high_cardinality_categorical_only():
    df = pd.DataFrame({"id": [f"row_{i}" for i in range(50)]})
    suggestion = suggest_chart_encoding(df, {"id": "categorical"})
    # A high-cardinality column is still a valid lone-categorical suggestion
    # (build_manual_chart itself caps to the top N categories) — must not raise.
    assert suggestion is None or suggestion["chart_type"] == "Bar"


def test_suggestion_chart_type_is_always_a_valid_manual_chart_type():
    df = pd.DataFrame(
        {
            "x": range(30),
            "y": [v * 2 for v in range(30)],
            "cat": (["a", "b", "c"] * 10),
        }
    )
    column_types = {"x": "numeric", "y": "numeric", "cat": "categorical"}
    suggestion = suggest_chart_encoding(df, column_types)
    assert suggestion is not None
    assert suggestion["chart_type"] in MANUAL_CHART_TYPES


def test_every_suggestion_builds_a_real_chart_without_raising():
    """The suggestion is only useful if build_manual_chart() actually accepts
    it — a suggester that recommends an encoding its own builder rejects
    would be worse than no suggestion. Exercise every suggestion branch."""
    rng = np.random.default_rng(3)
    cases = [
        # (df, column_types)
        (
            pd.DataFrame({"x": rng.normal(size=100), "y": rng.normal(size=100) + np.arange(100) * 0.05}),
            {"x": "numeric", "y": "numeric"},
        ),
        (
            pd.DataFrame({"value": [1, 2, 1, 2, 50, 51, 49, 52], "group": ["a"] * 4 + ["b"] * 4}),
            {"value": "numeric", "group": "categorical"},
        ),
        (
            pd.DataFrame({"date": pd.date_range("2024-01-01", periods=30, freq="D"), "n": rng.normal(size=30)}),
            {"date": "datetime", "n": "numeric"},
        ),
        (pd.DataFrame({"amount": range(20)}), {"amount": "numeric"}),
        (pd.DataFrame({"region": ["x", "y"] * 10}), {"region": "categorical"}),
    ]
    for df, column_types in cases:
        suggestion = suggest_chart_encoding(df, column_types)
        assert suggestion is not None
        fig = build_manual_chart(
            df,
            suggestion["chart_type"],
            suggestion["col_x"],
            suggestion.get("col_y"),
            color=suggestion.get("color"),
            agg=suggestion.get("agg", "mean"),
            facet=suggestion.get("facet"),
        )
        assert fig is not None
