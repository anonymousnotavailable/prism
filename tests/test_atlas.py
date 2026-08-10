"""Tests for modules.atlas's proactive alert HUD state — the JARVIS-copilot
incremental slice: the orb should light up unprompted when there's a
high-severity Auto-Insight finding, and clear once the user has seen it.

Streamlit's bare-mode `st.session_state` behaves like a real dict outside a
browser session (see modules/ai_analyst.py's rate-limit comment for the same
observation), which is what makes these testable without a live app.
"""
from __future__ import annotations

import streamlit as st

from modules.atlas import clear_alert, raise_alert, set_state


def setup_function(_fn):
    # atlas's session_state keys are module-global singletons across the
    # whole pytest process — reset the ones this test file touches before
    # every test so cases can't leak into each other.
    st.session_state.atlas_orb_state = "idle"
    st.session_state.atlas_alert_count = 0


def test_raise_alert_sets_alert_state_and_count():
    raise_alert(3)
    assert st.session_state.atlas_orb_state == "alert"
    assert st.session_state.atlas_alert_count == 3


def test_raise_alert_with_zero_is_a_noop():
    raise_alert(0)
    assert st.session_state.atlas_orb_state == "idle"
    assert st.session_state.atlas_alert_count == 0


def test_raise_alert_with_negative_is_a_noop():
    raise_alert(-1)
    assert st.session_state.atlas_orb_state == "idle"


def test_clear_alert_resets_count_and_returns_state_to_idle():
    raise_alert(2)
    clear_alert()
    assert st.session_state.atlas_alert_count == 0
    assert st.session_state.atlas_orb_state == "idle"


def test_clear_alert_does_not_clobber_a_non_alert_state():
    raise_alert(2)
    set_state("speaking")  # something else happened after the alert was raised
    clear_alert()
    # the count still resets (it's been "seen"/superseded), but clear_alert
    # shouldn't stomp on whatever more-recent state the orb is actually in
    assert st.session_state.atlas_alert_count == 0
    assert st.session_state.atlas_orb_state == "speaking"


def test_clear_alert_when_never_raised_is_safe():
    clear_alert()
    assert st.session_state.atlas_alert_count == 0
    assert st.session_state.atlas_orb_state == "idle"
