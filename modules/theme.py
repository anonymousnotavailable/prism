"""Theme — dark (default) and light Streamlit styling, plus a matching Plotly template.

Dark is Prism's brand look (deep navy background, cyan accents); light is a
straightforward high-contrast alternative for users who prefer it. Both
`apply_custom_theme()` and `apply_plotly_theme()` take a `mode` ("dark" |
"light") so app.py's sidebar toggle can switch both together.

v2 Part 2 (UI/UX Overhaul) added: Space Grotesk/Inter font pairing, an 8px
spacing + rounded-xl radius system (CSS custom properties), glassmorphism
cards, hover lift/glow micro-interactions, a shimmer skeleton-loader class,
a sticky mini-header, and a responsive rule that stops Streamlit's column
layout from causing horizontal scroll on narrow viewports.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

DARK_TEMPLATE_NAME = "prism_dark"
LIGHT_TEMPLATE_NAME = "prism_light"

# Shared across both themes: fonts, the 8px spacing / rounded-xl radius
# system, hover micro-interactions, shimmer loader, sticky header base, and
# the narrow-viewport column-wrap fix. Color values live in the per-mode
# blocks below so this stays theme-agnostic.
_SHARED_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

    :root {
        --prism-radius-xl: 1.1rem;
        --prism-radius-lg: 0.9rem;
        --prism-radius-md: 0.65rem;
        --prism-space-1: 0.5rem;
        --prism-space-2: 1rem;
        --prism-space-3: 1.5rem;
        --prism-space-4: 2rem;
    }

    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    }
    h1, h2, h3, h4, .prism-heading {
        font-family: 'Space Grotesk', 'Segoe UI', Arial, sans-serif !important;
        letter-spacing: 0.01em;
    }

    .stAlert {
        border-radius: var(--prism-radius-md);
    }
    /* SQL Lab's query editor — force a monospace font like a real code editor */
    textarea {
        font-family: 'Consolas', 'Courier New', monospace !important;
        font-size: 0.9rem !important;
    }

    /* Larger touch targets + rounded-xl on every interactive control */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
        border-radius: var(--prism-radius-lg) !important;
        padding: 0.6rem 1.3rem !important;
        min-height: 2.75rem;
        transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
        transform: translateY(-2px);
        filter: brightness(1.05);
    }
    .stButton > button:active, .stDownloadButton > button:active {
        transform: translateY(0);
    }
    .stTextInput input, .stTextArea textarea, .stSelectbox > div, .stMultiSelect > div {
        border-radius: var(--prism-radius-md) !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: var(--prism-radius-md) var(--prism-radius-md) 0 0 !important;
        transition: all 0.18s ease;
    }

    /* Glassmorphism — used for feature cards, insight cards, empty states,
       and the sticky mini-header. Alpha/border colors differ per theme. */
    .glass-card {
        border-radius: var(--prism-radius-xl);
        backdrop-filter: blur(14px) saturate(160%);
        -webkit-backdrop-filter: blur(14px) saturate(160%);
        transition: transform 0.22s ease, box-shadow 0.22s ease;
    }
    .glass-card.hoverable:hover {
        transform: translateY(-4px);
    }

    /* Shimmer skeleton loader — an alternative to st.spinner for a couple of
       longer-running actions, per the v2 spec's "skeleton loaders" ask. */
    @keyframes prism-shimmer-sweep {
        0% { background-position: -400px 0; }
        100% { background-position: 400px 0; }
    }
    .prism-shimmer {
        border-radius: var(--prism-radius-lg);
        background-image: linear-gradient(90deg, rgba(255,255,255,0.04) 0px,
            rgba(255,255,255,0.12) 40px, rgba(255,255,255,0.04) 80px);
        background-size: 400px 100%;
        animation: prism-shimmer-sweep 1.4s ease-in-out infinite;
    }

    /* Animated gradient shimmer on the "PRISM" wordmark — deep navy through
       electric blue to cyan, per the v2 spec. */
    @keyframes prism-hero-shift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .hero-title-animated {
        background: linear-gradient(90deg, #0a1a3d, #2979ff, #00e5ff, #2979ff, #0a1a3d);
        background-size: 300% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: prism-hero-shift 7s ease infinite;
        font-weight: 700;
        letter-spacing: 0.08em;
    }

    /* Sticky mini-header: dataset name, shape, and health score, always visible. */
    .prism-sticky-header {
        position: sticky;
        top: 0;
        z-index: 999;
        border-radius: var(--prism-radius-lg);
        padding: 0.6rem 1.1rem;
        margin-bottom: var(--prism-space-2);
        display: flex;
        align-items: center;
        gap: var(--prism-space-3);
        flex-wrap: wrap;
    }
    .prism-sticky-header .chip {
        font-size: 0.82rem;
        font-weight: 600;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
    }

    /* Empty-state cards */
    .prism-empty-state {
        text-align: center;
        border-radius: var(--prism-radius-xl);
        padding: var(--prism-space-4) var(--prism-space-3);
        margin: var(--prism-space-2) 0;
    }
    .prism-empty-state .icon { font-size: 2.2rem; margin-bottom: 0.4rem; }
    .prism-empty-state .title { font-weight: 700; font-size: 1.05rem; margin-bottom: 0.25rem; }
    .prism-empty-state .message { font-size: 0.9rem; opacity: 0.85; }

    /* Command palette suggestion chip */
    .prism-palette-hit {
        border-radius: var(--prism-radius-lg);
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
    }

    /* Narrow-viewport fix: Streamlit's column layout doesn't wrap on its own,
       which causes a horizontal-scroll disaster on phone-width screens. */
    @media (max-width: 680px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"] > div {
            min-width: 100% !important;
        }
        .hero-title-animated { font-size: 2.6rem !important; }
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
        color: #9fb3c8;
        padding: 8px 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background: #14243a;
        color: #00e5ff !important;
        border-bottom: 2px solid #00e5ff;
        box-shadow: 0 0 16px rgba(0, 229, 255, 0.35);
    }}
    div[data-testid="stMetric"] {{
        background: rgba(17, 24, 39, 0.55);
        border: 1px solid rgba(0, 229, 255, 0.15);
        border-radius: var(--prism-radius-lg);
        padding: 12px 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        transform: translateY(-3px);
        box-shadow: 0 8px 28px rgba(0, 229, 255, 0.18);
    }}
    div[data-testid="stMetricValue"] {{
        color: #00e5ff;
    }}
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background: linear-gradient(90deg, #00b8d4, #00e5ff);
        color: #05070d;
        border: none;
        font-weight: 600;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        box-shadow: 0 8px 24px rgba(0, 229, 255, 0.45);
    }}
    code {{
        color: #7ef9ff;
    }}
    .insight-card {{
        background: rgba(17, 24, 39, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 3px solid #00e5ff;
        border-radius: var(--prism-radius-lg);
        padding: 14px 18px;
        margin-bottom: 10px;
        backdrop-filter: blur(12px) saturate(160%);
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .insight-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 30px rgba(0, 229, 255, 0.2);
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
    .glass-card {{
        background: rgba(17, 24, 39, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
    }}
    .glass-card.hoverable:hover {{
        box-shadow: 0 12px 32px rgba(0, 229, 255, 0.22);
    }}
    .prism-sticky-header {{
        background: rgba(13, 18, 32, 0.75);
        border: 1px solid rgba(0, 229, 255, 0.15);
        color: #e0f7fa;
        backdrop-filter: blur(14px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }}
    .prism-sticky-header .chip {{
        background: rgba(0, 229, 255, 0.1);
        color: #00e5ff;
        border: 1px solid rgba(0, 229, 255, 0.25);
    }}
    .prism-empty-state {{
        background: rgba(17, 24, 39, 0.4);
        border: 1px dashed rgba(0, 229, 255, 0.25);
        color: #9fb3c8;
    }}
    .prism-empty-state .title {{ color: #00e5ff; }}
    .prism-palette-hit {{
        background: rgba(0, 229, 255, 0.08);
        border: 1px solid rgba(0, 229, 255, 0.3);
        color: #e0f7fa;
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
        color: #45566e;
        padding: 8px 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background: #ffffff;
        color: #007b94 !important;
        border-bottom: 2px solid #007b94;
        box-shadow: 0 0 14px rgba(0, 123, 148, 0.25);
    }}
    div[data-testid="stMetric"] {{
        background: rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(0, 123, 148, 0.18);
        border-radius: var(--prism-radius-lg);
        padding: 12px 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        transform: translateY(-3px);
        box-shadow: 0 8px 22px rgba(0, 123, 148, 0.18);
    }}
    div[data-testid="stMetricValue"] {{
        color: #007b94;
    }}
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background: linear-gradient(90deg, #007b94, #00a8c6);
        color: #ffffff;
        border: none;
        font-weight: 600;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        box-shadow: 0 8px 20px rgba(0, 123, 148, 0.35);
    }}
    code {{
        color: #007b94;
    }}
    .insight-card {{
        background: rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(0, 0, 0, 0.06);
        border-left: 3px solid #007b94;
        border-radius: var(--prism-radius-lg);
        padding: 14px 18px;
        margin-bottom: 10px;
        backdrop-filter: blur(12px) saturate(160%);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .insight-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 26px rgba(0, 123, 148, 0.18);
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
    .glass-card {{
        background: rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(0, 0, 0, 0.06);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
    }}
    .glass-card.hoverable:hover {{
        box-shadow: 0 12px 28px rgba(0, 123, 148, 0.18);
    }}
    .prism-sticky-header {{
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid rgba(0, 123, 148, 0.18);
        color: #0a0e17;
        backdrop-filter: blur(14px);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    }}
    .prism-sticky-header .chip {{
        background: rgba(0, 123, 148, 0.1);
        color: #007b94;
        border: 1px solid rgba(0, 123, 148, 0.25);
    }}
    .prism-empty-state {{
        background: rgba(255, 255, 255, 0.5);
        border: 1px dashed rgba(0, 123, 148, 0.3);
        color: #45566e;
    }}
    .prism-empty-state .title {{ color: #007b94; }}
    .prism-palette-hit {{
        background: rgba(0, 123, 148, 0.08);
        border: 1px solid rgba(0, 123, 148, 0.3);
        color: #0a0e17;
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
            font=dict(color=font_color, family="Inter, Segoe UI, Arial, sans-serif", size=13),
            title=dict(font=dict(color=title_color, size=19, family="Space Grotesk, Segoe UI, Arial, sans-serif")),
            colorway=colorway,
            xaxis=axis_style,
            yaxis=axis_style,
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=legend_font)),
            hoverlabel=dict(bgcolor=hover_bg, font=dict(color=hover_font)),
        )
    )


# Cyan / magenta / amber palette (plus supporting hues) — transparent
# backgrounds so every chart sits directly on Prism's glass/gradient
# surfaces instead of a boxed-in plot area.
_CHART_COLORWAY = ["#00e5ff", "#ff36ab", "#ffab40", "#7c4dff", "#69f0ae", "#40c4ff", "#f06292", "#b388ff"]


def apply_plotly_theme(mode: str = "dark") -> None:
    """Register the dark and light Plotly templates (once) and activate the
    requested one as the process-wide default.

    Every chart built with plotly.express — whether from visualization.py, the
    HTML report, or code the AI Analyst generates — picks this up automatically
    without each call site repeating the same layout overrides.
    """
    if DARK_TEMPLATE_NAME not in pio.templates:
        pio.templates[DARK_TEMPLATE_NAME] = _build_template(
            paper_bg="rgba(0,0,0,0)", plot_bg="rgba(0,0,0,0)", font_color="#e0f7fa", title_color="#00e5ff",
            grid_color="rgba(159,179,200,0.15)", zero_color="rgba(159,179,200,0.25)",
            line_color="rgba(159,179,200,0.25)", tick_color="#9fb3c8",
            legend_font="#e0f7fa", hover_bg="#111827", hover_font="#e0f7fa",
            colorway=_CHART_COLORWAY,
        )
    if LIGHT_TEMPLATE_NAME not in pio.templates:
        pio.templates[LIGHT_TEMPLATE_NAME] = _build_template(
            paper_bg="rgba(0,0,0,0)", plot_bg="rgba(0,0,0,0)", font_color="#0a0e17", title_color="#007b94",
            grid_color="rgba(69,86,110,0.15)", zero_color="rgba(69,86,110,0.25)",
            line_color="rgba(69,86,110,0.25)", tick_color="#45566e",
            legend_font="#0a0e17", hover_bg="#ffffff", hover_font="#0a0e17",
            colorway=["#007b94", "#d81b60", "#f57c00", "#7c4dff", "#00897b", "#3949ab", "#c2185b", "#5e35b1"],
        )
    pio.templates.default = LIGHT_TEMPLATE_NAME if mode == "light" else DARK_TEMPLATE_NAME
