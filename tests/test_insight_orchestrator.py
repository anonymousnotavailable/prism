"""Tests for modules.insight_orchestrator — the cross-detector synthesis
layer that de-duplicates overlapping claims from Prism's independent
detector modules, flags agreement/contradiction, and severity-ranks the
result into a "what matters most" list. Pure synthesis over already-
computed detector output — no detection logic is re-run here.
"""
from __future__ import annotations

from modules.insight_orchestrator import (
    MIN_DETECTORS_FOR_OUTPUT,
    Claim,
    fingerprint_result,
    format_top_text,
    group_claims,
    narrate_orchestration,
    normalize_findings,
    orchestrate_insights,
    severity_icon,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures — synthetic raw detector outputs
# ─────────────────────────────────────────────────────────────────────────


def _auto_insights_raw():
    return [
        {
            "category": "correlation",
            "severity": "high",
            "column": "spend ↔ revenue",
            "metric": "r=0.91",
            "message": "'spend' and 'revenue' are strongly correlated (r=0.910).",
        },
        {
            "category": "missing_data",
            "severity": "medium",
            "column": "region",
            "metric": "15.0% missing",
            "message": "'region' has 15.0% missing values.",
        },
        {
            "category": "duplicates",
            "severity": "low",
            "column": "(all columns)",
            "metric": "3 duplicates",
            "message": "Found 3 exact duplicate rows.",
        },
    ]


def _confounder_raw_agreeing_with_causal():
    """A confounder finding on the same (spend, revenue) pair the fixture
    causal ATT result below also targets, whose flagged confounder
    ('channel') is NOT among the causal estimate's covariates — the
    textbook contradiction case."""
    return [
        {
            "x": "spend",
            "y": "revenue",
            "overall_r": 0.91,
            "findings": [
                {
                    "confounder": "channel",
                    "type": "categorical",
                    "overall_r": 0.91,
                    "adjusted_r": -0.1,
                    "verdict": "paradox",
                    "detail": [{"group": "online", "r": -0.2, "n": 20}],
                }
            ],
        }
    ]


def _causal_att_raw_missing_channel_covariate():
    return {
        "ok": True,
        "att": 12.3,
        "ci_low": 4.0,
        "ci_high": 20.0,
        "n_treated": 30,
        "n_control": 30,
        "n_matched": 28,
        "match_rate": 0.93,
        "treatment_col": "spend",
        "treated_value": "high",
        "control_value": "low",
        "outcome_col": "revenue",
        "covariates": ["tenure"],  # deliberately excludes 'channel'
        "balance_before": [],
        "balance_after": [],
        "warnings": [],
    }


def _causal_att_raw_adjusting_for_confounder():
    return {
        "ok": True,
        "att": 12.3,
        "ci_low": 4.0,
        "ci_high": 20.0,
        "n_treated": 30,
        "n_control": 30,
        "n_matched": 28,
        "match_rate": 0.93,
        "treatment_col": "spend",
        "treated_value": "high",
        "control_value": "low",
        "outcome_col": "revenue",
        "covariates": ["tenure", "channel"],  # includes the flagged confounder
        "balance_before": [],
        "balance_after": [],
        "warnings": [],
    }


def _causal_cate_raw_sign_reversal():
    return {
        "ok": True,
        "pooled": {"treatment_col": "spend", "outcome_col": "revenue", "att": 8.0, "ci_low": 2.0, "ci_high": 14.0},
        "subgroup_col": "region",
        "subgroups": [],
        "sign_reversal": True,
        "heterogeneity_detected": True,
        "warnings": [],
    }


def _anomaly_raw():
    return {
        "count": 12,
        "total_rows": 100,
        "reasons": [
            "spend is 4.2x above the column median.",
            "spend is 3.9x above the column median.",
            "tenure is 2.1x below the column median.",
        ],
    }


def _drift_raw():
    return {
        "column_reports": [
            {"column": "revenue", "type": "numeric", "drift_score": 82.0},
            {"column": "notes", "type": "categorical", "drift_score": 10.0},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────────────────


def test_normalize_auto_insights_splits_pair_subjects():
    claims = normalize_findings({"auto_insights": _auto_insights_raw()})
    corr_claim = next(c for c in claims if c.kind == "auto_insights:correlation")
    assert corr_claim.subjects == frozenset({"spend", "revenue"})
    dup_claim = next(c for c in claims if c.kind == "auto_insights:duplicates")
    assert dup_claim.subjects == frozenset()  # "(all columns)" -> dataset-wide


def test_normalize_confounder_paradox_is_high_severity():
    claims = normalize_findings({"confounder": _confounder_raw_agreeing_with_causal()})
    assert len(claims) == 1
    assert claims[0].severity == "high"
    assert claims[0].subjects == frozenset({"spend", "revenue"})
    assert claims[0].meta["confounder"] == "channel"


def test_normalize_causal_att_significant_when_ci_excludes_zero():
    claims = normalize_findings({"causal_att": _causal_att_raw_missing_channel_covariate()})
    assert claims[0].severity == "high"


def test_normalize_causal_att_low_severity_when_ci_crosses_zero():
    raw = _causal_att_raw_missing_channel_covariate()
    raw["ci_low"], raw["ci_high"] = -2.0, 20.0
    claims = normalize_findings({"causal_att": raw})
    assert claims[0].severity == "low"


def test_normalize_causal_att_not_ok_produces_no_claims():
    claims = normalize_findings({"causal_att": {"ok": False, "error": "not enough data"}})
    assert claims == []


def test_normalize_causal_cate_sign_reversal_is_high_severity():
    claims = normalize_findings({"causal_cate": _causal_cate_raw_sign_reversal()})
    assert len(claims) == 1
    assert claims[0].severity == "high"
    assert claims[0].subjects == frozenset({"spend", "revenue"})


def test_normalize_causal_cate_no_heterogeneity_produces_no_claims():
    raw = _causal_cate_raw_sign_reversal()
    raw["sign_reversal"] = False
    raw["heterogeneity_detected"] = False
    assert normalize_findings({"causal_cate": raw}) == []


def test_normalize_anomaly_extracts_top_column_and_scales_severity():
    claims = normalize_findings({"anomaly": _anomaly_raw()})
    assert len(claims) == 1
    assert claims[0].subjects == frozenset({"spend"})  # most common column in reasons
    assert claims[0].severity == "high"  # 12% >= 10%


def test_normalize_anomaly_with_no_extractable_column_is_dataset_wide():
    claims = normalize_findings(
        {"anomaly": {"count": 2, "total_rows": 100, "reasons": ["Unusual combination of values across numeric columns."]}}
    )
    assert claims[0].subjects == frozenset()


def test_normalize_anomaly_empty_count_produces_no_claims():
    assert normalize_findings({"anomaly": {"count": 0, "total_rows": 100, "reasons": []}}) == []


def test_normalize_drift_filters_below_threshold():
    claims = normalize_findings({"drift": _drift_raw()})
    assert len(claims) == 1
    assert claims[0].subjects == frozenset({"revenue"})
    assert claims[0].severity == "high"  # 82 >= 75


def test_normalize_unknown_detector_key_is_ignored():
    claims = normalize_findings({"some_future_detector": [{"whatever": True}]})
    assert claims == []


def test_normalize_malformed_detector_output_does_not_raise():
    # auto_insights adapter expects dicts with a "message" key — garbage in
    # one detector must not break normalization of the others.
    claims = normalize_findings({"auto_insights": ["not a dict"], "drift": _drift_raw()})
    assert any(c.detector == "drift" for c in claims)


def test_normalize_none_and_missing_values_are_safe():
    assert normalize_findings({"auto_insights": None, "confounder": None}) == []
    assert normalize_findings({}) == []
    assert normalize_findings(None) == []


# ─────────────────────────────────────────────────────────────────────────
# Grouping / de-duplication
# ─────────────────────────────────────────────────────────────────────────


def test_group_claims_merges_same_subject_pair_across_detectors():
    claims = normalize_findings(
        {
            "auto_insights": _auto_insights_raw(),
            "confounder": _confounder_raw_agreeing_with_causal(),
        }
    )
    groups = group_claims(claims)
    spend_revenue_groups = [g for g in groups if g.subjects == frozenset({"spend", "revenue"})]
    assert len(spend_revenue_groups) == 1
    group = spend_revenue_groups[0]
    assert set(group.detectors) == {"auto_insights", "confounder"}
    assert group.agreement is True


def test_group_claims_keeps_dataset_wide_findings_separate():
    claims = [
        Claim(detector="auto_insights", subjects=frozenset(), severity="low", kind="a", message="finding A"),
        Claim(detector="drift", subjects=frozenset(), severity="low", kind="b", message="finding B"),
    ]
    groups = group_claims(claims)
    # two dataset-wide claims from different detectors must NOT be merged
    # into one topic just because both have empty subjects
    assert len(groups) == 2


def test_dedupe_exact_collapses_identical_repeated_claim():
    # normalize_findings() itself does not dedupe (that's orchestrate_insights'
    # job) — accidental duplication upstream (e.g. a detector re-run) must
    # still collapse to one claim once orchestrated.
    raw = _auto_insights_raw()
    result = orchestrate_insights({"auto_insights": raw + raw, "drift": _drift_raw()})
    corr_claims = [c for c in result.groups if c.subjects == frozenset({"spend", "revenue"})][0].claims
    assert len(corr_claims) == 1


# ─────────────────────────────────────────────────────────────────────────
# Agreement / contradiction
# ─────────────────────────────────────────────────────────────────────────


def test_agreement_across_three_detectors_on_same_pair():
    result = orchestrate_insights(
        {
            "auto_insights": _auto_insights_raw(),
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_adjusting_for_confounder(),
        }
    )
    group = next(g for g in result.groups if g.subjects == frozenset({"spend", "revenue"}))
    assert group.agreement is True
    assert set(group.detectors) == {"auto_insights", "confounder", "causal_att"}
    # covariates include the confounder -> no contradiction here
    assert group.contradiction is None


def test_contradiction_flagged_when_causal_estimate_ignores_flagged_confounder():
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
        }
    )
    assert len(result.contradictions) == 1
    contradiction_group = result.contradictions[0]
    assert "channel" in contradiction_group.contradiction
    assert "Check this" in contradiction_group.contradiction
    assert contradiction_group.headline == contradiction_group.contradiction


def test_no_contradiction_when_causal_estimate_adjusts_for_confounder():
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_adjusting_for_confounder(),
        }
    )
    assert result.contradictions == []


