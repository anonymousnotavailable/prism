"""
PII Detector — regex-scans text/categorical columns for emails, phone
numbers, and likely person names, and offers one-click masking per flagged
column (e.g. "j***@gmail.com"). Runs automatically whenever a new dataset
becomes active (upload, sample dataset, restored session, or join result).
"""

from __future__ import annotations

import re

import pandas as pd

_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$")

# Loose enough to catch common phone formats; the digit-count check in
# _looks_like_phone() below is what actually keeps false positives down.
_PHONE_RE = re.compile(r"^\+?\d{0,3}[\s.\-]?\(?\d{2,4}\)?[\s.\-]?\d{3,4}[\s.\-]?\d{0,4}$")

# Two or three Title-Case words, letters only — a deliberately simple
# heuristic for "looks like a full person's name", not a rigorous NER model.
_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}$")

# Column-name hints checked before applying the name pattern, so generic
# Title-Case categorical values (e.g. "New York", "Team Lead") aren't flagged
# just because they happen to match the shape of a name.
_NAME_HINT_KEYWORDS = ["name", "employee", "customer", "client", "contact", "person"]

# A column is flagged once at least this share of its non-null values match.
MATCH_THRESHOLD_PCT = 30.0


def _looks_like_phone(value: str) -> bool:
    value = value.strip()
    if not _PHONE_RE.match(value):
        return False
    digit_count = sum(c.isdigit() for c in value)
    return 7 <= digit_count <= 15


def _looks_like_name_column(col: str) -> bool:
    lowered = col.lower()
    return any(hint in lowered for hint in _NAME_HINT_KEYWORDS)


def _mask_email(value: str) -> str:
    if "@" not in value:
        return value
    local, _, domain = value.partition("@")
    masked_local = (local[0] + "***") if local else "***"
    return f"{masked_local}@{domain}"


def _mask_phone(value: str) -> str:
    total_digits = sum(c.isdigit() for c in value)
    keep_last = min(2, total_digits)
    digits_seen = 0
    out_chars = []
    for c in value:
        if c.isdigit():
            digits_seen += 1
            out_chars.append(c if digits_seen > total_digits - keep_last else "*")
        else:
            out_chars.append(c)
    return "".join(out_chars)


def _mask_name(value: str) -> str:
    parts = value.split()
    masked_parts = [p[0] + "*" * (len(p) - 1) if len(p) > 1 else p for p in parts]
    return " ".join(masked_parts)


_MASK_FUNCS = {"email": _mask_email, "phone": _mask_phone, "name": _mask_name}


def scan_dataframe(df: pd.DataFrame, column_types: dict[str, str]) -> dict:
    """Regex-scan text/categorical columns for emails, phone numbers, and
    likely person names. Returns {"email": [...], "phone": [...], "name": [...]}
    — each a list of {"column", "match_pct", "sample"} dicts, "sample" already
    masked so the banner itself never displays raw PII.
    """
    findings: dict[str, list[dict]] = {"email": [], "phone": [], "name": []}

    for col, ctype in column_types.items():
        if ctype not in ("text", "categorical"):
            continue
        non_null = df[col].dropna().astype(str)
        if non_null.empty:
            continue

        email_pct = 100 * non_null.apply(lambda v: bool(_EMAIL_RE.match(v.strip()))).mean()
        if email_pct >= MATCH_THRESHOLD_PCT:
            findings["email"].append(
                {"column": col, "match_pct": round(email_pct, 1), "sample": _mask_email(non_null.iloc[0])}
            )
            continue  # treat a column as one PII type at most

        phone_pct = 100 * non_null.apply(_looks_like_phone).mean()
        if phone_pct >= MATCH_THRESHOLD_PCT:
            findings["phone"].append(
                {"column": col, "match_pct": round(phone_pct, 1), "sample": _mask_phone(non_null.iloc[0])}
            )
            continue

        if _looks_like_name_column(col):
            name_pct = 100 * non_null.apply(lambda v: bool(_NAME_RE.match(v.strip()))).mean()
            if name_pct >= MATCH_THRESHOLD_PCT:
                findings["name"].append(
                    {"column": col, "match_pct": round(name_pct, 1), "sample": _mask_name(non_null.iloc[0])}
                )

    return findings


def has_findings(findings: dict) -> bool:
    return any(findings.get(k) for k in ("email", "phone", "name"))


def describe_findings(findings: dict) -> str:
    parts = []
    if findings.get("email"):
        parts.append(f"{len(findings['email'])} email column(s)")
    if findings.get("phone"):
        parts.append(f"{len(findings['phone'])} phone number column(s)")
    if findings.get("name"):
        parts.append(f"{len(findings['name'])} likely name column(s)")
    return f"Detected {', '.join(parts)}." if parts else "No PII detected."


def mask_column(df: pd.DataFrame, column: str, pii_type: str) -> pd.DataFrame:
    """Return a copy of df with `column` masked in place, per pii_type
    ('email'/'phone'/'name'). Null values pass through unchanged.
    """
    mask_func = _MASK_FUNCS.get(pii_type)
    if mask_func is None:
        return df
    new_df = df.copy()
    new_df[column] = new_df[column].apply(lambda v: mask_func(str(v)) if pd.notna(v) else v)
    return new_df
