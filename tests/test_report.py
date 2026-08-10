"""Tests for modules/report.py — first coverage for this module.

Covers this run's addition: the Data Health Score section in the
exportable HTML report (`generate_html_report(..., health_breakdown=...)`),
optional and backward-compatible so existing callers without it still get
a report.
"""

import pandas as pd
import plotly.graph_objects as go

from modules import data_engine
from modules.report import generate_html_report


def _sample_inputs():
    df = pd.DataFrame({"a": [1, 2, 3, None], "b": ["x", "y", "y", "z"]})
    column_types = data_engine.detect_column_types(df)
    quality = data_engine.get_data_quality_report(df, column_types)
    stats_df = pd.DataFrame({"a": [1, 2, 3]})
    charts = {"Sample Chart": go.Figure()}
    return df, quality, stats_df, charts, column_types


def test_report_without_health_breakdown_omits_section():
    df, quality, stats_df, charts, _ = _sample_inputs()
    html = generate_html_report(df, quality, stats_df, charts)
    assert "Data Health Score" not in html
    assert "Prism — Auto-EDA Report" in html


def test_report_with_health_breakdown_includes_score_and_components():
    df, quality, stats_df, charts, column_types = _sample_inputs()
    breakdown = data_engine.get_health_breakdown(quality, column_types)
    html = generate_html_report(df, quality, stats_df, charts, health_breakdown=breakdown)

    assert "Data Health Score" in html
    assert f"{breakdown['total']} / 100" in html
    for component in data_engine.HEALTH_COMPONENT_WEIGHTS:
        assert component.replace("_", " ").title() in html