def test_contradiction_is_a_flag_not_a_hard_error_still_produces_output():
    # A contradiction must never look like a crash/error path — the group
    # still carries its normal claims and a valid severity.
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
        }
    )
    assert result.silent is False
    group = result.contradictions[0]
    assert group.severity in ("high", "medium", "low")
    assert len(group.claims) >= 2


# ─────────────────────────────────────────────────────────────────────────
# Severity ranking
# ─────────────────────────────────────────────────────────────────────────


def test_top_list_is_ranked_worst_first():
    result = orchestrate_insights(
        {
            "auto_insights": _auto_insights_raw(),  # includes a low-severity duplicates finding
            "drift": _drift_raw(),  # one high-severity drift finding
        }
    )
    assert result.silent is False
    scores = [g.score for g in result.top]
    assert scores == sorted(scores, reverse=True)


def test_contradiction_and_agreement_outrank_a_lone_high_severity_claim():
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
            "drift": _drift_raw(),  # a lone high-severity claim, no agreement/contradiction
        }
    )
    assert result.top[0].contradiction is not None


def test_top_list_capped_at_max_top():
    from modules.insight_orchestrator import MAX_TOP

    many_drift_reports = {
        "column_reports": [{"column": f"col_{i}", "type": "numeric", "drift_score": 90.0} for i in range(20)]
    }
    result = orchestrate_insights({"auto_insights": _auto_insights_raw(), "drift": many_drift_reports})
    assert len(result.top) == MAX_TOP
    assert len(result.groups) > MAX_TOP


