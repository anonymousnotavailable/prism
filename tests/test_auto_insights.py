"""
Auto-Insight Engine — pytest suite (ported from eval/auto_insights_eval.py,
which existed but was never wired into `pytest`/CI despite the CHANGELOG
claiming "23 new tests"; see .prism/audit_2026-08-10.md for how that gap
was found and .prism/routine_log.md for why it matters).
"""

import numpy as np
import pandas as pd

from modules.auto_insights import (
    _detect_distribution_insights,
    _detect_duplicate_rows,
    _detect_structural_insights,
    _iqr_outlier_pct,
    _detect_missing_insights,
    category_label,
    format_insights_text,
    generate_insights,
    severity_icon,
)


def make_clean_df():
    np.random.seed(42)
    return pd.DataFrame({
        "id": range(100),
        "value": np.random.normal(50, 10, 100),
        "category": np.random.choice(["A", "B", "C"], 100),
    })


def make_messy_df():
    np.random.seed(42)
    n = 200
    df = pd.DataFrame({
        "price": np.concatenate([np.random.normal(100, 20, 190), np.array([10000] * 10)]),
        "quantity": np.random.exponential(5, n),
        "category": (["A"] * 180 + ["B"] * 10 + ["C"] * 10),
        "unique_id": [f"ID_{i}" for i in range(n)],
        "constant": [1] * n,
        "corr_a": np.random.normal(0, 1, n),
    })
    df["corr_b"] = df["corr_a"] * 0.95 + np.random.normal(0, 0.1, n)
    df.loc[0:39, "price"] = np.nan
    return pd.concat([df, df.iloc[:20]], ignore_index=True)


MESSY_TYPES = {
    "price": "numeric", "quantity": "numeric", "category": "categorical",
    "unique_id": "categorical", "constant": "numeric", "corr_a": "numeric",
    "corr_b": "numeric",
}


def test_clean_dataset_has_few_low_severity_insights():
    clean_insights = generate_insights(make_clean_df(), {"id": "numeric", "value": "numeric", "category": "categorical"})
    assert len(clean_insights) <= 3
    assert all(i["severity"] != "high" for i in clean_insights)


def test_messy_dataset_flags_expected_categories():
    messy_insights = generate_insights(make_messy_df(), MESSY_TYPES)
    assert 5 <= len(messy_insights) <= 12
    categories_found = {i["category"] for i in messy_insights}
    assert "missing_data" in categories_found
    assert "correlation" in categories_found
    assert "duplicates" in categories_found


def test_insights_sorted_by_severity():
    messy_insights = generate_insights(make_messy_df(), MESSY_TYPES)
    order = {"high": 0, "medium": 1, "low": 2}
    severities = [order[i["severity"]] for i in messy_insights]
    assert severities == sorted(severities)


def test_skewed_distribution_detected():
    skewed_df = pd.DataFrame({"skewed": pd.Series(np.random.exponential(0.3, 500) ** 2)})
    assert len(_detect_distribution_insights(skewed_df, {"skewed": "numeric"})) > 0


def test_missing_data_percentage_reported():
    missing_df = pd.DataFrame({"col_a": [1, 2, None, None, None] * 20, "col_b": range(100)})
    miss_insights = _detect_missing_insights(missing_df)
    assert any("60" in i["metric"] for i in miss_insights)


def test_iqr_outlier_pct_low_for_normal_high_for_spiked():
    normal_vals = pd.Series(np.random.normal(0, 1, 1000))
    assert _iqr_outlier_pct(normal_vals) < 10

    core = np.random.normal(50, 5, 900)
    spike = np.array([1000] * 100)
    spiked = pd.Series(np.concatenate([core, spike]))
    assert _iqr_outlier_pct(spiked) > 5


def test_near_constant_column_detected():
    const_df = pd.DataFrame({"x": [1] * 99 + [2]})
    struct_insights = _detect_structural_insights(const_df, {"x": "numeric"})
    assert any(i["category"] == "structure" for i in struct_insights)


def test_duplicate_rows_detected():
    dup_df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
    assert len(_detect_duplicate_rows(dup_df)) == 1


def test_formatting_helpers():
    assert severity_icon("high") == "🔴"
    assert severity_icon("medium") == "🟡"
    assert severity_icon("low") == "🔵"
    assert category_label("missing_data") == "Missing Data"

    messy_insights = generate_insights(make_messy_df(), MESSY_TYPES)
    assert len(format_insights_text(messy_insights)) > 50
    assert "No notable" in format_insights_text([])


def test_edge_cases_do_not_crash():
    assert isinstance(generate_insights(pd.DataFrame(), {}), list)

    single_df = pd.DataFrame({"a": [1], "b": ["x"]})
    assert isinstance(generate_insights(single_df, {"a": "numeric", "b": "categorical"}), list)

    nan_df = pd.DataFrame({"all_nan": [None] * 100, "good": range(100)})
    nan_insights = generate_insights(nan_df, {"all_nan": "numeric", "good": "numeric"})
    assert any("100" in i.get("metric", "") for i in nan_insights)
