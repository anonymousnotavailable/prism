"""
Web Speech API voice input — a self-contained, zero-server-dependency mic
button that drives Chrome/Edge's native `SpeechRecognition` entirely inside
the browser, then hands the transcript to one of Atlas's existing text
widgets exactly as if the user had typed and pressed Enter.

Why this exists alongside `modules/voice_input.py`: that module's
`speech_to_text()` (via the `streamlit-mic-recorder` package) records raw
audio in the browser, ships the bytes to *this* Python process, and calls
`SpeechRecognition`'s `recognize_google()` — an undocumented, unauthenticated
Google endpoint reached over the *server's* network, not the browser's. Two
real problems follow: (1) whether voice works at all depends on the
server's outbound network reaching that endpoint, not on the visitor's own
browser, so `voice_input.is_available()` — which only checks whether the
pip package imported — is the wrong gate entirely; and (2) round-tripping
full audio through an extra hop adds latency and a third-party dependency
for something the browser can already do natively, on-device-triggered, for
free. This module fixes both: browser support is feature-detected in JS
(the only place that can actually know), the transcript never leaves the
browser process before landing back in Streamlit's own widget, and an
unsupported browser gets a real, specific message instead of a generic
"package missing or permission denied" catch-all.

No new pip dependency, no external CDN script (a strict CSP would block
one anyway, per this app's Artifact-adjacent constraints) — the widget is
plain HTML/CSS/JS rendered through `st.components.v1.html()`, using the
same "reach into `window.parent.document`" technique `modules/ui.py`'s
`render_tab_jump_script()` and `modules/atlas.py`'s `render_neuron_bg()`
already use, targeting a widget by its Streamlit `.st-key-<key>` CSS class
(stable since Streamlit 1.38; this app pins 1.50).

Browser support (2025-2026): `SpeechRecognition`/`webkitSpeechRecognition`
ships in Chrome, Edge, and other Chromium-based browsers only — Firefox and
Safari have never implemented it (Safari has no SpeechRecognition-family
API at all as of this writing; Firefox has an experimental flag but it is
not on by default). Feature-detecting `window.SpeechRecognition ||
window.webkitSpeechRecognition` client-side is the only reliable check —
user-agent sniffing is exactly the anti-pattern this module avoids.
"""

from __future__ import annotations

import json
from typing import Optional

# Mirrors the SpeechRecognition Web API's error event codes
# (https://developer.mozilla.org/docs/Web/API/SpeechRecognitionErrorEvent/error).
# "aborted" (user/JS called .stop()/.abort()) deliberately maps to "" — it's
# not a failure, so it gets no message rather than an alarming one.
ERROR_MESSAGES: dict[str, str] = {
    "not-allowed": "Microphone access was denied. Allow it in your browser's site settings, or type a command below.",
    "service-not-allowed": "Microphone access was denied. Allow it in your browser's site settings, or type a command below.",
    "no-speech": "Didn't catch that — try again, or type a command below.",
    "audio-capture": "No microphone found. Type a command below.",
    "network": "Speech service unreachable — check your connection, or type a command below.",
    "aborted": "",
}
DEFAULT_ERROR_MESSAGE = "Voice input hit an unexpected error. Type a command below."


def error_message(code: str) -> str:
    """User-facing text for a SpeechRecognition error event code. Never
    raises, never returns None — unrecognized codes fall back to a generic
    but still actionable message rather than going silent.
    """
    return ERROR_MESSAGES.get(code, DEFAULT_ERROR_MESSAGE)


def _json_for_script(value) -> str:
    """`json.dumps()`, hardened for embedding inside an HTML `<script>`
    block. Python's (and JS's own `JSON.stringify`'s) string escaping
    never touches `/`, so a value containing the literal text `</script>`
    — e.g. a target key or label an attacker fully controls — would close
    the real script tag early and let raw HTML/JS after it execute as
    markup. Escaping every "</" occurrence with a backslash before the
    slash is the standard fix — a browser's JS parser treats a
    backslash-escaped slash inside a string literal as the plain "/"
    character, identical to unescaped, so it changes nothing about the
    value once parsed; it only removes the literal "<" "/" adjacency that
    the HTML parser watches for.
    """
    return json.dumps(value).replace("</", "<\\/")


