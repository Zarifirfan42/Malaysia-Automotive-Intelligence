"""Turn aggregated Phase 3 extracts into descriptive measures and test records."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.analysis.inference import (
    ALPHA,
    apply_bonferroni,
    chi_square_periods,
    fuel_period_years,
    kruskal_by_group,
    spearman_trend,
)
from src.analysis.metrics import (
    calendar_month_summary,
    coefficient_of_variation,
    cumulative_share_curve,
    describe_counts,
    hhi,
    high_volume_observations,
    low_volume_months,
    period_change,
    quarter_summary,
    top_share,
    year_normalized_month_shares,
)
from src.transformation.rules import CHANNEL_STATE


def analyze(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Build the Phase 4 result from aggregated frames. Registration rows are already counted."""
    overview = _overview(frames)
    monthly = frames["monthly"].copy()
    yearly = frames["yearly"].copy()
    yearly["registration_year"] = yearly["registration_year"].astype(int)
    monthly["registration_year"] = monthly["registration_year"].astype(int)
    complete_years = set(int(year) for year in yearly.loc[~yearly["is_partial_year"].astype(bool), "registration_year"])
    partial_years = [int(year) for year in yearly.loc[yearly["is_partial_year"].astype(bool), "registration_year"]]

    temporal = _temporal(monthly, yearly, frames["like_for_like"], complete_years)
    manufacturers = _manufacturers(frames["manufacturer_month"], frames["like_for_like"])
    models = _models(frames["model_year"])
    vehicle_types = _category_totals(frames["type_month"], "type")
    fuels = _fuels(frames["fuel_month"], sorted(complete_years))
    electric = _electric_hybrid(yearly, overview, partial_years)
    states = _states(frames["state_month"], complete_years, partial_years)
    tests = _tests(monthly, yearly, fuels["fuel_year"], complete_years, temporal["low_volume_months"])
    adjustment = apply_bonferroni(tests, ALPHA)
    _attach_conclusions(tests)

    monthly_sum = int(monthly["registration_count"].sum())
    reconciled = monthly_sum == overview["registration_count"]
    status = "PASS" if reconciled else "FAIL"
    if reconciled and any(not test.get("applicable", False) and test["id"] in adjustment["primary_test_ids"] for test in tests):
        status = "WARN"

    return {
        "status": status,
        "reconciled_with_monthly_view": reconciled,
        "overview": overview,
        "partial_years": partial_years,
        "complete_years": sorted(complete_years),
        "temporal": temporal,
        "manufacturer": manufacturers,
        "model": models,
        "vehicle_type": vehicle_types,
        "fuel": fuels["summary"],
        "electric_hybrid": electric,
        "state_channel": states,
        "tests": tests,
        "multiple_testing": adjustment,
        "phase5": _phase5_notes(overview, temporal, states, electric, tests),
        "loaded_all_rows_into_python_memory": False,
        "largest_frame_rows": max(len(frame) for frame in frames.values()),
    }


