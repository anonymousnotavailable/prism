"""
UI — the landing screen (hero, feature cards, command palette, sample
datasets, load-session), the site-wide footer, per-tab help expanders,
first-visit onboarding, and (v2 Part 2) the shared "delight" primitives used
across every tab: empty states, a sticky mini-header, a shimmer skeleton
loader, and rotating analyst-themed loading messages.

Kept separate from theme.py: theme.py owns *styling* (CSS + the Plotly
template); this module owns page *content* built out of that styling.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import streamlit as st

DEVELOPER_NAME = "Prathmesh Katkade"
GITHUB_URL = "https://github.com/anonymousnotavailable"
LINKEDIN_URL = "https://linkedin.com/in/your-profile"

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "samples"
SAMPLE_DATASETS = {
    "Sales": {
        "file": "sales_data.csv",
        "description": "500 retail orders — nulls, duplicates, and revenue stored as currency text (₹1,200).",
    },
    "HR": {
        "file": "hr_data.csv",
        "description": "300 employee records — nulls, duplicates, and salary stored as currency text (₹1,200).",
    },
    "Stocks": {
        "file": "stock_data.csv",
        "description": "400 daily OHLCV rows across 2 tickers — includes a multi-week date gap.",
    },
}

FEATURE_CARDS = [
    ("🧹", "Clean", "One-click null handling, dedup, and dtype fixes — with full undo history."),
    ("📊", "Visualize", "Auto-picked charts per column type, plus a correlation heatmap."),
    ("💬", "Ask AI", "Chat with your data in plain English — typed or by voice."),
    ("🗄️", "SQL Lab", "Run raw SQL against your dataset via DuckDB, no server required."),
]

# Rotating loading-message pool — used in place of generic "Loading..." spinner
# text for the app's longer-running AI/stats/model calls.
LOADING_MESSAGES = [
    "Crunching correlations…",
    "Interrogating outliers…",
    "Reticulating scatterplots…",
    "Consulting the data gods…",
    "Chasing down duplicates…",
    "Untangling distributions…",
    "Whispering to the dataframe…",
    "Counting on pandas…",
    "Polishing p-values…",
    "Auditing the averages…",
    "Teaching the model some manners…",
    "Herding rows into columns…",
]

# Keyword -> tab label, for the landing screen's command palette. Order
# matters only in that the first substring match wins, so more specific
# phrases are listed before their more generic overlaps.
PALETTE_KEYWORDS: dict[str, str] = {
    "full analysis": "Auto Analyst",
    "auto analy": "Auto Analyst",
    "agent": "Auto Analyst",
    "clean": "Clean",
    "missing": "Clean",
    "duplicate": "Clean",
    "null": "Clean",
    "dashboard": "Visualize",
    "report": "Visualize",
    "visuali": "Visualize",
    "chart": "Visualize",
    "plot": "Visualize",
    "sql": "SQL Lab",
    "query": "SQL Lab",
    "ask": "AI Analyst",
    "chat": "AI Analyst",
    "question": "AI Analyst",
    "signific": "Stats Lab",
    "hypothes": "Stats Lab",
    "t-test": "Stats Lab",
    "anova": "Stats Lab",
    "stat": "Stats Lab",
    "forecast": "Forecasting",
    "predict": "Forecasting",
    "trend": "Forecasting",
    "cluster": "Clustering",
    "segment": "Clustering",
    "combine": "Combine",
    "join": "Combine",
    "merge": "Combine",
    "drift": "Combine",
    "compare": "Combine",
    "overview": "Overview",
    "quality": "Overview",
    "pii": "Overview",
    "privacy": "Overview",
    "anomaly": "Overview",
    "correlat": "Visualize",
}


def get_loading_message() -> str:
    """A random analyst-themed loading line, for spinners on longer AI/model calls."""
    return random.choice(LOADING_MESSAGES)


def match_palette_query(query: str) -> Optional[str]:
    """Best-effort keyword match from a free-text query to a tab name."""
    lowered = query.lower()
    for keyword, tab_label in PALETTE_KEYWORDS.items():
        if keyword in lowered:
            return tab_label
    return None


def render_hero() -> None:
    """The big animated-gradient PRISM title + tagline, shown on the landing screen."""
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1rem 0;">
            <div class="hero-title-animated" style="font-size:4rem;">
                PRISM
            </div>
            <div style="font-size:1.3rem; color:#00e5ff; font-weight:600; margin-top:0.25rem;">
                Your AI-Powered Data Analyst
            </div>
            <div style="font-size:1rem; color:#9fb3c8; margin-top:0.5rem;">
                Upload a dataset and get instant cleaning, visualization, SQL, and AI-driven insight —
                no code required.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_cards() -> None:
    """4 feature cards: Clean / Visualize / Ask AI / SQL Lab."""
    cols = st.columns(len(FEATURE_CARDS))
    for col, (icon, title, desc) in zip(cols, FEATURE_CARDS):
        with col:
            st.markdown(
                f"""
                <div class="glass-card hoverable" style="padding:1.25rem 1rem; height:160px;">
                    <div style="font-size:1.4rem; margin-bottom:0.35rem;">{icon}</div>
                    <div class="prism-heading" style="color:#00e5ff; font-weight:700; font-size:1.05rem; margin-bottom:0.5rem;">
                        {title}
                    </div>
                    <div style="color:#9fb3c8; font-size:0.85rem; line-height:1.4;">
                        {desc}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_command_palette() -> tuple[Optional[str], Optional[str]]:
    """The landing screen's "what do you want to do?" search box.

    Returns (query, matched_tab) for this run — both None if nothing was
    typed. Doesn't load data or switch tabs itself; app.py decides what to
    do with a match (load a sample, remember which tab to jump to).
    """
    st.markdown("#### What do you want to do?")
    query = st.text_input(
        "Command palette",
        placeholder='Try "clean my messy data", "forecast next month", or "find segments"...',
        key="command_palette_query",
        label_visibility="collapsed",
    )
    if not query:
        return None, None

    matched_tab = match_palette_query(query)
    if matched_tab:
        st.markdown(
            f'<div class="glass-card prism-palette-hit">'
            f'Sounds like <b>{matched_tab}</b> is what you need — pick a sample below (or upload your '
            f"own) and Prism will jump you straight there.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Not sure which tool that is — try a sample dataset below and explore the tabs.")
    return query, matched_tab


