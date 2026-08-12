"""Tests for modules.web_speech — the browser-native Web Speech API mic
widget (see the module docstring for why it exists alongside
modules.voice_input). Since the payload is JS executed in a real browser,
these tests cover what's actually testable from Python: the error-message
mapping, safe embedding of identifiers/theme tokens into the generated
script (no way for a key to break out of its string literal), and that the
generated JS is at least syntactically valid (checked with Node, since a
syntax error would silently no-op the whole widget in production with no
visible symptom other than "the mic button does nothing").
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

import pytest

from modules.web_speech import (
    DEFAULT_ERROR_MESSAGE,
    ERROR_MESSAGES,
    build_widget_html,
    error_message,
)

_THEME = {
    "accent": "#22D3EE",
    "text": "#E6EAF2",
    "text_muted": "#8A93A6",
    "surface": "rgba(15,20,35,.72)",
    "border": "rgba(138,147,166,.16)",
    "on_accent": "#04141A",
}


# ── error_message() ──────────────────────────────────────────────────────
@pytest.mark.parametrize("code", list(ERROR_MESSAGES.keys()))
def test_error_message_known_codes(code):
    assert error_message(code) == ERROR_MESSAGES[code]


def test_error_message_unknown_code_falls_back():
    assert error_message("some-future-error-code") == DEFAULT_ERROR_MESSAGE


def test_error_message_never_raises_on_odd_input():
    for bad in ["", None, 123, object()]:
        # error_message expects a str, but callers should never see an
        # exception bubble out of this — a dict.get() based lookup can't
        # raise on any hashable input.
        try:
            error_message(bad)  # type: ignore[arg-type]
        except TypeError:
            pytest.fail(f"error_message raised on {bad!r}")


def test_aborted_maps_to_empty_message():
    # "aborted" means the widget itself stopped recognition (e.g. the user
    # clicked stop) — not a failure, so it must not show an alarming error.
    assert error_message("aborted") == ""


# ── build_widget_html() basic shape ──────────────────────────────────────
def test_build_widget_html_embeds_target_key():
    html = build_widget_html("mykey", "my_target", _THEME)
    assert "my_target" in html
    assert "st-key-" in html


def test_build_widget_html_embeds_lang():
    html = build_widget_html("k", "t", _THEME, lang="fr-FR")
    assert json.dumps("fr-FR") in html


def test_build_widget_html_embeds_custom_idle_label():
    html = build_widget_html("k", "t", _THEME, idle_label="Speak to Atlas")
    assert "Speak to Atlas" in html


def test_build_widget_html_uses_theme_colors():
    html = build_widget_html("k", "t", _THEME)
    assert _THEME["accent"] in html
    assert _THEME["surface"] in html


def test_build_widget_html_falls_back_on_missing_theme_keys():
    # A theme dict missing a token (future theme added without updating
    # this module) should degrade to a sane default, never KeyError.
    html = build_widget_html("k", "t", {})
    assert "#22D3EE" in html  # default accent


def test_build_widget_html_includes_feature_detection():
    html = build_widget_html("k", "t", _THEME)
    assert "window.SpeechRecognition" in html
    assert "webkitSpeechRecognition" in html


def test_build_widget_html_includes_unsupported_message():
    html = build_widget_html("k", "t", _THEME)
    assert "isn't supported in this browser" in html


def test_build_widget_html_includes_error_handlers():
    html = build_widget_html("k", "t", _THEME)
    assert "onerror" in html
    assert "not-allowed" in html
    assert "no-speech" in html


def test_build_widget_html_uses_native_value_setter_trick():
    # The whole mechanism hinges on bypassing React's tracked value via the
    # native property descriptor — losing this silently breaks delivery.
    html = build_widget_html("k", "t", _THEME)
    assert "getOwnPropertyDescriptor" in html
    assert "dispatchEvent" in html
    assert "KeyboardEvent" in html


# ── safe embedding: keys/labels that could break out of a JS string ─────
@pytest.mark.parametrize(
    "dangerous",
    [
        'key"with"quotes',
        "key'with'quotes",
        "key</script><script>alert(1)</script>",
        "key\\with\\backslashes",
        "key\nwith\nnewlines",
        "key`with`backticks${1+1}",
    ],
)
def test_build_widget_html_safely_embeds_dangerous_target_key(dangerous):
    html = build_widget_html("k", dangerous, _THEME)
    # The JSON-encoded form must appear with every "</" further escaped to
    # "<\/" (see _json_for_script's docstring) — plain json.dumps() would
    # NOT be found verbatim whenever `dangerous` contains "</", which is
    # exactly the case this test exists to cover.
    assert json.dumps(dangerous).replace("</", "<\\/") in html
    # And the page must still contain exactly one real closing </script> —
    # a raw, unescaped "</script>" payload would close the script block
    # early (a bare, unescaped "<script>" with no leading "/" is inert:
    # per the HTML5 tokenizer, script-data state only ends on the literal
    # "</script" sequence, so a stray "<script>" substring sitting inside
    # an already-open script's string literal is never parsed as a tag).
    assert html.count("</script>") == 1


def test_build_widget_html_safely_embeds_dangerous_idle_label():
    dangerous = '<img src=x onerror=alert(1)>"; alert(1); //'
    html = build_widget_html("k", "t", _THEME, idle_label=dangerous)
    markup = html.split("<script>")[0]  # the HTML-visible button, before the JS block
    # The HTML-visible button text must be escaped (no raw < or > survives
    # into the DOM as markup) — it's fine for the same string to appear
    # unescaped inside the JS string literal further down, which this
    # split intentionally excludes.
    assert "<img" not in markup
    assert "&lt;img" in markup


# ── generated JS is syntactically valid ──────────────────────────────────
def _extract_script(html: str) -> str:
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>")
    return html[start:end]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available in this environment")
def test_generated_js_is_syntactically_valid():
    html = build_widget_html("atlas_mic", "atlas_command_input", _THEME)
    script = _extract_script(html)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
    finally:
        os.unlink(path)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available in this environment")
def test_generated_js_is_syntactically_valid_with_dangerous_key():
    html = build_widget_html("k", "weird\"key'with`stuff", _THEME, idle_label="say \"hi\" </script>")
    script = _extract_script(html)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
    finally:
        os.unlink(path)


# ── render() smoke test ──────────────────────────────────────────────────
def test_render_does_not_raise(monkeypatch):
    calls = {}

    import streamlit.components.v1 as components

    def _fake_html(html, height=None):
        calls["html"] = html
        calls["height"] = height

    monkeypatch.setattr(components, "html", _fake_html)

    from modules import web_speech

    web_speech.render("k", "t", _THEME)
    assert "st-key-" in calls["html"]
    assert json.dumps("t") in calls["html"]  # the target_key, JSON-encoded
    assert calls["height"] == 68
