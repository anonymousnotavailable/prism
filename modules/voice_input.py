"""
Voice Input — a thin wrapper around streamlit-mic-recorder's speech_to_text
component, so app.py doesn't need to know whether the package is installed
or care about the component's own quirks.
"""

from __future__ import annotations

from typing import Optional

try:
    from streamlit_mic_recorder import speech_to_text as _speech_to_text
except ImportError:  # the app should still load even if the package isn't installed yet
    _speech_to_text = None


def is_available() -> bool:
    """Whether the streamlit-mic-recorder package is installed."""
    return _speech_to_text is not None


def record_question(key: str = "voice_question") -> Optional[str]:
    """Render the mic button and return newly transcribed text, or None.

    Returns None when nothing new was said, when the component isn't
    installed, or when the component itself errors. There's no server-side
    way to distinguish "browser denied microphone access" from "hasn't
    spoken yet" — both simply produce no text, which is why app.py also
    shows a static caption pointing users back to the text box.
    """
    if _speech_to_text is None:
        return None
    try:
        return _speech_to_text(
            language="en",
            start_prompt="Ask by voice",
            stop_prompt="Stop recording",
            just_once=True,
            use_container_width=True,
            key=key,
        )
    except Exception:
        return None
