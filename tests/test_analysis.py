"""Phase 4 tests. Snapshot totals come from the analytical layer, not from literals here."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analysis.analyze import analyze
from src.analysis.inference import chi_square_periods, cramers_v, epsilon_squared, kruskal_by_group
from src.analysis.metrics import hhi, top_share
from src.analysis.report import render_report
from src.config import DUCKDB_PATH, PHASE3_REPORT_JSON, SQL_DIR
from src.transformation.rules import CHANNEL_STATE


def test_hhi_is_one_over_n_for_equal_shares_and_one_for_a_single_group() -> None:
    assert hhi(pd.Series([1, 1, 1, 1])) == pytest.approx(0.25)
    assert hhi(pd.Series([5])) == pytest.approx(1)
    assert top_share(pd.Series([50, 30, 20]), 2) == pytest.approx(0.8)


def test_cramers_v_is_zero_for_independence_and_one_for_complete_association() -> None:
    assert cramers_v(0, 200, 2, 2) == pytest.approx(0)
    assert cramers_v(200, 200, 2, 2) == pytest.approx(1)


def test_epsilon_squared_is_large_when_groups_are_separated() -> None:
    values = pd.Series([1, 1, 1, 1, 100, 100, 100, 100])
    groups = pd.Series([1, 1, 1, 1, 2, 2, 2, 2])
    result = kruskal_by_group(values, groups)
    assert result["applicable"]
    assert result["effect_size"] == pytest.approx(epsilon_squared(result["statistic"], result["sample_size"]))
    assert result["effect_size_label"] == "large"


def test_chi_square_omits_a_sparse_fuel_and_keeps_the_rest() -> None:
    rows = []
    for year, petrol, electric in ((2017, 50, 5), (2024, 20, 40)):
        rows.append({"fuel_category": "petrol", "registration_year": year, "registration_count": petrol})
        rows.append({"fuel_category": "electric", "registration_year": year, "registration_count": electric})
        rows.append({"fuel_category": "hydrogen", "registration_year": year, "registration_count": 1})
    result = chi_square_periods(pd.DataFrame(rows), [2017], [2024])
    assert result["applicable"]
    assert "hydrogen" in result["omitted_fuel_categories"]
    assert "petrol" in result["included_fuel_categories"]
    assert "electric" in result["included_fuel_categories"]


def test_partial_year_full_comparison_is_withheld_and_channels_stay_split() -> None:
    analysis = analyze(_frames())
    partial = [row for row in analysis["temporal"]["yearly"] if row["is_partial_year"]]
    assert partial[0]["yoy_percentage_change"] is None
    assert partial[0]["yoy_basis"] == "withheld_partial_year"
    assert analysis["temporal"]["like_for_like"]["through_month"] == 8
    assert "not a full-year comparison" in analysis["temporal"]["like_for_like"]["comparison_label"]
    geographic = {row["state_category"] for row in analysis["state_channel"]["geographic_offices"]}
    assert CHANNEL_STATE not in geographic
    assert analysis["state_channel"]["geographic_registration_count"] < analysis["state_channel"]["national_registration_count"]
    pairs = {(row["maker_clean"], row["model_clean"]) for row in analysis["model"]["largest_pairs"]}
    assert pairs == {("Alpha", "Shared"), ("Beta", "Shared")}
    assert analysis["temporal"]["monthly_descriptive"]["n"] == len(_monthly())
    assert any(item["registration_year_month"] == "2024-04" for item in analysis["temporal"]["low_volume_months"])
    report = render_report(analysis, [])
    lowered = report.lower()
    assert "sales increased" not in lowered
    assert "consumers preferred" not in lowered
    assert "market adoption" not in lowered
    assert "confirmed anomaly" not in lowered
    assert "not a full-year comparison" in lowered
    assert "greendiesel" in lowered and "diesel" in lowered


def test_extract_queries_aggregate_before_python() -> None:
    for path in (SQL_DIR / "analysis").glob("*.sql"):
        text = path.read_text(encoding="utf-8").lower()
        assert "select *" not in text
        if "fact_registrations" in text:
            assert "count(" in text


@pytest.mark.skipif(not DUCKDB_PATH.exists() or not PHASE3_REPORT_JSON.exists(), reason="Phase 3 database is required.")
def test_phase4_matches_the_analytical_layer(tmp_path: Path) -> None:
    from src.analysis.build import run_phase4

    result = run_phase4(
        analysis_dir=tmp_path / "analysis",
        report_path=tmp_path / "phase4_report.md",
        figures_dir=tmp_path / "figures",
    )
    assert result["status"] in {"PASS", "WARN"}
    assert result["loaded_all_rows_into_python_memory"] is False
    assert result["largest_frame_rows"] < 500_000
    assert result["overview"]["registration_count"] == result["phase3_fact_rows"]
    report = (tmp_path / "phase4_report.md").read_text(encoding="utf-8").lower()
    assert "sales increased" not in report
    assert "not a full-year comparison" in report
    assert list((tmp_path / "figures").glob("*.png"))


def _frames() -> dict[str, pd.DataFrame]:
    monthly = _monthly()
    years = sorted(monthly["registration_year"].unique())
    yearly_rows = []
    for year in years:
        count = int(monthly.loc[monthly["registration_year"] == year, "registration_count"].sum())
        electric = int(monthly.loc[monthly["registration_year"] == year, "electric_registrations"].sum())
        hybrid = int(monthly.loc[monthly["registration_year"] == year, "hybrid_registrations"].sum())
        partial = year == 2026
        yearly_rows.append(
            {
                "registration_year": year,
                "is_partial_year": partial,
                "registration_count": count,
                "electric_registrations": electric,
                "hybrid_registrations": hybrid,
                "prior_full_year_registrations": None if partial or year == years[0] else count,
                "yoy_absolute_change": None if partial or year == years[0] else 0,
                "yoy_percentage_change": None if partial or year == years[0] else 0.0,
                "yoy_basis": "withheld_partial_year" if partial else ("no_prior_year" if year == years[0] else "full_year"),
            }
        )
    total = int(monthly["registration_count"].sum())
    electric_total = int(monthly["electric_registrations"].sum())
    hybrid_total = int(monthly["hybrid_registrations"].sum())
    return {
        "overview": pd.DataFrame(
            [
                {
                    "registration_count": total,
                    "minimum_date_reg": "2017-01-15",
                    "maximum_date_reg": "2026-08-31",
                    "registration_years": len(years),
                    "observed_months": len(monthly),
                    "manufacturers": 2,
                    "model_names": 1,
                    "fuel_categories": 5,
                    "vehicle_types": 2,
                    "state_channels": 2,
                    "electric_registrations": electric_total,
                    "hybrid_registrations": hybrid_total,
                    "hybrid_petrol_registrations": hybrid_total,
                    "hybrid_diesel_registrations": 0,
                }
            ]
        ),
        "manufacturer_model_pairs": pd.DataFrame([{"manufacturer_model_pairs": 2}]),
        "monthly": monthly,
        "yearly": pd.DataFrame(yearly_rows),
        "like_for_like": pd.DataFrame(
            [
                {
                    "latest_year": 2026,
                    "prior_year": 2025,
                    "through_month": 8,
                    "latest_year_is_partial": True,
                    "comparison_label": "January through August 2026 compared with January through August 2025. This is not a full-year comparison.",
                    "latest_period_registrations": 800,
                    "prior_period_registrations": 800,
                    "latest_period_electric_registrations": 80,
                    "prior_period_electric_registrations": 40,
                    "latest_period_hybrid_registrations": 40,
                    "prior_period_hybrid_registrations": 20,
                    "yoy_absolute_change": 0,
                    "yoy_percentage_change": 0.0,
                    "yoy_basis": "partial_year_like_for_like",
                }
            ]
        ),
        "manufacturer_month": _manufacturer_month(monthly),
        "model_year": pd.DataFrame(
            [
                {"maker_clean": "Alpha", "model_clean": "Shared", "registration_year": 2024, "registration_count": 10, "electric_registrations": 4, "hybrid_registrations": 1},
                {"maker_clean": "Beta", "model_clean": "Shared", "registration_year": 2024, "registration_count": 30, "electric_registrations": 1, "hybrid_registrations": 2},
            ]
        ),
        "state_month": _state_month(monthly),
        "fuel_month": _fuel_month(monthly),
        "type_month": _type_month(monthly),
    }


def _monthly() -> pd.DataFrame:
    names = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    rows = []
    for year in (2017, 2018, 2019, 2023, 2024, 2025):
        for month in range(1, 13):
            count = 1 if year == 2024 and month == 4 else 100
            electric = 0 if year < 2020 else 20
            hybrid = 0 if year < 2020 else 10
            if electric + hybrid > count:
                electric, hybrid = 0, 0
            rows.append(_month_row(year, month, names[month - 1], count, electric, hybrid))
    for month in range(1, 9):
        rows.append(_month_row(2026, month, names[month - 1], 100, 10, 5))
    return pd.DataFrame(rows)


def _month_row(year: int, month: int, name: str, count: int, electric: int, hybrid: int) -> dict[str, object]:
    return {
        "registration_year": year,
        "registration_month_number": month,
        "registration_month_name": name,
        "registration_quarter": (month - 1) // 3 + 1,
        "registration_year_month": f"{year}-{month:02d}",
        "registration_count": count,
        "electric_registrations": electric,
        "hybrid_registrations": hybrid,
        "electric_registration_share": electric / count,
        "hybrid_registration_share": hybrid / count,
    }


def _manufacturer_month(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in monthly.itertuples(index=False):
        for maker, share in (("Alpha", 0.4), ("Beta", 0.6)):
            rows.append(
                {
                    "maker_clean": maker,
                    "registration_year": row.registration_year,
                    "registration_month_number": row.registration_month_number,
                    "registration_year_month": row.registration_year_month,
                    "registration_count": row.registration_count * share,
                    "electric_registrations": row.electric_registrations * share,
                    "hybrid_registrations": row.hybrid_registrations * share,
                }
            )
    return pd.DataFrame(rows)


def _state_month(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in monthly.itertuples(index=False):
        rows.append(
            {
                "state_category": "Johor",
                "registration_year": row.registration_year,
                "registration_month_number": row.registration_month_number,
                "registration_year_month": row.registration_year_month,
                "registration_count": row.registration_count * 0.7,
                "electric_registrations": row.electric_registrations * 0.5,
                "hybrid_registrations": row.hybrid_registrations * 0.5,
            }
        )
        rows.append(
            {
                "state_category": CHANNEL_STATE,
                "registration_year": row.registration_year,
                "registration_month_number": row.registration_month_number,
                "registration_year_month": row.registration_year_month,
                "registration_count": row.registration_count * 0.3,
                "electric_registrations": row.electric_registrations * 0.5,
                "hybrid_registrations": row.hybrid_registrations * 0.5,
            }
        )
    return pd.DataFrame(rows)


def _fuel_month(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in monthly.itertuples(index=False):
        petrol = row.registration_count - row.electric_registrations - row.hybrid_registrations - 2
        rows.extend(
            [
                _fuel_row(row, "petrol", petrol),
                _fuel_row(row, "electric", row.electric_registrations),
                _fuel_row(row, "hybrid_petrol", row.hybrid_registrations),
                _fuel_row(row, "greendiesel", 1),
                _fuel_row(row, "diesel", 1),
            ]
        )
    rows.append(_fuel_row(monthly.iloc[0], "hydrogen", 1))
    return pd.DataFrame(rows)


def _fuel_row(row: object, fuel: str, count: float) -> dict[str, object]:
    return {
        "fuel_category": fuel,
        "registration_year": int(row.registration_year),
        "registration_month_number": int(row.registration_month_number),
        "registration_year_month": row.registration_year_month,
        "registration_count": count,
    }


def _type_month(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in monthly.itertuples(index=False):
        rows.append(
            {
                "type": "motokar",
                "registration_year": row.registration_year,
                "registration_month_number": row.registration_month_number,
                "registration_year_month": row.registration_year_month,
                "registration_count": row.registration_count * 0.8,
            }
        )
        rows.append(
            {
                "type": "jip",
                "registration_year": row.registration_year,
                "registration_month_number": row.registration_month_number,
                "registration_year_month": row.registration_year_month,
                "registration_count": row.registration_count * 0.2,
            }
        )
    return pd.DataFrame(rows)
