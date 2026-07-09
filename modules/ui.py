"""
UI — the landing screen (hero, feature cards, sample datasets, load-session),
the site-wide footer, per-tab help expanders, and first-visit onboarding.

Kept separate from theme.py: theme.py owns *styling* (CSS + the Plotly
template); this module owns page *content* built out of that styling.
"""

from __future__ import annotations

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
    ("Clean", "One-click null handling, dedup, and dtype fixes — with full undo history."),
    ("Visualize", "Auto-picked charts per column type, plus a correlation heatmap."),
    ("Ask AI", "Chat with your data in plain English — typed or by voice."),
    ("SQL Lab", "Run raw SQL against your dataset via DuckDB, no server required."),
]


def render_hero() -> None:
    """The big glowing PRISM title + tagline, shown on the landing screen."""
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1rem 0;">
            <div style="font-size:4rem; font-weight:800; letter-spacing:0.08em;
                        background: linear-gradient(90deg, #00e5ff, #7c4dff, #00e5ff);
                        background-size: 200% auto;
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                        background-clip: text; text-shadow: 0 0 30px rgba(0,229,255,0.35);">
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
    for col, (title, desc) in zip(cols, FEATURE_CARDS):
        with col:
            st.markdown(
                f"""
                <div style="background:#111827; border:1px solid #1c2942; border-radius:12px;
                            padding:1.25rem 1rem; height:150px;">
                    <div style="color:#00e5ff; font-weight:700; font-size:1.05rem; margin-bottom:0.5rem;">
                        {title}
                    </div>
                    <div style="color:#9fb3c8; font-size:0.85rem; line-height:1.4;">
                        {desc}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
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
