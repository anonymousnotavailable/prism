"""Tests for modules.auto_insights — proactive statistical insight detectors.

Ported from eval/auto_insights_eval.py (Run 2 shipped this as a standalone
print/check() script that pytest never collected; see .prism/audit_2026-08-10.md).
Same fixtures and assertions, phrased as real pytest tests so `pytest` shows
the coverage the project actually claims.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.auto_insights import (
    _detect_correlation_insights,
    _detect_distribution_insights,
    _detect_duplicate_rows,
    _detect_missing_insights,
    _detect_structural_insights,
    _iqr_outlier_pct,
    category_label,
    format_insights_text,
    generate_insights,
    severity_icon,
)


def make_clean_df() -> pd.DataFrame:
    """A clean dataset — should produce few/no insights."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "id": range(100),
            "value": rng.normal(50, 10, 100),
            "category": rng.choice(["A", "B", "C"], 100),
        }
    )


def make_messy_df() -> pd.DataFrame:
    """A messy dataset that should trigger many insights."""
    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame(
        {
            "price": np.concatenate([rng.normal(100, 20, 190), np.array([10000] * 10)]),  # outliers
            "quantity": rng.exponential(5, n),  # right-skewed
            "category": (["A"] * 180 + ["B"] * 10 + ["C"] * 10),  # imbalanced
            "unique_id": [f"ID_{i}" for i in range(n)],  # high cardinality
            "constant": [1] * n,  # near-constant
            "corr_a": rng.normal(0, 1, n),
        }
    )
    df["corr_b"] = df["corr_a"] * 0.95 + rng.normal(0, 0.1, n)  # strongly correlated
    df.loc[0:39, "price"] = np.nan  # 20% missing
    df = pd.concat([df, df.iloc[:20]], ignore_index=True)  # duplicate rows
    return df


CLEAN_TYPES = {"id": "numeric", "value": "numeric", "category": "categorical"}
MESSY_TYPES = {
    "price": "numeric",
    "quantity": "numeric",
    "category": "categorical",
    "unique_id": "categorical",
    "constant": "numeric",
    "corr_a": "numeric",
    "corr_b": "numeric",
}


def test_clean_dataset_produces_few_low_severity_insights():
    insights = generate_insights(make_clean_df(), CLEAN_TYPES)
    assert len(insights) <= 3
    assert all(i["severity"] != "high" for i in insights)


def test_messy_dataset_produces_many_insights_capped_at_max():
    insights = generate_insights(make_messy_df(), MESSY_TYPES)
    assert len(insights) >= 5
    assert len(insights) <= 12  # MAX_INSIGHTS cap


def test_messy_dataset_detects_expected_categories():
    insights = generate_insights(make_messy_df(), MESSY_TYPES)
    categories = {i["category"] for i in insights}
    assert "missing_data" in categories
    assert "correlation" in categories
    assert "duplicates" in categories


def test_insights_sorted_by_severity():
    insights = generate_insights(make_messy_df(), MESSY_TYPES)
    order = {"high": 0, "medium": 1, "low": 2}
    severities = [order[i["severity"]] for i in insights]
    assert severities == sorted(severities)


def test_skewed_distribution_detected():
    rng = np.random.default_rng(0)
    skewed = pd.DataFrame({"skewed": pd.Series(rng.exponential(0.3, 500) ** 2)})
    dist_insights = _detect_distribution_insights(skewed, {"skewed": "numeric"})
    assert len(dist_insights) > 0


def test_high_missing_column_detected():
    missing_df = pd.DataFrame({"col_a": [1, 2, None, None, None] * 20, "col_b": range(100)})
    miss_insights = _detect_missing_insights(missing_df)
    assert any("60" in i["metric"] for i in miss_insights)


def test_iqr_outlier_pct_low_for_normal_data():
    rng = np.random.default_rng(1)
    normal_vals = pd.Series(rng.normal(0, 1, 1000))
    assert _iqr_outlier_pct(normal_vals) < 10


def test_iqr_outlier_pct_high_for_spiked_data():
    rng = np.random.default_rng(2)
    core = rng.normal(50, 5, 900)
    spike = np.array([1000] * 100)
    spiked = pd.Series(np.concatenate([core, spike]))
    assert _iqr_outlier_pct(spiked) > 5


def test_near_constant_column_flagged_as_structural():
    const_df = pd.DataFrame({"x": [1] * 99 + [2]})
    struct_insights = _detect_structural_insights(const_df, {"x": "numeric"})
    assert any(i["category"] == "structure" for i in struct_insights)


def test_duplicate_rows_detected_once():
    dup_df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
    dup_insights = _detect_duplicate_rows(dup_df)
    assert len(dup_insights) == 1


def test_correlation_insights_flag_strongly_correlated_pair():
    messy_insights = generate_insights(make_messy_df(), MESSY_TYPES)
    corr_insights = [i for i in messy_insights if i["category"] == "correlation"]
    assert len(corr_insights) >= 1


def test_severity_icons_and_category_label():
    assert severity_icon("high") == "🔴"
    assert severity_icon("medium") == "🟡"
    assert severity_icon("low") == "🔵"
    assert category_label("missing_data") == "Missing Data"


def test_format_insights_text():
    messy_insights = generate_insights(make_messy_df(), MESSY_TYPES)
    formatted = format_insights_text(messy_insights)
    assert len(formatted) > 50
    assert "No notable" in format_insights_text([])


def test_empty_dataframe_produces_no_crash():
    insights = generate_insights(pd.DataFrame(), {})
    assert isinstance(insights, list)


def test_single_row_dataframe_produces_no_crash():
    single_df = pd.DataFrame({"a": [1], "b": ["x"]})
    insights = generate_insights(single_df, {"a": "numeric", "b": "categorical"})
    assert isinstance(insights, list)


def test_all_nan_column_detected_as_fully_missing():
    nan_df = pd.DataFrame({"all_nan": [None] * 100, "good": range(100)})
    insights = generate_insights(nan_df, {"all_nan": "numeric", "good": "numeric"})
    assert any("100" in i.get("metric", "") for i in insights)
