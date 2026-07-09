"""
Story Mode — assembles a full-screen "presentation" out of an existing set
of findings and charts (Auto Analyst's synthesized top findings + the
auto-generated charts already built elsewhere in the app). This is pure
content assembly, not a new analysis feature — it re-presents results the
app already computed. app.py owns the actual stepper UI (current-step
index, Next/Prev buttons, styling).
"""

from __future__ import annotations

import plotly.graph_objects as go


def build_story_steps(
    dataset_name: str,
    n_rows: int,
    n_cols: int,
    findings: list[str],
    charts: dict[str, go.Figure],
) -> list[dict]:
    """Build an ordered list of {"headline", "narrative", "chart", "chart_title"} steps:
    an intro, one step per finding, and a closing step.

    Charts are cycled round-robin across findings so every finding gets a
    visual whenever any charts are available at all, even with fewer charts
    than findings.
    """
    chart_items = list(charts.items())

    steps = [
        {
            "headline": "Your Data Story",
            "narrative": (
                f"A walkthrough of {dataset_name} — {n_rows:,} rows and {n_cols} columns — "
                "and what stood out most."
            ),
            "chart": chart_items[0][1] if chart_items else None,
            "chart_title": chart_items[0][0] if chart_items else None,
        }
    ]

    for i, finding in enumerate(findings):
        chart_title, chart_fig = (None, None)
        if chart_items:
            chart_title, chart_fig = chart_items[(i + 1) % len(chart_items)]
        steps.append(
            {
                "headline": f"Finding {i + 1}",
                "narrative": finding,
                "chart": chart_fig,
                "chart_title": chart_title,
            }
        )

    steps.append(
        {
            "headline": "That's the story",
            "narrative": "Explore any tab to dig deeper, export a full report, or ask a follow-up question.",
            "chart": None,
            "chart_title": None,
        }
    )
    return steps
