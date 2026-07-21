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
    "prism_hud": {
        "label": "Prism HUD (Dark)",
        "mode": "dark",
        "bg": "#07090F",
        "bg_end": "#0B0E17",
        "surface": "rgba(15,20,35,.72)",
        "surface_hover": "#151A2C",
        "border": "rgba(138,147,166,.16)",
        "text": "#E6EAF2",
        "text_muted": "#8A93A6",
        "accent": "#22D3EE",
        "accent_rgb": "34, 211, 238",
        "accent2": "#818CF8",
        "accent2_rgb": "129, 140, 248",
        "accent3": "#E879F9",
        "accent3_rgb": "232, 121, 249",
        "success": "#34D399",
        "warning": "#FBBF24",
        "danger": "#F87171",
        "on_accent": "#04141A",
        "chart_colorway": ["#22D3EE", "#818CF8", "#E879F9", "#34D399", "#FBBF24", "#F87171", "#60A5FA", "#94A3B8"],
    },
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
        "accent3": "#F472B6",
        "accent3_rgb": "244, 114, 182",
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
        "accent3": "#F472B6",
        "accent3_rgb": "244, 114, 182",
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
        "accent3": "#DB2777",
        "accent3_rgb": "219, 39, 119",
        "success": "#059669",
        "warning": "#B45309",
        "danger": "#DC2626",
        "on_accent": "#FFFFFF",
        "chart_colorway": ["#0891B2", "#7C3AED", "#059669", "#B45309", "#DC2626", "#2563EB", "#DB2777", "#64748B"],
    },
}

DEFAULT_THEME = "prism_hud"


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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Rajdhani:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

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
    --prism-accent3: $accent3;
    --prism-accent3-rgb: $accent3_rgb;
    --prism-beam: linear-gradient(90deg, $accent, $accent2, $accent3);
    --prism-success: $success;
    --prism-warning: $warning;
    --prism-danger: $danger;
    --prism-on-accent: $on_accent;
    --prism-radius: 14px;
    --prism-ease: cubic-bezier(0.16, 1, 0.3, 1);
    --prism-hud-font: 'Rajdhani', 'Inter', sans-serif;
    --prism-mono-font: 'IBM Plex Mono', 'JetBrains Mono', monospace;
}

.hud {
    font-family: var(--prism-hud-font) !important;
    letter-spacing: .12em;
    text-transform: uppercase;
    font-weight: 600;
}
.mono { font-family: var(--prism-mono-font); }

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
    border-left: 3px solid transparent;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s $ease;
    animation: prismFadeInUp 0.35s $ease both;
}
.insight-card::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: var(--prism-beam, $accent2);
}
.insight-card:hover { transform: translateX(2px); }
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

/* Ported from the pre-Atlas v2/v3 UI overhaul: classes app.py and
   modules/ui.py still reference (hero title shimmer, empty states, sticky
   header, command palette, glass cards) that this token-driven redesign
   doesn't define on its own. This system has no spacing/radius scale, so
   those values are hardcoded rather than tokenized. */