# ─────────────────────────────────────────────────────────────────────────
# Silent / empty-state path
# ─────────────────────────────────────────────────────────────────────────


def test_silent_when_zero_detectors_have_findings():
    result = orchestrate_insights({})
    assert result.silent is True
    assert result.top == []
    assert result.n_detectors_fired == 0


def test_silent_when_only_one_detector_has_findings():
    assert MIN_DETECTORS_FOR_OUTPUT == 2
    result = orchestrate_insights({"auto_insights": _auto_insights_raw()})
    assert result.silent is True
    assert result.top == []
    assert result.n_detectors_fired == 1
    assert result.n_total_claims == len(_auto_insights_raw())


def test_not_silent_once_a_second_detector_contributes():
    result = orchestrate_insights({"auto_insights": _auto_insights_raw(), "drift": _drift_raw()})
    assert result.silent is False
    assert result.n_detectors_fired == 2
    assert len(result.top) > 0


def test_silent_when_all_detectors_present_but_empty():
    result = orchestrate_insights({"auto_insights": [], "confounder": None, "causal_att": {"ok": False}})
    assert result.silent is True


# ─────────────────────────────────────────────────────────────────────────
# Narration — cache/fallback convention
# ─────────────────────────────────────────────────────────────────────────


def test_narrate_orchestration_no_model_returns_error():
    result = orchestrate_insights({"auto_insights": _auto_insights_raw(), "drift": _drift_raw()})
    text, error = narrate_orchestration(None, result)
    assert text == ""
    assert error


