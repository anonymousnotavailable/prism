"""Theme — token-driven multi-theme system for Prism's Streamlit chrome and
matching Plotly templates.

Three curated themes ship by default: Graphite (dark, default), Midnight
(dark, violet-forward), and Arctic (light). Each is a flat dict of design
tokens; `_build_css()` turns any of them into the same stylesheet via
string.Template, so adding a fourth theme is just adding another token
dict below — no CSS duplication, and no risk of the dark/light copies
drifting out of sync the way the old two-hardcoded-strings version did.

`apply_custom_theme()` and `apply_plotly_theme()` both take a theme key
(one of THEMES) so app.py's sidebar selector can switch both together.
"""

from __future__ import annotations

from string import Template

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

THEMES: dict[str, dict] = {
    "graphite": {
        "label": "Graphite (Dark)",
        "mode": "dark",
        "bg": "#0A0C10",
        "bg_end": "#0D1016",
        "surface": "#12151B",
        "surface_hover": "#1A1E27",
        "border": "#232833",
        "text": "#F1F5F9",
        "text_muted": "#8A97A8",
        "accent": "#22D3EE",
        "accent_rgb": "34, 211, 238",
        "accent2": "#A78BFA",
        "accent2_rgb": "167, 139, 250",
        "success": "#34D399",
        "warning": "#FBBF24",
        "danger": "#F87171",
        "on_accent": "#04141A",
        "chart_colorway": ["#22D3EE", "#A78BFA", "#34D399", "#FBBF24", "#F87171", "#60A5FA", "#F472B6", "#94A3B8"],
    },
    "midnight": {
        "label": "Midnight (Dark)",
        "mode": "dark",
        "bg": "#0D0B14",
        "bg_end": "#120F1C",
        "surface": "#161320",
        "surface_hover": "#1E1A2C",
        "border": "#2A2438",
        "text": "#F5F3FF",
        "text_muted": "#9B92B5",
        "accent": "#A78BFA",
        "accent_rgb": "167, 139, 250",
        "accent2": "#22D3EE",
        "accent2_rgb": "34, 211, 238",
        "success": "#34D399",
        "warning": "#FBBF24",
        "danger": "#F87171",
        "on_accent": "#160B2E",
        "chart_colorway": ["#A78BFA", "#22D3EE", "#F472B6", "#34D399", "#FBBF24", "#F87171", "#60A5FA", "#94A3B8"],
    },
    "arctic": {
        "label": "Arctic (Light)",
        "mode": "light",
        "bg": "#F8FAFC",
        "bg_end": "#EEF2F7",
        "surface": "#FFFFFF",
        "surface_hover": "#F1F5F9",
        "border": "#E2E8F0",
        "text": "#0F172A",
        "text_muted": "#5B6B82",
        "accent": "#0891B2",
        "accent_rgb": "8, 145, 178",
        "accent2": "#7C3AED",
        "accent2_rgb": "124, 58, 237",
        "success": "#059669",
        "warning": "#B45309",
        "danger": "#DC2626",
        "on_accent": "#FFFFFF",
        "chart_colorway": ["#0891B2", "#7C3AED", "#059669", "#B45309", "#DC2626", "#2563EB", "#DB2777", "#64748B"],
    },
}

DEFAULT_THEME = "graphite"


def theme_options() -> dict[str, str]:
    """key -> display label, for the sidebar selectbox."""
    return {key: t["label"] for key, t in THEMES.items()}


def _tokens(theme_key: str) -> dict:
    return THEMES.get(theme_key, THEMES[DEFAULT_THEME])


# One template for every theme — dark and light are just different token
# values flowing through the same rules, so they can never drift apart.
_CSS_TEMPLATE = Template(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --prism-bg: $bg;
    --prism-surface: $surface;
    --prism-surface-hover: $surface_hover;
    --prism-border: $border;
    --prism-text: $text;
    --prism-text-muted: $text_muted;
    --prism-accent: $accent;
    --prism-accent-rgb: $accent_rgb;
    --prism-accent2: $accent2;
    --prism-accent2-rgb: $accent2_rgb;
    --prism-success: $success;
    --prism-warning: $warning;
    --prism-danger: $danger;
    --prism-on-accent: $on_accent;
    --prism-radius: 14px;
    --prism-ease: cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes prismFadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes prismShimmer { 0% { background-position: 0% 50%; } 100% { background-position: 200% 50%; } }
@keyframes prismPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
        scroll-behavior: auto !important;
    }
}

html, body, [class*="css"] { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }

.stApp {
    background: linear-gradient(180deg, $bg 0%, $bg_end 100%);
    color: $text;
}