def render_tab_jump_script(tab_label: str) -> None:
    """Best-effort: click the tab whose visible text contains tab_label.

    Streamlit's tabs have no Python API to select one programmatically, so
    this reaches into the parent document via a small JS snippet (the
    standard workaround used across the Streamlit component ecosystem for
    this exact gap). If the DOM shape ever changes upstream and the click
    doesn't land, the user can just click the tab by hand — this is
    best-effort polish, not load-bearing navigation.
    """
    import streamlit.components.v1 as components

    safe_label = tab_label.replace("\\", "").replace('"', "").replace("\n", "")
    components.html(
        f"""
        <script>
        const target = "{safe_label}".trim().toLowerCase();
        const tryClick = () => {{
            const doc = window.parent.document;
            const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
            for (const tab of tabs) {{
                if (tab.innerText.trim().toLowerCase().includes(target)) {{
                    tab.click();
                    return true;
                }}
            }}
            return false;
        }};
        if (!tryClick()) {{ setTimeout(tryClick, 300); }}
        </script>
        """,
        height=0,
    )


def render_sample_buttons() -> Optional[str]:
    """Render the 3 'Try a sample dataset' cards. Returns the chosen label, or None."""
    st.markdown("#### Try a sample dataset")
    cols = st.columns(len(SAMPLE_DATASETS))
    chosen = None
    for col, (label, info) in zip(cols, SAMPLE_DATASETS.items()):
        with col:
            st.caption(info["description"])
            if st.button(f"Load {label}", key=f"sample_{label}", use_container_width=True):
                chosen = label
    return chosen


