"""Concentration and descriptive measures for aggregated registration counts."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.config import LOW_VOLUME_MONTH_FRACTION
from src.transformation.rules import CHANNEL_STATE

MONTH_NAMES: tuple[str, ...] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def hhi(shares: pd.Series) -> float:
    """Sum of squared shares. Equal shares across n groups equal 1/n. One group equals 1."""
    values = pd.Series(shares, dtype="float64")
    total = float(values.sum())
    if total <= 0 or not math.isfinite(total):
        return float("nan")
    normalized = values / total
    return float((normalized ** 2).sum())


def top_share(counts: pd.Series, k: int) -> float:
    """Share of the total held by the k largest counts."""
    values = pd.Series(counts, dtype="float64").sort_values(ascending=False)
    total = float(values.sum())
    if total <= 0 or k <= 0:
        return float("nan")
    return float(values.head(k).sum() / total)


def describe_counts(counts: pd.Series) -> dict[str, Any]:
    """Describe an observed set of counts. The standard deviation uses divisor n."""
    values = pd.Series(counts, dtype="float64").dropna()
    if values.empty:
        return {"n": 0, "mean": None, "median": None, "std": None, "minimum": None, "maximum": None}
    return {
        "n": int(values.shape[0]),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std(ddof=0)),
        "minimum": float(values.min()),
        "maximum": float(values.max()),
    }


def coefficient_of_variation(counts: pd.Series) -> float | None:
    summary = describe_counts(counts)
    if not summary["mean"]:
        return None
    return float(summary["std"] / summary["mean"])


def low_volume_months(monthly: pd.DataFrame) -> pd.DataFrame:
    """Months below 10% of the median monthly count. They stay in the source series."""
    median = float(monthly["registration_count"].median())
    threshold = LOW_VOLUME_MONTH_FRACTION * median
    flagged = monthly.loc[monthly["registration_count"] < threshold].copy()
    flagged["threshold"] = threshold
    flagged["median_monthly_count"] = median
    return flagged.sort_values("registration_year_month")


def high_volume_observations(monthly: pd.DataFrame) -> pd.DataFrame:
    """Year-months above the Tukey upper fence. These are EDA observations, not anomaly flags."""
    values = monthly["registration_count"]
    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    fence = q3 + 1.5 * (q3 - q1)
    flagged = monthly.loc[values > fence].copy()
    flagged["upper_fence"] = fence
    return flagged.sort_values("registration_count", ascending=False)


def cumulative_share_curve(counts: pd.Series, cuts: tuple[int, ...]) -> list[dict[str, float | int]]:
    rows = []
    for k in cuts:
        rows.append({"k": k, "share": top_share(counts, k)})
    return rows


def year_normalized_month_shares(monthly: pd.DataFrame, complete_years: set[int]) -> pd.DataFrame:
    """Within each complete year, month count divided by that year's count, then summarized."""
    subset = monthly.loc[monthly["registration_year"].isin(complete_years)].copy()
    if subset.empty:
        return pd.DataFrame()
    totals = subset.groupby("registration_year")["registration_count"].transform("sum")
    subset["within_year_share"] = subset["registration_count"] / totals
    summary = (
        subset.groupby("registration_month_number", as_index=False)
        .agg(
            registration_month_name=("registration_month_name", "first"),
            years=("registration_year", "nunique"),
            mean_within_year_share=("within_year_share", "mean"),
            median_within_year_share=("within_year_share", "median"),
        )
        .sort_values("registration_month_number")
    )
    return summary


def calendar_month_summary(monthly: pd.DataFrame) -> pd.DataFrame:
    return (
        monthly.groupby(["registration_month_number", "registration_month_name"], as_index=False)
        .agg(
            n=("registration_count", "size"),
            mean_registrations=("registration_count", "mean"),
            median_registrations=("registration_count", "median"),
            std_registrations=("registration_count", lambda s: float(s.std(ddof=0))),
        )
        .sort_values("registration_month_number")
    )


def quarter_summary(monthly: pd.DataFrame) -> pd.DataFrame:
    return (
        monthly.groupby("registration_quarter", as_index=False)
        .agg(
            n=("registration_count", "size"),
            mean_registrations=("registration_count", "mean"),
            median_registrations=("registration_count", "median"),
        )
        .sort_values("registration_quarter")
    )


def period_change(current: float, prior: float) -> tuple[float | None, float | None]:
    """Absolute change and percentage change. Percentage is null when the prior count is 0."""
    if current is None or prior is None or (isinstance(current, float) and math.isnan(current)):
        return None, None
    absolute = float(current) - float(prior)
    if prior == 0:
        return absolute, None
    return absolute, absolute / float(prior)


def is_geographic(state_category: str) -> bool:
    return state_category != CHANNEL_STATE
