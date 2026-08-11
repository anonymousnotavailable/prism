"""
Text Analytics — lightweight, pure numpy/scipy/scikit-learn analysis of a
free-text column: lexicon-based sentiment scoring, TF-IDF keyword
extraction, and NMF topic modeling. Fills a real, previously-empty gap in
Prism's surface: every other module works on structured (numeric/
categorical/datetime) columns, and nothing in the app has looked inside a
"text"-typed column's actual content beyond counting nulls/uniques — the
column type `data_engine.detect_column_types()` already assigns to a
reviews/comments/feedback field.

Three independent pieces, callable on their own or bundled by
analyze_text():

  - Sentiment: a compact, hand-built polarity lexicon (~90 words spanning
    strong/mild positive and negative) plus a token-window negation flip
    ("not good" -> negative) and intensifier/diminisher scaling ("very
    good" > "good" > "slightly good"). This is a heuristic bag-of-words
    scorer, not a trained classifier or a full NLP pipeline (no new
    dependency — nltk/textblob/vaderSentiment are all NOT pinned) — it
    will misread sarcasm, domain-specific jargon, and negation more than
    ~3 tokens from its cue. Framed throughout as a fast first read on
    sentiment *direction and rough proportion*, not a precision instrument
    — same "state the honest limitation" convention as
    modules.power_analysis's post-hoc-power caveat.
  - Keyword extraction: TfidfVectorizer (already-pinned scikit-learn) over
    the column's documents, ranked by summed TF-IDF weight across the
    corpus — the terms that are both frequent and distinctive, not just
    frequent (a raw word-count top-N would surface stopword-adjacent noise
    instead).
  - Topic modeling: TF-IDF + NMF (Non-negative Matrix Factorization) —
    the standard scikit-learn topic-modeling recipe, cheaper and more
    deterministic than LDA for short/medium documents and needs no extra
    dependency (gensim is not pinned). Each topic is its top-weighted
    terms; each document gets a dominant-topic assignment used to report
    a doc_share per topic.

Pure numpy/pandas/scikit-learn. 100% local compute; narrate_text_analytics()
is the optional plain-English layer on an already-computed result, same
call_gemini() plumbing and graceful no-model fallback as every other
narrate_* helper in the app.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd

# Tractability caps, same "stay silent rather than force it" / cost-control
# convention as modules.survival._MAX_ROWS and modules.bayesian_ab._MAX_ROWS.
_MAX_ROWS = 50_000
_MAX_CHARS_PER_CELL = 5_000  # a single runaway cell (e.g. an embedded HTML blob) can't blow up tokenization
_MIN_ROWS_SENTIMENT = 10
_MIN_ROWS_KEYWORDS = 5
_MIN_ROWS_TOPICS = 20
_MIN_AVG_WORDS = 3  # below this, a "text" column reads as IDs/codes, not prose

_SENTIMENT_NEUTRAL_BAND = 0.15  # |score| below this rounds to "neutral"
_NEGATION_CARRY_TOKENS = 4  # how many tokens a negation/intensifier can reach forward

# ─────────────────────────────────────────────────────────────────────────
# Sentiment lexicon — hand-curated, -3 (strong negative) .. +3 (strong
# positive), loosely AFINN-style. Not exhaustive; unmatched words score 0
# (contribute no signal either way) rather than guessing.
# ─────────────────────────────────────────────────────────────────────────
_SENTIMENT_LEXICON: dict[str, int] = {
    # strong positive (+3)
    "excellent": 3, "amazing": 3, "outstanding": 3, "fantastic": 3, "wonderful": 3,
    "perfect": 3, "incredible": 3, "exceptional": 3, "superb": 3, "brilliant": 3,
    "phenomenal": 3, "flawless": 3, "love": 3, "loved": 3, "loving": 3,
    # positive (+2)
    "great": 2, "good": 2, "happy": 2, "pleased": 2, "satisfied": 2,
    "impressive": 2, "recommend": 2, "recommended": 2, "awesome": 2, "delightful": 2,
    "enjoyable": 2, "favorite": 2, "favourite": 2, "best": 2, "positive": 2,
    "helpful": 2, "reliable": 2, "efficient": 2, "friendly": 2, "beautiful": 2,
    "solid": 2, "smooth": 2,
    # mild positive (+1)
    "fine": 1, "okay": 1, "ok": 1, "decent": 1, "fair": 1, "adequate": 1,
    "acceptable": 1, "useful": 1, "convenient": 1, "easy": 1, "quick": 1,
    "fast": 1, "clean": 1, "improved": 1, "improvement": 1, "better": 1,
    "glad": 1, "nice": 1, "comfortable": 1, "valuable": 1, "works": 1, "worked": 1,
    # mild negative (-1)
    "slow": -1, "difficult": -1, "hard": -1, "confusing": -1, "expensive": -1,
    "pricey": -1, "late": -1, "delayed": -1, "missing": -1, "mediocre": -1,
    "average": -1, "bland": -1, "lacking": -1, "weak": -1, "minor": -1,
    # negative (-2)
    "bad": -2, "poor": -2, "disappointing": -2, "disappointed": -2, "unhappy": -2,
    "dislike": -2, "disliked": -2, "broken": -2, "annoying": -2, "frustrating": -2,
    "frustrated": -2, "problem": -2, "problems": -2, "issue": -2, "issues": -2,
    "complaint": -2, "complaints": -2, "rude": -2, "unreliable": -2,
    "uncomfortable": -2, "wrong": -2, "error": -2, "errors": -2, "fail": -2,
    "failed": -2, "failure": -2,
    # strong negative (-3)
    "terrible": -3, "awful": -3, "horrible": -3, "worst": -3, "disgusting": -3,
    "useless": -3, "unacceptable": -3, "atrocious": -3, "disaster": -3,
    "scam": -3, "garbage": -3, "hate": -3, "hated": -3, "hideous": -3,
    "appalling": -3,
}

_NEGATIONS = frozenset({
    "not", "no", "never", "without", "hardly", "barely", "cannot", "neither", "nor",
    # the tokenizer keeps apostrophes (so "don't" stays one token, not
    # "don" + "t") — both the contracted and un-contracted spellings are
    # listed so either input form is recognized.
    "don't", "dont", "doesn't", "doesnt", "didn't", "didnt", "isn't", "isnt",
    "wasn't", "wasnt", "aren't", "arent", "weren't", "werent", "won't", "wont",
    "wouldn't", "wouldnt", "shouldn't", "shouldnt", "couldn't", "couldnt", "can't", "cant",
})
_INTENSIFIERS = {"very": 1.6, "extremely": 2.0, "really": 1.4, "so": 1.3, "too": 1.3, "absolutely": 1.8, "incredibly": 1.7}
_DIMINISHERS = {"slightly": 0.5, "somewhat": 0.6, "barely": 0.4, "kind": 0.6, "sort": 0.6}

_TOKEN_RE = re.compile(r"[a-z']+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def score_text_sentiment(text: str) -> float:
    """Score one string's sentiment in [-1, 1] via the lexicon above, with
    negation flipping and intensifier/diminisher scaling. 0.0 for empty
    text or text with no lexicon matches (no signal, not "neutral
    sentiment" in a strong sense — see the module docstring's honesty
    caveat). Never raises.
    """
    if not text:
        return 0.0
    tokens = _tokenize(str(text)[:_MAX_CHARS_PER_CELL])
    if not tokens:
        return 0.0

    total = 0.0
    matched = 0
    negate_ttl = 0
    multiplier = 1.0
    multiplier_ttl = 0

    for tok in tokens:
        if tok in _NEGATIONS:
            negate_ttl = _NEGATION_CARRY_TOKENS
            continue
        if tok in _INTENSIFIERS:
            multiplier = _INTENSIFIERS[tok]
            multiplier_ttl = _NEGATION_CARRY_TOKENS
            continue
        if tok in _DIMINISHERS:
            multiplier = _DIMINISHERS[tok]
            multiplier_ttl = _NEGATION_CARRY_TOKENS
            continue

        base = _SENTIMENT_LEXICON.get(tok)
        if base is not None:
            val = base * (multiplier if multiplier_ttl > 0 else 1.0)
            if negate_ttl > 0:
                val = -val
            total += val
            matched += 1
            negate_ttl = 0
            multiplier, multiplier_ttl = 1.0, 0
        else:
            if negate_ttl > 0:
                negate_ttl -= 1
            if multiplier_ttl > 0:
                multiplier_ttl -= 1

    if matched == 0:
        return 0.0
    avg = total / matched
    return float(np.clip(avg / 3.0, -1.0, 1.0))


def _sentiment_label(score: float) -> str:
    if score > _SENTIMENT_NEUTRAL_BAND:
        return "positive"
    if score < -_SENTIMENT_NEUTRAL_BAND:
        return "negative"
    return "neutral"


def eligible_text_columns(df: pd.DataFrame, column_types: dict[str, str], min_rows: int = _MIN_ROWS_SENTIMENT) -> list[str]:
    """Which "text"-typed columns actually look like free-form prose
    (average >= _MIN_AVG_WORDS words/cell) rather than IDs/codes/names —
    the same distinction data_engine.detect_column_types() itself doesn't
    make (it only separates categorical from high-cardinality "text").
    Pure function, cheap to call every rerun. Never raises.
    """
    if df is None or df.empty or not column_types:
        return []
    out = []
    for col, ctype in column_types.items():
        if ctype != "text" or col not in df.columns:
            continue
        non_null = df[col].dropna().astype(str)
        non_null = non_null[non_null.str.strip() != ""]
        if len(non_null) < min_rows:
            continue
        avg_words = non_null.str.split().str.len().mean()
        if avg_words is not None and avg_words >= _MIN_AVG_WORDS:
            out.append(col)
    return out


def _clean_corpus(df: pd.DataFrame, text_col: str) -> list[str]:
    series = df[text_col].dropna().astype(str).str.slice(0, _MAX_CHARS_PER_CELL)
    series = series[series.str.strip() != ""]
    if len(series) > _MAX_ROWS:
        series = series.sample(n=_MAX_ROWS, random_state=42)
    return series.tolist()


def analyze_sentiment(df: pd.DataFrame, text_col: str, min_rows: int = _MIN_ROWS_SENTIMENT) -> dict:
    """Per-row lexicon sentiment score + label for every non-empty cell in
    `text_col`, plus a corpus-level summary. Returns a dict, always with an
    "ok" key. Never raises.

    ok=True: {"ok": True, "text_col", "n_scored", "coverage" (fraction of
      rows with >=1 lexicon match), "summary": {"mean", "pct_positive",
      "pct_neutral", "pct_negative"}, "most_positive": [{"text","score"}],
      "most_negative": [...]} (up to 3 each, truncated for display).
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    if text_col not in df.columns:
        return {"ok": False, "error": f"Column '{text_col}' not found in the dataset."}

    docs = _clean_corpus(df, text_col)
    if len(docs) < min_rows:
        return {"ok": False, "error": f"Need at least {min_rows} non-empty rows in '{text_col}' (found {len(docs)})."}

    scores = np.array([score_text_sentiment(d) for d in docs])
    matched_mask = np.array([len(_tokenize(d)) > 0 and any(t in _SENTIMENT_LEXICON for t in _tokenize(d)) for d in docs])
    labels = [_sentiment_label(s) for s in scores]

    order = np.argsort(scores)
    most_negative_idx = order[:3]
    most_positive_idx = order[::-1][:3]

    def _sample(idx_list):
        return [{"text": (docs[i][:200] + ("…" if len(docs[i]) > 200 else "")), "score": round(float(scores[i]), 3)} for i in idx_list]

    n = len(scores)
    return {
        "ok": True,
        "text_col": text_col,
        "n_scored": n,
        "coverage": round(float(matched_mask.mean()), 3),
        "summary": {
            "mean": round(float(scores.mean()), 3),
            "pct_positive": round(100 * labels.count("positive") / n, 1),
            "pct_neutral": round(100 * labels.count("neutral") / n, 1),
            "pct_negative": round(100 * labels.count("negative") / n, 1),
        },
        "most_positive": _sample([i for i in most_positive_idx if scores[i] > 0]),
        "most_negative": _sample([i for i in most_negative_idx if scores[i] < 0]),
    }


