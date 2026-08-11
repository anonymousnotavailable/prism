"""Tests for modules.mllab.export_baseline_script() — generates a standalone,
runnable .py file that reproduces the ML Lab baseline model run (preprocessing
pipeline, train/test split, optional SMOTE, both baseline models, printed
metrics) outside the app. Mirrors the existing pattern in
cleaning.export_script() (which only replays cleaning steps) but scoped to
the ML Lab baseline-model pipeline specifically.

The most important tests here are round-trip: write the generated script to
disk, execute it as a real subprocess against a real CSV, and check it runs
clean and prints the expected metrics — proving the script is a faithful,
literally-runnable reproduction, not just plausible-looking text.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.mllab import export_baseline_script


def _classification_csv(tmp_path: Path, n: int = 300, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    cat = rng.choice(["a", "b", "c"], size=n)
    target = (x1 + rng.normal(scale=0.5, size=n) > 0).astype(int)
    df = pd.DataFrame({"x1": x1, "x2": x2, "cat": cat, "target": target})
    path = tmp_path / "class_data.csv"
    df.to_csv(path, index=False)
    return path


def _imbalanced_classification_csv(tmp_path: Path, n: int = 400, seed: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    n_pos = max(2, int(n * 0.1))
    target = np.zeros(n, dtype=int)
    pos_idx = rng.choice(n, size=n_pos, replace=False)
    target[pos_idx] = 1
    x1[pos_idx] += 2.5
    df = pd.DataFrame({"x1": x1, "x2": x2, "target": target})
    path = tmp_path / "imb_data.csv"
    df.to_csv(path, index=False)
    return path


def _regression_csv(tmp_path: Path, n: int = 250, seed: int = 2) -> Path:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = 3 * x1 - 2 * x2 + rng.normal(scale=1.0, size=n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "target": target})
    path = tmp_path / "reg_data.csv"
    df.to_csv(path, index=False)
    return path


def _run_script(script_text: str, workdir: Path) -> subprocess.CompletedProcess:
    script_path = workdir / "exported_script.py"
    script_path.write_text(script_text)
    return subprocess.run(
        [sys.executable, str(script_path)], cwd=workdir, capture_output=True, text=True, timeout=60,
    )


class TestExportBaselineScriptContent:
    def test_classification_script_contains_expected_pieces(self):
        script = export_baseline_script(
            ["x1", "x2", "cat"], "target", "classification", use_smote=False, original_filename="my_data.csv",
        )
        assert "RandomForestClassifier" in script
        assert "LogisticRegression" in script
        assert "train_test_split" in script
        assert "'target'" in script or '"target"' in script
        assert "my_data.csv" in script
        assert "SMOTE" not in script

    def test_regression_script_uses_regression_models(self):
        script = export_baseline_script(["x1", "x2"], "target", "regression")
        assert "RandomForestRegressor" in script
        assert "LinearRegression" in script
        assert "RandomForestClassifier" not in script

    def test_smote_flag_adds_smote_block(self):
        script = export_baseline_script(["x1", "x2"], "target", "classification", use_smote=True)
        assert "SMOTE" in script
        assert "imblearn" in script

    def test_no_original_filename_uses_placeholder(self):
        script = export_baseline_script(["x1", "x2"], "target", "classification")
        assert "your_file.csv" in script

    def test_excel_filename_uses_read_excel(self):
        script = export_baseline_script(["x1", "x2"], "target", "classification", original_filename="data.xlsx")
        assert "read_excel" in script

    def test_script_is_valid_python_syntax(self):
        script = export_baseline_script(["x1", "x2"], "target", "classification", use_smote=True)
        compile(script, "<exported>", "exec")  # raises SyntaxError if malformed


class TestExportBaselineScriptRoundTrip:
    def test_classification_script_actually_runs_and_prints_metrics(self, tmp_path):
        csv_path = _classification_csv(tmp_path)
        script = export_baseline_script(
            ["x1", "x2", "cat"], "target", "classification", original_filename=csv_path.name,
        )
        result = _run_script(script, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "Baseline" in result.stdout
        assert "Random Forest" in result.stdout
        assert "accuracy" in result.stdout.lower()

    def test_regression_script_actually_runs_and_prints_metrics(self, tmp_path):
        csv_path = _regression_csv(tmp_path)
        script = export_baseline_script(["x1", "x2"], "target", "regression", original_filename=csv_path.name)
        result = _run_script(script, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "rmse" in result.stdout.lower()
        assert "r2" in result.stdout.lower()

    def test_smote_script_actually_runs_on_imbalanced_data(self, tmp_path):
        csv_path = _imbalanced_classification_csv(tmp_path)
        script = export_baseline_script(
            ["x1", "x2"], "target", "classification", use_smote=True, original_filename=csv_path.name,
        )
        result = _run_script(script, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "SMOTE" in result.stdout or "resampl" in result.stdout.lower()


class TestExportBaselineScriptEdgeCases:
    def test_empty_feature_list_still_produces_valid_python(self):
        script = export_baseline_script([], "target", "classification")
        compile(script, "<exported>", "exec")

    def test_column_names_with_special_characters_are_safely_quoted(self):
        script = export_baseline_script(["weird col!", "x2"], "weird'target", "classification")
        compile(script, "<exported>", "exec")
        assert "weird col!" in script