def test_narrate_orchestration_silent_result_skips_gemini():
    class _ShouldNotBeCalled:
        def generate_content(self, contents):
            raise AssertionError("Gemini should not be called for a silent orchestration result")

    result = orchestrate_insights({"auto_insights": _auto_insights_raw()})  # only 1 detector -> silent
    text, error = narrate_orchestration(_ShouldNotBeCalled(), result)
    assert error is None
    assert "not enough" in text.lower()


def test_narrate_orchestration_calls_gemini_with_ranked_findings():
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
        }
    )

    class _FakeResponse:
        text = "Your spend-revenue relationship looks strong, but double-check the channel confound before acting on it."

    class _FakeModel:
        def generate_content(self, contents):
            assert "check this" in contents.lower() or "channel" in contents.lower()
            return _FakeResponse()

    text, error = narrate_orchestration(_FakeModel(), result)
    assert error is None
    assert "channel" in text.lower()


def test_fingerprint_result_stable_for_same_top_list():
    result = orchestrate_insights({"auto_insights": _auto_insights_raw(), "drift": _drift_raw()})
    fp1 = fingerprint_result(result)
    fp2 = fingerprint_result(result)
    assert fp1 == fp2
    assert fp1 != "empty"


def test_fingerprint_result_empty_for_silent_result():
    result = orchestrate_insights({"auto_insights": _auto_insights_raw()})
    assert fingerprint_result(result) == "empty"
    assert fingerprint_result(None) == "empty"


def test_fingerprint_result_changes_when_top_list_changes():
    result_a = orchestrate_insights({"auto_insights": _auto_insights_raw(), "drift": _drift_raw()})
    result_b = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
        }
    )
    assert fingerprint_result(result_a) != fingerprint_result(result_b)


# ─────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────


def test_format_top_text_tags_contradiction_and_agreement():
    result = orchestrate_insights(
        {
            "confounder": _confounder_raw_agreeing_with_causal(),
            "causal_att": _causal_att_raw_missing_channel_covariate(),
        }
    )
    text = format_top_text(result.top)
    assert "CHECK THIS" in text


def test_format_top_text_empty():
    assert "No cross-checked findings" in format_top_text([])


def test_severity_icon_covers_known_values():
    assert severity_icon("high") != severity_icon("low")
    assert severity_icon("unknown") == "⚪"