::selection { background: $accent; color: $on_accent; }

/* ── Scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba($accent_rgb, 0.35); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: rgba($accent_rgb, 0.55); }

/* ── Sidebar ─────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: $surface;
    border-right: 1px solid $border;
}
section[data-testid="stSidebar"] hr { border-color: $border; }

/* ── Native Streamlit chrome ─────────────────────────────────────────
   Streamlit's own widgets (header bar, captions, labels, file uploader)
   read from its built-in dark theme regardless of our injected CSS
   unless explicitly overridden here — otherwise a light theme like
   Arctic inherits near-invisible light-on-light text and a stray dark
   top bar. */
header[data-testid="stHeader"] { background: $bg !important; }
div[data-testid="stCaptionContainer"], .stCaption, small {
    color: $text_muted !important;
}
label[data-testid="stWidgetLabel"] p { color: $text !important; }
section[data-testid="stFileUploaderDropzone"] {
    background: $surface !important;
    border: 1px dashed $border !important;
    border-radius: 10px !important;
}
section[data-testid="stFileUploaderDropzone"] span,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] div {
    color: $text_muted !important;
}
section[data-testid="stFileUploaderDropzone"] button {
    background: $surface_hover !important;
    color: $text !important;
    border: 1px solid $border !important;
}

/* ── Headings ────────────────────────────────────────────────────── */
h1, h2, h3 { color: $text !important; font-weight: 700 !important; letter-spacing: -0.01em; }
h4, h5, h6 { color: $text !important; font-weight: 600 !important; }

/* ── Tabs ────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid $border; }
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px 8px 0 0;
    color: $text_muted;
    padding: 10px 20px;
    font-weight: 500;
    transition: color 0.2s $ease, background 0.2s $ease;
}
.stTabs [data-baseweb="tab"]:hover { color: $text; background: $surface_hover; }
.stTabs [aria-selected="true"] {
    background: $surface;
    color: $accent !important;
    font-weight: 600;
    box-shadow: inset 0 -2px 0 $accent;
}

/* ── Metrics ─────────────────────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: var(--prism-radius);
    padding: 14px 18px;
    transition: transform 0.2s $ease, border-color 0.2s $ease, box-shadow 0.2s $ease;
    animation: prismFadeInUp 0.4s $ease both;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    border-color: rgba($accent_rgb, 0.5);
    box-shadow: 0 10px 28px -14px rgba($accent_rgb, 0.35);
}
div[data-testid="stMetricValue"] { color: $accent; font-weight: 700; }
div[data-testid="stMetricLabel"] { color: $text_muted; }

/* ── Buttons ─────────────────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    background: linear-gradient(90deg, $accent, $accent2);
    color: $on_accent;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    letter-spacing: 0.01em;
    transition: transform 0.15s $ease, box-shadow 0.15s $ease, filter 0.15s $ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 22px -8px rgba($accent_rgb, 0.55);
    filter: brightness(1.05);
}
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0) scale(0.98); }

/* Secondary / non-primary buttons keep a quieter outline treatment */
button[kind="secondary"] {
    background: $surface !important;
    color: $text !important;
    border: 1px solid $border !important;
}
button[kind="secondary"]:hover { border-color: $accent !important; color: $accent !important; }

/* ── Inputs, selects, textareas ─────────────────────────────────── */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div, .stMultiSelect [data-baseweb="select"] > div {
    background: $surface !important;
    border: 1px solid $border !important;
    border-radius: 8px !important;
    color: $text !important;
    transition: border-color 0.15s $ease, box-shadow 0.15s $ease;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color: $accent !important;
    box-shadow: 0 0 0 3px rgba($accent_rgb, 0.18) !important;
}
textarea {
    font-family: 'JetBrains Mono', 'Consolas', monospace !important;
    font-size: 0.9rem !important;
}
/* Multiselect tag chips — BaseWeb otherwise pulls the config.toml primaryColor,
   which doesn't track the active theme. */
span[data-baseweb="tag"] { background: $accent !important; color: $on_accent !important; }

/* ── Expanders ───────────────────────────────────────────────────── */
.streamlit-expanderHeader, div[data-testid="stExpander"] summary {
    background: $surface !important;
    border: 1px solid $border !important;
    border-radius: 10px !important;
    color: $text !important;
    font-weight: 500;
    transition: border-color 0.2s $ease;
}
div[data-testid="stExpander"] summary:hover { border-color: rgba($accent_rgb, 0.5) !important; }

/* ── Dataframes / tables ─────────────────────────────────────────── */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    border: 1px solid $border;
    border-radius: var(--prism-radius);
    overflow: hidden;
}

