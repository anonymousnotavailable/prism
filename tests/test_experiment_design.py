"""Tests for modules.experiment_design — A/B test sample-size/power
calculator and post-hoc power checks for existing test results.
"""
from __future__ import annotations

from modules.experiment_design import (
    achieved_power_chi2,
    achieved_power_ttest,
    interpret_power_check,
    interpret_sample_size_means,
    interpret_sample_size_proportions,
    power_check_chi2,
    power_check_ttest,
    sample_size_two_means,
    sample_size_two_proportions,
)


# --- sample_size_two_proportions -------------------------------------------

def test_sample_size_two_proportions_basic_is_sane():
    result = sample_size_two_proportions(baseline_rate=0.20, mde=0.05)
    assert result.get("error") is None
    # 20% -> 25% lift, alpha=.05, power=.8, two-sided (statsmodels'
    # NormalIndPower/Cohen's h reference value, cross-checked against
    # standard online A/B calculators using the same arcsine formula).
    assert 1000 <= result["n_per_group"] <= 1200
    assert result["total_n"] == result["n_per_group"] * 2


def test_sample_size_two_proportions_smaller_effect_needs_more_n():
    small_effect = sample_size_two_proportions(baseline_rate=0.20, mde=0.02)
    large_effect = sample_size_two_proportions(baseline_rate=0.20, mde=0.10)
    assert small_effect["n_per_group"] > large_effect["n_per_group"]


def test_sample_size_two_proportions_higher_power_needs_more_n():
    low_power = sample_size_two_proportions(baseline_rate=0.20, mde=0.05, power=0.8)
    high_power = sample_size_two_proportions(baseline_rate=0.20, mde=0.05, power=0.95)
    assert high_power["n_per_group"] > low_power["n_per_group"]


def test_sample_size_two_proportions_rejects_invalid_rate():
    for bad_rate in (0.0, 1.0, -0.1, 1.2):
        result = sample_size_two_proportions(baseline_rate=bad_rate, mde=0.05)
        assert result.get("error")


def test_sample_size_two_proportions_rejects_out_of_range_variant():
    # baseline 0.98 + mde 0.05 -> variant rate 1.03, impossible
    result = sample_size_two_proportions(baseline_rate=0.98, mde=0.05)
    assert result.get("error")


def test_sample_size_two_proportions_rejects_zero_mde():
    result = sample_size_two_proportions(baseline_rate=0.2, mde=0.0)
    assert result.get("error")


def test_sample_size_two_proportions_unequal_ratio():
    result = sample_size_two_proportions(baseline_rate=0.2, mde=0.05, ratio=2.0)
    assert result.get("error") is None
    assert result["n_group_b"] == round(result["n_group_a"] * 2.0)


# --- sample_size_two_means --------------------------------------------------

def test_sample_size_two_means_matches_known_medium_effect():
    # Cohen's d=0.5 (medium), alpha=.05, power=.8, two-sided is a textbook
    # reference value: ~64 per group.
    result = sample_size_two_means(mean_diff=5.0, std_dev=10.0)  # d = 0.5
    assert result.get("error") is None
    assert result["cohens_d"] == 0.5
    assert 60 <= result["n_per_group"] <= 68


def test_sample_size_two_means_larger_diff_needs_less_n():
    small = sample_size_two_means(mean_diff=1.0, std_dev=10.0)
    large = sample_size_two_means(mean_diff=8.0, std_dev=10.0)
    assert small["n_per_group"] > large["n_per_group"]


def test_sample_size_two_means_rejects_zero_std_dev():
    result = sample_size_two_means(mean_diff=5.0, std_dev=0.0)
    assert result.get("error")


def test_sample_size_two_means_rejects_zero_mean_diff():
    result = sample_size_two_means(mean_diff=0.0, std_dev=10.0)
    assert result.get("error")


# --- achieved_power_ttest ----------------------------------------------------

def test_achieved_power_ttest_matches_known_reference():
    # d=0.5, n=64 per group, alpha=.05 two-sided -> power ~0.8
    power = achieved_power_ttest(cohens_d=0.5, n1=64, n2=64)
    assert 0.75 <= power <= 0.85


def test_achieved_power_ttest_increases_with_sample_size():
    small_n = achieved_power_ttest(cohens_d=0.3, n1=20, n2=20)
    large_n = achieved_power_ttest(cohens_d=0.3, n1=500, n2=500)
    assert large_n > small_n


def test_achieved_power_ttest_zero_effect_equals_alpha():
    # With no true effect, power to (falsely) reject is just the alpha level.
    power = achieved_power_ttest(cohens_d=0.0, n1=100, n2=100, alpha=0.05)
    assert 0.03 <= power <= 0.07


# --- power_check_ttest -------------------------------------------------------

def test_power_check_flags_underpowered_result():
    check = power_check_ttest(cohens_d=0.3, n1=15, n2=15)
    assert check["underpowered"] is True
    assert check["achieved_power"] < 0.8
    assert check["recommended_n_per_group"] > 15


def test_power_check_flags_well_powered_result():
    check = power_check_ttest(cohens_d=0.5, n1=500, n2=500)
    assert check["underpowered"] is False
    assert check["achieved_power"] > 0.95


def test_power_check_handles_zero_effect_size_without_raising():
    check = power_check_ttest(cohens_d=0.0, n1=50, n2=50)
    assert check.get("error") is None
    assert check["underpowered"] is True
    # No true effect -> no finite sample size reaches 80% power; the
    # calculator should say so rather than return a bogus number.
    assert check["recommended_n_per_group"] is None