def _overview(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    row = frames["overview"].iloc[0]
    pairs = int(frames["manufacturer_model_pairs"].iloc[0]["manufacturer_model_pairs"])
    return {
        "registration_count": int(row["registration_count"]),
        "minimum_date": _date_text(row["minimum_date_reg"]),
        "maximum_date": _date_text(row["maximum_date_reg"]),
        "registration_years": int(row["registration_years"]),
        "observed_months": int(row["observed_months"]),
        "manufacturers": int(row["manufacturers"]),
        "model_names": int(row["model_names"]),
        "manufacturer_model_pairs": pairs,
        "fuel_categories": int(row["fuel_categories"]),
        "vehicle_types": int(row["vehicle_types"]),
        "state_channels": int(row["state_channels"]),
        "electric_registrations": int(row["electric_registrations"]),
        "hybrid_registrations": int(row["hybrid_registrations"]),
        "hybrid_petrol_registrations": int(row["hybrid_petrol_registrations"]),
        "hybrid_diesel_registrations": int(row["hybrid_diesel_registrations"]),
    }


def _temporal(
    monthly: pd.DataFrame,
    yearly: pd.DataFrame,
    like_for_like: pd.DataFrame,
    complete_years: set[int],
) -> dict[str, Any]:
    counts = monthly["registration_count"]
    low = low_volume_months(monthly)
    low_keys = set(low["registration_year_month"])
    kept = monthly.loc[~monthly["registration_year_month"].isin(low_keys), "registration_count"]
    high = high_volume_observations(monthly)
    ordered = monthly.sort_values(["registration_year", "registration_month_number"]).copy()
    ordered["month_to_month_change"] = ordered["registration_count"].pct_change()
    changes = ordered["month_to_month_change"].dropna()
    normalized = year_normalized_month_shares(monthly, complete_years)
    normalized_cv = None
    if not normalized.empty:
        normalized_cv = coefficient_of_variation(normalized["mean_within_year_share"])
    like = like_for_like.iloc[0]
    yearly_rows = []
    for row in yearly.itertuples(index=False):
        partial = bool(row.is_partial_year)
        yearly_rows.append(
            {
                "registration_year": int(row.registration_year),
                "is_partial_year": partial,
                "registration_count": int(row.registration_count),
                "electric_registrations": int(row.electric_registrations),
                "hybrid_registrations": int(row.hybrid_registrations),
                "electric_registration_share": _share(row.electric_registrations, row.registration_count),
                "hybrid_registration_share": _share(row.hybrid_registrations, row.registration_count),
                "yoy_absolute_change": None if partial or pd.isna(row.yoy_absolute_change) else int(row.yoy_absolute_change),
                "yoy_percentage_change": None if partial or pd.isna(row.yoy_percentage_change) else float(row.yoy_percentage_change),
                "yoy_basis": str(row.yoy_basis),
            }
        )
    return {
        "monthly_descriptive": describe_counts(counts),
        "monthly_descriptive_excluding_low_volume": describe_counts(kept),
        "coefficient_of_variation": coefficient_of_variation(counts),
        "year_normalized_coefficient_of_variation": normalized_cv,
        "low_volume_months": [_month_record(row) for row in low.itertuples(index=False)],
        "low_volume_threshold": None if low.empty else float(low["threshold"].iloc[0]),
        "high_volume_eda_observations": [_month_record(row) for row in high.head(8).itertuples(index=False)],
        "month_to_month_median_change": None if changes.empty else float(changes.median()),
        "month_to_month_minimum_change": None if changes.empty else float(changes.min()),
        "month_to_month_minimum_month": None
        if changes.empty
        else str(ordered.loc[changes.idxmin(), "registration_year_month"]),
        "calendar_month": _records(calendar_month_summary(monthly)),
        "year_normalized_month": _records(normalized),
        "quarter": _records(quarter_summary(monthly)),
        "yearly": yearly_rows,
        "like_for_like": {
            "latest_year": int(like["latest_year"]),
            "prior_year": int(like["prior_year"]),
            "through_month": int(like["through_month"]),
            "through_month_name": _month_name(int(like["through_month"])),
            "comparison_label": str(like["comparison_label"]),
            "latest_period_registrations": int(like["latest_period_registrations"]),
            "prior_period_registrations": int(like["prior_period_registrations"]),
            "latest_period_electric_registrations": int(like["latest_period_electric_registrations"]),
            "prior_period_electric_registrations": int(like["prior_period_electric_registrations"]),
            "latest_period_hybrid_registrations": int(like["latest_period_hybrid_registrations"]),
            "prior_period_hybrid_registrations": int(like["prior_period_hybrid_registrations"]),
            "yoy_absolute_change": None if pd.isna(like["yoy_absolute_change"]) else int(like["yoy_absolute_change"]),
            "yoy_percentage_change": None if pd.isna(like["yoy_percentage_change"]) else float(like["yoy_percentage_change"]),
            "yoy_basis": str(like["yoy_basis"]),
        },
    }


def _manufacturers(manufacturer_month: pd.DataFrame, like_for_like: pd.DataFrame) -> dict[str, Any]:
    grouped = (
        manufacturer_month.groupby("maker_clean", as_index=False)[["registration_count", "electric_registrations", "hybrid_registrations"]]
        .sum()
        .sort_values(["registration_count", "maker_clean"], ascending=[False, True])
    )
    total = float(grouped["registration_count"].sum())
    grouped["registration_share"] = grouped["registration_count"] / total
    grouped["electric_registration_share"] = grouped["electric_registrations"] / grouped["registration_count"]
    grouped["hybrid_registration_share"] = grouped["hybrid_registrations"] / grouped["registration_count"]
    like = like_for_like.iloc[0]
    window = manufacturer_month.loc[
        manufacturer_month["registration_month_number"] <= int(like["through_month"])
    ]
    latest_year = int(like["latest_year"])
    prior_year = int(like["prior_year"])
    latest_counts = _year_counts(window, latest_year)
    prior_counts = _year_counts(window, prior_year)
    comparison = grouped.head(10)[["maker_clean", "registration_count"]].copy()
    comparison["latest_period_registrations"] = comparison["maker_clean"].map(latest_counts).fillna(0).astype(int)
    comparison["prior_period_registrations"] = comparison["maker_clean"].map(prior_counts).fillna(0).astype(int)
    changes = comparison.apply(
        lambda row: period_change(row["latest_period_registrations"], row["prior_period_registrations"]),
        axis=1,
    )
    comparison["yoy_absolute_change"] = [item[0] for item in changes]
    comparison["yoy_percentage_change"] = [item[1] for item in changes]
    electric_leaders = grouped.sort_values(["electric_registrations", "maker_clean"], ascending=[False, True]).head(10)
    hybrid_leaders = grouped.sort_values(["hybrid_registrations", "maker_clean"], ascending=[False, True]).head(10)
    return {
        "manufacturers": int(len(grouped)),
        "top_5_share": top_share(grouped["registration_count"], 5),
        "top_10_share": top_share(grouped["registration_count"], 10),
        "hhi": hhi(grouped["registration_share"]),
        "cumulative_share": cumulative_share_curve(grouped["registration_count"], (1, 5, 10, 20)),
        "largest": _records(grouped.head(15)),
        "like_for_like": _records(comparison),
        "like_for_like_window": {
            "latest_year": latest_year,
            "prior_year": prior_year,
            "through_month": int(like["through_month"]),
        },
        "electric_leaders": _records(electric_leaders),
        "hybrid_leaders": _records(hybrid_leaders),
    }


def _models(model_year: pd.DataFrame) -> dict[str, Any]:
    pairs = (
        model_year.groupby(["maker_clean", "model_clean"], as_index=False)[
            ["registration_count", "electric_registrations", "hybrid_registrations"]
        ]
        .sum()
        .sort_values(["registration_count", "maker_clean", "model_clean"], ascending=[False, True, True])
    )
    total = float(pairs["registration_count"].sum())
    pairs["registration_share"] = pairs["registration_count"] / total
    names_with_multiple = int((model_year.groupby("model_clean")["maker_clean"].nunique() > 1).sum())
    electric_pairs = pairs.loc[pairs["electric_registrations"] > 0].sort_values(
        ["electric_registrations", "maker_clean", "model_clean"], ascending=[False, True, True]
    )
    hybrid_pairs = pairs.loc[pairs["hybrid_registrations"] > 0].sort_values(
        ["hybrid_registrations", "maker_clean", "model_clean"], ascending=[False, True, True]
    )
    return {
        "manufacturer_model_pairs": int(len(pairs)),
        "model_names": int(pairs["model_clean"].nunique()),
        "model_names_with_multiple_manufacturers": names_with_multiple,
        "top_10_share": top_share(pairs["registration_count"], 10),
        "hhi": hhi(pairs["registration_share"]),
        "largest_pairs": _records(pairs.head(15)),
        "electric_pairs": _records(electric_pairs.head(10)),
        "hybrid_pairs": _records(hybrid_pairs.head(10)),
    }


def _category_totals(frame: pd.DataFrame, key: str) -> dict[str, Any]:
    grouped = (
        frame.groupby(key, as_index=False)["registration_count"]
        .sum()
        .sort_values(["registration_count", key], ascending=[False, True])
    )
    total = float(grouped["registration_count"].sum())
    grouped["registration_share"] = grouped["registration_count"] / total
    yearly = (
        frame.groupby([key, "registration_year"], as_index=False)["registration_count"]
        .sum()
    )
    return {
        "totals": _records(grouped),
        "hhi": hhi(grouped["registration_share"]),
        "yearly_rows": len(yearly),
    }


def _fuels(fuel_month: pd.DataFrame, complete_years: list[int]) -> dict[str, Any]:
    grouped = (
        fuel_month.groupby("fuel_category", as_index=False)["registration_count"]
        .sum()
        .sort_values(["registration_count", "fuel_category"], ascending=[False, True])
    )
    total = float(grouped["registration_count"].sum())
    grouped["registration_share"] = grouped["registration_count"] / total
    fuel_year = fuel_month.groupby(["fuel_category", "registration_year"], as_index=False)["registration_count"].sum()
    periods = fuel_period_years(complete_years)
    comparison = []
    if periods is not None:
        earlier, recent = periods
        earlier_counts = _period_counts(fuel_year, earlier)
        recent_counts = _period_counts(fuel_year, recent)
        earlier_total = sum(earlier_counts.values())
        recent_total = sum(recent_counts.values())
        for fuel in sorted(set(earlier_counts) | set(recent_counts)):
            earlier_n = earlier_counts.get(fuel, 0)
            recent_n = recent_counts.get(fuel, 0)
            comparison.append(
                {
                    "fuel_category": fuel,
                    "earlier_registrations": earlier_n,
                    "recent_registrations": recent_n,
                    "earlier_share": earlier_n / earlier_total if earlier_total else None,
                    "recent_share": recent_n / recent_total if recent_total else None,
                    "share_point_change": (recent_n / recent_total - earlier_n / earlier_total)
                    if earlier_total and recent_total
                    else None,
                }
            )
    lookup = {row.fuel_category: int(row.registration_count) for row in grouped.itertuples(index=False)}
    return {
        "fuel_year": fuel_year,
        "summary": {
            "totals": _records(grouped),
            "hhi": hhi(grouped["registration_share"]),
            "greendiesel_registrations": lookup.get("greendiesel", 0),
            "diesel_registrations": lookup.get("diesel", 0),
            "period_years": None if periods is None else {"earlier": periods[0], "recent": periods[1]},
            "period_comparison": comparison,
        },
    }


def _electric_hybrid(yearly: pd.DataFrame, overview: dict[str, Any], partial_years: list[int]) -> dict[str, Any]:
    annual = []
    for row in yearly.itertuples(index=False):
        annual.append(
            {
                "registration_year": int(row.registration_year),
                "is_partial_year": bool(row.is_partial_year),
                "electric_registrations": int(row.electric_registrations),
                "hybrid_registrations": int(row.hybrid_registrations),
                "electric_registration_share": _share(row.electric_registrations, row.registration_count),
                "hybrid_registration_share": _share(row.hybrid_registrations, row.registration_count),
            }
        )
    complete = [row for row in annual if not row["is_partial_year"]]
    first_electric = next((row["registration_year"] for row in complete if row["electric_registrations"] > 0), None)
    return {
        "electric_registrations": overview["electric_registrations"],
        "hybrid_registrations": overview["hybrid_registrations"],
        "hybrid_petrol_registrations": overview["hybrid_petrol_registrations"],
        "hybrid_diesel_registrations": overview["hybrid_diesel_registrations"],
        "partial_years": partial_years,
        "first_complete_year_with_electric": first_electric,
        "latest_complete_year": complete[-1]["registration_year"] if complete else None,
        "latest_complete_electric_share": complete[-1]["electric_registration_share"] if complete else None,
        "latest_complete_hybrid_share": complete[-1]["hybrid_registration_share"] if complete else None,
        "annual": annual,
    }


def _states(state_month: pd.DataFrame, complete_years: set[int], partial_years: list[int]) -> dict[str, Any]:
    grouped = (
        state_month.groupby("state_category", as_index=False)[["registration_count", "electric_registrations", "hybrid_registrations"]]
        .sum()
        .sort_values(["registration_count", "state_category"], ascending=[False, True])
    )
    total = float(grouped["registration_count"].sum())
    grouped["registration_share"] = grouped["registration_count"] / total
    grouped["electric_registration_share"] = grouped["electric_registrations"] / grouped["registration_count"]
    grouped["hybrid_registration_share"] = grouped["hybrid_registrations"] / grouped["registration_count"]
    geographic = grouped.loc[grouped["state_category"] != CHANNEL_STATE].copy()
    geographic_total = float(geographic["registration_count"].sum())
    if geographic_total:
        geographic["geographic_share"] = geographic["registration_count"] / geographic_total
    annual = state_month.groupby(["registration_year", "state_category"], as_index=False)["registration_count"].sum()
    year_totals = annual.groupby("registration_year")["registration_count"].sum()
    rakan = annual.loc[annual["state_category"] == CHANNEL_STATE].copy()
    rakan_share = []
    for row in rakan.itertuples(index=False):
        year = int(row.registration_year)
        rakan_share.append(
            {
                "registration_year": year,
                "is_partial_year": year in partial_years,
                "registrations": int(row.registration_count),
                "registration_share": float(row.registration_count) / float(year_totals.loc[row.registration_year]),
            }
        )
    rakan_share.sort(key=lambda item: item["registration_year"])
    complete_rakan = [item for item in rakan_share if item["registration_year"] in complete_years]
    return {
        "all_channels": _records(grouped),
        "geographic_offices": _records(geographic),
        "geographic_registration_count": int(geographic["registration_count"].sum()),
        "national_registration_count": int(grouped["registration_count"].sum()),
        "hhi_all_channels": hhi(grouped["registration_share"]),
        "hhi_geographic_offices": hhi(geographic["registration_count"]) if not geographic.empty else None,
        "rakan_niaga_registrations": int(grouped.loc[grouped["state_category"] == CHANNEL_STATE, "registration_count"].sum())
        if (grouped["state_category"] == CHANNEL_STATE).any()
        else 0,
        "rakan_niaga_share": float(grouped.loc[grouped["state_category"] == CHANNEL_STATE, "registration_share"].sum())
        if (grouped["state_category"] == CHANNEL_STATE).any()
        else 0.0,
        "rakan_niaga_by_year": rakan_share,
        "rakan_niaga_first_year": complete_rakan[0]["registration_year"] if complete_rakan else None,
        "rakan_niaga_latest_complete_share": complete_rakan[-1]["registration_share"] if complete_rakan else None,
    }


def _tests(
    monthly: pd.DataFrame,
    yearly: pd.DataFrame,
    fuel_year: pd.DataFrame,
    complete_years: set[int],
    low_months: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kw = kruskal_by_group(monthly["registration_count"], monthly["registration_month_number"])
    tests = [
        _pack(
            "calendar_month_volume",
            kw,
            research_question="Do recorded monthly registration volumes differ by calendar month?",
            null_hypothesis="The distribution of year-month registration counts is the same for every calendar month.",
            alternative_hypothesis="At least one calendar month has a different distribution.",
            variables="Response: registration count for one year-month. Factor: calendar month number.",
            test_name="Kruskal-Wallis",
            assumptions=(
                "Each observation is one year-month, not one registration transaction. "
                "The test does not assume a normal distribution. "
                "Year-months are treated as separate observations, although successive years are not fully independent. "
                "Low-volume months stay in this primary test."
            ),
            limitation=(
                "A difference between month distributions can reflect level changes across eras as well as a repeating within-year pattern. "
                "The year-normalized month shares are the descriptive check for a within-year pattern. "
                "This is not an anomaly-detection result."
            ),
        )
    ]
    without = monthly.loc[~monthly["registration_year_month"].isin({item["registration_year_month"] for item in low_months})]
    sensitivity = kruskal_by_group(without["registration_count"], without["registration_month_number"])
    tests.append(
        _pack(
            "calendar_month_volume_sensitivity",
            sensitivity,
            research_question="Does the calendar-month comparison change if the low-volume months are set aside?",
            null_hypothesis="The distribution of the remaining year-month counts is the same for every calendar month.",
            alternative_hypothesis="At least one calendar month still has a different distribution.",
            variables="Same as the primary calendar-month test, after removing months below 10% of the median monthly count.",
            test_name="Kruskal-Wallis sensitivity",
            assumptions="This is a sensitivity check. It is not in the Bonferroni family and it does not remove the months from the dataset.",
            limitation="Setting unusual months aside changes the question being asked. The primary result keeps those months.",
            primary=False,
        )
    )
    complete = yearly.loc[yearly["registration_year"].isin(complete_years)].copy()
    complete["electric_registration_share"] = complete["electric_registrations"] / complete["registration_count"]
    complete["hybrid_registration_share"] = complete["hybrid_registrations"] / complete["registration_count"]
    tests.append(
        _pack(
            "electric_share_trend",
            spearman_trend(complete["registration_year"], complete["electric_registration_share"]),
            research_question="Does the annual share of recorded registrations classified as electric change monotonically across complete years?",
            null_hypothesis="The Spearman rank correlation between year and annual electric registration share is zero.",
            alternative_hypothesis="The rank correlation is not zero.",
            variables="Paired observations are complete registration years. The share is electric registrations divided by that year's registrations.",
            test_name="Spearman rank correlation",
            assumptions="The correlation describes a monotonic association. Partial years are excluded. Years are ordered but are not a random sample from a larger population of years.",
            limitation="A rank correlation with year does not identify a cause. It does not estimate a future share.",
        )
    )
    tests.append(
        _pack(
            "hybrid_share_trend",
            spearman_trend(complete["registration_year"], complete["hybrid_registration_share"]),
            research_question="Does the annual share of recorded registrations classified as hybrid change monotonically across complete years?",
            null_hypothesis="The Spearman rank correlation between year and annual hybrid registration share is zero.",
            alternative_hypothesis="The rank correlation is not zero.",
            variables="Paired observations are complete registration years. Hybrid means hybrid_petrol or hybrid_diesel. Those fuel codes stay separate in the fuel tables.",
            test_name="Spearman rank correlation",
            assumptions="Same design as the electric-share correlation. A partial latest year is excluded.",
            limitation="A rank correlation with year does not identify a cause and is not a forecast.",
        )
    )
    volume_association = spearman_trend(complete["registration_count"], complete["electric_registration_share"])
    tests.append(
        _pack(
            "volume_and_electric_share",
            volume_association,
            research_question="Are annual registration volume and annual electric registration share associated across complete years?",
            null_hypothesis="The Spearman rank correlation between annual registration count and annual electric share is zero.",
            alternative_hypothesis="The rank correlation is not zero.",
            variables="Complete years only. Volume is the annual registration count. Electric share uses that same year's count as the denominator.",
            test_name="Spearman rank correlation",
            assumptions="Two-sided rank correlation. This association is not in the Bonferroni family because volume and electric share can move together through a shared time trend.",
            limitation="An association between volume and electric share is not evidence that one produces the other. Both can follow the same time order.",
            primary=False,
        )
    )
    periods = fuel_period_years(sorted(complete_years))
    if periods is None:
        fuel_result = {"applicable": False, "reason": "Two separated windows of three complete years are not available."}
        earlier_text = "unavailable"
        recent_text = "unavailable"
    else:
        fuel_result = chi_square_periods(fuel_year, list(periods[0]), list(periods[1]))
        earlier_text = _year_span(periods[0])
        recent_text = _year_span(periods[1])
    omitted = ", ".join(fuel_result.get("omitted_fuel_categories") or []) or "none"
    tests.append(
        _pack(
            "fuel_composition_periods",
            fuel_result,
            research_question=(
                f"Does the fuel-category composition of recorded registrations differ between {earlier_text} and {recent_text}?"
            ),
            null_hypothesis="Fuel category and period are independent in the included categories.",
            alternative_hypothesis="Fuel category and period are not independent.",
            variables=(
                "Counts of registration transactions in two windows of complete years. "
                "Each window is three years. The windows are 2017-2019 and the latest three complete years when both exist. "
                "2020 and 2021, which contain the low-volume months, are outside both windows. The partial latest year is outside both windows."
            ),
            test_name="Chi-square test of independence",
            assumptions=(
                "Expected counts must be at least 5. Categories that break that rule are omitted from the test and listed. "
                "They remain in the descriptive fuel table. No continuity correction is applied. "
                f"Omitted from the test: {omitted}."
            ),
            limitation=(
                "The sample size is a count of registration transactions, so a small composition difference can produce a very small p-value. "
                "Practical reading uses Cramér's V and the change in shares. "
                "The test does not say why the composition differs, and it does not merge the omitted fuel codes into another code."
            ),
        )
    )
    return tests


def _pack(
    test_id: str,
    result: dict[str, Any],
    *,
    research_question: str,
    null_hypothesis: str,
    alternative_hypothesis: str,
    variables: str,
    test_name: str,
    assumptions: str,
    limitation: str,
    primary: bool = True,
) -> dict[str, Any]:
    packed = {
        "id": test_id,
        "primary": primary,
        "research_question": research_question,
        "null_hypothesis": null_hypothesis,
        "alternative_hypothesis": alternative_hypothesis,
        "variables": variables,
        "test": test_name,
        "assumptions": assumptions,
        "limitation": limitation,
        "applicable": bool(result.get("applicable")),
        "reason": result.get("reason"),
        "statistic": result.get("statistic"),
        "p_value": result.get("p_value"),
        "sample_size": result.get("sample_size"),
        "effect_size_name": result.get("effect_size_name"),
        "effect_size": result.get("effect_size"),
        "effect_size_label": result.get("effect_size_label"),
        "confidence_interval": result.get("confidence_interval"),
        "groups": result.get("groups"),
        "degrees_of_freedom": result.get("degrees_of_freedom"),
        "included_fuel_categories": result.get("included_fuel_categories"),
        "omitted_fuel_categories": result.get("omitted_fuel_categories"),
        "share_of_period_registrations_included": result.get("share_of_period_registrations_included"),
        "earlier_years": result.get("earlier_years"),
        "recent_years": result.get("recent_years"),
    }
    return packed


def _attach_conclusions(tests: list[dict[str, Any]]) -> None:
    for test in tests:
        if not test["applicable"]:
            test["conclusion"] = "The test was not used. " + str(test.get("reason") or "Assumptions were not met.")
            test["interpretation"] = test["conclusion"]
            continue
        effect = test.get("effect_size_label") or "undefined"
        if test.get("in_bonferroni_family"):
            rejected = bool(test.get("null_rejected"))
            if rejected:
                test["conclusion"] = (
                    f"The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is {effect}."
                )
            else:
                test["conclusion"] = "The null hypothesis is not rejected at the Bonferroni-adjusted 5% level."
        else:
            p_value = test.get("p_value")
            if p_value is not None and p_value < ALPHA:
                test["conclusion"] = (
                    f"The unadjusted p-value is below 5%. This test is outside the Bonferroni family. The effect size is {effect}."
                )
            else:
                test["conclusion"] = "The unadjusted p-value is not below 5%. This test is outside the Bonferroni family."
        test["interpretation"] = (
            test["conclusion"]
            + " Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid."
        )


def _phase5_notes(
    overview: dict[str, Any],
    temporal: dict[str, Any],
    states: dict[str, Any],
    electric: dict[str, Any],
    tests: list[dict[str, Any]],
) -> list[str]:
    like = temporal["like_for_like"]
    month_test = next(test for test in tests if test["id"] == "calendar_month_volume")
    if month_test.get("applicable") and month_test.get("null_rejected") and month_test.get("effect_size_label") not in {"negligible", "undefined"}:
        month_note = (
            f"Calendar month is a candidate feature. The primary Kruskal-Wallis test rejects equal month distributions "
            f"and the effect size is {month_test.get('effect_size_label')}."
        )
    elif month_test.get("applicable") and month_test.get("null_rejected"):
        month_note = (
            "Calendar month shows a statistically detectable difference, but the effect size is negligible on the conventional benchmark. "
            "It is a weak candidate feature."
        )
    else:
        month_note = "Calendar month is not supported as a strong feature by the primary test."
    rakan_note = (
        "The national monthly count mixes geographic registration offices and the Rakan Niaga channel. "
        f"Rakan Niaga accounts for {_pct(states['rakan_niaga_share'])} of recorded registrations in the full series."
    )
    if states.get("rakan_niaga_first_year") and states.get("rakan_niaga_latest_complete_share") is not None:
        rakan_note += (
            f" Its share in {states['rakan_niaga_first_year']} and in the latest complete year should be read from the annual channel table "
            "before a later model treats the national series as one stable process."
        )
    return [
        (
            f"A candidate forecasting target is the monthly count of recorded registrations from {overview['minimum_date']} "
            f"through {overview['maximum_date']}. The grain is one month. The series includes every channel and the low-volume months."
        ),
        (
            f"{like['latest_year']} is observed through {like['through_month_name']} and is a partial year. "
            "A later model should not treat that year as a full year equal to the previous full year. "
            "This phase does not extend it to a full-year figure."
        ),
        month_note,
        rakan_note,
        (
            "A second candidate target is the monthly count of registrations classified as electric. "
            f"The first complete year with an electric registration in this snapshot is {electric['first_complete_year_with_electric']}. "
            "Early years are sparse. Electric share is a composition of recorded registrations, not a measure of consumer adoption."
        ),
        (
            "The rank correlations of electric share and hybrid share with year are exploratory. "
            "They do not mean a later model should use year as its main predictor of registration volume."
        ),
        (
            "Annual electric share, fuel-category share, and manufacturer share are not adopted as forecasting predictors. "
            "Any later use would need a time-ordered evaluation and a leakage check. "
            "An association with registration volume is not evidence that one series causes the other."
        ),
        "Low-volume months remain in the series. A later model has to decide how to treat them with that limitation stated, rather than dropping them silently.",
    ]


def _year_counts(frame: pd.DataFrame, year: int) -> dict[str, int]:
    subset = frame.loc[frame["registration_year"] == year]
    return {str(row.maker_clean): int(row.registration_count) for row in subset.groupby("maker_clean")["registration_count"].sum().reset_index().itertuples(index=False)}


def _period_counts(fuel_year: pd.DataFrame, years: list[int]) -> dict[str, int]:
    subset = fuel_year.loc[fuel_year["registration_year"].isin(years)]
    grouped = subset.groupby("fuel_category")["registration_count"].sum()
    return {str(key): int(value) for key, value in grouped.items()}


def _month_record(row: Any) -> dict[str, Any]:
    return {
        "registration_year_month": str(row.registration_year_month),
        "registration_count": int(row.registration_count),
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows = []
    for record in frame.to_dict(orient="records"):
        cleaned = {}
        for key, value in record.items():
            if value is None or (isinstance(value, float) and math.isnan(value)):
                cleaned[key] = None
            elif hasattr(value, "item") and not isinstance(value, (bytes, str)):
                cleaned[key] = value.item()
            else:
                cleaned[key] = value
        rows.append(cleaned)
    return rows


def _share(part: Any, whole: Any) -> float | None:
    if whole in (0, None) or pd.isna(whole):
        return None
    return float(part) / float(whole)


def _date_text(value: Any) -> str:
    return str(value)[:10]


def _month_name(month_number: int) -> str:
    names = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    if month_number < 1 or month_number > 12:
        return str(month_number)
    return names[month_number - 1]


def _year_span(years: list[int]) -> str:
    if not years:
        return "unavailable"
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}-{years[-1]}"


def _pct(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{value * 100:.1f}%"
