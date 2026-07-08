"""
SQL Lab — run raw SQL against the active dataset via DuckDB. The DataFrame is
registered as a table named "data"; DuckDB queries it in-memory with no disk
I/O and no separate database server.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import pandas as pd

try:
    import duckdb
except ImportError:  # the app should still load even if the package isn't installed yet
    duckdb = None


def run_query(df: pd.DataFrame, sql: str) -> tuple[Optional[pd.DataFrame], Optional[str], float]:
    """Execute a raw SQL query against `df` (registered as table `data`) via DuckDB.

    Returns (result_df, error, elapsed_seconds). On failure, result_df is None
    and error holds DuckDB's message; elapsed_seconds is measured either way.
    """
    start = time.perf_counter()
    if not sql or not sql.strip():
        return None, "Query is empty.", time.perf_counter() - start

    con = None
    try:
        con = duckdb.connect(database=":memory:")
        con.register("data", df)
        result = con.execute(sql).df()
        return result, None, time.perf_counter() - start
    except Exception as e:
        return None, str(e), time.perf_counter() - start
    finally:
        if con is not None:
            con.close()


def _safe_alias(name: str) -> str:
    """Turn an arbitrary column name into a valid, readable SQL alias fragment."""
    return re.sub(r"\W+", "_", name).strip("_") or "value"


def build_example_queries(df: pd.DataFrame, column_types: dict[str, str]) -> dict[str, str]:
    """Build 4 ready-to-run example queries using the dataset's real column
    names, falling back sensibly when a needed column type isn't present
    (e.g. no categorical column for a GROUP BY).
    """
    cols = df.columns.tolist()
    numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in column_types.items() if t == "categorical"]

    examples: dict[str, str] = {"SELECT *": 'SELECT *\nFROM data\nLIMIT 10;'}

    if categorical_cols and numeric_cols:
        cat, num = categorical_cols[0], numeric_cols[0]
        examples["GROUP BY aggregation"] = (
            f'SELECT "{cat}", COUNT(*) AS row_count, AVG("{num}") AS avg_{_safe_alias(num)}\n'
            f'FROM data\nGROUP BY "{cat}"\nORDER BY row_count DESC;'
        )
    elif categorical_cols:
        cat = categorical_cols[0]
        examples["GROUP BY aggregation"] = (
            f'SELECT "{cat}", COUNT(*) AS row_count\nFROM data\nGROUP BY "{cat}"\nORDER BY row_count DESC;'
        )
    elif numeric_cols:
        num = numeric_cols[0]
        examples["GROUP BY aggregation"] = (
            f'SELECT ROUND("{num}") AS {_safe_alias(num)}_rounded, COUNT(*) AS row_count\n'
            f'FROM data\nGROUP BY 1\nORDER BY row_count DESC;'
        )
    else:
        col0 = cols[0]
        examples["GROUP BY aggregation"] = (
            f'SELECT "{col0}", COUNT(*) AS row_count\nFROM data\nGROUP BY "{col0}"\nORDER BY row_count DESC;'
        )

    if numeric_cols:
        num = numeric_cols[0]
        median_val = df[num].median()
        threshold = 0.0 if pd.isna(median_val) else round(float(median_val), 2)
        examples["WHERE filter"] = f'SELECT *\nFROM data\nWHERE "{num}" > {threshold}\nLIMIT 20;'
        examples["ORDER BY + LIMIT"] = f'SELECT *\nFROM data\nORDER BY "{num}" DESC\nLIMIT 10;'
    else:
        col0 = cols[0]
        examples["WHERE filter"] = f'SELECT *\nFROM data\nWHERE "{col0}" IS NOT NULL\nLIMIT 20;'
        examples["ORDER BY + LIMIT"] = f'SELECT *\nFROM data\nORDER BY "{col0}"\nLIMIT 10;'

    return examples
