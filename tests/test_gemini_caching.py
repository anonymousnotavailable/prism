"""Unit tests for the response cache + retry-with-backoff wrapped around
modules.ai_analyst.call_gemini(). Uses a fake model + a fake
google_exceptions namespace (monkeypatched in) so these run with no real
Gemini SDK installed and no real network/sleep time spent.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import ai_analyst


class _FakeResourceExhausted(Exception):
    pass


class _FakePermissionDenied(Exception):
    pass


@pytest.fixture(autouse=True)
def _fake_google_exceptions(monkeypatch):
    """Give call_gemini real exception classes to match against without
    requiring the google-generativeai package to be installed."""
    fake_module = types.SimpleNamespace(
        ResourceExhausted=_FakeResourceExhausted,
        PermissionDenied=_FakePermissionDenied,
        Unauthenticated=_FakePermissionDenied,
        InvalidArgument=_FakePermissionDenied,
    )
    monkeypatch.setattr(ai_analyst, "google_exceptions", fake_module)
    # Skip the Streamlit-session rate limiter (no real session in tests).
    monkeypatch.setattr(ai_analyst, "_check_rate_limit", lambda: None)
    # No real sleeping in unit tests.
    monkeypatch.setattr(ai_analyst.time, "sleep", lambda _seconds: None)
    ai_analyst._RESPONSE_CACHE.clear()
    yield
    ai_analyst._RESPONSE_CACHE.clear()


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _CountingModel:
    """Fake Gemini model — records every generate_content() call and can be
    scripted to raise for the first N calls before succeeding."""

    def __init__(self, raises=0, exc=_FakeResourceExhausted, text="hello"):
        self.calls = 0
        self.raises = raises
        self.exc = exc
        self.text = text
        self.model_name = "fake-model"

    def generate_content(self, contents):
        self.calls += 1
        if self.calls <= self.raises:
            raise self.exc("rate limited")
        return _FakeResponse(self.text)


def test_call_gemini_happy_path():
    model = _CountingModel()
    text, error = ai_analyst.call_gemini(model, "what is the mean?")
    assert error is None
    assert text == "hello"
    assert model.calls == 1


def test_call_gemini_caches_identical_prompt():
    model = _CountingModel()
    text1, _ = ai_analyst.call_gemini(model, "what is the mean?")
    text2, _ = ai_analyst.call_gemini(model, "what is the mean?")
    assert text1 == text2 == "hello"
    assert model.calls == 1, "second identical call should be served from cache, not hit the API again"


def test_call_gemini_does_not_cache_across_different_prompts():
    model = _CountingModel()
    ai_analyst.call_gemini(model, "prompt A")
    ai_analyst.call_gemini(model, "prompt B")
    assert model.calls == 2


def test_call_gemini_retries_transient_rate_limit_then_succeeds():
    model = _CountingModel(raises=2)  # fails twice, then succeeds
    text, error = ai_analyst.call_gemini(model, "flaky question")
    assert error is None
    assert text == "hello"
    assert model.calls == 3


def test_call_gemini_gives_up_after_max_retries():
    model = _CountingModel(raises=99)  # always raises
    text, error = ai_analyst.call_gemini(model, "always fails")
    assert text == ""
    assert "quota" in error.lower()
    assert model.calls == ai_analyst._GEMINI_MAX_ATTEMPTS


def test_call_gemini_does_not_retry_on_permission_denied():
    model = _CountingModel(raises=1, exc=_FakePermissionDenied)
    text, error = ai_analyst.call_gemini(model, "bad key")
    assert text == ""
    assert "API key" in error or "credential" in error
    assert model.calls == 1, "auth errors are not transient — should fail fast, no retry"


def test_call_gemini_failure_is_not_cached():
    model = _CountingModel(raises=99)
    ai_analyst.call_gemini(model, "always fails")
    model.raises = 0  # now it would succeed
    text, error = ai_analyst.call_gemini(model, "always fails")
    assert error is None
    assert text == "hello"
