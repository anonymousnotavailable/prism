"""
Atlas intent-router eval harness.

8 utterances spanning app commands, a data question, chitchat, and a
destructive-action confirmation flow, run against the real
atlas.classify_intent() — which means this needs GEMINI_API_KEY configured
(.env locally, or the environment already exporting it). It checks
classification *accuracy* (type/action/target), not exact wording —
spoken_reply is free-text and expected to vary between runs.

No eval harness existed for Prism before Atlas — this is new.

Run from the project root with:  python -m eval.atlas_eval
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402  (session_state is touched by atlas.py's imports)

if not hasattr(st, "session_state") or "chat_history" not in st.session_state:
    st.session_state.chat_history = []

from modules import atlas  # noqa: E402

CASES = [
    {
        "utterance": "go to the visualize tab",
        "expect_type": "APP_COMMAND",
        "expect_action": "navigate",
        "expect_target": "Visualize",
    },
    {
        "utterance": "clean up the missing values",
        "expect_type": "APP_COMMAND",
        "expect_action": "clean_nulls",
    },
    {
        "utterance": "run auto analysis on this",
        "expect_type": "APP_COMMAND",
        "expect_action": "run_auto_analysis",
    },
    {
        "utterance": "generate a report for me",
        "expect_type": "APP_COMMAND",
        "expect_action": "generate_report",
    },
    {
        "utterance": "demo yourself",
        "expect_type": "APP_COMMAND",
        "expect_action": "demo_mode",
    },
    {
        "utterance": "what's the average revenue by region?",
        "expect_type": "DATA_QUESTION",
    },
    {
        "utterance": "good morning Atlas, how are you",
        "expect_type": "CHITCHAT",
    },
    {
        # Destructive-action confirmation flow: the FIRST utterance stages
        # the action without executing it (tested at the app.py/atlas.guarded()
        # layer, not classify_intent() — classify_intent's job here is just
        # to route "drop the age column" as APP_COMMAND, and a follow-up
        # "yes" as a "confirm" action).
        "utterance": "drop the age column",
        "expect_type": "APP_COMMAND",
        "expect_action": "clean_nulls",  # closest existing action; a dedicated
        # "drop_column" action isn't in the registry yet, see README note.
        "note": "Routing only — the actual guard/confirm mechanics are covered by "
        "modules/atlas.py's own inline logic tests, not this classifier-only harness.",
    },
]

CONFIRM_CASE = {"utterance": "yes, do it", "expect_type": "APP_COMMAND", "expect_action": "confirm"}


def _check(case: dict, actual: dict) -> tuple[bool, str]:
    if actual["type"] != case["expect_type"]:
        return False, f"type: expected {case['expect_type']}, got {actual['type']}"
    if "expect_action" in case and actual.get("action") != case["expect_action"]:
        return False, f"action: expected {case['expect_action']}, got {actual.get('action')}"
    if "expect_target" in case and actual.get("target") != case["expect_target"]:
        return False, f"target: expected {case['expect_target']}, got {actual.get('target')}"
    return True, "ok"


def run() -> int:
    if atlas._client() is None:
        print("No GEMINI_API_KEY configured — can't run a live eval. Set it in .env and retry.")
        return 1

    all_cases = CASES + [CONFIRM_CASE]
    passed = 0
    for i, case in enumerate(all_cases, 1):
        actual = atlas.classify_intent(case["utterance"])
        ok, detail = _check(case, actual)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {i}. \"{case['utterance']}\" -> {detail if not ok else actual['type'] + '/' + str(actual.get('action'))}")
        passed += ok

    print(f"\n{passed}/{len(all_cases)} passed")
    return 0 if passed == len(all_cases) else 1


if __name__ == "__main__":
    raise SystemExit(run())