def load_sample_dataframe(label: str):
    """Read a bundled sample CSV by label. Returns a pandas DataFrame."""
    import pandas as pd

    info = SAMPLE_DATASETS[label]
    return pd.read_csv(SAMPLE_DATA_DIR / info["file"])


def render_load_session_widget():
    """File uploader for restoring a previously saved .json session. Returns
    the uploaded file object (or None) — app.py owns the actual load/parsing.
    """
    st.markdown("#### Restore a saved session")
    return st.file_uploader("Upload a Prism session file (.json)", type=["json"], key="session_upload")


FOOTER_HTML = f"""
<div style="text-align:center; padding: 2rem 0 1rem 0; margin-top: 2rem;
            border-top: 1px solid #1c2942; color:#6b7d94; font-size:0.85rem;">
    Developed by {DEVELOPER_NAME}
    &nbsp;·&nbsp;
    <a href="{GITHUB_URL}" target="_blank" style="color:#9fb3c8; text-decoration:none;">GitHub</a>
    &nbsp;·&nbsp;
    <a href="{LINKEDIN_URL}" target="_blank" style="color:#9fb3c8; text-decoration:none;">LinkedIn</a>
</div>
"""


def render_footer() -> None:
    """Site-wide footer — call once at the bottom of every page (landing and main app)."""
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)


def render_help_expander(text: str) -> None:
    """A small '? Help' expander explaining the current tab in ~2 lines."""
    with st.expander("? Help"):
        st.caption(text)


def render_sticky_header(dataset_name: str, n_rows: int, n_cols: int, health_score: int) -> None:
    """Always-visible mini-header: active dataset name, shape, and a 0-100
    health score, so context never scrolls out of view on a long tab.
    """
    if health_score >= 80:
        health_label = "Healthy"
    elif health_score >= 50:
        health_label = "Needs attention"
    else:
        health_label = "Poor"

    st.markdown(
        f"""
        <div class="glass-card prism-sticky-header">
            <span class="prism-heading" style="font-weight:700;">{dataset_name}</span>
            <span class="chip">{n_rows:,} rows &times; {n_cols} cols</span>
            <span class="chip">Health {health_score}/100 — {health_label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(icon: str, title: str, message: str) -> None:
    """A designed "nothing here yet" block (icon + title + one-line
    guidance) used in place of a bare st.info() across every tab's
    not-yet-run state. Callers add their own action button below it.
    """
    st.markdown(
        f"""
        <div class="glass-card prism-empty-state">
            <div class="icon">{icon}</div>
            <div class="title">{title}</div>
            <div class="message">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_shimmer(height: int = 90) -> None:
    """A shimmering skeleton placeholder — an alternative to a bare
    st.spinner for a couple of the app's longer-running actions.
    """
    st.markdown(f'<div class="prism-shimmer" style="height:{height}px;"></div>', unsafe_allow_html=True)


ONBOARDING_STEPS = [
    ("1. Overview", "Check the data-quality report, column health, and drill into any column."),
    ("2. Clean", "Use the sidebar's Cleaning Controls, Datetime Features, and Type Coercion tools."),
    ("3. Combine", "Optionally join a second file onto your active dataset."),
    ("4. Visualize", "Browse auto-generated charts or build your own in Manual mode."),
    ("5. SQL Lab", "Run raw SQL against your data, with example queries to get started."),
    ("6. AI Analyst", "Ask questions in plain English — by typing or by voice."),
]


def render_onboarding() -> None:
    """First-visit, dismissible step-by-step intro. Shown once per session
    unless dismissed; state lives in st.session_state.onboarding_dismissed.
    """
    if st.session_state.get("onboarding_dismissed"):
        return
    with st.expander("New here? Quick tour", expanded=True):
        for title, desc in ONBOARDING_STEPS:
            st.markdown(f"**{title}** — {desc}")
        if st.button("Got it, dismiss"):
            st.session_state.onboarding_dismissed = True
            st.rerun()
