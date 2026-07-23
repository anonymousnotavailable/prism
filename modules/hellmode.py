"""
Hell Mode — a deeper cleaning engine for the kind of real-world-messy data
that "Smart Type Coercion" and the basic null handling in v1 don't cover:
disguised nulls ("NA", "-", "Nil", ...), Indian-formatted currency/numbers
(lakh/crore, Indian comma grouping), mixed date formats within one column,
fuzzy-duplicate categories, mixed measurement units, and a richer set of
imputation strategies (including KNN and group-wise fill) with an optional
LLM recommendation pass.

Each subsystem is a set of pure functions: a detector (what's wrong, and
how much of it), and an applier (fix it), plus a `*_code()` function that
returns the pandas-equivalent code line(s) for the cleaning log / export
script, matching the convention already used in modules/cleaning.py.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Union

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from sklearn.impute import KNNImputer

from modules.ai_analyst import build_data_context, call_gemini

# ==========================================================================
# 1. Null synonym detection
# ==========================================================================

DEFAULT_NULL_SYNONYMS = [
    "NA", "N/A", "n/a", "na", "-", "--", "Nil", "NIL", "NULL", "null",
    "?", "not available", "N.A.", "none", "None",
]


def scan_disguised_nulls(
    df: pd.DataFrame, column_types: dict[str, str], synonyms: Optional[list[str]] = None
) -> dict[str, dict[str, int]]:
    """Scan text/categorical columns for disguised-null values.

    Returns {column: {marker: count}} for every column where at least one
    disguised null was found. Whitespace-only and empty strings are
    reported under the labels "(whitespace only)" and "(empty string)"
    since they aren't meaningfully displayable as a table row otherwise.
    """
    synonym_set = set(synonyms if synonyms is not None else DEFAULT_NULL_SYNONYMS)
    findings: dict[str, dict[str, int]] = {}

    for col, ctype in column_types.items():
        if ctype not in ("text", "categorical"):
            continue
        counts: dict[str, int] = {}
        for value in df[col].dropna():
            text = str(value)
            if text == "":
                counts["(empty string)"] = counts.get("(empty string)", 0) + 1
            elif text.strip() == "":
                counts["(whitespace only)"] = counts.get("(whitespace only)", 0) + 1
            elif text in synonym_set:
                counts[text] = counts.get(text, 0) + 1
        if counts:
            findings[col] = counts

    return findings


def describe_disguised_nulls(findings: dict[str, dict[str, int]]) -> list[str]:
    """One-line summaries, e.g. "Salary: 43 disguised null(s) — 31 '-', 12 'NA'"."""
    lines = []
    for col, counts in findings.items():
        total = sum(counts.values())
        parts = ", ".join(f"{n} {label!r}" for label, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        lines.append(f"{col}: {total} disguised null(s) — {parts}")
    return lines


def convert_disguised_nulls(df: pd.DataFrame, columns: list[str], synonyms: list[str]) -> pd.DataFrame:
    """Replace every disguised-null marker (or whitespace-only/empty string)
    in `columns` with a real NaN.
    """
    synonym_set = set(synonyms)
    new_df = df.copy()
    for col in columns:
        new_df[col] = new_df[col].apply(
            lambda v: np.nan if (isinstance(v, str) and (v in synonym_set or v.strip() == "")) else v
        )
    return new_df


def disguised_nulls_code(columns: list[str], synonyms: list[str]) -> str:
    return (
        f"_null_synonyms = set({synonyms!r})\n"
        f"for _col in {columns!r}:\n"
        f"    df[_col] = df[_col].apply(\n"
        f"        lambda v: pd.NA if (isinstance(v, str) and (v in _null_synonyms or v.strip() == '')) else v\n"
        f"    )"
    )


# ==========================================================================
# 2. Indian number parser
# ==========================================================================

_NUMBER_UNIT_RE = re.compile(
    r"^(-?[\d.]+)\s*(crores?|cr\.?|lakhs?|lacs?|l|k|million|mn|m|billion|bn|b)?$", re.IGNORECASE
)
_UNIT_MULTIPLIERS = {
    "crore": 1_00_00_000, "crores": 1_00_00_000, "cr": 1_00_00_000,
    "lakh": 1_00_000, "lakhs": 1_00_000, "lac": 1_00_000, "lacs": 1_00_000, "l": 1_00_000,
    "k": 1_000,
    "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
    "billion": 1_000_000_000, "bn": 1_000_000_000, "b": 1_000_000_000,
}


def parse_indian_number(value) -> Optional[float]:
    """Parse a messy Indian-formatted number string into a float.

    Handles ₹/Rs./$ prefixes, Indian-style comma grouping (1,20,000) as well
    as Western grouping (1,200) — commas are stripped unconditionally rather
    than validated against either locale's grouping rule, since in both
    conventions a comma is purely a digit separator with no numeric meaning
    of its own. Also handles Cr/crore, L/lakh/lac, K, M/million, B/billion
    suffixes and a trailing '%' (returned as a fraction, e.g. "5%" -> 0.05,
    matching modules/type_coercion.py's convention for percent values).

    Returns None if the value can't be parsed as a number at all (e.g. "Undisclosed").
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    negative = text.startswith("-")
    text = text.lstrip("-").strip()

    text = re.sub(r"^[₹$]\s*", "", text)
    text = re.sub(r"^rs\.?\s*", "", text, flags=re.IGNORECASE)

    is_percent = text.endswith("%")
    text = text.rstrip("%").strip()

    # Commas are pure digit separators in both Indian and Western grouping —
    # strip unconditionally rather than validating group size against either locale.
    text = text.replace(",", "").strip()

    match = _NUMBER_UNIT_RE.match(text)
    if not match:
        return None
    number_part, unit_part = match.groups()

    try:
        result = float(number_part)
    except ValueError:
        return None

    if unit_part:
        result *= _UNIT_MULTIPLIERS.get(unit_part.lower(), 1)
    if is_percent:
        result /= 100

    return -result if negative else result


def detect_indian_number_candidates(
    df: pd.DataFrame, column_types: dict[str, str], threshold_pct: float = 60.0
) -> list[dict]:
    """Scan text/categorical columns for values that parse as Indian-style numbers.

    Returns [{"column", "match_pct", "sample_before", "sample_after"}, ...]
    for columns where at least threshold_pct of non-null values parse successfully.
    """
    candidates = []
    for col, ctype in column_types.items():
        if ctype not in ("text", "categorical"):
            continue
        non_null = df[col].dropna().astype(str)
        if non_null.empty:
            continue
        parsed = non_null.apply(parse_indian_number)
        match_pct = 100 * parsed.notna().mean()
        if match_pct >= threshold_pct:
            candidates.append(
                {
                    "column": col,
                    "match_pct": round(match_pct, 1),
                    "sample_before": non_null.head(5).tolist(),
                    "sample_after": [None if pd.isna(v) else round(v, 2) for v in parsed.head(5)],
                }
            )
    return candidates


def convert_indian_column(
    df: pd.DataFrame, column: str, add_unit_suffix: bool = True
) -> tuple[pd.DataFrame, str]:
    """Convert an Indian-formatted numeric text column to a true numeric
    column, expressing crore/lakh/etc. values as absolute numbers.

    When add_unit_suffix is True, the column is renamed to "{column}_inr" so
    the unit conversion that happened is visible in the schema itself, not
    just in the cleaning log. Returns (new_df, resulting_column_name).
    """
    converted = df[column].apply(parse_indian_number)
    new_column = f"{column}_inr" if add_unit_suffix else column

    new_df = df.copy()
    if new_column != column:
        new_df = new_df.drop(columns=[column])
    new_df[new_column] = converted
    return new_df, new_column


def indian_number_code(column: str, new_column: str) -> str:
    rename_line = f"\ndf = df.drop(columns=[{column!r}])" if new_column != column else ""
    return (
        f"df[{new_column!r}] = df[{column!r}].apply(_prism_parse_indian_number)  "
        f"# see modules/hellmode.py:parse_indian_number{rename_line}"
    )


# ==========================================================================
# 3. Mixed date format resolver
# ==========================================================================

_ORDINAL_SUFFIX_RE = re.compile(r"(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")

_DATE_FORMAT_PATTERNS = [
    ("YYYY-MM-DD", re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")),
    ("DD/MM/YYYY or MM/DD/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")),
    ("DD-MM-YYYY", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")),
    ("DD.MM.YYYY", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")),
    ("DD-Mon-YY", re.compile(r"^\d{1,2}-[A-Za-z]{3,9}-\d{2,4}$")),
    ("Day + Month name + Year", re.compile(r"^\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}$", re.IGNORECASE)),
]


def _strip_ordinal_suffix(text: str) -> str:
    return _ORDINAL_SUFFIX_RE.sub(r"\1", text)


def detect_date_formats(series: pd.Series) -> dict[str, int]:
    """Label each non-null value's structural date format and tally counts —
    e.g. {"DD/MM/YYYY or MM/DD/YYYY": 120, "YYYY-MM-DD": 40, "unrecognized": 3}.
    """
    counts: dict[str, int] = {}
    for value in series.dropna():
        text = str(value).strip()
        label = next((name for name, pattern in _DATE_FORMAT_PATTERNS if pattern.match(text)), "unrecognized")
        counts[label] = counts.get(label, 0) + 1
    return counts


def find_ambiguous_dates(series: pd.Series, sample_size: int = 10) -> list[dict]:
    """Find distinct numeric date values (d/m/y-shaped) where day-first vs
    month-first parsing would disagree — both leading components are <=12
    and different from each other. Returns up to sample_size distinct
    examples as {"value", "day_first_reading", "month_first_reading"}.
    """
    seen: set[str] = set()
    results = []
    for value in series.dropna():
        text = str(value).strip()
        if text in seen:
            continue
        match = _NUMERIC_DATE_RE.match(text)
        if not match:
            continue
        a, b, year = match.groups()
        a_i, b_i = int(a), int(b)
        if a_i <= 12 and b_i <= 12 and a_i != b_i:
            seen.add(text)
            results.append(
                {
                    "value": text,
                    "day_first_reading": f"{a.zfill(2)}-{b.zfill(2)}-{year} (day={a}, month={b})",
                    "month_first_reading": f"{b.zfill(2)}-{a.zfill(2)}-{year} (month={a}, day={b})",
                }
            )
            if len(results) >= sample_size:
                break
    return results


def resolve_dates(series: pd.Series, day_first: bool = True) -> tuple[pd.Series, list[str]]:
    """Parse a mixed-format date column to a single datetime dtype.

    Ordinal suffixes ("12th") are stripped before parsing. Uses pandas'
    format='mixed' so each row's format is inferred independently instead of
    forcing one format across the whole column. Returns (parsed_series,
    failed_values) — failed_values lists the distinct original strings that
    could not be parsed at all, so they can be reported instead of silently
    becoming NaT.
    """
    cleaned = series.apply(lambda v: _strip_ordinal_suffix(str(v).strip()) if pd.notna(v) else v)
    parsed = pd.to_datetime(cleaned, dayfirst=day_first, format="mixed", errors="coerce")

    failed_mask = cleaned.notna() & parsed.isna()
    failed_values = cleaned[failed_mask].astype(str).unique().tolist()

    return parsed, failed_values


def date_resolver_code(column: str, day_first: bool) -> str:
    return (
        f"df[{column!r}] = df[{column!r}].astype(str).str.replace(r'(\\d+)(st|nd|rd|th)\\b', r'\\1', regex=True)\n"
        f"df[{column!r}] = pd.to_datetime(df[{column!r}], dayfirst={day_first!r}, format='mixed', errors='coerce')"
    )


# ==========================================================================
# 4. Fuzzy category cleanup (rapidfuzz)
# ==========================================================================


def suggest_fuzzy_groups(series: pd.Series, threshold: int = 85) -> list[dict]:
    """Cluster similar strings within a categorical column using rapidfuzz.

    Values are first grouped by an exact casefold+strip match (the "cheap
    win" for case variants and trailing spaces), then the remaining distinct
    normalized forms are greedily clustered by fuzz.ratio similarity >=
    threshold (catching near-misspellings like "Maharastra"). Returns groups
    with more than one member, sorted by total count descending:
    [{"canonical": str, "members": [{"value", "count"}], "total_count": int}]
    """
    value_counts = series.dropna().astype(str).value_counts()
    values = value_counts.index.tolist()
    if len(values) < 2:
        return []

    normalized_groups: dict[str, list[str]] = {}
    for v in values:
        key = v.strip().casefold()
        normalized_groups.setdefault(key, []).append(v)

    normalized_keys = list(normalized_groups.keys())
    assigned = [False] * len(normalized_keys)
    groups = []

    for i, key_i in enumerate(normalized_keys):
        if assigned[i]:
            continue
        cluster_keys = [key_i]
        assigned[i] = True
        for j in range(i + 1, len(normalized_keys)):
            if assigned[j]:
                continue
            if fuzz.ratio(key_i, normalized_keys[j]) >= threshold:
                cluster_keys.append(normalized_keys[j])
                assigned[j] = True

        members = [
            {"value": original_value, "count": int(value_counts[original_value])}
            for key in cluster_keys
            for original_value in normalized_groups[key]
        ]
        if len(members) > 1:
            members.sort(key=lambda m: -m["count"])
            groups.append(
                {"canonical": members[0]["value"], "members": members, "total_count": sum(m["count"] for m in members)}
            )

    groups.sort(key=lambda g: -g["total_count"])
    return groups


def apply_fuzzy_merge(df: pd.DataFrame, column: str, merge_map: dict[str, str]) -> pd.DataFrame:
    """Replace values in `column` per merge_map (original_value -> canonical_name)."""
    new_df = df.copy()
    new_df[column] = new_df[column].replace(merge_map)
    return new_df


def fuzzy_merge_code(column: str, merge_map: dict[str, str]) -> str:
    return f"df[{column!r}] = df[{column!r}].replace({merge_map!r})"


# ==========================================================================
# 5. Unit chaos detector
# ==========================================================================

UNIT_FAMILIES = {
    "distance": {
        "pattern": re.compile(r"^(-?[\d.]+)\s*(km|kilometers?|m|meters?|mi|miles?)$", re.IGNORECASE),
        "to_base": {
            "km": 1000, "kilometer": 1000, "kilometers": 1000,
            "m": 1, "meter": 1, "meters": 1,
            "mi": 1609.34, "mile": 1609.34, "miles": 1609.34,
        },
        "base_unit": "m",
    },
    "weight": {
        "pattern": re.compile(r"^(-?[\d.]+)\s*(kg|kilograms?|lbs?|pounds?)$", re.IGNORECASE),
        "to_base": {
            "kg": 1, "kilogram": 1, "kilograms": 1,
            "lb": 0.453592, "lbs": 0.453592, "pound": 0.453592, "pounds": 0.453592,
        },
        "base_unit": "kg",
    },
    "duration": {
        "pattern": re.compile(r"^(-?[\d.]+)\s*(sec|secs|seconds?|min|mins|minutes?|hr|hrs|hours?)$", re.IGNORECASE),
        "to_base": {
            "sec": 1, "secs": 1, "second": 1, "seconds": 1,
            "min": 60, "mins": 60, "minute": 60, "minutes": 60,
            "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
        },
        "base_unit": "sec",
    },
}


def detect_mixed_units(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Scan text/categorical columns for values carrying a recognized unit
    suffix, flagging columns where more than one distinct unit is in use.

    Returns [{"column", "family", "units_found": {unit: count}}, ...].
    """
    findings = []
    for col, ctype in column_types.items():
        if ctype not in ("text", "categorical"):
            continue
        non_null = df[col].dropna().astype(str)
        if non_null.empty:
            continue
        for family, spec in UNIT_FAMILIES.items():
            units_found: dict[str, int] = {}
            matched = 0
            for value in non_null:
                m = spec["pattern"].match(value.strip())
                if m:
                    matched += 1
                    unit = m.group(2).lower()
                    units_found[unit] = units_found.get(unit, 0) + 1
            if matched >= len(non_null) * 0.5 and len(units_found) > 1:
                findings.append({"column": col, "family": family, "units_found": units_found})
    return findings


def normalize_units(series: pd.Series, family: str, target_unit: Optional[str] = None) -> tuple[pd.Series, str]:
    """Convert every value in `series` (numbers with mixed unit suffixes) to
    a single target unit (defaults to the family's base unit).

    Returns (numeric_series_in_target_unit, description) — description is a
    one-line log summarizing what was converted, for the cleaning history.
    """
    spec = UNIT_FAMILIES[family]
    target_unit = (target_unit or spec["base_unit"]).lower()
    target_factor = spec["to_base"].get(target_unit, 1)
    counts_by_unit: dict[str, int] = {}

    def _convert(value):
        if pd.isna(value):
            return np.nan
        m = spec["pattern"].match(str(value).strip())
        if not m:
            return np.nan
        number, unit = m.groups()
        unit = unit.lower()
        counts_by_unit[unit] = counts_by_unit.get(unit, 0) + 1
        return (float(number) * spec["to_base"].get(unit, 1)) / target_factor

    converted = series.apply(_convert)
    parts = ", ".join(f"{u} ({n})" for u, n in counts_by_unit.items())
    description = f"Converted {sum(counts_by_unit.values())} value(s) to {target_unit} (from: {parts})"
    return converted, description


def unit_normalize_code(column: str, family: str, target_unit: str) -> str:
    return (
        f"# Unit normalization for '{column}' ({family} -> {target_unit}) — "
        f"see modules/hellmode.py:normalize_units for the full implementation"
    )


# ==========================================================================
# 5b. Sentinel-zero detector — 0 used as a disguised null
# ==========================================================================
#
# The Pima Diabetes dataset's Glucose/BloodPressure/BMI columns are the
# canonical example: 0 is biologically impossible for a living patient, but
# reads as a perfectly normal float, so it passes every disguised-null and
# outlier check Prism already has. The same pattern shows up as budget=0 /
# revenue=0 in movie datasets and visibility=0 in retail data. This is
# inherently a domain-knowledge call (0 IS legitimate for "number of prior
# purchases" or "discount amount"), so detection deliberately requires BOTH
# a name that suggests a physically-positive-only quantity AND a zero
# share too small to be the column's normal shape — and it only ever
# surfaces as a REVIEW suggestion, never an auto-applied SAFE fix.

ZERO_SENTINEL_NAME_HINTS = (
    "glucose", "bmi", "blood_pressure", "bloodpressure", "heart_rate", "heartrate",
    "temperature", "weight", "height", "budget", "revenue", "price", "salary", "income",
)


def detect_zero_sentinel_candidates(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Numeric columns where 0 looks like a disguised null: a name that
    implies a physically-positive-only measurement, a minority-but-nonzero
    share of exact zeros, and no negative values (ruling out a column
    where zero is just an ordinary midpoint).

    Returns [{"column", "zero_pct", "zero_count"}, ...].
    """
    findings = []
    for col, ctype in column_types.items():
        if ctype != "numeric":
            continue
        if not any(hint in col.lower() for hint in ZERO_SENTINEL_NAME_HINTS):
            continue
        series = df[col].dropna()
        if series.empty or (series < 0).any():
            continue
        zero_count = int((series == 0).sum())
        zero_pct = 100 * zero_count / len(series)
        if 1.0 <= zero_pct <= 70.0:
            findings.append({"column": col, "zero_pct": round(zero_pct, 1), "zero_count": zero_count})
    return findings


def convert_zero_sentinel_to_null(df: pd.DataFrame, column: str) -> pd.DataFrame:
    new_df = df.copy()
    new_df[column] = new_df[column].replace(0, np.nan)
    return new_df


def zero_sentinel_code(column: str) -> str:
    return f"df[{column!r}] = df[{column!r}].replace(0, np.nan)"


# ==========================================================================
# 5c. Multi-value delimited-cell detector
# ==========================================================================
#
# Netflix's cast/listed_in, Amazon's pipe-delimited category taxonomy,
# YouTube's pipe-delimited tags: a single cell packing several values
# behind a delimiter. Treating the whole string as one categorical value
# silently destroys the real cardinality — every combination becomes its
# own "category" instead of the shared underlying tags. This only reports
# the finding and adds two helper columns (how many values, and the first/
# primary one) rather than a full one-hot explosion — explosion can blow
# up column count unpredictably depending on how many distinct tokens
# exist, which isn't something Auto Cleaner should decide unsupervised.

_MULTI_VALUE_DELIMITERS = [",", "|", ";"]
MULTI_VALUE_MATCH_THRESHOLD_PCT = 50.0


def detect_multi_value_columns(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Text/categorical columns where most non-null values contain a
    consistent delimiter with 2+ tokens — a strong sign the cell packs a
    list, not a single categorical value.

    Returns [{"column", "delimiter", "match_pct", "avg_values"}, ...].
    """
    findings = []
    for col, ctype in column_types.items():
        if ctype not in ("text", "categorical"):
            continue
        non_null = df[col].dropna().astype(str)
        if non_null.empty:
            continue
        best = None
        for delim in _MULTI_VALUE_DELIMITERS:
            counts = non_null.str.count(re.escape(delim))
            match_pct = 100 * (counts >= 1).mean()
            avg_values = (counts + 1).mean()
            if match_pct >= MULTI_VALUE_MATCH_THRESHOLD_PCT and avg_values >= 1.5:
                if best is None or match_pct > best["match_pct"]:
                    best = {
                        "column": col, "delimiter": delim,
                        "match_pct": round(match_pct, 1), "avg_values": round(avg_values, 1),
                    }
        if best:
            findings.append(best)
    return findings


def split_multi_value_column(df: pd.DataFrame, column: str, delimiter: str) -> pd.DataFrame:
    """Adds `<column>_count` and `<column>_primary` (first value) alongside
    the original column — the original is left untouched since a full
    one-hot explosion is a judgment call for the user, not Auto Cleaner.
    """
    new_df = df.copy()
    split_series = new_df[column].apply(
        lambda v: [p.strip() for p in str(v).split(delimiter) if p.strip()] if pd.notna(v) else []
    )
    new_df[f"{column}_count"] = split_series.apply(len)
    new_df[f"{column}_primary"] = split_series.apply(lambda parts: parts[0] if parts else np.nan)
    return new_df


def multi_value_split_code(column: str, delimiter: str) -> str:
    return (
        f"_split = df[{column!r}].apply(lambda v: [p.strip() for p in str(v).split({delimiter!r}) if p.strip()] "
        f"if pd.notna(v) else [])\n"
        f"df[{column!r} + '_count'] = _split.apply(len)\n"
        f"df[{column!r} + '_primary'] = _split.apply(lambda parts: parts[0] if parts else None)"
    )


# ==========================================================================
# 6b. Meaningful-NA detector — missingness that isn't really missing
# ==========================================================================
#
# The single most common gotcha across real-world Kaggle datasets (House
# Prices' PoolQC/Fence/Alley being the canonical example, but also Telco
# Churn's "No internet service", BigMart's blank Outlet_Size, Pokemon's
# empty Type 2): a categorical column with a LOT of missing values is more
# often "this attribute doesn't apply to most rows" than "data collection
# failed at random." Mode-imputing PoolQC (99.5% missing because 99.5% of
# houses have no pool) with whatever pool quality IS most common among the
# 0.5% that have one manufactures a fake signal and destroys the real one —
# "no pool" is information, not a gap. This can't be known for certain from
# the data alone, so it's a statistical heuristic (concentrated high
# missingness in one optional-looking column, not spread from a systemic
# row problem) that changes Auto Cleaner's *suggested* strategy, not an
# auto-applied fix — the REVIEW tier still lets the user override it.

HIGH_MISSINGNESS_THRESHOLD_PCT = 40.0
MEANINGFUL_NA_PLACEHOLDER = "Not Applicable"


def detect_meaningful_na_candidates(
    column_types: dict[str, str], missing_by_column: dict[str, float]
) -> list[str]:
    """Categorical/text columns whose missing % is high enough that the gap
    more likely means "doesn't apply" than "unknown" — candidates for
    filling with an explicit category instead of the column's mode.
    """
    return [
        col
        for col, pct in missing_by_column.items()
        if pct >= HIGH_MISSINGNESS_THRESHOLD_PCT and column_types.get(col) in ("categorical", "text")
    ]


# ==========================================================================
# 6. Imputation intelligence
# ==========================================================================

IMPUTATION_STRATEGIES = ["mean", "median", "mode", "constant", "ffill", "bfill", "knn", "groupwise"]

IMPUTATION_STRATEGY_LABELS = {
    "mean": "Mean", "median": "Median", "mode": "Mode", "constant": "Constant value",
    "ffill": "Forward fill", "bfill": "Backward fill", "knn": "KNN imputation",
    "groupwise": "Group-wise (median/mode by group)",
}


def impute_column(
    df: pd.DataFrame,
    column: str,
    strategy: str,
    group_col: Optional[str] = None,
    custom_value: Optional[Union[str, float]] = None,
    n_neighbors: int = 5,
) -> tuple[pd.DataFrame, Optional[str]]:
    """Fill missing values in `column` using the chosen strategy.

    Returns (new_df, error) — new_df is the original df, unchanged, if error is set.
    """
    new_df = df.copy()
    series = new_df[column]

    try:
        if strategy == "mean":
            new_df[column] = series.fillna(series.mean())
        elif strategy == "median":
            new_df[column] = series.fillna(series.median())
        elif strategy == "mode":
            mode_values = series.mode()
            if mode_values.empty:
                return df, f"'{column}' has no mode to fill with (all values are missing)."
            new_df[column] = series.fillna(mode_values.iloc[0])
        elif strategy == "constant":
            new_df[column] = series.fillna(custom_value)
        elif strategy == "ffill":
            new_df[column] = series.ffill()
        elif strategy == "bfill":
            new_df[column] = series.bfill()
        elif strategy == "knn":
            numeric_cols = new_df.select_dtypes(include=np.number).columns.tolist()
            if column not in numeric_cols:
                return df, f"KNN imputation needs a numeric column — '{column}' isn't numeric."
            imputer = KNNImputer(n_neighbors=n_neighbors)
            new_df[numeric_cols] = imputer.fit_transform(new_df[numeric_cols])
        elif strategy == "groupwise":
            if not group_col:
                return df, "Group-wise fill needs a group column."
            if pd.api.types.is_numeric_dtype(series):
                new_df[column] = series.fillna(new_df.groupby(group_col)[column].transform("median"))
            else:
                new_df[column] = series.fillna(
                    new_df.groupby(group_col)[column].transform(
                        lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
                    )
                )
        else:
            return df, f"Unknown imputation strategy: {strategy}"
    except Exception as e:
        return df, f"Imputation failed: {e}"

    return new_df, None


def impute_code(
    column: str, strategy: str, group_col: Optional[str] = None, custom_value: Optional[Union[str, float]] = None
) -> str:
    """The pandas-equivalent code line(s), for the cleaning log / export script."""
    if strategy == "mean":
        return f"df[{column!r}] = df[{column!r}].fillna(df[{column!r}].mean())"
    if strategy == "median":
        return f"df[{column!r}] = df[{column!r}].fillna(df[{column!r}].median())"
    if strategy == "mode":
        return f"df[{column!r}] = df[{column!r}].fillna(df[{column!r}].mode().iloc[0])"
    if strategy == "constant":
        return f"df[{column!r}] = df[{column!r}].fillna({custom_value!r})"
    if strategy == "ffill":
        return f"df[{column!r}] = df[{column!r}].ffill()"
    if strategy == "bfill":
        return f"df[{column!r}] = df[{column!r}].bfill()"
    if strategy == "knn":
        return (
            "from sklearn.impute import KNNImputer\n"
            "_numeric_cols = df.select_dtypes(include='number').columns.tolist()\n"
            "df[_numeric_cols] = KNNImputer(n_neighbors=5).fit_transform(df[_numeric_cols])"
        )
    if strategy == "groupwise":
        return f"df[{column!r}] = df[{column!r}].fillna(df.groupby({group_col!r})[{column!r}].transform('median'))"
    return f"# Unknown strategy '{strategy}'"


_IMPUTATION_PROMPT_TEMPLATE = (
    "{context}\n\n"
    "Columns with missing values and their missing %:\n{missing_summary}\n\n"
    "You are a senior data analyst. For each column listed above, recommend ONE "
    'imputation strategy from this exact set: "mean", "median", "mode", "constant", '
    '"ffill", "bfill", "knn", "groupwise". Return a JSON object mapping column name to '
    '{{"strategy": "...", "reason": "one-line reason"}}. Only recommend "groupwise" if '
    "there's an obvious categorical grouping column in the schema above; otherwise prefer "
    "median for skewed numeric data, mean for roughly-symmetric numeric data, and mode for "
    "categorical data. Return ONLY the JSON object, no prose, no markdown code fences."
)


def ai_recommend_imputation(
    model, df: pd.DataFrame, column_types: dict[str, str], quality_report: dict
) -> tuple[dict, Optional[str]]:
    """Ask Gemini for a recommended imputation strategy per column with
    missing values. Returns (recommendations, error) — recommendations is
    {column: {"strategy": str, "reason": str}}, empty on failure.
    """
    if model is None:
        return {}, "No Gemini model available."

    missing_cols = {col: pct for col, pct in quality_report["missing_by_column"].items() if pct > 0}
    if not missing_cols:
        return {}, "No missing values to recommend a strategy for."

    context = build_data_context(df, column_types)
    missing_summary = "\n".join(
        f"- {col}: {pct}% missing ({column_types.get(col)})" for col, pct in missing_cols.items()
    )
    prompt = _IMPUTATION_PROMPT_TEMPLATE.format(context=context, missing_summary=missing_summary)

    text, error = call_gemini(model, prompt)
    if error:
        return {}, error

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}, "Could not parse Gemini's recommendation."
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}, "Could not parse Gemini's recommendation."

    valid_strategies = set(IMPUTATION_STRATEGIES)
    recommendations = {
        col: rec
        for col, rec in parsed.items()
        if col in missing_cols and isinstance(rec, dict) and rec.get("strategy") in valid_strategies
    }
    if not recommendations:
        return {}, "Gemini's response didn't match any expected columns/strategies."
    return recommendations, None


# ==========================================================================
# 8. Chaos Intensity — data resilience stress-tester
# ==========================================================================


def inject_chaos(df: pd.DataFrame, column_types: dict[str, str], intensity_pct: float, seed: int = 42) -> tuple[pd.DataFrame, dict]:
    """Deliberately degrade a COPY of df, scaled by intensity_pct (0-100),
    simulating real-world data decay so a user can see how badly a real
    degradation event would hurt their Data Health Score before it happens
    for real. Never mutates df in place.

    Three independent techniques, each scaled by intensity_pct:
    - Distribution drift: a random subset of numeric columns gets a
      fraction of their values scaled by a random multiplier — simulates a
      sensor recalibration, currency mixup, or unit error mid-dataset.
    - Null injection: every column independently loses ~intensity_pct% of
      its values.
    - Casing corruption: text/categorical values get randomized letter
      casing — simulates inconsistent manual entry.

    Deterministic given `seed` (default fixed, so a repeated run at the
    same intensity is reproducible) rather than reseeded from the clock —
    predictable results matter more here than fresh randomness each click.

    Returns (chaotic_df, report) — report names exactly what was changed
    per technique, so a before/after Health Score comparison has a
    concrete cause, not just a number.
    """
    rng = np.random.default_rng(seed)
    frac = max(0.0, min(100.0, intensity_pct)) / 100.0
    work = df.copy()
    report = {"drifted_columns": [], "null_cells_injected": 0, "casing_corrupted_columns": []}
    if frac <= 0 or work.empty:
        return work, report

    numeric_cols = [c for c, t in column_types.items() if t == "numeric" and c in work.columns]
    text_cols = [c for c, t in column_types.items() if t in ("categorical", "text") and c in work.columns]

    for col in numeric_cols:
        if rng.random() > 0.6:  # not every numeric column every run — real degradation is partial, not uniform
            continue
        cell_mask = rng.random(len(work)) < frac
        if not cell_mask.any():
            continue
        multiplier = float(rng.uniform(1.5, 4.0) * rng.choice([-1.0, 1.0]))
        work.loc[cell_mask, col] = work.loc[cell_mask, col] * multiplier
        report["drifted_columns"].append(col)

    for col in work.columns:
        cell_mask = rng.random(len(work)) < frac
        n_hit = int(cell_mask.sum())
        if n_hit == 0:
            continue
        work.loc[cell_mask, col] = np.nan
        report["null_cells_injected"] += n_hit

    def _randomize_case(value):
        if not isinstance(value, str) or not value:
            return value
        return "".join(ch.upper() if rng.random() > 0.5 else ch.lower() for ch in value)

    for col in text_cols:
        cell_mask = rng.random(len(work)) < frac
        if not cell_mask.any():
            continue
        work.loc[cell_mask, col] = work.loc[cell_mask, col].apply(_randomize_case)
        report["casing_corrupted_columns"].append(col)

    return work, report
