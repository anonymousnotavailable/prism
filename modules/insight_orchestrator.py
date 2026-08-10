"""
Agentic Insight Orchestrator — synthesizes findings across Prism's
independent detector modules (auto_insights, confounder_detection,
causal_inference's ATT + CATE, anomaly, drift) into one ranked "what
matters most" list.

Why this exists: Prism has grown a whole bench of self-contained analysis
agents that each run and render independently — Auto-Insights flags a
strong correlation, Confounder Check stress-tests it, the Causal Effect
Estimator tries to quantify it, Anomaly Detection flags unusual rows,
Drift compares two snapshots — but nothing ties their outputs together.
A user staring at five separate panels has no signal for which of a dozen
findings is the one that actually matters, and no way to notice when two
detectors are quietly agreeing (higher confidence) or, worse, when one
detector's methodology contradicts another's assumptions (e.g. a causal
ATT estimate that never adjusted for a variable Confounder Check just
flagged as reversing that exact relationship).

This module is a pure synthesis layer — it does not re-run any detection.
It takes the already-computed structured findings each detector module
produces for its own panel, normalizes them into a common `Claim` shape,
groups claims that share the same subject columns (the "de-duplication" —
two detectors independently flagging the same variable pair collapse into
one topic instead of two disconnected panel entries), flags cross-detector
agreement and the one specific contradiction pattern described above as a
"check this" flag (never a hard error — confounding is a reason to look
closer, not proof the causal estimate is wrong), and severity-ranks the
result into a top-N list.

Deliberately silent by design, same convention as every other detector in
this codebase: with fewer than two detectors contributing any findings at
all, there is nothing to cross-check, so `orchestrate_insights()` returns
a result with `silent=True` and an empty `top` list, and the caller should
render nothing rather than a one-detector list dressed up as a synthesis.

An optional Gemini narration pass (`narrate_orchestration`) turns the
ranked list into one stakeholder paragraph, following the exact same
call_gemini() / cached-by-caller / graceful-fallback convention as every
other narrate_* helper in the app (see modules/auto_insights.py,
modules/confounder_detection.py).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Tunables ─────────────────────────────────────────────────────────────

MAX_TOP = 5                 # cap the "what matters most" list
MIN_DETECTORS_FOR_OUTPUT = 2  # fewer distinct detectors firing -> nothing to orchestrate, stay silent

_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_AGREEMENT_BONUS_PER_EXTRA_DETECTOR = 1.5
_CONTRADICTION_BONUS = 2.5  # keeps a "check this" flag above a lone same-severity claim (a mismatch
                            # between two independent checks is more actionable than one detector's
                            # unconfirmed opinion), while still ranking below genuine multi-detector
                            # agreement on the strongest findings

_DRIFT_NOTABLE_SCORE = 50.0  # drift_score (0-100) at/above this is worth surfacing
_ANOMALY_HIGH_PCT = 10.0
_ANOMALY_MEDIUM_PCT = 3.0

_ANOMALY_REASON_COL_RE = re.compile(r"([A-Za-z0-9_ ]+?) is \d")


# ── Data shapes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Claim:
    """One normalized finding from a single detector, ready to be grouped
    and cross-checked against claims from other detectors."""

    detector: str            # "auto_insights" | "confounder" | "causal_att" | "causal_cate" | "anomaly" | "drift"
    subjects: frozenset       # column name(s) this claim is about; empty = dataset-wide
    severity: str             # "high" | "medium" | "low"
    kind: str                 # fine-grained tag, e.g. "confounder:paradox"
    message: str
    meta: dict = field(default_factory=dict)


@dataclass
class ClaimGroup:
    """All claims that share the same subject columns, treated as one topic."""

    subjects: frozenset
    claims: list  # list[Claim], sorted worst-first
    severity: str
    score: float
    detectors: list  # sorted distinct detector names contributing to this group
    agreement: bool
    contradiction: Optional[str]
    headline: str


@dataclass
class OrchestrationResult:
    groups: list         # list[ClaimGroup], all groups, ranked worst/most-important-first
    top: list             # list[ClaimGroup], top MAX_TOP
    contradictions: list  # subset of `groups` where contradiction is set
    n_detectors_fired: int
    n_total_claims: int
    silent: bool           # True -> caller should render nothing


# ── Adapters: raw detector output -> list[Claim] ────────────────────────


def _subjects_from_column_label(label: Optional[str]) -> frozenset:
    """auto_insights encodes pairs as 'colA ↔ colB' and dataset-wide
    findings (duplicate rows) as '(all columns)'."""
    if not label or label == "(all columns)":
        return frozenset()
    if " ↔ " in label:
        a, b = label.split(" ↔ ", 1)
        return frozenset({a.strip(), b.strip()})
    return frozenset({label.strip()})


def _adapt_auto_insights(raw: Any) -> list:
    claims = []
    for ins in raw or []:
        try:
            claims.append(
                Claim(
                    detector="auto_insights",
                    subjects=_subjects_from_column_label(ins.get("column")),
                    severity=ins.get("severity", "low"),
                    kind=f"auto_insights:{ins.get('category', 'other')}",
                    message=ins["message"],
                )
            )
        except (KeyError, AttributeError):
            continue
    return claims


_CONFOUNDER_SEVERITY = {"paradox": "high", "attenuated": "medium"}
_CONFOUNDER_ACTION = {"paradox": "reverses sign", "attenuated": "weakens substantially"}


def _adapt_confounder(raw: Any) -> list:
    """raw = confounder_detection.auto_scan_for_confounding() result:
    [{x, y, overall_r, findings: [{confounder, type, verdict, ...}]}]."""
    claims = []
    for scan in raw or []:
        x, y = scan.get("x"), scan.get("y")
        if not x or not y:
            continue
        subjects = frozenset({x, y})
        for finding in scan.get("findings", []):
            verdict = finding.get("verdict")
            severity = _CONFOUNDER_SEVERITY.get(verdict)
            if severity is None:
                continue
            confounder = finding.get("confounder")
            action = _CONFOUNDER_ACTION[verdict]
            claims.append(
                Claim(
                    detector="confounder",
                    subjects=subjects,
                    severity=severity,
                    kind=f"confounder:{verdict}",
                    message=(
                        f"The relationship between '{x}' and '{y}' {action} once you "
                        f"control for '{confounder}'."
                    ),
                    meta={"confounder": confounder},
                )
            )
    return claims


def _adapt_causal_att(raw: Any) -> list:
    """raw = causal_inference.estimate_causal_effect() result (single dict, or None)."""
    if not raw or not raw.get("ok"):
        return []
    treatment, outcome = raw.get("treatment_col"), raw.get("outcome_col")
    if not treatment or not outcome:
        return []
    ci_low, ci_high = raw.get("ci_low"), raw.get("ci_high")
    significant = ci_low is not None and ci_high is not None and (ci_low > 0) == (ci_high > 0)
    severity = "high" if significant else "low"
    att = raw.get("att", 0.0)
    covariates = set(raw.get("covariates") or [])
    n_cov = len(covariates)
    return [
        Claim(
            detector="causal_att",
            subjects=frozenset({treatment, outcome}),
            severity=severity,
            kind="causal_att",
            message=(
                f"Estimated causal effect of '{treatment}' on '{outcome}': ATT = {att:.3g} "
                f"(matched, adjusting for {n_cov} covariate{'s' if n_cov != 1 else ''})."
            ),
            meta={"covariates": covariates, "treatment": treatment, "outcome": outcome},
        )
    ]


def _adapt_causal_cate(raw: Any) -> list:
    """raw = causal_inference.estimate_cate_by_subgroup() result (single dict, or None)."""
    if not raw or not raw.get("ok"):
        return []
    pooled = raw.get("pooled") or {}
    treatment, outcome = pooled.get("treatment_col"), pooled.get("outcome_col")
    subgroup_col = raw.get("subgroup_col")
    if not treatment or not outcome:
        return []
    subjects = frozenset({treatment, outcome})
    if raw.get("sign_reversal"):
        message = (
            f"The effect of '{treatment}' on '{outcome}' reverses sign across "
            f"'{subgroup_col}' segments — a single pooled estimate would hide this."
        )
        return [Claim(detector="causal_cate", subjects=subjects, severity="high",
                       kind="causal_cate:sign_reversal", message=message,
                       meta={"subgroup_col": subgroup_col})]
    if raw.get("heterogeneity_detected"):
        message = (
            f"The effect of '{treatment}' on '{outcome}' varies meaningfully across "
            f"'{subgroup_col}' segments."
        )
        return [Claim(detector="causal_cate", subjects=subjects, severity="medium",
                       kind="causal_cate:heterogeneity", message=message,
                       meta={"subgroup_col": subgroup_col})]
    return []


def _top_anomaly_column(reasons: list) -> Optional[str]:
    """Best-effort extraction of the numeric column most often cited in a
    set of anomaly_reason strings (see modules/anomaly.py's _reason_for_row /
    find_anomalies_ensemble), used only to give the anomaly claim a subject
    to potentially cross-reference against other detectors' claims. None if
    no reason string had an extractable column (e.g. the generic fallback
    "Unusual combination of values...")."""
    counts: dict = {}
    for reason in reasons or []:
        match = _ANOMALY_REASON_COL_RE.search(reason or "")
        if match:
            col = match.group(1).strip()
            counts[col] = counts.get(col, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _adapt_anomaly(raw: Any) -> list:
    """raw = {"count": int, "total_rows": int, "reasons": [str, ...]} — a
    small summary the caller builds from find_anomalies()/find_anomalies_
    ensemble()'s flagged DataFrame; this module never touches pandas."""
    if not raw:
        return []
    count = raw.get("count", 0)
    if not count:
        return []
    total = raw.get("total_rows") or 0
    pct = (count / total * 100) if total else 0.0
    top_col = _top_anomaly_column(raw.get("reasons", []))
    subjects = frozenset({top_col}) if top_col else frozenset()
    severity = "high" if pct >= _ANOMALY_HIGH_PCT else "medium" if pct >= _ANOMALY_MEDIUM_PCT else "low"
    message = f"{count:,} row(s) flagged as statistical anomalies ({pct:.1f}% of the dataset)"
    if top_col:
        message += f", most often driven by '{top_col}'."
    else:
        message += "."
    return [Claim(detector="anomaly", subjects=subjects, severity=severity, kind="anomaly", message=message)]