.hero-title-animated {
    background: linear-gradient(90deg, var(--prism-accent2), var(--prism-accent), var(--prism-accent2));
    background-size: 300% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: prism-hero-shift 7s ease infinite;
    font-weight: 700;
    letter-spacing: 0.08em;
}
@keyframes prism-hero-shift { to { background-position: 300% center; } }
h1, h2, h3, h4, .prism-heading {
    font-family: 'Space Grotesk', 'Segoe UI', Arial, sans-serif !important;
    letter-spacing: 0.01em;
}
.glass-card {
    border-radius: 20px;
    backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    transition: transform 0.22s ease, box-shadow 0.22s ease;
}
.glass-card.hoverable:hover { transform: translateY(-4px); }
.prism-empty-state {
    text-align: center;
    border-radius: 20px;
    padding: 1.5rem 1rem;
    margin: 0.5rem 0;
    background: var(--prism-surface);
    border: 1px solid var(--prism-border);
}
.prism-empty-state .icon { font-size: 2.2rem; margin-bottom: 0.4rem; }
.prism-empty-state .title { font-weight: 700; font-size: 1.05rem; margin-bottom: 0.25rem; color: var(--prism-text); }
.prism-empty-state .message { font-size: 0.9rem; opacity: 0.85; color: var(--prism-text-muted); }
.prism-sticky-header {
    position: sticky; top: 0; z-index: 999;
    border-radius: 16px;
    padding: 0.6rem 1.1rem;
    margin-bottom: 0.5rem;
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    background: var(--prism-surface);
    border: 1px solid var(--prism-border);
}
.prism-sticky-header .chip {
    font-size: 0.82rem; font-weight: 600;
    padding: 0.15rem 0.6rem; border-radius: 999px;
    background: var(--prism-surface-hover); color: var(--prism-text-muted);
}
.prism-palette-hit {
    border-radius: 16px;
    padding: 0.75rem 1rem;
    margin-top: 0.5rem;
    background: var(--prism-surface-hover);
    border: 1px solid var(--prism-border);
}
.prism-shimmer {
    border-radius: 16px;
    background-image: linear-gradient(90deg, rgba(255,255,255,0.04) 0px,
        rgba(255,255,255,0.12) 40px, rgba(255,255,255,0.04) 80px);
    background-size: 400px 100%;
    animation: prism-shimmer-sweep 1.4s ease-in-out infinite;
}
@keyframes prism-shimmer-sweep { to { background-position: -400px 0; } }

/* --- Sprint 1 of the HUD redesign (see DESIGN_BRIEF.md / prism_redesign_mockup.html).
   Signature rule: --prism-beam appears ONLY in: logo/hero title, the active
   pipeline step indicator, the Atlas orb, the Atlas energy bar, and an
   insight-card's left border. Nowhere else — restraint is the design. */

/* Dataset context chip — sticky top-of-page indicator of what's loaded. */
.prism-dataset-chip {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 5px 14px; border: 1px solid var(--prism-border); border-radius: 999px;
    background: var(--prism-surface); backdrop-filter: blur(8px);
    font-size: 12.5px; color: var(--prism-text);
}
.prism-dataset-chip .dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--prism-success); box-shadow: 0 0 8px var(--prism-success);
}
.prism-dataset-chip .sep { color: var(--prism-text-muted); }

/* Atlas energy bar — Gemini quota usage, beam-filled. */
.prism-quota { display: flex; flex-direction: column; gap: 4px; min-width: 140px; }
.prism-quota .lbl {
    display: flex; justify-content: space-between; font-size: 10.5px; color: var(--prism-text-muted);
}
.prism-quota .bar { height: 5px; border-radius: 999px; background: rgba(138,147,166,.18); overflow: hidden; }
.prism-quota .fill { height: 100%; border-radius: 999px; background: var(--prism-beam); transition: width .3s var(--prism-ease); }

/* Pipeline sidebar — numbered steps, done / active / locked. */
.prism-pipeline { display: flex; flex-direction: column; gap: 3px; margin-bottom: 4px; }
.prism-step {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px;
    color: var(--prism-text-muted); position: relative; border: 1px solid transparent;
    font-family: var(--prism-hud-font); font-weight: 600; font-size: 13.5px;
    letter-spacing: .08em; text-transform: uppercase;
}
.prism-step .num { font-family: var(--prism-mono-font); font-size: 10.5px; width: 20px; text-transform: none; letter-spacing: 0; }
.prism-step .st { margin-left: auto; font-size: 10px; text-transform: none; }
.prism-step.done { color: var(--prism-text); }
.prism-step.done .st { color: var(--prism-success); }
.prism-step.active { color: var(--prism-text); background: rgba(var(--prism-accent2-rgb),.10); border-color: rgba(var(--prism-accent2-rgb),.28); }
.prism-step.active::before {
    content: ""; position: absolute; left: -1px; top: 6px; bottom: 6px; width: 3px;
    border-radius: 3px; background: var(--prism-beam);
}
.prism-step.locked { opacity: .45; }