/* ── Alerts ──────────────────────────────────────────────────────── */
.stAlert { border-radius: 10px; animation: prismFadeInUp 0.3s $ease both; }

code { color: $accent; }

/* ── Prism component classes (used from ui.py's injected HTML) ─────── */
.prism-card {
    background: $surface;
    border: 1px solid $border;
    border-radius: var(--prism-radius);
    padding: 1.25rem 1.25rem;
    height: 100%;
    transition: transform 0.2s $ease, border-color 0.2s $ease, box-shadow 0.2s $ease;
    animation: prismFadeInUp 0.45s $ease both;
}
.prism-card:hover {
    transform: translateY(-3px);
    border-color: rgba($accent_rgb, 0.55);
    box-shadow: 0 16px 36px -16px rgba($accent_rgb, 0.35);
}
.prism-card-icon {
    width: 22px; height: 22px;
    color: $accent;
    margin-bottom: 0.65rem;
}
.prism-card-title { color: $text; font-weight: 700; font-size: 1.02rem; margin-bottom: 0.4rem; }
.prism-card-desc { color: $text_muted; font-size: 0.86rem; line-height: 1.5; }

.prism-badge {
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.28rem 0.65rem; border-radius: 999px;
    background: rgba($accent_rgb, 0.12); color: $accent;
}
.prism-badge.ai { background: rgba($accent2_rgb, 0.14); color: $accent2; }

.prism-hero-title {
    font-weight: 800; font-size: 3.6rem; letter-spacing: -0.02em; line-height: 1;
    background: linear-gradient(90deg, $accent, $accent2, $accent);
    background-size: 200% auto;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    animation: prismShimmer 7s linear infinite;
}

.prism-live-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: $success; box-shadow: 0 0 8px $success;
    animation: prismPulse 2.2s ease-in-out infinite;
}

.insight-card {
    background: $surface;
    border: 1px solid $border;
    border-left: 3px solid $accent2;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    transition: border-color 0.2s $ease, transform 0.2s $ease;
    animation: prismFadeInUp 0.35s $ease both;
}
.insight-card:hover { transform: translateX(2px); border-left-color: $accent; }
.insight-card .insight-number {
    color: $accent2; font-weight: 700; font-size: 0.8rem; letter-spacing: 0.05em; margin-bottom: 4px;
}
.insight-card .insight-text { color: $text; font-size: 0.95rem; line-height: 1.55; }

.prism-footer {
    text-align: center; padding: 2rem 0 1rem 0; margin-top: 2rem;
    border-top: 1px solid $border; color: $text_muted; font-size: 0.85rem;
}
.prism-footer a { color: $accent; text-decoration: none; }
.prism-footer a:hover { text-decoration: underline; }
</style>
"""
)


def apply_custom_theme(theme_key: str = DEFAULT_THEME) -> None:
    """Inject the CSS for the given theme key. Call once per rerun, right
    after set_page_config, before any other UI is rendered.
    """
    st.markdown(_CSS_TEMPLATE.substitute(_tokens(theme_key), ease="var(--prism-ease)"), unsafe_allow_html=True)


def _build_template(tokens: dict) -> go.layout.Template:
    is_light = tokens["mode"] == "light"
    grid = tokens["border"]
    axis_style = dict(
        gridcolor=grid,
        zerolinecolor=tokens["border"],
        linecolor=tokens["border"],
        tickfont=dict(color=tokens["text_muted"]),
    )
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=tokens["surface"] if is_light else tokens["bg"],
            plot_bgcolor=tokens["surface"] if is_light else tokens["surface"],
            font=dict(color=tokens["text"], family="Inter, Segoe UI, Arial, sans-serif", size=13),
            title=dict(font=dict(color=tokens["text"], size=18)),
            colorway=tokens["chart_colorway"],
            xaxis=axis_style,
            yaxis=axis_style,
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=tokens["text"])),
            hoverlabel=dict(bgcolor=tokens["surface_hover"], font=dict(color=tokens["text"])),
        )
    )


def apply_plotly_theme(theme_key: str = DEFAULT_THEME) -> None:
    """Register this theme's Plotly template (once, cached by key) and
    activate it as the process-wide default.

    Every chart built with plotly.express — whether from visualization.py, the
    HTML report, or code the AI Analyst generates — picks this up automatically
    without each call site repeating the same layout overrides.
    """
    name = f"prism_{theme_key}"
    if name not in pio.templates:
        pio.templates[name] = _build_template(_tokens(theme_key))
    pio.templates.default = name
