"""
Dataset Knowledge — a small fingerprint library of well-known public
datasets, curated from hands-on research into 34 commonly-used Kaggle EDA
datasets (see docs/kaggle_dataset_research.md). Lets Prism recognize one on
upload and hand out tailored, specific advice instead of generic detection
alone — both in the UI and fed into Atlas's own answers.

Matching is a plain column-name-signature overlap, not ML: it's meant to
catch "yes, this is basically the Titanic dataset" with high precision on
an exact or near-exact schema, not to guess at loosely related data. A
false negative (a known dataset that isn't recognized) just means Prism
falls back to its normal generic detectors — recognition is a bonus layer,
never something other features depend on.
"""

from __future__ import annotations

from typing import Optional

MATCH_THRESHOLD = 0.6  # fraction of a fingerprint's signature columns that must be present

KNOWN_DATASETS: list[dict] = [
    {
        "name": "Kaggle House Prices (Ames)",
        "signature": ["SalePrice", "MSSubClass", "MSZoning", "LotFrontage", "OverallQual", "PoolQC"],
        "tips": [
            "PoolQC, MiscFeature, Alley, Fence, FireplaceQu, and the Garage/Bsmt-prefixed quality columns use NA to mean the house doesn't have that feature, not missing data — Auto Cleaner's meaningful-NA detector should suggest an explicit 'Not Applicable' category for the high-missingness ones rather than mode-imputing them.",
            "MSSubClass is a numeric-looking dwelling-type code — treat it as categorical, not continuous.",
            "GarageYrBlt has a documented typo outlier (2207, meant to be 2007).",
        ],
    },
    {
        "name": "Kaggle Telco Customer Churn",
        "signature": ["customerID", "tenure", "PhoneService", "InternetService", "TotalCharges", "Churn"],
        "tips": [
            "TotalCharges is stored as text with blank/whitespace values for customers with tenure=0, not NaN — a naive float cast fails silently.",
            "OnlineSecurity/OnlineBackup/TechSupport/StreamingTV etc. use 'No internet service' as a legitimate third category, not missingness.",
            "Churn is imbalanced (~26.5% positive) — worth a pass through ML Lab's Class Imbalance Detector before modeling.",
        ],
    },
    {
        "name": "Kaggle Titanic",
        "signature": ["PassengerId", "Survived", "Pclass", "SibSp", "Parch", "Embarked"],
        "tips": [
            "Cabin is ~77% missing — too sparse for reliable imputation; a 'has_cabin' flag is usually more useful than filling it.",
            "Fare has legitimate $0 values for crew/deadheads mixed in with real fares.",
            "Ticket format is inconsistent (pure numeric vs. alphanumeric prefixes) and isn't a unique key — tickets are shared across families.",
        ],
    },
    {
        "name": "Kaggle Netflix Shows",
        "signature": ["show_id", "listed_in", "release_year", "duration", "date_added"],
        "tips": [
            "duration mixes units in one column: '90 min' for movies vs. '2 Seasons' for TV shows.",
            "cast, country, and listed_in are comma-separated multi-value cells — Auto Cleaner's multi-value split surfaces a count + primary value instead of treating the whole string as one category.",
            "director is ~30% missing — often genuinely unlisted in the source catalog, not a data error.",
        ],
    },
    {
        "name": "Pima Indians Diabetes Dataset",
        "signature": ["Pregnancies", "Glucose", "BloodPressure", "SkinThickness", "Insulin", "BMI", "Outcome"],
        "tips": [
            "Glucose, BloodPressure, SkinThickness, Insulin, and BMI use 0 as a disguised null (biologically impossible readings) — Auto Cleaner's zero-sentinel detector targets exactly this pattern.",
            "Insulin has the highest zero-rate (~48%) — worth checking whether it's usable at all before modeling.",
        ],
    },
    {
        "name": "Kaggle BigMart Sales",
        "signature": ["Item_Identifier", "Item_Fat_Content", "Item_Visibility", "Outlet_Identifier", "Outlet_Size"],
        "tips": [
            "Item_Fat_Content has abbreviation-style duplicates ('Low Fat'/'LF'/'low fat', 'Regular'/'reg') that are too different in spelling for fuzzy matching alone — a manual merge map works better here than the automatic fuzzy-category cleanup.",
            "Item_Visibility uses 0.0 as a sentinel for 'not tracked', not a genuine zero.",
            "Item_Weight is missing for ~17% of rows but is recoverable: the same Item_Identifier always has the same weight across outlets.",
        ],
    },
    {
        "name": "NYC Airbnb Open Data",
        "signature": ["neighbourhood_group", "neighbourhood", "host_id", "minimum_nights", "availability_365"],
        "tips": [
            "last_review and reviews_per_month are null for listings with zero reviews — informative ('never reviewed'), not random missingness.",
            "price has a handful of rows at exactly 0, a sentinel rather than a real free listing, alongside legitimate outliers up to $10,000.",
            "minimum_nights has extreme outliers (some over 1,000 nights).",
        ],
    },
    {
        "name": "UCI/Kaggle Online Retail",
        "signature": ["InvoiceNo", "StockCode", "UnitPrice", "CustomerID", "InvoiceDate"],
        "tips": [
            "InvoiceNo starting with 'C' marks a cancellation, paired with negative Quantity — a prefix-plus-sign convention rather than a clean boolean flag.",
            "StockCode mixes real 5-digit SKUs with non-product codes like 'POST', 'D', 'M', 'BANK CHARGES'.",
            "The original file is Windows-1252 encoded — if it fails to load as UTF-8, Prism's CSV loader now retries CP1252/Latin-1 automatically.",
        ],
    },
    {
        "name": "Kaggle Amazon Sales Dataset",
        "signature": ["discounted_price", "actual_price", "discount_percentage", "rating_count", "category"],
        "tips": [
            "discounted_price/actual_price are text with a ₹ prefix and comma separators — Smart Type Coercion should catch these.",
            "category is a single pipe-delimited hierarchy cramming multiple taxonomy levels into one cell — a good candidate for the multi-value split.",
            "rating has at least one corrupted non-numeric value reported in community EDA — check for parse failures after coercion.",
        ],
    },
    {
        "name": "Kaggle YouTube Trending Videos",
        "signature": ["video_id", "trending_date", "channel_title", "tags", "category_id"],
        "tips": [
            "This file is very often not valid UTF-8 (titles/tags in many languages) — Prism's CSV loader auto-retries CP1252/Latin-1 on decode failure instead of failing outright.",
            "tags is pipe-delimited multi-value text.",
            "trending_date historically uses a non-standard 'YY.DD.MM' order while publish_time is full ISO8601 — two incompatible date formats in one table.",
        ],
    },
    {
        "name": "Kaggle IMDb/TMDB Movies Dataset",
        "signature": ["budget", "revenue", "genres", "original_language", "runtime"],
        "tips": [
            "budget and revenue use 0 as a disguised-null sentinel for 'unknown', not a real zero — Auto Cleaner's zero-sentinel detector targets exactly this pattern.",
            "genres is a comma-separated multi-value cell.",
            "status mixes 'Released' with 'Post Production'/'Rumored'/'Canceled' — filter before analyzing box-office performance.",
        ],
    },
    {
        "name": "Kaggle Pokemon (with stats)",
        "signature": ["Type 1", "Type 2", "HP", "Attack", "Defense", "Sp. Atk", "Legendary"],
        "tips": [
            "Type 2 is legitimately null for single-typed Pokemon — that's a real category, not missing data.",
            "Mega Evolution names are concatenated with no separator (e.g. 'VenusaurMega Venusaur') and need regex splitting.",
            "# (Pokedex number) isn't a unique row key — alternate forms reuse their base form's number.",
        ],
    },
]


def identify_dataset(columns: list[str]) -> Optional[dict]:
    """Match a DataFrame's columns against the known-dataset fingerprint
    library. Returns the best match ({"name", "tips", "match_score"}) if
    enough of its signature columns are present, else None.
    """
    col_set = set(columns)
    best = None
    best_score = 0.0
    for entry in KNOWN_DATASETS:
        sig = entry["signature"]
        overlap = sum(1 for c in sig if c in col_set)
        score = overlap / len(sig)
        if score >= MATCH_THRESHOLD and score > best_score:
            best = entry
            best_score = score
    if best is None:
        return None
    return {"name": best["name"], "tips": best["tips"], "match_score": round(best_score, 2)}
