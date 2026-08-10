"""Tests for modules.ui.build_html_table — the theme-aware HTML table used
in place of st.dataframe() for small Overview summary tables, since
st.dataframe()'s canvas-based grid doesn't respect the in-app light/dark
toggle (see .prism/audit_2026-08-10.md and build_html_table's docstring).
"""

from __future__ import annotations

import pandas as pd

from modules import ui


def test_renders_headers_and_cell_values():
    df = pd.DataFrame({"Column": ["age", "income"], "Missing %": [1.5, 0.0]})
    html_out = ui.build_html_table(df)
    assert "<th>Column</th>" in html_out
    assert "<th>Missing %</th>" in html_out
    assert "<td>age</td>" in html_out
    assert "<td>1.5</td>" in html_out


def test_uses_prism_theme_css_classes_not_streamlit_dataframe():
    df = pd.DataFrame({"x": [1]})
    html_out = ui.build_html_table(df)
    assert "prism-html-table" in html_out
    assert "<table" in html_out


def test_escapes_html_in_cell_and_column_values():
    df = pd.DataFrame({"<script>": ["<b>bold</b>"]})
    html_out = ui.build_html_table(df)
    assert "<script>" not in html_out.replace("&lt;script&gt;", "")
    assert "&lt;script&gt;" in html_out
    assert "&lt;b&gt;bold&lt;/b&gt;" in html_out


def test_handles_empty_dataframe():
    df = pd.DataFrame({"Column": [], "Missing %": []})
    html_out = ui.build_html_table(df)
    assert "<thead>" in html_out
    assert "<tbody></tbody>" in html_out
