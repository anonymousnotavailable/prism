"""
Titan Enrichment — merges free, public weather data onto a dataset that
has a location column and a date column, so questions like "did rain
affect sales that week" become answerable without the user hunting down
weather data themselves.

Uses Open-Meteo specifically: no API key, no signup, no per-user credential
to store or leak — a real constraint for a public, unauthenticated app.
Geocoding and the historical weather archive are both free and keyless.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import requests
import streamlit as st

_LOCATION_NAME_HINTS = (
    "city", "location", "place", "region", "state", "country", "town",
    "district", "province", "zipcode", "zip_code", "postal", "pincode",
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_REQUEST_TIMEOUT_SECONDS = 15

# A free, keyless public API is still a shared resource — cap how many
# distinct locations one enrichment run looks up, both to be a considerate
# user of Open-Meteo's rate limits and to keep the button responsive
# instead of geocoding hundreds of one-off values.
MAX_DISTINCT_LOCATIONS = 20


def detect_enrichment_columns(df: pd.DataFrame, column_types: dict[str, str]) -> list[dict]:
    """Find (location_column, date_column) pairs Titan Enrichment could use.

    Location columns are detected by *name* (fast, no network) rather than
    by checking values against a geocoder — that would itself cost API
    calls just to decide whether to show a button.
    """
    location_cols = [
        col for col, ctype in column_types.items()
        if ctype in ("categorical", "text") and any(hint in col.lower() for hint in _LOCATION_NAME_HINTS)
    ]
    date_cols = [col for col, ctype in column_types.items() if ctype == "datetime"]
    if not location_cols or not date_cols:
        return []
    return [{"location_column": loc, "date_column": dt} for loc in location_cols for dt in date_cols]


@st.cache_data(show_spinner=False, ttl=86400)
def geocode_location(place_name: str) -> Optional[tuple[float, float]]:
    """(latitude, longitude) for a place name via Open-Meteo's free
    geocoding API, or None if it couldn't be resolved. Cached for a day —
    place names don't move, and this is the call most likely to repeat
    across rows sharing the same city/region.
    """
    try:
        resp = requests.get(GEOCODING_URL, params={"name": place_name, "count": 1}, timeout=_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            return None
        return results[0]["latitude"], results[0]["longitude"]
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=86400)
def fetch_daily_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Daily max/min temperature and precipitation for one location across
    a date range, in a single request — one call per *location*, covering
    its full min-to-max date span in the data, rather than one call per row.
    """
    try:
        resp = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": latitude, "longitude": longitude,
                "start_date": start_date, "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto",
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        daily = resp.json().get("daily")
        if not daily or not daily.get("time"):
            return None
        return pd.DataFrame({
            "date": pd.to_datetime(daily["time"]).date,
            "temp_max_c": daily["temperature_2m_max"],
            "temp_min_c": daily["temperature_2m_min"],
            "precipitation_mm": daily["precipitation_sum"],
        })
    except Exception:
        return None


def enrich_with_weather(df: pd.DataFrame, location_col: str, date_col: str) -> tuple[pd.DataFrame, dict]:
    """Merge daily weather onto df, matched by (location, date).

    Returns (enriched_df, report). report has: locations_enriched,
    locations_failed (geocoding or weather lookup came back empty),
    locations_skipped_for_cap (distinct locations beyond
    MAX_DISTINCT_LOCATIONS, never looked up), and rows_matched. On total
    failure (no location resolved), returns the original df unchanged —
    enrichment is additive, never destructive.
    """
    work = df.copy()
    # format="mixed" matters here, not just style: this app's own sample data
    # (and real-world exports generally) routinely mixes date formats within
    # one column (12/03/2024, 2024-03-12, 12-Mar-24, ...) — see Hell Mode's
    # Mixed Date Format Resolver, built for exactly this. A plain
    # pd.to_datetime() without it silently coerces most of a mixed-format
    # column to NaT instead of raising, which would have made this function
    # look like it "worked" while quietly matching a fraction of the rows it
    # should have. Caught by testing against Prism's own messy sample data,
    # not by inspection — rows_matched was far lower than the enriched
    # location list implied.
    work["_enrich_date"] = pd.to_datetime(work[date_col], errors="coerce", format="mixed").dt.date

    distinct_locations = work[location_col].dropna().astype(str).unique().tolist()
    capped = distinct_locations[:MAX_DISTINCT_LOCATIONS]
    skipped_for_cap = distinct_locations[MAX_DISTINCT_LOCATIONS:]

    weather_frames = []
    locations_enriched, locations_failed = [], []
    for location in capped:
        coords = geocode_location(location)
        if coords is None:
            locations_failed.append(location)
            continue
        subset_dates = work.loc[work[location_col].astype(str) == location, "_enrich_date"].dropna()
        if subset_dates.empty:
            continue
        weather = fetch_daily_weather(coords[0], coords[1], str(subset_dates.min()), str(subset_dates.max()))
        if weather is None or weather.empty:
            locations_failed.append(location)
            continue
        weather["_enrich_location"] = location
        weather_frames.append(weather)
        locations_enriched.append(location)

    if not weather_frames:
        return df, {
            "locations_enriched": [], "locations_failed": locations_failed,
            "locations_skipped_for_cap": skipped_for_cap, "rows_matched": 0,
        }

    weather_all = pd.concat(weather_frames, ignore_index=True)
    merged = work.merge(
        weather_all, left_on=["_enrich_date", location_col], right_on=["date", "_enrich_location"], how="left",
    )
    merged = merged.drop(columns=["_enrich_date", "date", "_enrich_location"])
    rows_matched = int(merged["temp_max_c"].notna().sum())

    return merged, {
        "locations_enriched": locations_enriched, "locations_failed": locations_failed,
        "locations_skipped_for_cap": skipped_for_cap, "rows_matched": rows_matched,
    }
