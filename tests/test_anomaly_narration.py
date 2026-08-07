"""Unit tests for the anomaly auto-narration feature added to modules.anomaly.

A fake Gemini model stands in for the real API (matching model.generate_content(...).text,
the same shape modules.ai_analyst.call_gemini expects) so these run offline, deterministically,
with zero API quota consumed — the whole point being that CI and this test suite never touch
the network or a real key.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import anomaly


@pytest.fixture(autouse=True)
def _clear_narration_cache():
    """The narration cache is module-level by design (it should outlive a
    single call within the running app) — clear it between tests so each
    test starts from a clean slate instead of leaking cached text from
    whichever test happened to run first with the same flagged content.
    """
    anomaly._narration_cache.clear()
    yield
    anomaly._narration_cache.clear()


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Records calls so tests can assert the cache prevents duplicate hits."""

    def __init__(self, text="Looks like genuine high-value outliers, worth a closer look."):
        self.text = text
        self.calls = 0

    def generate_content(self, _contents):
        self.calls += 1
        return _FakeResponse(self.text)


def _flagged_df():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"amount": rng.normal(100, 10, size=5), "region": ["A", "B", "A", "C", "B"]})
    df["anomaly_reason"] = "amount is 4.0x above the column median."
    return df


def test_narrate_anomalies_returns_text_from_model():
    model = _FakeModel()
    text, error = anomaly.narrate_anomalies(model, _flagged_df(), ["amount"])
    assert error is None
    assert text == model.text
    assert model.calls == 1


def test_narrate_anomalies_no_model_returns_error():
    text, error = anomaly.narrate_anomalies(None, _flagged_df(), ["amount"])
    assert text == ""
    assert error is not None


def test_narrate_anomalies_empty_flagged_is_a_noop():
    empty = pd.DataFrame(columns=["amount", "anomaly_reason"])
    model = _FakeModel()
    text, error = anomaly.narrate_anomalies(model, empty, ["amount"])
    assert text == ""
    assert error is None
    assert model.calls == 0


def test_narrate_anomalies_caches_identical_flagged_sets():
    model = _FakeModel()
    flagged = _flagged_df()

    first_text, first_error = anomaly.narrate_anomalies(model, flagged, ["amount"])
    second_text, second_error = anomaly.narrate_anomalies(model, flagged.copy(), ["amount"])

    assert first_error is None and second_error is None
    assert first_text == second_text
    assert model.calls == 1, "second call with an identical flagged set should hit the cache, not the API"


def test_narrate_anomalies_propagates_model_errors():
    class _ErrorModel:
        def generate_content(self, _contents):
            raise RuntimeError("boom")

    text, error = anomaly.narrate_anomalies(_ErrorModel(), _flagged_df(), ["amount"])
    assert text == ""
    assert error is not None and "boom" in error