/* Data Health ring — conic-gradient score, 0-100. */
.prism-health-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; height: 100%; }
.prism-health-ring {
    width: 92px; height: 92px; border-radius: 50%; display: grid; place-items: center;
}
.prism-health-ring .in {
    width: 74px; height: 74px; border-radius: 50%; background: var(--prism-surface-hover, var(--prism-surface));
    display: grid; place-items: center; font-family: var(--prism-mono-font); font-size: 23px; font-weight: 500;
    color: var(--prism-text);
}
.prism-health-label { font-family: var(--prism-hud-font); font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--prism-text-muted); }

/* Column profiler cards. */
.prism-col-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.prism-col-card {
    background: var(--prism-surface); border: 1px solid var(--prism-border); border-radius: var(--prism-radius);
    padding: 14px 16px; backdrop-filter: blur(8px);
}
.prism-col-card .hd { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.prism-col-card .cn { font-family: var(--prism-mono-font); font-size: 13px; color: var(--prism-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prism-badge {
    font-size: 10px; padding: 2px 8px; border-radius: 999px; border: 1px solid; margin-left: auto;
    font-family: var(--prism-hud-font); font-weight: 600; letter-spacing: .08em; flex-shrink: 0;
}
.prism-badge.b-num { color: var(--prism-accent); border-color: rgba(var(--prism-accent-rgb),.4); }
.prism-badge.b-cat { color: var(--prism-accent3); border-color: rgba(var(--prism-accent3-rgb),.4); }
.prism-badge.b-dt { color: var(--prism-accent2); border-color: rgba(var(--prism-accent2-rgb),.45); }
.prism-badge.b-txt { color: var(--prism-text-muted); border-color: var(--prism-border); }
.prism-spark { display: flex; align-items: flex-end; gap: 3px; height: 34px; margin: 8px 0; }
.prism-spark i { flex: 1; background: linear-gradient(180deg, var(--prism-accent2), rgba(var(--prism-accent2-rgb),.15)); border-radius: 2px 2px 0 0; display: block; }
.prism-miss { height: 4px; border-radius: 999px; background: rgba(138,147,166,.18); overflow: hidden; margin-top: 8px; }
.prism-miss i { display: block; height: 100%; background: var(--prism-warning); }
.prism-col-card .meta { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--prism-text-muted); margin-top: 6px; }
.prism-col-card .meta span:last-child { text-align: right; white-space: nowrap; }

/* Section label — HUD caption with a trailing rule, used to break up a
   long tab into scannable zones (Column Profiler, Atlas Insight Feed, ...). */
.prism-sec {
    font-family: var(--prism-hud-font); font-weight: 600; font-size: 12.5px;
    letter-spacing: .14em; text-transform: uppercase; color: var(--prism-text-muted);
    display: flex; align-items: center; gap: 10px; margin: 4px 0 12px;
}
.prism-sec::after { content: ""; flex: 1; height: 1px; background: var(--prism-border); }

/* Pipeline navigation — restyles st.segmented_control (app.py's step
   router) to read as HUD nav pills instead of generic Streamlit chips.
   The selected pill gets the beam as its underline, matching the sidebar
   step indicator's rule (sanctioned beam location #2). */
div[data-testid="stSegmentedControl"] label {
    font-family: var(--prism-hud-font) !important;
    letter-spacing: .08em;
    text-transform: uppercase;
    font-size: 13px !important;
}
div[data-testid="stSegmentedControl"] label[data-baseweb="radio"][aria-checked="true"],
div[data-testid="stSegmentedControl"] label[aria-selected="true"] {
    box-shadow: inset 0 -2px 0 0 var(--prism-accent2);
}
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
