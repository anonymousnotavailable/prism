"""Tests for Population Stability Index (PSI) drift metric in modules/drift.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules import drift


def _seeded_normal(mean: float, std: float, n: int, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, std, n))


class TestComputePsi:
    def test_identical_distributions_near_zero(self):
        a = _seeded_normal(50, 10, 2000, seed=1)
        b = a.copy()
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert psi < 0.02

    def test_same_distribution_different_sample_is_low(self):
        a = _seeded_normal(50, 10, 2000, seed=1)
        b = _seeded_normal(50, 10, 2000, seed=2)
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert psi < 0.1

    def test_large_mean_shift_is_significant(self):
        a = _seeded_normal(50, 10, 2000, seed=1)
        b = _seeded_normal(90, 10, 2000, seed=2)
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert psi > 0.25

    def test_moderate_shift_lands_in_moderate_band(self):
        a = _seeded_normal(50, 10, 3000, seed=1)
        b = _seeded_normal(53, 10, 3000, seed=2)
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert 0.03 < psi < 0.25

    def test_psi_is_symmetric_direction_agnostic_in_magnitude_class(self):
        # PSI(A,B) and PSI(B,A) are not numerically identical (baseline bins
        # differ) but both should agree on a large shift being "significant".
        a = _seeded_normal(50, 10, 2000, seed=1)
        b = _seeded_normal(90, 10, 2000, seed=2)
        psi_ab = drift.compute_psi(a, b)
        psi_ba = drift.compute_psi(b, a)
        assert psi_ab > 0.25
        assert psi_ba > 0.25

    def test_constant_baseline_returns_none(self):
        a = pd.Series([5.0] * 100)
        b = pd.Series(np.random.default_rng(0).normal(5, 1, 100))
        assert drift.compute_psi(a, b) is None

    def test_empty_series_returns_none(self):
        a = pd.Series([], dtype=float)
        b = pd.Series([1.0, 2.0, 3.0])
        assert drift.compute_psi(a, b) is None
        assert drift.compute_psi(b, a) is None

    def test_too_few_points_returns_none_or_finite(self):
        a = pd.Series([1.0, 2.0])
        b = pd.Series([1.5, 2.5])
        result = drift.compute_psi(a, b)
        # Either bails out gracefully (None) or returns a finite number —
        # must never raise or return NaN/inf.
        if result is not None:
            assert np.isfinite(result)

    def test_nans_are_dropped_not_propagated(self):
        a = pd.Series([1.0, 2.0, 3.0, np.nan, 4.0, 5.0] * 50)
        b = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, np.nan] * 50)
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert np.isfinite(psi)

    def test_no_zero_division_when_bin_has_no_comparison_points(self):
        # b entirely outside a's range in the top bin should not raise a
        # divide-by-zero or log(0) error.
        a = _seeded_normal(50, 5, 1000, seed=1)
        b = pd.Series([1000.0] * 200)
        psi = drift.compute_psi(a, b)
        assert psi is not None
        assert np.isfinite(psi)
        assert psi > 0.25


class TestPsiVerdict:
    def test_stable_band(self):
        assert "stable" in drift.psi_verdict(0.0).lower()
        assert "stable" in drift.psi_verdict(0.09).lower()

    def test_moderate_band(self):
        assert "moderate" in drift.psi_verdict(0.1).lower()
        assert "moderate" in drift.psi_verdict(0.2).lower()

    def test_significant_band(self):
        assert "significant" in drift.psi_verdict(0.25).lower()
        assert "significant" in drift.psi_verdict(0.9).lower()

    def test_none_input_handled(self):
        result = drift.psi_verdict(None)
        assert isinstance(result, str)


class TestCompareDatasetsIncludesPsi:
    def test_numeric_report_has_psi_key(self):
        df_a = pd.DataFrame({"amount": _seeded_normal(50, 10, 500, seed=1)})
        df_b = pd.DataFrame({"amount": _seeded_normal(90, 10, 500, seed=2)})
        report = drift.compare_datasets(df_a, df_b, {"amount": "numeric"})
        assert report["column_reports"][0]["psi"] is not None
        assert report["column_reports"][0]["psi"] > 0.25

    def test_categorical_report_has_no_psi_key_or_none(self):
        df_a = pd.DataFrame({"grade": ["A", "B", "A", "C"] * 25})
        df_b = pd.DataFrame({"grade": ["A", "B", "A", "C"] * 25})
        report = drift.compare_datasets(df_a, df_b, {"grade": "categorical"})
        # Categorical PSI is out of scope for this feature — should not crash,
        # and should not silently claim a numeric-style psi score.
        assert report["column_reports"][0].get("psi") is None

    def test_describe_drift_mentions_psi_for_numeric(self):
        df_a = pd.DataFrame({"amount": _seeded_normal(50, 10, 500, seed=1)})
        df_b = pd.DataFrame({"amount": _seeded_normal(90, 10, 500, seed=2)})
        report = drift.compare_datasets(df_a, df_b, {"amount": "numeric"})
        summary = drift.describe_drift(report["column_reports"][0])
        assert "PSI" in summary
