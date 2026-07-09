"""
Domain Lens — two "domain packs" that turn a user-mapped set of columns
into ready-made, interview-ready analytics: Product (retention cohorts,
DAU/MAU stickiness, funnels, churn) and Banking (RFM segmentation,
transaction anomalies, NPA/overdue analysis, credit utilization). Each
metric has a short plain-English explanation string alongside it.

Every function here takes plain column names the caller has already mapped
from the user's schema (via the Domain Lens tab's column mapper) — nothing
in this module assumes fixed column names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ==========================================================================
# Product Analytics Pack
# ==========================================================================

PRODUCT_METRIC_EXPLANATIONS = {
    "retention": (
        "Retention cohorts group users by the month they first showed up, then track what % of "
        "each cohort keeps coming back in later months — a classic way to see if a product is "
        "'sticky' over time, not just growing."
    ),
    "dau_mau": (
        "DAU/MAU stickiness (Daily Active Users / Monthly Active Users) measures how often active "
        "users come back — 20% stickiness roughly means the average monthly user is active about "
        "1 in every 5 days."
    ),
    "funnel": (
        "A funnel tracks how many users make it through each step of a sequential flow (e.g. "
        "signup -> activation -> purchase), showing exactly where the biggest drop-off happens."
    ),
    "churn": (
        "A simple churn flag marks any user who hasn't been active in a chosen window (e.g. 30 "
        "days) as 'churned' — a fast proxy for the harder question of who's actually gone for good."
    ),
}


def compute_retention_cohorts(df: pd.DataFrame, user_col: str, timestamp_col: str) -> pd.DataFrame:
    """Monthly cohort retention: rows = cohort month (each user's first-seen
    month), columns = months since that cohort started (0, 1, 2, ...),
    values = % of that cohort's users active in that period.
    """
    data = df[[user_col, timestamp_col]].dropna().copy()
    data[timestamp_col] = pd.to_datetime(data[timestamp_col], errors="coerce")
    data = data.dropna(subset=[timestamp_col])
    data["activity_month"] = data[timestamp_col].dt.to_period("M")

    first_seen = data.groupby(user_col)["activity_month"].min().rename("cohort_month")
    data = data.join(first_seen, on=user_col)
    data["period_number"] = (data["activity_month"] - data["cohort_month"]).apply(lambda x: x.n)

    cohort_sizes = data.groupby("cohort_month")[user_col].nunique()
    pivot = data.groupby(["cohort_month", "period_number"])[user_col].nunique().unstack(fill_value=0)
    retention_pct = pivot.divide(cohort_sizes, axis=0) * 100
    retention_pct.index = retention_pct.index.astype(str)
    retention_pct.columns = [f"Month {c}" for c in retention_pct.columns]
    return retention_pct.round(1)


def compute_dau_mau(df: pd.DataFrame, user_col: str, timestamp_col: str) -> pd.DataFrame:
    """Daily active users, a trailing 30-day monthly-active-user count, and
    stickiness (DAU/MAU) for every day in the data's date range.
    """
    data = df[[user_col, timestamp_col]].dropna().copy()
    data[timestamp_col] = pd.to_datetime(data[timestamp_col], errors="coerce")
    data = data.dropna(subset=[timestamp_col])
    data["activity_date"] = data[timestamp_col].dt.normalize()

    dau = data.groupby("activity_date")[user_col].nunique()
    all_dates = pd.date_range(data["activity_date"].min(), data["activity_date"].max(), freq="D")
    dau = dau.reindex(all_dates, fill_value=0)

    mau = []
    for current_date in all_dates:
        window_mask = (data["activity_date"] > current_date - pd.Timedelta(days=30)) & (
            data["activity_date"] <= current_date
        )
        mau.append(data.loc[window_mask, user_col].nunique())

    result = pd.DataFrame({"dau": dau.values, "mau": mau}, index=all_dates)
    result["stickiness"] = (result["dau"] / result["mau"].replace(0, np.nan)).fillna(0).round(3)
    return result


def compute_funnel(df: pd.DataFrame, user_col: str, event_col: str, stages: list[str]) -> dict:
    """Sequential funnel: each stage's user set is intersected with the
    previous stage's, so counts strictly narrow (true funnel semantics —
    a user who skipped an earlier stage doesn't count toward a later one).

    Returns {"stage_counts", "conversion_pct" (of the first stage), "dropoff_pct" (vs. the
    previous stage)}, all keyed by stage name.
    """
    stage_users: set = None
    stage_counts = {}
    for stage in stages:
        users_at_stage = set(df.loc[df[event_col] == stage, user_col].dropna().unique())
        stage_users = users_at_stage if stage_users is None else (stage_users & users_at_stage)
        stage_counts[stage] = len(stage_users)

    first_count = stage_counts[stages[0]] or 1
    conversion_pct = {stage: round(100 * count / first_count, 1) for stage, count in stage_counts.items()}

    dropoff_pct = {}
    previous_count = None
    for stage in stages:
        if previous_count is not None and previous_count > 0:
            dropoff_pct[stage] = round(100 * (previous_count - stage_counts[stage]) / previous_count, 1)
        previous_count = stage_counts[stage]

    return {"stage_counts": stage_counts, "conversion_pct": conversion_pct, "dropoff_pct": dropoff_pct}


def flag_churn(df: pd.DataFrame, user_col: str, timestamp_col: str, inactive_days: int) -> pd.DataFrame:
    """Per-user last-activity date, days inactive (relative to the dataset's
    latest timestamp), and a churned flag (days_inactive >= inactive_days).
    """
    data = df[[user_col, timestamp_col]].dropna().copy()
    data[timestamp_col] = pd.to_datetime(data[timestamp_col], errors="coerce")
    data = data.dropna(subset=[timestamp_col])

    last_activity = data.groupby(user_col)[timestamp_col].max().rename("last_activity")
    reference_date = data[timestamp_col].max()
    result = last_activity.to_frame()
    result["days_inactive"] = (reference_date - result["last_activity"]).dt.days
    result["churned"] = result["days_inactive"] >= inactive_days
    return result.reset_index()


def build_cohort_heatmap(retention_df: pd.DataFrame) -> go.Figure:
    fig = px.imshow(
        retention_df, text_auto=".0f", color_continuous_scale="Tealgrn", aspect="auto",
        labels=dict(x="Months since first activity", y="Cohort month", color="% returning"),
    )
    fig.update_layout(title="Retention Cohort Heatmap", margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_dau_mau_chart(dau_mau_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dau_mau_df.index, y=dau_mau_df["dau"], mode="lines", name="DAU"))
    fig.add_trace(go.Scatter(x=dau_mau_df.index, y=dau_mau_df["mau"], mode="lines", name="MAU (trailing 30d)"))
    fig.update_layout(title="Daily / Monthly Active Users", margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_stickiness_chart(dau_mau_df: pd.DataFrame) -> go.Figure:
    fig = px.line(
        x=dau_mau_df.index, y=dau_mau_df["stickiness"], labels={"x": "Date", "y": "Stickiness (DAU/MAU)"},
        title="Stickiness Ratio",
    )
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_funnel_chart(funnel_result: dict, stages: list[str]) -> go.Figure:
    fig = go.Figure(
        go.Funnel(y=stages, x=[funnel_result["stage_counts"][s] for s in stages], textinfo="value+percent initial")
    )
    fig.update_layout(title="Funnel Analysis", margin=dict(t=50, b=10, l=10, r=10))
    return fig


# ==========================================================================
# Banking Analytics Pack
# ==========================================================================

BANKING_METRIC_EXPLANATIONS = {
    "rfm": (
        "RFM segments customers by Recency (days since last transaction), Frequency (how often "
        "they transact), and Monetary value (how much) — a classic, interview-ready way to find "
        "your best customers and who's slipping away."
    ),
    "anomalies": (
        "Flags transactions with an amount far outside a customer's own normal range (beyond 3x "
        "their IQR) or days with an unusually high transaction count — the two simplest, most "
        "common signals used for first-pass fraud/error triage."
    ),
    "npa": (
        "NPA (Non-Performing Asset) ratio is the standard banking metric for loan book health: the "
        "share of total loan value that's 90+ days overdue and unlikely to be repaid on schedule."
    ),
    "credit_utilization": (
        "Credit utilization (balance / limit) is one of the strongest predictors of credit risk — "
        "sustained utilization above roughly 30% is a commonly used early-warning threshold."
    ),
}

OVERDUE_BUCKETS = ["0-30", "31-60", "61-90", "90+"]


def compute_rfm(df: pd.DataFrame, customer_col: str, date_col: str, amount_col: str) -> pd.DataFrame:
    """Recency (days since last transaction), Frequency (transaction count),
    Monetary (total amount) per customer, each scored 1-5 by quantile and
    combined into a labeled segment (Champions, Loyal Customers, At Risk, ...).
    """
    data = df[[customer_col, date_col, amount_col]].dropna().copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col])

    reference_date = data[date_col].max()
    rfm = data.groupby(customer_col).agg(
        recency=(date_col, lambda s: (reference_date - s.max()).days),
        frequency=(amount_col, "count"),
        monetary=(amount_col, "sum"),
    )

    def _score(series: pd.Series, best_is_low: bool) -> pd.Series:
        labels = [5, 4, 3, 2, 1] if best_is_low else [1, 2, 3, 4, 5]
        try:
            return pd.qcut(series.rank(method="first"), 5, labels=labels).astype(int)
        except ValueError:
            return pd.Series(3, index=series.index)

    rfm["r_score"] = _score(rfm["recency"], best_is_low=True)
    rfm["f_score"] = _score(rfm["frequency"], best_is_low=False)
    rfm["m_score"] = _score(rfm["monetary"], best_is_low=False)
    rfm["rfm_score"] = rfm["r_score"] + rfm["f_score"] + rfm["m_score"]

    def _segment(row) -> str:
        if row["r_score"] >= 4 and row["f_score"] >= 4:
            return "Champions"
        if row["r_score"] >= 3 and row["f_score"] >= 3:
            return "Loyal Customers"
        if row["r_score"] >= 4 and row["f_score"] <= 2:
            return "New Customers"
        if row["r_score"] <= 2 and row["f_score"] >= 3:
            return "At Risk"
        if row["r_score"] <= 2 and row["f_score"] <= 2:
            return "Lost"
        return "Needs Attention"

    rfm["segment"] = rfm.apply(_segment, axis=1)
    return rfm.reset_index()


def detect_transaction_anomalies(df: pd.DataFrame, customer_col: str, amount_col: str, date_col: str) -> pd.DataFrame:
    """Per-customer amount outliers (beyond Q3 + 3xIQR) and sudden daily
    transaction-frequency spikes (a day's count more than 3 std-devs above
    that customer's own daily average). Returns a flat DataFrame of flagged
    rows/days with a plain-English reason column.
    """
    data = df[[customer_col, date_col, amount_col]].dropna().copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col])

    flags = []

    for customer, group in data.groupby(customer_col):
        if len(group) < 4:
            continue
        q1, q3 = group[amount_col].quantile([0.25, 0.75])
        upper_bound = q3 + 3 * (q3 - q1)
        for _, row in group[group[amount_col] > upper_bound].iterrows():
            flags.append(
                {
                    "customer": customer, "date": row[date_col], "amount": row[amount_col],
                    "reason": f"Amount {row[amount_col]:,.2f} is beyond 3xIQR for this customer (threshold {upper_bound:,.2f})",
                }
            )

    daily_counts = data.groupby([customer_col, data[date_col].dt.date]).size().rename("daily_count").reset_index()
    for customer, group in daily_counts.groupby(customer_col):
        if len(group) < 4:
            continue
        mean_count, std_count = group["daily_count"].mean(), group["daily_count"].std()
        if not std_count or pd.isna(std_count):
            continue
        threshold = mean_count + 3 * std_count
        for _, row in group[group["daily_count"] > threshold].iterrows():
            flags.append(
                {
                    "customer": customer, "date": row[date_col], "amount": None,
                    "reason": (
                        f"{row['daily_count']} transactions on this day vs. average "
                        f"{mean_count:.1f} (threshold {threshold:.1f})"
                    ),
                }
            )

    return pd.DataFrame(flags)


def compute_overdue_buckets(df: pd.DataFrame, overdue_days_col: str) -> pd.Series:
    """Bucket loan rows by days overdue into the standard 0-30/31-60/61-90/90+ NPA buckets."""

    def _bucket(days) -> str:
        if days <= 30:
            return "0-30"
        if days <= 60:
            return "31-60"
        if days <= 90:
            return "61-90"
        return "90+"

    bucketed = df[overdue_days_col].dropna().apply(_bucket)
    return bucketed.value_counts().reindex(OVERDUE_BUCKETS, fill_value=0)


def compute_npa_ratio(df: pd.DataFrame, loan_amount_col: str, overdue_days_col: str) -> dict:
    """Standard NPA definition: loans overdue more than 90 days are non-performing.

    Returns {"npa_ratio_pct", "npa_amount", "total_amount", "npa_count", "total_count"}.
    """
    data = df[[loan_amount_col, overdue_days_col]].dropna()
    npa_mask = data[overdue_days_col] > 90
    total_amount = data[loan_amount_col].sum()
    npa_amount = data.loc[npa_mask, loan_amount_col].sum()
    return {
        "npa_ratio_pct": round(100 * npa_amount / total_amount, 2) if total_amount else 0.0,
        "npa_amount": float(npa_amount),
        "total_amount": float(total_amount),
        "npa_count": int(npa_mask.sum()),
        "total_count": len(data),
    }


def compute_credit_utilization(df: pd.DataFrame, limit_col: str, balance_col: str) -> pd.Series:
    """balance / limit ratio per row (credit utilization), expressed as a percentage."""
    data = df[[limit_col, balance_col]].dropna()
    utilization = (data[balance_col] / data[limit_col].replace(0, np.nan)) * 100
    return utilization.dropna()


def build_rfm_segment_chart(rfm_df: pd.DataFrame) -> go.Figure:
    counts = rfm_df["segment"].value_counts()
    fig = px.bar(x=counts.index, y=counts.values, labels={"x": "Segment", "y": "Customers"}, title="RFM Segments")
    fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_overdue_bucket_chart(bucket_counts: pd.Series) -> go.Figure:
    fig = px.bar(
        x=bucket_counts.index, y=bucket_counts.values,
        labels={"x": "Days overdue", "y": "Loan count"}, title="Overdue Bucket Distribution",
        color=bucket_counts.index, color_discrete_sequence=["#69f0ae", "#ffab40", "#ff6e40", "#ff1744"],
    )
    fig.update_layout(showlegend=False, margin=dict(t=50, b=10, l=10, r=10))
    return fig


def build_credit_utilization_chart(utilization: pd.Series) -> go.Figure:
    fig = px.histogram(
        utilization, nbins=30, labels={"value": "Credit utilization %"}, title="Credit Utilization Distribution"
    )
    fig.update_layout(showlegend=False, margin=dict(t=50, b=10, l=10, r=10))
    return fig