def extract_top_terms(df: pd.DataFrame, text_col: str, top_n: int = 20, ngram_range: tuple = (1, 2), min_rows: int = _MIN_ROWS_KEYWORDS) -> dict:
    """TF-IDF keyword/keyphrase extraction over `text_col`'s corpus, ranked
    by summed TF-IDF weight across documents (frequent AND distinctive,
    not just frequent). Returns a dict, always with an "ok" key. Never
    raises.

    ok=True: {"ok": True, "text_col", "n_docs", "terms": [{"term","score"}, ...]}
    (sorted descending, up to top_n).
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    if text_col not in df.columns:
        return {"ok": False, "error": f"Column '{text_col}' not found in the dataset."}

    docs = _clean_corpus(df, text_col)
    if len(docs) < min_rows:
        return {"ok": False, "error": f"Need at least {min_rows} non-empty rows in '{text_col}' (found {len(docs)})."}

    from sklearn.feature_extraction.text import TfidfVectorizer

    min_df = 2 if len(docs) >= 20 else 1
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=ngram_range, max_features=2000, min_df=min_df)
        matrix = vectorizer.fit_transform(docs)
    except ValueError as exc:
        # Empty vocabulary — every document was pure stopwords/punctuation
        # after cleaning (rare, but a corpus of e.g. all-numeric "text"
        # cells can trigger it).
        return {"ok": False, "error": f"Couldn't build a vocabulary from '{text_col}': {exc}"}

    if matrix.shape[1] == 0:
        return {"ok": False, "error": f"No usable terms found in '{text_col}' after removing stopwords."}

    weights = np.asarray(matrix.sum(axis=0)).ravel()
    terms = np.array(vectorizer.get_feature_names_out())
    order = np.argsort(weights)[::-1][:top_n]

    return {
        "ok": True,
        "text_col": text_col,
        "n_docs": len(docs),
        "terms": [{"term": terms[i], "score": round(float(weights[i]), 3)} for i in order],
    }


def topic_model(df: pd.DataFrame, text_col: str, n_topics: int = 5, top_words: int = 8, min_rows: int = _MIN_ROWS_TOPICS) -> dict:
    """TF-IDF + NMF topic model over `text_col`'s corpus. `n_topics` is
    clipped down to what the corpus can actually support (never more
    topics than documents or than the vocabulary size) rather than
    raising. Returns a dict, always with an "ok" key. Never raises.

    ok=True: {"ok": True, "text_col", "n_docs", "n_topics", "topics":
      [{"id", "top_terms": [str, ...], "doc_share": float}, ...]}
    ("doc_share" is the fraction of documents whose single largest topic
    weight is this topic — dominant-topic assignment, not fractional
    membership.)
    """
    if df is None or df.empty:
        return {"ok": False, "error": "No data to analyze."}
    if text_col not in df.columns:
        return {"ok": False, "error": f"Column '{text_col}' not found in the dataset."}

    docs = _clean_corpus(df, text_col)
    if len(docs) < min_rows:
        return {"ok": False, "error": f"Need at least {min_rows} non-empty rows in '{text_col}' (found {len(docs)})."}

    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    min_df = 2 if len(docs) >= 20 else 1
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 1), max_features=2000, min_df=min_df)
        matrix = vectorizer.fit_transform(docs)
    except ValueError as exc:
        return {"ok": False, "error": f"Couldn't build a vocabulary from '{text_col}': {exc}"}

    vocab_size = matrix.shape[1]
    if vocab_size < 2:
        return {"ok": False, "error": f"No usable vocabulary found in '{text_col}' after removing stopwords."}

    n_topics_used = max(2, min(n_topics, len(docs) - 1, vocab_size))
    if n_topics_used < 2:
        return {"ok": False, "error": "Not enough distinct documents/vocabulary to fit more than one topic."}

    model = NMF(n_components=n_topics_used, init="nndsvda", random_state=42, max_iter=400)
    doc_topic = model.fit_transform(matrix)
    terms = np.array(vectorizer.get_feature_names_out())

    dominant = doc_topic.argmax(axis=1)
    topics = []
    for i in range(n_topics_used):
        top_idx = np.argsort(model.components_[i])[::-1][:top_words]
        doc_share = float((dominant == i).mean())
        topics.append({"id": i, "top_terms": [terms[j] for j in top_idx], "doc_share": round(doc_share, 3)})
    topics.sort(key=lambda t: t["doc_share"], reverse=True)

    return {
        "ok": True,
        "text_col": text_col,
        "n_docs": len(docs),
        "n_topics": n_topics_used,
        "topics": topics,
    }


def analyze_text(df: pd.DataFrame, text_col: str, n_topics: int = 5) -> dict:
    """Bundles analyze_sentiment() + extract_top_terms() + topic_model()
    for one column into a single result for the Stats Lab panel /
    Atlas's zero-configuration invocation. Each sub-result keeps its own
    "ok" flag — one piece failing (e.g. too few docs for topic modeling)
    doesn't block the others; the panel/caller renders whatever came back
    ok=True. Never raises.
    """
    return {
        "ok": True,
        "text_col": text_col,
        "sentiment": analyze_sentiment(df, text_col),
        "keywords": extract_top_terms(df, text_col),
        "topics": topic_model(df, text_col, n_topics=n_topics),
    }


def narrate_text_analytics(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one analyze_text() bundle in plain English.
    Returns (narration, error) — never raises.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    sentiment = result.get("sentiment") or {}
    keywords = result.get("keywords") or {}
    topics = result.get("topics") or {}

    lines = [f"Text analysis of column '{result['text_col']}':"]
    if sentiment.get("ok"):
        s = sentiment["summary"]
        lines.append(
            f"Sentiment across {sentiment['n_scored']} rows: {s['pct_positive']}% positive, "
            f"{s['pct_neutral']}% neutral, {s['pct_negative']}% negative (mean score {s['mean']})."
        )
    if keywords.get("ok"):
        top5 = ", ".join(t["term"] for t in keywords["terms"][:8])
        lines.append(f"Top distinctive terms: {top5}.")
    if topics.get("ok"):
        topic_lines = "; ".join(
            f"Topic {t['id']} ({t['doc_share']:.0%} of docs): " + ", ".join(t["top_terms"][:5]) for t in topics["topics"]
        )
        lines.append(f"Topics found: {topic_lines}.")

    if len(lines) == 1:
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    prompt = (
        "\n".join(lines) + "\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, summarize what this free-text "
        "column is telling us — overall tone, and the main themes. Do not repeat the raw numbers verbatim."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
