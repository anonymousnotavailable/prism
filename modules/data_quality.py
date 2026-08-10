"""Data Quality Scorecard — closes a backlog item flagged, unbuilt, across
three prior routine runs ("Data Quality Score with exportable scorecard").

The 0-100 Data Health Score and its 5-component weighted breakdown already
exist in `data_engine.get_health_score()` / `get_health_breakdown()` and
are used all over the app (Overview's gauge, before/after deltas, Chaos
Intensity, the cleaning certificate) — this module does **not** duplicate
that computation. What was actually missing, and what this module adds:

1. `build_scorecard()` — assembles the already-computed breakdown plus
   dataset context into one clean, JSON-serializable structure, so the
   score is exportable and shareable rather than only ever visible live
   in the running app.
2. `narrate_health_score()` — an agentic-theme narration layer (same
   detector-then-interpreter pattern as `anomaly.narrate_anomalies()` and
   `auto_insights.narrate_insights()`): Gemini turns the component
   breakdown into a short plain-English read of what's actually dragging
   the score down and what to fix first, cached per fingerprint so
   re-viewing an unchanged score doesn't re-spend a free-tier call.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from modules.data_engine import HEALTH_COMPONENT_WEIGHTS


def fingerprint_breakdown(breakdown: dict) -> str:
    """Stable hash of a `get_health_breakdown()` result — used to cache the
    AI narration below so re-viewing the same score (tab switch, etc.)
    doesn't re-spend a Gemini call. Changes whenever any component score
    changes, not just the total (two datasets could tie on total while
    failing for different reasons, and the narration should reflect that).
    """
    parts = [f"{k}:{breakdown.get(k)}" for k in sorted(HEALTH_COMPONENT_WEIGHTS) + ["total"]]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def build_scorecard(
    quality_report: dict,
    health_breakdown: dict,
    dataset_name: Optional[str] = None,
) -> dict:
    """Assemble a clean, JSON-serializable scorecard from data already
    computed elsewhere in the app — no new statistics, just a shareable
    shape for what `get_health_breakdown()` already produced.
    """
    components = {
        name: {"score": health_breakdown[name], "max": weight}
        for name, weight in HEALTH_COMPONENT_WEIGHTS.items()
    }
    return {
        "dataset_name": dataset_name or "unnamed dataset",
        "rows": quality_report["n_rows"],
        "columns": quality_report["n_cols"],
        "total_score": health_breakdown["total"],
        "max_score": 100,
        "components": components,
        "summary_stats": {
            "missing_cells_pct": quality_report["total_missing_pct"],
            "duplicate_rows": quality_report["duplicate_rows"],
            "outlier_columns": len(
                [c for c, v in quality_report.get("outliers", {}).items() if v["count"] > 0]
            ),
            "fully_empty_columns": len(quality_report.get("all_null_columns", [])),
        },
    }


def scorecard_json_bytes(scorecard: dict) -> bytes:
    """UTF-8 JSON bytes ready for `st.download_button`."""
    return json.dumps(scorecard, indent=2).encode("utf-8")


_NARRATION_PROMPT = (
    "You are a senior data analyst explaining a Data Health Score to a stakeholder. The "
    "dataset scored {total}/100 overall, broken into 5 weighted components (score/max): "
    "{components_text}\n\n"
    "In 3-4 sentences: explain in plain English what's actually dragging the score down "
    "(name the weakest component(s) specifically, not just the total), and suggest one "
    "concrete next action to improve it most. Do not simply restate the numbers back."
)


def narrate_health_score(model, health_breakdown: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to turn a `get_health_breakdown()` result into a short
    plain-English read of the score. Returns (narration, error).

    Callers should cache the result keyed by `fingerprint_breakdown()` —
    same convention as `anomaly.narrate_anomalies()` — this function makes
    no caching decision itself.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if "total" not in health_breakdown:
        return "", "This result has no health breakdown to narrate."

    from modules.ai_analyst import call_gemini

    components_text = ", ".join(
        f"{name.replace('_', ' ')}: {health_breakdown[name]}/{weight}"
        for name, weight in HEALTH_COMPONENT_WEIGHTS.items()
    )
    prompt = _NARRATION_PROMPT.format(total=health_breakdown["total"], components_text=components_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