def build_widget_html(
    key: str,
    target_key: str,
    theme_tokens: dict,
    lang: str = "en-US",
    idle_label: str = "Ask by voice",
) -> str:
    """Build the self-contained HTML/JS for the mic widget.

    `target_key` is the Streamlit `key=` of the text widget (a `st.text_input`
    or `st.chat_input`) the transcript should land in — found at runtime via
    `.st-key-<target_key> input, .st-key-<target_key> textarea`. `theme_tokens`
    is one of `modules.theme.THEMES`' value dicts, so the widget's colors
    always match the app's active theme instead of guessing from
    `prefers-color-scheme` (this app's theme picker is a manual session-state
    choice, not tied to the OS setting).

    All identifiers are JSON-encoded before embedding so a key containing a
    quote or backslash can never break out of its string literal — belt and
    braces even though every caller in this codebase passes a fixed
    constant, never user input.
    """
    key_js = _json_for_script(key)
    target_key_js = _json_for_script(target_key)
    lang_js = _json_for_script(lang)
    idle_label_text = f"\U0001F3A4 {idle_label}"
    idle_label_js = _json_for_script(idle_label_text)
    listening_label_js = _json_for_script("\U0001F534 Listening…")
    unsupported_label_js = _json_for_script("\U0001F3A4 Voice unavailable")
    error_map_js = _json_for_script(ERROR_MESSAGES)
    default_error_js = _json_for_script(DEFAULT_ERROR_MESSAGE)
    unsupported_msg_js = _json_for_script(
        "Voice input isn't supported in this browser. Try Chrome or Edge, or type a command below."
    )
    idle_label_html = (
        idle_label_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    accent = theme_tokens.get("accent", "#22D3EE")
    text_color = theme_tokens.get("text", "#E6EAF2")
    text_muted = theme_tokens.get("text_muted", "#8A93A6")
    surface = theme_tokens.get("surface", "rgba(15,20,35,.72)")
    border = theme_tokens.get("border", "rgba(138,147,166,.16)")
    on_accent = theme_tokens.get("on_accent", "#04141A")

    return f"""
<div id="web-speech-root" style="font-family: system-ui, -apple-system, sans-serif;">
  <button id="ws-mic-btn" type="button" style="
      width: 100%; padding: 7px 10px; border-radius: 999px; cursor: pointer;
      background: {surface}; color: {text_color}; border: 1px solid {border};
      font-size: 12.5px; font-weight: 600; transition: background .15s ease;">
    {idle_label_html}
  </button>
  <div id="ws-status" style="font-size: 11px; color: {text_muted}; margin-top: 4px; min-height: 14px;"></div>
</div>
<script>
(function() {{
  const KEY = {key_js};
  const TARGET_KEY = {target_key_js};
  const LANG = {lang_js};
  const IDLE_LABEL = {idle_label_js};
  const LISTENING_LABEL = {listening_label_js};
  const UNSUPPORTED_LABEL = {unsupported_label_js};
  const ERROR_MAP = {error_map_js};
  const DEFAULT_ERROR = {default_error_js};
  const UNSUPPORTED_MSG = {unsupported_msg_js};
  const ACCENT = {_json_for_script(accent)};
  const ON_ACCENT = {_json_for_script(on_accent)};

  const btn = document.getElementById('ws-mic-btn');
  const status = document.getElementById('ws-status');

  function setStatus(text) {{ status.textContent = text || ''; }}

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{
    btn.disabled = true;
    btn.style.opacity = '0.55';
    btn.style.cursor = 'not-allowed';
    btn.textContent = UNSUPPORTED_LABEL;
    setStatus(UNSUPPORTED_MSG);
    return;
  }}

  let recognizing = false;
  let recognition = null;

  function sleep(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }}

  // Streamlit's chat_input and single-text-input st.form both submit on a
  // real Enter keypress from a real user — but a synthetic (untrusted)
  // KeyboardEvent does NOT trigger that internal submit handler (verified
  // against this exact app: the value lands and React sees the change, the
  // widget just never fires). The one thing that reliably *does* work is
  // finding and .click()-ing the widget's own submit control — the
  // chat_input's built-in send-arrow button, or the enclosing st.form's
  // submit button — since a synthetic click event is handled the same as
  // a trusted one by both React's and Streamlit's click handlers. The
  // button starts disabled (empty input) and only enables itself a render
  // tick after the 'input' event lands, hence the short poll below rather
  // than clicking immediately.
  async function submitToTarget(transcript) {{
    try {{
      const doc = window.parent.document;
      const target = doc.querySelector(
        '.st-key-' + TARGET_KEY + ' textarea, .st-key-' + TARGET_KEY + ' input'
      );
      if (!target) {{
        setStatus('Heard: "' + transcript + '" — could not reach the input box. Type it instead.');
        return;
      }}
      const isTextarea = target.tagName === 'TEXTAREA';
      const proto = isTextarea
        ? window.parent.HTMLTextAreaElement.prototype
        : window.parent.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(target, transcript);
      target.dispatchEvent(new Event('input', {{ bubbles: true }}));
      target.focus();

      const formAncestor = target.closest('.stForm');
      const chatAncestor = target.closest('[data-testid="stChatInput"]');
      let submitBtn = null;
      for (let i = 0; i < 20; i++) {{
        if (formAncestor) {{
          submitBtn = formAncestor.querySelector('button[data-testid^="stBaseButton"]');
        }} else if (chatAncestor) {{
          submitBtn = chatAncestor.querySelector('[data-testid="stChatInputSubmitButton"]');
        }}
        if (submitBtn && !submitBtn.disabled) break;
        await sleep(50);
      }}
      if (submitBtn && !submitBtn.disabled) {{
        submitBtn.click();
      }} else {{
        // Best-effort fallback if the DOM shape above ever changes upstream
        // (mirrors modules/ui.py's render_tab_jump_script's own fallback
        // philosophy) — a real Enter keypress would submit, so try one in
        // case some future Streamlit version does honor synthetic ones.
        const opts = {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }};
        target.dispatchEvent(new KeyboardEvent('keydown', opts));
        target.dispatchEvent(new KeyboardEvent('keyup', opts));
      }}
      setStatus('Heard: "' + transcript + '"');
    }} catch (e) {{
      setStatus('Heard: "' + transcript + '" — could not deliver it. Type it instead.');
    }}
  }}

  function makeRecognition() {{
    const r = new SR();
    r.lang = LANG;
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.continuous = false;
    r.onstart = function() {{
      recognizing = true;
      btn.textContent = LISTENING_LABEL;
      btn.style.background = ACCENT;
      btn.style.color = ON_ACCENT;
      setStatus('Listening — speak now.');
    }};
    r.onresult = function(event) {{
      const transcript = event.results[0][0].transcript;
      submitToTarget(transcript);
    }};
    r.onerror = function(event) {{
      const msg = ERROR_MAP.hasOwnProperty(event.error) ? ERROR_MAP[event.error] : DEFAULT_ERROR;
      if (msg) setStatus(msg);
    }};
    r.onend = function() {{
      recognizing = false;
      btn.textContent = IDLE_LABEL;
      btn.style.background = '';
      btn.style.color = '';
    }};
    return r;
  }}

  btn.addEventListener('click', function() {{
    if (recognizing && recognition) {{ recognition.stop(); return; }}
    setStatus('');
    recognition = makeRecognition();
    try {{
      recognition.start();
    }} catch (e) {{
      setStatus('Could not start voice input. Try again.');
    }}
  }});
}})();
</script>
"""


def render(
    key: str,
    target_key: str,
    theme_tokens: dict,
    lang: str = "en-US",
    idle_label: str = "Ask by voice",
    height: int = 68,
) -> None:
    """Render the mic widget. Purely additive to the page — it never raises
    and never returns a value; the transcript reaches Python by re-entering
    through `target_key`'s own widget and triggering a normal Streamlit
    rerun, not through this function's return.
    """
    import streamlit.components.v1 as components

    components.html(
        build_widget_html(key, target_key, theme_tokens, lang=lang, idle_label=idle_label),
        height=height,
    )
