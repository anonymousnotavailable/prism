"""
Data Engine — handles file ingestion, column type detection, and data quality
auditing for Prism. Every function here returns *new* objects rather than
mutating the DataFrame it's given, so the rest of the app can safely diff
before/after state.
"""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd

# Rows beyond this threshold are truncated on load so the app stays responsive
# in the browser — Plotly and Streamlit both slow down heavily past ~50k rows.
MAX_ROWS = 50_000


def get_excel_sheet_names(uploaded_file) -> Optional[list[str]]:
    """Return the sheet names in an uploaded Excel file, or None if the file
    isn't Excel (or can't be read as one). Used to prompt the user to pick a
    sheet before loading a multi-sheet workbook — for a single-sheet workbook
    or a plain CSV, callers can skip the prompt and load directly.
    """
    filename = uploaded_file.name.lower()
    if not filename.endswith((".xlsx", ".xls")):
        return None
    try:
        uploaded_file.seek(0)
        sheet_names = pd.ExcelFile(uploaded_file).sheet_names
        uploaded_file.seek(0)
        return list(sheet_names)
    except Exception:
        return None


def load_data(
    uploaded_file, sheet_name: Union[str, int] = 0
) -> tuple[Optional[pd.DataFrame], Optional[str], list[str]]:
    """Read an uploaded CSV/Excel file into a DataFrame.

    sheet_name is only used for Excel files — defaults to the first sheet
    (matching plain pd.read_excel's default) so existing single-sheet callers
    are unaffected. Pass an explicit sheet name once the user has picked one
    from get_excel_sheet_names().

    Returns a (dataframe, error_message, warnings) tuple. On failure,
    dataframe is None and error_message explains why. On success,
    error_message is None and dataframe is ready to use.
    """
    warnings: list[str] = []
    filename = uploaded_file.name.lower()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif filename.endswith((".xlsx", ".xls")):
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
        else:
            return None, "Unsupported file type. Please upload a .csv, .xlsx, or .xls file.", warnings
    except pd.errors.EmptyDataError:
        return None, "The uploaded file is empty.", warnings
    except pd.errors.ParserError as e:
        return None, f"Could not parse the file — it may be malformed. Details: {e}", warnings
    except UnicodeDecodeError:
        return None, "Could not decode the file. Try re-saving it as UTF-8 CSV.", warnings
    except ValueError as e:
        return None, f"Could not read the file. Details: {e}", warnings
    except Exception as e:  # last-resort catch so a bad upload never hard-crashes the app
        return None, f"Unexpected error while reading the file: {e}", warnings

    if df.shape[0] == 0:
        return None, "The uploaded file contains no rows.", warnings
    if df.shape[1] == 0:
        return None, "The uploaded file contains no columns.", warnings

    # Some Excel exports leave fully-empty trailing rows behind — drop them before
    # they skew the quality report. Fully-empty *columns* are intentionally kept:
    # they're a data-quality signal (flagged in the report, droppable in Cleaning
    # Controls) rather than something to silently discard on load.
    df = df.dropna(how="all")

    if df.shape[0] > MAX_ROWS:
        warnings.append(
            f"The file has {df.shape[0]:,} rows — Prism sampled the first {MAX_ROWS:,} "
            "rows to keep the app responsive. The cleaned-data download will only "
            "reflect this sample."
        )
        df = df.head(MAX_ROWS).reset_index(drop=True)

    return df, None, warnings


def _looks_like_datetime(series: pd.Series) -> bool:
    """Heuristic: try parsing an object column as dates and see how well it sticks."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    # Pure numbers (e.g. "42") shouldn't be treated as dates even though pandas
    # can sometimes coerce them into odd epoch-based timestamps.
    if pd.to_numeric(non_null, errors="coerce").notna().mean() > 0.9:
        return False
    parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    return parsed.notna().mean() > 0.9


def detect_column_types(df: pd.DataFrame) -> dict[str, str]:
    """Classify each column as one of: numeric, datetime, categorical, text, all_null.

    - numeric / datetime are inferred from the pandas dtype, or by attempting
      to parse object columns as dates.
    - Among remaining object columns, low-cardinality ones are 'categorical'
      (good for pie/bar charts) and high-cardinality free text is 'text'.
    """
    column_types: dict[str, str] = {}

    for col in df.columns:
        series = df[col]

        if series.isna().all():
            column_types[col] = "all_null"
            continue

        if pd.api.types.is_bool_dtype(series):
            column_types[col] = "categorical"
        elif pd.api.types.is_numeric_dtype(series):
            column_types[col] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(series):
            column_types[col] = "datetime"
        elif _looks_like_datetime(series):
            column_types[col] = "datetime"
        else:
            non_null = series.dropna()
            n_unique = non_null.nunique()
            unique_ratio = n_unique / len(non_null) if len(non_null) else 0
            if n_unique <= 50 and unique_ratio < 0.5:
                column_types[col] = "categorical"
            else:
                column_types[col] = "text"

    return column_types


def _format_bytes(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def detect_outliers_iqr(series: pd.Series) -> tuple[int, float]:
    """Count outliers in a numeric series using the IQR (Tukey's fence) method."""
    clean = series.dropna()
    if len(clean) < 4:
        return 0, 0.0
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = clean[(clean < lower) | (clean > upper)]
    return len(outliers), round(100 * len(outliers) / len(clean), 2)


def get_data_quality_report(df: pd.DataFrame, column_types: dict[str, str]) -> dict:
    """Build a single dict summarizing dataset health for the Overview tab and report export."""
    n_rows, n_cols = df.shape
    missing_by_column = {col: round(100 * df[col].isna().sum() / n_rows, 2) for col in df.columns}

    outliers = {}
    for col, ctype in column_types.items():
        if ctype == "numeric":
            count, pct = detect_outliers_iqr(df[col])
            outliers[col] = {"count": count, "pct": pct}

    total_cells = n_rows * n_cols
    return {
        "n_rows": n_rows,
        "n_cols": n_cols,
        "missing_by_column": missing_by_column,
        "total_missing_cells": int(df.isna().sum().sum()),
        "total_missing_pct": round(100 * df.isna().sum().sum() / total_cells, 2) if total_cells else 0.0,
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage": _format_bytes(df.memory_usage(deep=True).sum()),
        "outliers": outliers,
        "all_null_columns": [c for c, t in column_types.items() if t == "all_null"],
    }


def get_health_score(quality_report: dict) -> int:
    """A single 0-100 "at a glance" health score for the sticky mini-header —
    a fast composite of the same signals already shown in the Overview tab's
    data quality report, not a rigorous statistical metric.
    """
    score = 100.0
    score -= quality_report["total_missing_pct"] * 0.5

    n_rows = quality_report["n_rows"] or 1
    duplicate_pct = 100 * quality_report["duplicate_rows"] / n_rows
    score -= duplicate_pct * 0.3

    outlier_pcts = [info["pct"] for info in quality_report["outliers"].values()]
    if outlier_pcts:
        score -= (sum(outlier_pcts) / len(outlier_pcts)) * 0.2

    score -= min(len(quality_report["all_null_columns"]) * 5, 20)

    return max(0, min(100, round(score)))