def _adapt_drift(raw: Any) -> list:
    """raw = drift.compare_datasets() result: {"column_reports": [...], ...}."""
    if not raw:
        return []
    claims = []
    for rep in raw.get("column_reports", []):
        score = rep.get("drift_score", 0) or 0
        if score < _DRIFT_NOTABLE_SCORE:
            continue
        col = rep.get("column")
        severity = "high" if score >= 75 else "medium"
        message = f"'{col}' shows notable drift between the two datasets (drift score {score:.0f}/100)."
        claims.append(
            Claim(
                detector="drift",
                subjects=frozenset({col}) if col else frozenset(),
                severity=severity,
                kind="drift",
                message=message,
            )
        )
    return claims


_ADAPTERS = {
    "auto_insights": _adapt_auto_insights,
    "confounder": _adapt_confounder,
    "causal_att": _adapt_causal_att,
    "causal_cate": _adapt_causal_cate,
    "anomaly": _adapt_anomaly,
    "drift": _adapt_drift,
}


def normalize_findings(findings_by_detector: dict) -> list:
    """Adapt every detector's raw, already-computed output into a flat
    list of Claim objects. Unknown detector keys are ignored (forward
    compatible with new detectors); a malformed value from one detector
    never breaks orchestration of the others."""
    claims: list = []
    for name, raw in (findings_by_detector or {}).items():
        adapter = _ADAPTERS.get(name)
        if adapter is None:
            continue
        try:
            claims.extend(adapter(raw))
        except Exception:
            continue
    return claims


