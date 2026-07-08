"""Theme — dark (default) and light Streamlit styling, plus a matching Plotly template.

Dark is Prism's brand look (deep navy background, cyan accents); light is a
straightforward high-contrast alternative for users who prefer it. Both
`apply_custom_theme()` and `apply_plotly_theme()` take a `mode` ("dark" |
"light") so app.py's sidebar toggle can switch both together.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

DARK_TEMPLATE_NAME = "prism_dark"
LIGHT_TEMPLATE_NAME = "prism_light"

# Shared across both themes so components like insight-card and the SQL
# editor's monospace font don't need to be duplicated per-mode.
_SHARED_CSS = """
    .stAlert {
        border-radius: 8px;
    }
    /* SQL Lab's query editor — force a monospace font like a real code editor */
    textarea {
        font-family: 'Consolas', 'Courier New', monospace !important;
        font-size: 0.9rem !important;
    }
"""

CUSTOM_CSS_DARK = f"""
<style>
    .stApp {{
        background: linear-gradient(180deg, #05070d 0%, #0a0e17 100%);
        color: #e0f7fa;
    }}
    section[data-testid="stSidebar"] {{
        background: #0d1220;
        border-right: 1px solid #1c2942;
    }}
    h1, h2, h3 {{
        color: #00e5ff !important;
        text-shadow: 0 0 12px rgba(0, 229, 255, 0.25);
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: #111827;
        border-radius: 8px 8px 0 0;
        color: #9fb3c8;
        padding: 8px 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background: #14243a;
        color: #00e5ff !important;
        border-bottom: 2px solid #00e5ff;
    }}
    div[data-testid="stMetric"] {{
        background: #111827;
        border: 1px solid #1c2942;
        border-radius: 10px;
        padding: 12px 16px;
    }}
    div[data-testid="stMetricValue"] {{
        color: #00e5ff;
    }}
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background: linear-gradient(90deg, #00b8d4, #00e5ff);
        color: #05070d;
        border: none;
        border-radius: 6px;
        font-weight: 600;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        box-shadow: 0 0 14px rgba(0, 229, 255, 0.5);
    }}
    code {{
        color: #7ef9ff;
    }}
    .insight-card {{
        background: #111827;
        border: 1px solid #1c2942;
        border-left: 3px solid #00e5ff;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }}
    .insight-card .insight-number {{
        color: #00e5ff;
        font-weight: 700;
        font-size: 0.8rem;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }}
    .insight-card .insight-text {{
        color: #e0f7fa;
        font-size: 0.95rem;
        line-height: 1.5;
    }}
    {_SHARED_CSS}
</style>
"""

CUSTOM_CSS_LIGHT = f"""
<style>
    .stApp {{
        background: linear-gradient(180deg, #ffffff 0%, #eef2f7 100%);
        color: #0a0e17;
    }}
    section[data-testid="stSidebar"] {{
        background: #f4f6f9;
        border-right: 1px solid #d6dee8;
    }}
    h1, h2, h3 {{
        color: #007b94 !important;
        text-shadow: none;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: #e6ecf3;
        border-radius: 8px 8px 0 0;
        color: #45566e;
        padding: 8px 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background: #ffffff;
        color: #007b94 !important;
        border-bottom: 2px solid #007b94;
    }}
    div[data-testid="stMetric"] {{
        background: #ffffff;
        border: 1px solid #d6dee8;
        border-radius: 10px;
        padding: 12px 16px;
    }}
    div[data-testid="stMetricValue"] {{
        color: #007b94;
    }}
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background: linear-gradient(90deg, #007b94, #00a8c6);
        color: #ffffff;
        border: none;
        border-radius: 6px;
        font-weight: 600;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        box-shadow: 0 0 10px rgba(0, 123, 148, 0.4);
    }}
    code {{
        color: #007b94;
    }}
    .insight-card {{
        background: #ffffff;
        border: 1px solid #d6dee8;
        border-left: 3px solid #007b94;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }}
    .insight-card .insight-number {{
        color: #007b94;
        font-weight: 700;
        font-size: 0.8rem;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }}
    .insight-card .insight-text {{
        color: #0a0e17;
        font-size: 0.95rem;
        line-height: 1.5;
    }}
    {_SHARED_CSS}
</style>
"""


def apply_custom_theme(mode: str = "dark") -> None:
    """Inject the CSS for the given mode ("dark" | "light"). Call once per
    rerun, right after set_page_config, before any other UI is rendered.
    """
    st.markdown(CUSTOM_CSS_LIGHT if mode == "light" else CUSTOM_CSS_DARK, unsafe_allow_html=True)


def _build_template(paper_bg, plot_bg, font_color, title_color, grid_color, zero_color, line_color,
                     tick_color, legend_font, hover_bg, hover_font, colorway) -> go.layout.Template:
    axis_style = dict(gridcolor=grid_color, zerolinecolor=zero_color, linecolor=line_color,
                       tickfont=dict(color=tick_color))
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=paper_bg,
            plot_bgcolor=plot_bg,
            font=dict(color=font_color, family="Segoe UI, Arial, sans-serif", size=13),
            title=dict(font=dict(color=title_color, size=18)),
            colorway=colorway,
            xaxis=axis_style,
            yaxis=axis_style,
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=legend_font)),
            hoverlabel=dict(bgcolor=hover_bg, font=dict(color=hover_font)),
        )
    )


def apply_plotly_theme(mode: str = "dark") -> None:
    """Register the dark and light Plotly templates (once) and activate the
    requested one as the process-wide default.

    Every chart built with plotly.express — whether from visualization.py, the
    HTML report, or code the AI Analyst generates — picks this up automatically
    without each call site repeating the same layout overrides.
    """
    if DARK_TEMPLATE_NAME not in pio.templates:
        pio.templates[DARK_TEMPLATE_NAME] = _build_template(
            paper_bg="#0a0e17", plot_bg="#0d1220", font_color="#e0f7fa", title_color="#00e5ff",
            grid_color="#1c2942", zero_color="#26344a", line_color="#26344a", tick_color="#9fb3c8",
            legend_font="#e0f7fa", hover_bg="#111827", hover_font="#e0f7fa",
            colorway=["#00e5ff", "#7c4dff", "#ff4081", "#69f0ae", "#ffab40", "#40c4ff", "#f06292", "#b388ff"],
        )
    if LIGHT_TEMPLATE_NAME not in pio.templates:
        pio.templates[LIGHT_TEMPLATE_NAME] = _build_template(
            paper_bg="#ffffff", plot_bg="#ffffff", font_color="#0a0e17", title_color="#007b94",
            grid_color="#e6ecf3", zero_color="#d6dee8", line_color="#d6dee8", tick_color="#45566e",
            legend_font="#0a0e17", hover_bg="#ffffff", hover_font="#0a0e17",
            colorway=["#007b94", "#7c4dff", "#d81b60", "#00897b", "#f57c00", "#3949ab", "#c2185b", "#5e35b1"],
        )
    pio.templates.default = LIGHT_TEMPLATE_NAME if mode == "light" else DARK_TEMPLATE_NAME
