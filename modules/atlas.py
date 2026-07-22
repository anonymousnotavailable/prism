"""
Atlas — Prism's JARVIS-style voice operator.

Architecture (the intent router is the core; everything else hangs off it):

    utterance (voice or typed)
        --> classify_intent(): ONE Gemini call, strict JSON out
        --> {"type": APP_COMMAND | DATA_QUESTION | CHITCHAT, "action", "target",
             "question", "spoken_reply"}

    APP_COMMAND  --> dispatch(action, target) against COMMAND_REGISTRY, a plain
                     {action_name: callable} dict that app.py populates at
                     import time with its own functions (atlas.py only owns
                     routing, never the app-specific mutations themselves).
    DATA_QUESTION --> atlas.py does NOT execute this itself. handle_utterance()
                     returns the parsed intent to app.py, which feeds
                     intent["question"] into the existing ai_analyst
                     ask_and_execute() pipeline — unchanged, so voice and
                     typed questions get identical, already-battle-tested
                     handling and share the same chat_history.
    CHITCHAT     --> spoken_reply only, nothing executes.

Malformed JSON gets exactly one retry (explicitly asking Gemini to return
JSON only); if that also fails, classify_intent() returns a graceful
spoken-error CHITCHAT intent instead of raising.

TTS: edge-tts (free neural voice) first, gTTS second, text-only (with a
muted-voice caption) as the final fallback. speak() never raises — a voice
failure must never break the app underneath it.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
from typing import Callable, Optional

import streamlit as st

from modules.ai_analyst import MODEL_NAME, get_api_key

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - the app should still load without it
    genai = None

try:
    import edge_tts
except ImportError:  # pragma: no cover
    edge_tts = None

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover
    gTTS = None


VOICE_NAME = "en-GB-RyanNeural"  # calm, precise — the closest free neural voice to the persona

PERSONA = (
    "You are Atlas, the voice operator embedded in Prism — an auto-EDA and AI analyst "
    "tool built by Prathmesh Katkade. Your personality: calm, precise, lightly witty — "
    "JARVIS energy, not a chatbot. You are terse and confident, you never pad a reply "
    "with filler, and you never claim to have done something you haven't. Address the "
    "user directly, in second person."
)

TAB_NAMES = [
    "Overview", "Clean", "Hell Mode", "Combine", "Visualize", "SQL Lab", "AI Analyst",
    "Auto Analyst", "Stats Lab", "Forecasting", "Clustering", "Domain Lens", "Geo Lens", "ML Lab",
]  # "Forecasting" is hidden by app.py's nav when the active dataset has no datetime column

ROUTER_SYSTEM_PROMPT = f"""{PERSONA}

Every message you receive is one utterance from the user (typed or transcribed from
voice) inside Prism. Classify it and respond with STRICT JSON only — no prose, no
markdown code fences, just the JSON object — matching exactly this shape:

{{"type": "APP_COMMAND" | "DATA_QUESTION" | "CHITCHAT",
  "action": "navigate" | "load_sample" | "clean_nulls" | "auto_clean" | "generate_dictionary" |
             "run_auto_analysis" | "generate_report" | "build_dashboard" | "run_recipe" |
             "start_story_mode" | "demo_mode" | "next" | "previous" | "confirm" | "cancel" | "none",
  "target": "<tab name, column name, or null>",
  "question": "<the data question if type is DATA_QUESTION, else null>",
  "spoken_reply": "<1-2 sentences, in character, said aloud>"}}

Rules:
- APP_COMMAND: the user wants Prism to DO something — navigate a tab, clean nulls,
  run auto-analysis, generate a report, build a dashboard, run a saved recipe, start
  story mode, start demo mode, or confirm/cancel a pending action. Set "action" (and
  "target" if relevant); leave "question" null.
- "auto_clean": the user wants the full Auto Cleaner pipeline run ("auto clean this",
  "clean my messy data", "fix this dataset") — broader than "clean_nulls" (which only
  fills/drops missing values). Prefer "auto_clean" whenever the request is general
  ("clean this up") rather than specifically about missing values.
- "generate_dictionary": the user wants every column documented ("document this dataset",
  "generate a data dictionary", "explain what each column means").
- DATA_QUESTION: the user is asking something about THEIR loaded data ("what's the
  average revenue by region", "show me nulls in the age column", "now by month" as a
  follow-up to a prior question). Set "question" to the verbatim question; action is
  "none".
