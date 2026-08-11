"""Tests for modules.data_engine's large-file ingestion path.

load_data()'s existing behavior (encoding/delimiter sniffing, header
recovery, MAX_ROWS truncation) reads the *entire* file into pandas before
deciding what to keep — fine for small files, wasteful and eventually
impossible for a genuinely large one (a multi-GB CSV shouldn't have to
fully materialize in Python memory just to get truncated down to 50k rows
a moment later). This module adds an optional DuckDB-backed path: for
files above a size threshold, DuckDB's out-of-core CSV reader counts rows
and pulls a random sample directly, without pandas ever seeing the full
file. Below the threshold, behavior is byte-for-byte unchanged — these
tests exist to prove that boundary, not to re-test load_data()'s existing
encoding/header logic (already exercised manually across every prior run's
audit).
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from modules.data_engine import (
    LARGE_FILE_THRESHOLD_BYTES,
    _duckdb_sample_csv,
    _should_attempt_duckdb,
    load_data,
)


class _FakeUploadedFile(io.BytesIO):
    """Minimal stand-in for streamlit's UploadedFile — a BytesIO with the
    extra `.name`/`.size` attributes load_data() and its helpers read."""

    def __init__(self, data: bytes, name: str = "data.csv", size: int | None = None):
        super().__init__(data)
        self.name = name
        self.size = size if size is not None else len(data)


def _csv_bytes(n_rows: int) -> bytes:
    lines = ["id,value,label"] + [f"{i},{i * 1.5},group{i % 3}" for i in range(n_rows)]
    return ("\n".join(lines)).encode("utf-8")


pytest.importorskip("duckdb")


# ─────────────────────────────────────────────────────────────────────────
# _should_attempt_duckdb — the size gate
# ─────────────────────────────────────────────────────────────────────────
def test_should_attempt_duckdb_false_for_small_file():
    f = _FakeUploadedFile(_csv_bytes(10), size=1_000)
    assert _should_attempt_duckdb(f) is False


def test_should_attempt_duckdb_true_above_threshold():
    f = _FakeUploadedFile(_csv_bytes(10), size=LARGE_FILE_THRESHOLD_BYTES + 1)
    assert _should_attempt_duckdb(f) is True


def test_should_attempt_duckdb_false_when_size_unknown():
    f = _FakeUploadedFile(_csv_bytes(10))
    del f.size  # simulate an object that doesn't expose .size at all
    assert _should_attempt_duckdb(f) is False


# ─────────────────────────────────────────────────────────────────────────
# _duckdb_sample_csv — the actual out-of-core read
# ─────────────────────────────────────────────────────────────────────────
def test_duckdb_sample_returns_all_rows_when_under_cap():
    f = _FakeUploadedFile(_csv_bytes(50))
    result = _duckdb_sample_csv(f, max_rows=200)
    assert result is not None
    df, warnings = result
    assert len(df) == 50
    assert list(df.columns) == ["id", "value", "label"]
    assert warnings == []


def test_duckdb_sample_takes_random_sample_when_over_cap():
    f = _FakeUploadedFile(_csv_bytes(2000))
    result = _duckdb_sample_csv(f, max_rows=100, random_state=42)
    assert result is not None
    df, warnings = result
    assert len(df) == 100
    assert warnings and "2,000" in warnings[0]
    # A random sample across the whole file, not just the first 100 rows —
    # ids shouldn't all be small/contiguous the way df.head(100) would be.
    assert df["id"].max() > 200


def test_duckdb_sample_is_reproducible_given_same_seed():
    data = _csv_bytes(2000)
    df1, _ = _duckdb_sample_csv(_FakeUploadedFile(data), max_rows=50, random_state=7)
    df2, _ = _duckdb_sample_csv(_FakeUploadedFile(data), max_rows=50, random_state=7)
    assert sorted(df1["id"].tolist()) == sorted(df2["id"].tolist())


def test_duckdb_sample_returns_none_on_unparseable_content():
    garbage = _FakeUploadedFile(b"\x00\x01\x02\xff\xfe not a csv at all \x00")
    assert _duckdb_sample_csv(garbage, max_rows=100) is None


# ─────────────────────────────────────────────────────────────────────────
# load_data() — wiring: large files route through DuckDB, small files don't
# ─────────────────────────────────────────────────────────────────────────
def test_load_data_small_file_unaffected():
    f = _FakeUploadedFile(_csv_bytes(20))
    df, error, warnings = load_data(f)
    assert error is None
    assert len(df) == 20
    assert not any("DuckDB" in w for w in warnings)


def test_load_data_routes_large_file_through_duckdb():
    # Content is small, but a spoofed .size forces the large-file path —
    # isolates the routing decision from actually generating a huge file.
    f = _FakeUploadedFile(_csv_bytes(500), size=LARGE_FILE_THRESHOLD_BYTES + 1)
    df, error, warnings = load_data(f, max_rows=100)
    assert error is None
    assert len(df) == 100
    assert any("DuckDB" in w for w in warnings)


def test_load_data_falls_back_to_pandas_if_duckdb_cant_parse():
    # Spoofed large size, but content DuckDB's CSV reader chokes on (a
    # banner row it can't reconcile as well as pandas' dedicated recovery
    # path can) — must still succeed via the existing pandas fallback.
    messy = b"Company Sales Report\n\nid,value,label\n" + _csv_bytes(30).split(b"\n", 1)[1]
    f = _FakeUploadedFile(messy, size=LARGE_FILE_THRESHOLD_BYTES + 1)
    df, error, warnings = load_data(f)
    assert error is None
    assert len(df) >= 1
