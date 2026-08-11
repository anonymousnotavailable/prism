"""Tests for modules.text_analytics — lexicon-based sentiment scoring,
TF-IDF keyword extraction, and NMF topic modeling over a free-text column.
Pure numpy/scikit-learn, no new dependency (nltk/textblob/vaderSentiment
are all NOT pinned) — the sentiment scorer is a documented heuristic, not
a trained classifier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.text_analytics import (
    analyze_sentiment,
    analyze_text,
    eligible_text_columns,
    extract_top_terms,
    narrate_text_analytics,
    score_text_sentiment,
    topic_model,
)
from modules.visualization import plot_sentiment_distribution, plot_top_terms, plot_topic_shares


# ─────────────────────────────────────────────────────────────────────────
# score_text_sentiment — lexicon + negation + intensifier/diminisher
# ─────────────────────────────────────────────────────────────────────────
def test_score_text_sentiment_positive_words():
    assert score_text_sentiment("This product is excellent and amazing") > 0.5


def test_score_text_sentiment_negative_words():
    assert score_text_sentiment("This product is terrible and awful") < -0.5


def test_score_text_sentiment_negation_flips_sign():
    positive = score_text_sentiment("This is good")
    negated = score_text_sentiment("This is not good")
    assert positive > 0
    assert negated < 0


def test_score_text_sentiment_intensifier_amplifies():
    plain = score_text_sentiment("The service was good")
    intensified = score_text_sentiment("The service was very good")
    assert intensified > plain


def test_score_text_sentiment_diminisher_softens():
    plain = score_text_sentiment("The service was good")
    diminished = score_text_sentiment("The service was slightly good")
    assert 0 < diminished < plain


def test_score_text_sentiment_no_lexicon_words_is_zero():
    assert score_text_sentiment("The sky is blue today") == 0.0


def test_score_text_sentiment_empty_or_none_is_zero():
    assert score_text_sentiment("") == 0.0
    assert score_text_sentiment(None) == 0.0


def test_score_text_sentiment_always_within_bounds():
    for text in ("excellent excellent excellent", "terrible terrible terrible", "meh", ""):
        s = score_text_sentiment(text)
        assert -1.0 <= s <= 1.0


def test_score_text_sentiment_mixed_leans_toward_stronger_signal():
    # one mild positive, one strong negative -> net negative
    assert score_text_sentiment("It was fine but honestly terrible overall") < 0


# ─────────────────────────────────────────────────────────────────────────
# eligible_text_columns
# ─────────────────────────────────────────────────────────────────────────
def _reviews_df(n=30, seed=0):
    rng = np.random.default_rng(seed)
    positive_texts = [
        "This product is excellent and works great, highly recommended",
        "Amazing quality, very happy with the purchase, would buy again",
        "Great value, fast shipping, wonderful experience overall",
    ]
    negative_texts = [
        "Terrible quality, broke after one day, very disappointing",
        "Awful experience, poor customer service, would not recommend",
        "Worst purchase ever, complete waste of money and time",
    ]
    texts = [rng.choice(positive_texts if i % 2 == 0 else negative_texts) for i in range(n)]
    return pd.DataFrame({"review": texts, "id": [f"u{i}" for i in range(n)], "rating": rng.integers(1, 6, n)})


def test_eligible_text_columns_picks_prose_column():
    df = _reviews_df()
    column_types = {"review": "text", "id": "text", "rating": "numeric"}
    picked = eligible_text_columns(df, column_types)
    assert "review" in picked
    assert "id" not in picked  # single-token IDs, not prose


def test_eligible_text_columns_respects_min_rows():
    df = _reviews_df(n=5)
    column_types = {"review": "text"}
    assert eligible_text_columns(df, column_types, min_rows=10) == []


def test_eligible_text_columns_none_for_empty_or_missing_types():
    assert eligible_text_columns(pd.DataFrame(), {}) == []
    assert eligible_text_columns(None, {}) == []


# ─────────────────────────────────────────────────────────────────────────
# analyze_sentiment
# ─────────────────────────────────────────────────────────────────────────
def test_analyze_sentiment_recovers_known_polarity_split():
    df = _reviews_df(n=40)
    result = analyze_sentiment(df, "review")
    assert result["ok"]
    assert result["n_scored"] == 40
    # half positive, half negative by construction — both should show up meaningfully
    assert result["summary"]["pct_positive"] > 30
    assert result["summary"]["pct_negative"] > 30


def test_analyze_sentiment_most_positive_and_negative_samples_are_consistent():
    df = _reviews_df(n=40)
    result = analyze_sentiment(df, "review")
    for sample in result["most_positive"]:
        assert sample["score"] > 0
    for sample in result["most_negative"]:
        assert sample["score"] < 0


def test_analyze_sentiment_missing_column():
    df = _reviews_df(n=20)
    result = analyze_sentiment(df, "nope")
    assert not result["ok"]
    assert "not found" in result["error"]


def test_analyze_sentiment_too_few_rows():
    df = _reviews_df(n=3)
    result = analyze_sentiment(df, "review", min_rows=10)
    assert not result["ok"]
    assert "Need at least" in result["error"]


def test_analyze_sentiment_empty_dataframe():
    result = analyze_sentiment(pd.DataFrame(), "review")
    assert not result["ok"]


# ─────────────────────────────────────────────────────────────────────────
# extract_top_terms
# ─────────────────────────────────────────────────────────────────────────
def test_extract_top_terms_surfaces_distinctive_words():
    df = _reviews_df(n=40)
    result = extract_top_terms(df, "review", top_n=10)
    assert result["ok"]
    terms = [t["term"] for t in result["terms"]]
    assert len(terms) > 0
    # "the"/"was"/"is" etc. are English stopwords and must not appear
    assert not any(t in ("the", "is", "was", "and", "very") for t in terms)


def test_extract_top_terms_sorted_descending():
    df = _reviews_df(n=40)
    result = extract_top_terms(df, "review")
    scores = [t["score"] for t in result["terms"]]
    assert scores == sorted(scores, reverse=True)


def test_extract_top_terms_too_few_rows():
    df = _reviews_df(n=2)
    result = extract_top_terms(df, "review", min_rows=5)
    assert not result["ok"]


def test_extract_top_terms_missing_column():
    df = _reviews_df(n=20)
    result = extract_top_terms(df, "nope")
    assert not result["ok"]


# ─────────────────────────────────────────────────────────────────────────
# topic_model
# ─────────────────────────────────────────────────────────────────────────
def test_topic_model_returns_requested_topic_structure():
    df = _reviews_df(n=60)
    result = topic_model(df, "review", n_topics=3, top_words=5)
    assert result["ok"]
    assert result["n_topics"] <= 3
    assert len(result["topics"]) == result["n_topics"]
    for topic in result["topics"]:
        assert len(topic["top_terms"]) <= 5
        assert 0.0 <= topic["doc_share"] <= 1.0


def test_topic_model_doc_shares_sum_to_one():
    df = _reviews_df(n=60)
    result = topic_model(df, "review", n_topics=4)
    total_share = sum(t["doc_share"] for t in result["topics"])
    assert abs(total_share - 1.0) < 1e-6


def test_topic_model_clips_n_topics_to_corpus_size():
    df = _reviews_df(n=25)
    result = topic_model(df, "review", n_topics=50, min_rows=20)
    assert result["ok"]
    assert result["n_topics"] < 50


def test_topic_model_too_few_rows():
    df = _reviews_df(n=5)
    result = topic_model(df, "review", min_rows=20)
    assert not result["ok"]


def test_topic_model_missing_column():
    df = _reviews_df(n=30)
    result = topic_model(df, "nope", min_rows=20)
    assert not result["ok"]


# ─────────────────────────────────────────────────────────────────────────
# analyze_text (bundle) + narrate_text_analytics
# ─────────────────────────────────────────────────────────────────────────
def test_analyze_text_bundles_all_three():
    df = _reviews_df(n=40)
    result = analyze_text(df, "review")
    assert result["ok"]
    assert result["sentiment"]["ok"]
    assert result["keywords"]["ok"]
    assert result["topics"]["ok"]


def test_narrate_text_analytics_no_model():
    df = _reviews_df(n=40)
    result = analyze_text(df, "review")
    text, error = narrate_text_analytics(None, result)
    assert text == ""
    assert "No Gemini model" in error


def test_narrate_text_analytics_no_result():
    text, error = narrate_text_analytics(object(), {"ok": False})
    assert text == ""
    assert error == "No result to narrate."


def test_narrate_text_analytics_calls_gemini_with_summary(monkeypatch):
    df = _reviews_df(n=40)
    result = analyze_text(df, "review")

    captured = {}

    def fake_call_gemini(model, prompt):
        captured["prompt"] = prompt
        return "It works.", None

    monkeypatch.setattr("modules.ai_analyst.call_gemini", fake_call_gemini)
    text, error = narrate_text_analytics(object(), result)
    assert error is None
    assert text == "It works."
    assert "review" in captured["prompt"]


# ─────────────────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────────────────
def test_plot_sentiment_distribution_returns_figure():
    df = _reviews_df(n=40)
    result = analyze_sentiment(df, "review")
    fig = plot_sentiment_distribution(result)
    assert fig is not None
    assert len(fig.data[0].y) == 3


def test_plot_sentiment_distribution_none_for_failed_result():
    assert plot_sentiment_distribution({"ok": False, "error": "boom"}) is None


def test_plot_top_terms_returns_figure():
    df = _reviews_df(n=40)
    result = extract_top_terms(df, "review")
    fig = plot_top_terms(result)
    assert fig is not None
    assert len(fig.data[0].y) == len(result["terms"])


def test_plot_top_terms_none_for_failed_result():
    assert plot_top_terms({"ok": False, "error": "boom"}) is None


def test_plot_topic_shares_returns_figure():
    df = _reviews_df(n=60)
    result = topic_model(df, "review", n_topics=3)
    fig = plot_topic_shares(result)
    assert fig is not None
    assert len(fig.data[0].y) == result["n_topics"]


def test_plot_topic_shares_none_for_failed_result():
    assert plot_topic_shares({"ok": False, "error": "boom"}) is None