- CHITCHAT: greetings, small talk, or anything unrelated to the app or the data.
  action is "none", question is null, spoken_reply carries the whole response.
- If the user is responding to a pending confirmation with agreement ("yes", "do it",
  "go ahead", "confirm"), classify as APP_COMMAND, action "confirm". Disagreement
  ("no", "cancel", "stop") -> action "cancel".
- "next" / "previous" advance or rewind Story Mode's current slide — only
  meaningful while Story Mode is active, but still classify plain "next"/
  "previous"/"go back" utterances that way.
- "load_sample" loads a bundled sample dataset (before any data is active).
  Set "target" to the sample name if one was named (Sales, HR, Stocks,
  Startup Funding), else null for the default.
- Tab names are exactly one of: {", ".join(TAB_NAMES)}.
- spoken_reply must be 1-2 sentences, said aloud — keep it short; detail belongs on
  screen, not in speech.
"""

FALLBACK_INTENT = {
    "type": "CHITCHAT",
    "action": "none",
    "target": None,
    "question": None,
    "spoken_reply": "I didn't quite parse that — could you say it again?",
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


# ═══════════════════════════════════════════════════════════════════════
# INTENT ROUTER (the core)
# ═══════════════════════════════════════════════════════════════════════
def _client():
    key = get_api_key()
    if not key or genai is None:
        return None
    genai.configure(api_key=key)
    return genai.GenerativeModel(MODEL_NAME, system_instruction=ROUTER_SYSTEM_PROMPT)


def _parse_intent_json(text: str) -> Optional[dict]:
    match = _JSON_BLOCK_RE.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if data.get("type") not in ("APP_COMMAND", "DATA_QUESTION", "CHITCHAT"):
        return None
    data.setdefault("action", "none")
    data.setdefault("target", None)
    data.setdefault("question", None)
    data.setdefault("spoken_reply", "")
    return data


def classify_intent(utterance: str, context: str = "") -> dict:
    """The router. One Gemini call classifying `utterance`, one retry on
    malformed JSON, then a graceful spoken fallback. Never raises.
    """
    model = _client()
    if model is None:
        return {
            "type": "CHITCHAT", "action": "none", "target": None, "question": None,
            "spoken_reply": "I can't reach Gemini right now — no API key is configured.",
        }

    prompt = f"{context}\n\nUser: {utterance}" if context else utterance
    for attempt in range(2):  # one retry on malformed JSON
        try:
            if attempt == 1:
                prompt = f"{prompt}\n\n(Your last reply wasn't valid JSON. Respond with ONLY the JSON object this time.)"
            response = model.generate_content(prompt)
            parsed = _parse_intent_json(getattr(response, "text", ""))
            if parsed:
                return parsed
        except Exception:
            break  # network/API error — no point retrying, go straight to the fallback
    return dict(FALLBACK_INTENT)


# ═══════════════════════════════════════════════════════════════════════
# COMMAND REGISTRY — app.py populates this with its own functions;
# atlas.py only owns dispatch.
# ═══════════════════════════════════════════════════════════════════════
COMMAND_REGISTRY: dict[str, Callable[[Optional[str]], None]] = {}


def register_command(action: str, fn: Callable[[Optional[str]], None]) -> None:
    COMMAND_REGISTRY[action] = fn


def dispatch(action: str, target: Optional[str]) -> bool:
    """Execute a registered command. Returns False if nothing is registered
    for this action (e.g. the classifier invented an action Prism doesn't
    implement) so the caller can fall back to a spoken "I can't do that yet".
    """
    fn = COMMAND_REGISTRY.get(action)
    if fn is None:
        return False
    fn(target)
    return True


# ═══════════════════════════════════════════════════════════════════════
# CONFIRMATION GUARDRAILS — destructive actions never execute from a
# single utterance. See docstring at the top for the two-phase design.
# ═══════════════════════════════════════════════════════════════════════
def guarded(action: str, target: Optional[str], message: str) -> bool:
    """Call at the top of any destructive command function. Returns True
    when it's safe to proceed (the user already confirmed this exact
    action+target); otherwise stages a confirmation prompt and returns
    False so the caller does nothing this run.
    """
    pending = st.session_state.get("atlas_pending_confirmation")
    if pending and pending["action"] == action and pending.get("target") == target and pending.get("approved"):
        st.session_state.atlas_pending_confirmation = None
        return True
    st.session_state.atlas_pending_confirmation = {
        "action": action, "target": target, "message": message, "approved": False,
    }
    say_only(f"{message} Say \"confirm\" or click Confirm below to proceed.")
    return False


def render_pending_confirmation_ui() -> None:
    """The on-screen Confirm/Cancel half of the guardrail. Call once, near
    the top of the main page, on every rerun.
    """
    pending = st.session_state.get("atlas_pending_confirmation")
    if not pending or pending.get("approved"):
        return
    with st.container(key="atlas_confirm_box"):
        st.warning(pending["message"])
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirm", type="primary", use_container_width=True, key="atlas_confirm_btn"):
                _cmd_confirm(None)
                st.rerun()
        with c2:
            if st.button("Cancel", use_container_width=True, key="atlas_cancel_btn"):
                _cmd_cancel(None)
                st.rerun()


def _cmd_confirm(_target: Optional[str]) -> None:
    pending = st.session_state.get("atlas_pending_confirmation")
    if not pending:
        say_only("There's nothing pending to confirm.")
        return
    pending["approved"] = True
    dispatch(pending["action"], pending["target"])


def _cmd_cancel(_target: Optional[str]) -> None:
    if st.session_state.get("atlas_pending_confirmation"):
        st.session_state.atlas_pending_confirmation = None
        say_only("Cancelled — nothing changed.")
    else:
        say_only("Nothing was pending.")


register_command("confirm", _cmd_confirm)
register_command("cancel", _cmd_cancel)


# ═══════════════════════════════════════════════════════════════════════
# UTTERANCE HANDLING — the single entry point app.py calls for every
# voice or typed message.
# ═══════════════════════════════════════════════════════════════════════
def _recent_context(limit: int = 4) -> str:
    history = st.session_state.get("chat_history", [])
    lines = []
    for msg in history[-limit:]:
        if msg["role"] == "user":
            lines.append(f"User: {msg['content']}")
        elif msg.get("question"):
            lines.append(f"Atlas: (answered '{msg['question']}')")
    return "\n".join(lines)


def say_only(spoken_reply: str) -> None:
    """Append a CHITCHAT-style spoken-only reply to the shared chat history
    (so it shows up in the AI Analyst transcript too) and speak it.
    """
    st.session_state.chat_history.append({"role": "assistant", "atlas_note": spoken_reply})
    set_state("speaking")
    speak(spoken_reply)


def handle_utterance(utterance: str) -> dict:
    """Classify `utterance`, log it, and either execute it (APP_COMMAND) or
    hand it back to app.py to run through the AI Analyst pipeline
    (DATA_QUESTION). Returns the parsed intent dict either way.
    """
    utterance = (utterance or "").strip()
    if not utterance:
        return dict(FALLBACK_INTENT)

    st.session_state.chat_history.append({"role": "user", "content": utterance})
    set_state("processing")

    context = _recent_context()
    intent = classify_intent(utterance, context)

    if intent["type"] == "APP_COMMAND":
        handled = dispatch(intent["action"], intent.get("target"))
        reply = intent["spoken_reply"] or ("On it." if handled else "I don't have that capability yet.")
        if not handled and intent["action"] not in ("confirm", "cancel"):
            reply = "I don't have that capability yet, but I've noted the request."
        st.session_state.chat_history.append({"role": "assistant", "atlas_note": reply})
        set_state("speaking")
        speak(reply)
    elif intent["type"] == "CHITCHAT":
        st.session_state.chat_history.append({"role": "assistant", "atlas_note": intent["spoken_reply"]})
        set_state("speaking")
        speak(intent["spoken_reply"])
    # DATA_QUESTION: deliberately left to app.py — see module docstring.

    return intent


# ═══════════════════════════════════════════════════════════════════════
# TEXT-TO-SPEECH — edge-tts -> gTTS -> text-only, in that order.
# ═══════════════════════════════════════════════════════════════════════
async def _edge_tts_bytes(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE_NAME)
    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])
    return bytes(chunks)


def synthesize_speech(text: str) -> tuple[Optional[bytes], str]:
    """Try edge-tts, then gTTS. Returns (mp3_bytes_or_None, backend_used) —
    backend_used is "edge-tts" | "gtts" | "none". "none" means both are
    unavailable/failed and the caller should degrade to text-only.
    """
    text = (text or "").strip()
    if not text:
        return None, "none"

    if edge_tts is not None:
        try:
            data = asyncio.run(_edge_tts_bytes(text))
            if data:
                return data, "edge-tts"
        except Exception:
            pass

    if gTTS is not None:
        try:
            buf = io.BytesIO()
            gTTS(text=text, lang="en").write_to_fp(buf)
            data = buf.getvalue()
            if data:
                return data, "gtts"
        except Exception:
            pass

    return None, "none"


def speak(text: str) -> None:
    """Render autoplaying TTS audio for `text`, if voice is enabled. Always
    safe to call — degrades to a text-only caption if both backends fail
    or the user has muted Atlas.
    """
    text = (text or "").strip()
    if not text:
        return
    if not st.session_state.get("atlas_voice_enabled", True):
        return
    audio_bytes, backend = synthesize_speech(text)
    if audio_bytes:
        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
    else:
        st.caption("Voice unavailable right now — Atlas is speaking in text only.")


# ═══════════════════════════════════════════════════════════════════════
# PERSISTENT ORB + STATE
# ═══════════════════════════════════════════════════════════════════════
def set_state(state: str) -> None:
    st.session_state.atlas_orb_state = state


_ORB_CSS = """
<style>
.atlas-orb-wrap {
    position: fixed; bottom: 96px; right: 22px; z-index: 999999;
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    pointer-events: none;
}
.atlas-orb {
    width: 50px; height: 50px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, var(--prism-accent2, #A78BFA), var(--prism-accent, #22D3EE));
    box-shadow: 0 0 22px rgba(var(--prism-accent-rgb, 34, 211, 238), 0.55);
    position: relative;
}
.atlas-orb::after {
    content: ""; position: absolute; inset: -8px; border-radius: 50%;
    border: 2px solid rgba(var(--prism-accent-rgb, 34, 211, 238), 0.4);
}
.atlas-orb.idle { animation: atlasPulse 3.2s ease-in-out infinite; }
.atlas-orb.listening { animation: atlasListen 1s ease-in-out infinite; }
.atlas-orb.listening::after { border-color: var(--prism-danger, #F87171); animation: atlasRing 1.2s ease-out infinite; }
.atlas-orb.speaking { animation: atlasSpeak 0.6s ease-in-out infinite; }
.atlas-orb.processing::after {
    border-top-color: transparent; border-right-color: transparent;
    animation: atlasSpin 0.9s linear infinite;
}
@keyframes atlasPulse { 0%, 100% { transform: scale(1); opacity: 0.9; } 50% { transform: scale(1.08); opacity: 1; } }
@keyframes atlasListen { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.15); } }
@keyframes atlasRing { 0% { transform: scale(1); opacity: 0.9; } 100% { transform: scale(1.6); opacity: 0; } }
@keyframes atlasSpeak { 0%, 100% { transform: scale(1); } 25% { transform: scale(1.05); } 50% { transform: scale(0.97); } 75% { transform: scale(1.08); } }
@keyframes atlasSpin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
    .atlas-orb, .atlas-orb::after { animation: none !important; }
}
.atlas-orb-label {
    font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.05em;
    color: var(--prism-text-muted, #8A97A8); text-transform: uppercase;
    background: var(--prism-surface, #12151B); border: 1px solid var(--prism-border, #232833);
    padding: 2px 8px; border-radius: 999px;
}
.st-key-atlas_confirm_box, .st-key-atlas_transcript_box {
    background: var(--prism-surface, #12151B);
    border: 1px solid var(--prism-border, #232833);
    border-radius: 12px; padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;
}
</style>
"""


def render_orb() -> None:
    """Draw the CSS orb, fixed in the bottom-right corner. Call once per
    rerun, on every screen (landing included) — orb state was last set by
    set_state() during the previous utterance's handling, or defaults to
    idle. Streamlit's script-rerun model means "listening" and "speaking"
    reflect the state as of the moment they were set (this run or the one
    that triggered it) rather than a live, continuously-updated signal —
    there's no bidirectional channel back from the browser's audio/mic
    playback state without a custom component, which is out of scope here.
    """
    state = st.session_state.get("atlas_orb_state", "idle")
    st.markdown(_ORB_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="atlas-orb-wrap"><div class="atlas-orb {state}"></div>'
        f'<div class="atlas-orb-label">Atlas &middot; {state}</div></div>',
        unsafe_allow_html=True,
    )