def _dedupe_exact(claims: list) -> list:
    """Collapse literally-identical claims (same detector, kind, subjects,
    message) — defensive against a detector's raw output containing an
    accidental repeat."""
    seen = set()
    deduped = []
    for c in claims:
        key = (c.detector, c.kind, c.subjects, c.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


# ── Cross-detector agreement / contradiction ────────────────────────────


def _contradiction_for_causal_claim(causal_claim: Claim, all_claims: list) -> Optional[str]:
    """The one specific "check this" pattern this module knows how to spot:
    a causal ATT estimate whose outcome column is one side of a relationship
    Confounder Check flagged (paradox/attenuated) against some third
    variable, where that flagged confounder was never included among the
    causal estimate's covariates. Deliberately checked against *every*
    confounder claim in the whole run, not just ones sharing the exact
    (treatment, outcome) pair — in practice a causal treatment column is
    categorical and a confounder pair is numeric/numeric, so they can never
    be literally identical, but "the estimate's own outcome variable has an
    unaddressed confound" is exactly the situation worth a second look.
    Surfaced as a flag, not a hard error — the causal estimate may still be
    directionally right."""
    covariates = causal_claim.meta.get("covariates") or set()
    outcome = causal_claim.meta.get("outcome")
    if not outcome:
        return None
    for fc in all_claims:
        if fc.detector != "confounder" or outcome not in fc.subjects:
            continue
        confounder_col = fc.meta.get("confounder")
        if not confounder_col or confounder_col in covariates or confounder_col in causal_claim.subjects:
            continue
        other = next(iter(fc.subjects - {outcome}), outcome)
        verb = "reverses" if fc.kind.endswith("paradox") else "weakens"
        return (
            f"Check this: the causal estimate for '{outcome}' doesn't adjust for "
            f"'{confounder_col}', which Confounder Check found {verb} the relationship "
            f"between '{outcome}' and '{other}'."
        )
    return None


def _detect_contradiction(claims: list, all_claims: list) -> Optional[str]:
    for c in claims:
        if c.detector == "causal_att":
            found = _contradiction_for_causal_claim(c, all_claims)
            if found:
                return found
    return None


def _build_headline(claims_sorted: list, detectors: list, agreement: bool, contradiction: Optional[str]) -> str:
    if contradiction:
        return contradiction
    primary = claims_sorted[0].message
    if agreement:
        others = [d for d in detectors]
        return f"{primary} (confirmed independently by {len(others)} detectors: {', '.join(others)})."
    return primary


def _build_group(subjects: frozenset, claims: list, all_claims: list) -> ClaimGroup:
    claims_sorted = sorted(claims, key=lambda c: -_SEVERITY_WEIGHT.get(c.severity, 0))
    detectors = sorted({c.detector for c in claims_sorted})
    top_severity = claims_sorted[0].severity
    contradiction = _detect_contradiction(claims_sorted, all_claims)
    agreement = len(detectors) >= 2

    score = float(_SEVERITY_WEIGHT.get(top_severity, 0))
    if agreement:
        score += (len(detectors) - 1) * _AGREEMENT_BONUS_PER_EXTRA_DETECTOR
    if contradiction:
        score += _CONTRADICTION_BONUS

    headline = _build_headline(claims_sorted, detectors, agreement, contradiction)
    return ClaimGroup(
        subjects=subjects,
        claims=claims_sorted,
        severity=top_severity,
        score=score,
        detectors=detectors,
        agreement=agreement,
        contradiction=contradiction,
        headline=headline,
    )


def group_claims(claims: list) -> list:
    """Group claims that share the same subject column(s) into one topic —
    this is the de-duplication step: two detectors independently flagging
    the same variable pair become one ClaimGroup instead of two disconnected
    entries. Claims with no subjects (dataset-wide findings, e.g. duplicate
    rows) never merge with each other since they aren't actually about the
    same thing."""
    buckets: dict = {}
    singleton_i = 0
    for c in claims:
        if c.subjects:
            key = c.subjects
        else:
            singleton_i += 1
            key = frozenset({f"__singleton_{singleton_i}__"})
        buckets.setdefault(key, []).append(c)

    groups = [_build_group(subjects, group_claims_, claims) for subjects, group_claims_ in buckets.items()]
    groups.sort(key=lambda g: (-g.score, -_SEVERITY_WEIGHT.get(g.severity, 0)))
    return groups


# ── Entry point ──────────────────────────────────────────────────────────


def orchestrate_insights(findings_by_detector: dict) -> OrchestrationResult:
    """Synthesize already-computed detector findings into a ranked
    "what matters most" list.

    `findings_by_detector` keys are detector names ("auto_insights",
    "confounder", "causal_att", "causal_cate", "anomaly", "drift") mapped
    to that detector's own raw, already-computed output — nothing in this
    function re-runs detection. Missing/None/empty values for a detector
    are fine; unknown keys are ignored.

    Stays silent (returns silent=True, top=[]) when fewer than
    MIN_DETECTORS_FOR_OUTPUT distinct detectors contributed any findings
    at all — with only one detector in play there is nothing to cross-check,
    so producing a "top list" would just be that detector's own list
    relabeled, manufacturing noise rather than synthesis.
    """
    claims = _dedupe_exact(normalize_findings(findings_by_detector))
    n_detectors_fired = len({c.detector for c in claims})
    n_total_claims = len(claims)

    if n_detectors_fired < MIN_DETECTORS_FOR_OUTPUT or n_total_claims == 0:
        return OrchestrationResult(
            groups=[], top=[], contradictions=[],
            n_detectors_fired=n_detectors_fired, n_total_claims=n_total_claims, silent=True,
        )

    groups = group_claims(claims)
    contradictions = [g for g in groups if g.contradiction]
    top = groups[:MAX_TOP]
    return OrchestrationResult(
        groups=groups, top=top, contradictions=contradictions,
        n_detectors_fired=n_detectors_fired, n_total_claims=n_total_claims, silent=False,
    )


# ── Narration + caching support ─────────────────────────────────────────


def format_top_text(top: list) -> str:
    """Render the top-N ClaimGroups as a compact text block for Gemini
    narration input."""
    if not top:
        return "No cross-checked findings."
    lines = []
    for i, g in enumerate(top, 1):
        tag = "CHECK THIS" if g.contradiction else ("AGREEMENT" if g.agreement else g.severity.upper())
        lines.append(f"{i}. [{tag}] {g.headline}")
    return "\n".join(lines)


def fingerprint_result(result: Optional[OrchestrationResult]) -> str:
    """A short, stable hash of an orchestrate_insights() result's top list —
    used to cache the AI narration below (same convention as modules.anomaly's
    fingerprint_flagged()) so re-rendering the same top list across Streamlit
    reruns doesn't re-spend a Gemini call; only a genuinely different top
    list invalidates the cache."""
    if result is None or result.silent or not result.top:
        return "empty"
    parts = [f"{g.severity}|{'|'.join(g.detectors)}|{g.headline}" for g in result.top]
    key = "||".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


_NARRATION_PROMPT = (
    "You are a senior data analyst producing one short executive-summary paragraph that "
    "synthesizes findings from several independent automated checks (distribution/outlier "
    "scans, confounder checks, causal effect estimates, anomaly detection, dataset drift) "
    "into a single coherent picture. Below is the ranked 'what matters most' list this "
    "synthesis already produced, including where multiple independent checks agree on the "
    "same issue (higher confidence) and any 'check this' items (a potential inconsistency "
    "between two checks worth a second look, not a hard error). Write 3-5 sentences for a "
    "non-technical stakeholder. Do not just restate every line — synthesize, and lead with "
    "the single most important item.\n\nRanked findings:\n{findings_text}"
)


def narrate_orchestration(model, result: Optional[OrchestrationResult]) -> tuple:
    """Ask Gemini to turn the ranked top list into a stakeholder paragraph.

    Returns (narration, error). Falls back gracefully if Gemini is
    unavailable or there's nothing yet to narrate — never raises. Callers
    should cache the result (e.g. keyed by fingerprint_result()) rather
    than re-calling this on every rerun, same convention as every other
    narrate_* helper in the app.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if result is None or result.silent or not result.top:
        return "Not enough independent findings yet to synthesize a top-line summary.", None

    from modules.ai_analyst import call_gemini

    findings_text = format_top_text(result.top)
    prompt = _NARRATION_PROMPT.format(findings_text=findings_text)
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None


def severity_icon(severity: str) -> str:
    """Emoji icon for UI display — mirrors modules.auto_insights.severity_icon."""
    return {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F535"}.get(severity, "⚪")