def test_power_check_respects_custom_target_power():
    check = power_check_ttest(cohens_d=0.5, n1=30, n2=30, target_power=0.5)
    loose = check["underpowered"]
    stricter = power_check_ttest(cohens_d=0.5, n1=30, n2=30, target_power=0.99)["underpowered"]
    # A stricter target is at least as likely to flag underpowered as a loose one.
    assert stricter or not loose or stricter == loose


# --- interpret_power_check ---------------------------------------------------

def test_interpret_power_check_text_underpowered():
    check = power_check_ttest(cohens_d=0.3, n1=15, n2=15)
    text = interpret_power_check(check)
    assert "underpowered" in text.lower()
    assert "%" in text


def test_interpret_power_check_text_well_powered():
    check = power_check_ttest(cohens_d=0.5, n1=500, n2=500)
    text = interpret_power_check(check)
    assert "well-powered" in text.lower()


def test_interpret_power_check_handles_none_recommendation():
    check = power_check_ttest(cohens_d=0.0, n1=50, n2=50)
    text = interpret_power_check(check)
    assert text  # doesn't raise, returns something sensible


# --- interpret_sample_size_* --------------------------------------------------

def test_interpret_sample_size_proportions_text():
    result = sample_size_two_proportions(baseline_rate=0.20, mde=0.05)
    text = interpret_sample_size_proportions(result)
    assert "per group" in text
    assert str(result["n_per_group"]) in text.replace(",", "")


def test_interpret_sample_size_proportions_error_passthrough():
    result = sample_size_two_proportions(baseline_rate=1.5, mde=0.05)
    assert interpret_sample_size_proportions(result) == result["error"]


def test_interpret_sample_size_means_text():
    result = sample_size_two_means(mean_diff=5.0, std_dev=10.0)
    text = interpret_sample_size_means(result)
    assert "per group" in text
    assert str(result["n_per_group"]) in text.replace(",", "")


def test_interpret_sample_size_means_error_passthrough():
    result = sample_size_two_means(mean_diff=5.0, std_dev=0.0)
    assert interpret_sample_size_means(result) == result["error"]


# --- achieved_power_chi2 / power_check_chi2 ----------------------------------
# Reference values cross-checked against R's `pwr.chisq.test()` (the standard
# citation for chi-square power): w=0.3 (medium effect per Cohen's convention),
# df=1 (a 2x2 table), sig.level=0.05, power=0.8 -> N ~= 87.9. statsmodels'
# GofChisquarePower uses the same noncentral-chi-square approximation and
# should land within a couple of rows of that reference.

def test_achieved_power_chi2_matches_known_reference():
    # Cramer's V for a 2x2 table (min_dim=1) equals Cohen's w directly, so
    # this is exactly the pwr.chisq.test(w=0.3, df=1, n=88) scenario.
    power = achieved_power_chi2(cramers_v=0.3, n=88, rows=2, cols=2)
    assert 0.78 <= power <= 0.82


def test_achieved_power_chi2_larger_n_increases_power():
    small_n = achieved_power_chi2(cramers_v=0.2, n=50, rows=2, cols=2)
    large_n = achieved_power_chi2(cramers_v=0.2, n=1000, rows=2, cols=2)
    assert large_n > small_n


def test_achieved_power_chi2_nonsquare_table_uses_min_dim_for_w():
    # A 2x4 table: min_dim = min(2,4)-1 = 1, so the same Cramer's V implies
    # the same Cohen's w as a 2x2 table — but dof = (2-1)*(4-1) = 3, so
    # power should differ from the 2x2 case at the same n despite equal w.
    power_2x2 = achieved_power_chi2(cramers_v=0.3, n=200, rows=2, cols=2)
    power_2x4 = achieved_power_chi2(cramers_v=0.3, n=200, rows=2, cols=4)
    assert power_2x2 != power_2x4


def test_achieved_power_chi2_invalid_shape_returns_zero():
    assert achieved_power_chi2(cramers_v=0.3, n=100, rows=1, cols=2) == 0.0


def test_power_check_chi2_flags_underpowered_result():
    check = power_check_chi2(cramers_v=0.15, n=40, rows=2, cols=2)
    assert check["test"] == "chi2"
    assert check["underpowered"] is True
    assert check["achieved_power"] < 0.8
    assert check["recommended_n"] > 40


def test_power_check_chi2_flags_well_powered_result():
    check = power_check_chi2(cramers_v=0.4, n=500, rows=2, cols=2)
    assert check["underpowered"] is False
    assert check["achieved_power"] > 0.95


def test_power_check_chi2_handles_zero_effect_size_without_raising():
    check = power_check_chi2(cramers_v=0.0, n=100, rows=2, cols=3)
    assert check.get("error") is None
    assert check["underpowered"] is True
    assert check["recommended_n"] is None


def test_power_check_chi2_rejects_degenerate_table():
    check = power_check_chi2(cramers_v=0.3, n=100, rows=1, cols=2)
    assert check.get("error")


def test_power_check_chi2_dof_matches_table_shape():
    check = power_check_chi2(cramers_v=0.3, n=200, rows=3, cols=4)
    assert check["dof"] == (3 - 1) * (4 - 1)


def test_interpret_power_check_dispatches_to_chi2():
    check = power_check_chi2(cramers_v=0.15, n=40, rows=2, cols=2)
    text = interpret_power_check(check)
    assert "underpowered" in text.lower()
    assert "table" in text.lower()


def test_interpret_power_check_chi2_well_powered_text():
    check = power_check_chi2(cramers_v=0.4, n=500, rows=2, cols=2)
    text = interpret_power_check(check)
    assert "well-powered" in text.lower()
