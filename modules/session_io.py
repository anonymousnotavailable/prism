"""
Session Save/Load — bundle the active dataset, cleaning history, and a
simplified AI chat transcript into a single downloadable file, and restore
it later.

Deliberately JSON, not pickle: `pickle.loads()` on a user-supplied file is a
code-execution vulnerability (a crafted pickle can run arbitrary code the
moment it's loaded), and a session file is uploaded through the browser just
like any other file. JSON keeps "load session" exactly as safe as "upload
CSV" — no deserialization of executable objects, ever.
"""

from __future__ import annotations

import json
from io import StringIO
from typing import Optional

import pandas as pd

SESSION_VERSION = 1


def _simplify_chat_history(chat_history: list[dict]) -> list[dict]:
    """Keep only JSON-safe fields — live DataFrame/Series/Figure objects
    attached to assistant messages can't (and don't need to) survive a round
    trip through JSON; the question/code/error text is what makes the
    transcript useful after reloading.
    """
    simplified = []
    for msg in chat_history:
        if msg["role"] == "user":
            simplified.append({"role": "user", "content": msg["content"]})
        else:
            simplified.append(
                {
                    "role": "assistant",
                    "question": msg.get("question"),
                    "code": msg.get("code"),
                    "error": msg.get("error"),
                    "ask_error": msg.get("ask_error"),
                }
            )
    return simplified


def save_session(raw_df: pd.DataFrame, working_df: pd.DataFrame, cleaning_log: list, chat_history: list) -> str:
    """Serialize the app state to a JSON string, ready for a download button."""
    bundle = {
        "prism_session_version": SESSION_VERSION,
        "raw_df": raw_df.to_json(orient="split", date_format="iso"),
        "working_df": working_df.to_json(orient="split", date_format="iso"),
        "cleaning_log": cleaning_log,
        "chat_history": _simplify_chat_history(chat_history),
    }
    return json.dumps(bundle)


def load_session(file_bytes: bytes) -> tuple[Optional[dict], Optional[str]]:
    """Deserialize a previously saved session.

    Returns (bundle, error). On success, bundle has keys: raw_df, working_df
    (both real DataFrames), cleaning_log, chat_history.
    """
    try:
        raw = json.loads(file_bytes.decode("utf-8"))
    except Exception as e:
        return None, f"Could not read session file: {e}"

    if not isinstance(raw, dict) or "working_df" not in raw or "raw_df" not in raw:
        return None, "This doesn't look like a valid Prism session file."

    try:
        raw_df = pd.read_json(StringIO(raw["raw_df"]), orient="split")
        working_df = pd.read_json(StringIO(raw["working_df"]), orient="split")
    except Exception as e:
        return None, f"Session file is corrupted — could not rebuild the dataset: {e}"

    return (
        {
            "raw_df": raw_df,
            "working_df": working_df,
            "cleaning_log": raw.get("cleaning_log", []),
            "chat_history": raw.get("chat_history", []),
        },
        None,
    )
