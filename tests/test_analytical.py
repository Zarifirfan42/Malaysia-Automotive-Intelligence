"""Phase 3 checks. Snapshot totals come from the Phase 2 report, not from literals here."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.analytical.build import build_database, run_phase3
from src.config import PHASE2_REPORT_JSON, PROCESSED_DIR, PROJECT_ROOT, SQL_DIR
from src.transformation.rules import transform_table
from tests.support import registration

_VIEW_NAMES = {
    "fact_registrations",
    "dim_dataset_coverage",
    "dim_registration_month",
    "analytics_monthly_registrations",
    "analytics_manufacturer_month",
    "analytics_model_month",
    "analytics_state_month",
    "analytics_fuel_month",
    "analytics_vehicle_type_month",
    "analytics_manufacturer",
    "analytics_year_registrations",
    "analytics_like_for_like_year",
}


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    processed = tmp_path_factory.mktemp("processed")
    database = tmp_path_factory.mktemp("analytical") / "registrations.duckdb"
    records = _records(31)
    _write_processed(processed, records)
    connection = build_database(processed_dir=processed, database_path=database)
    yield connection, records, processed
    connection.close()


def test_duckdb_database_is_created_from_processed_parquet(populated) -> None:
    connection, _, processed = populated
    assert any(processed.glob("registrations/*/registrations.parquet"))
    names = {row[0] for row in connection.execute("SELECT view_name FROM duckdb_views()").fetchall()}
    assert _VIEW_NAMES <= names


def test_processed_parquet_is_readable_through_the_fact_view(populated) -> None:
    connection, records, _ = populated
    assert connection.execute("SELECT count(*) FROM fact_registrations").fetchone()[0] == _row_count(records)
    august = connection.execute(
        """
        SELECT registration_month, registration_month_number, registration_month_name
        FROM fact_registrations
        WHERE registration_year_month = '2026-08'
        LIMIT 1
        """
    ).fetchone()
    assert august == (8, 8, "August")


def test_fact_row_count_matches_processed_rows(populated) -> None:
    connection, records, processed = populated
    footer = sum(pq.ParquetFile(path).metadata.num_rows for path in processed.glob("registrations/*/registrations.parquet"))
    fact = connection.execute("SELECT count(*) FROM fact_registrations").fetchone()[0]
    assert fact == footer == _row_count(records)


def test_year_totals_match_processed_rows(populated) -> None:
    connection, records, _ = populated
    assert dict(_pairs(connection, "analytics_year_registrations", "registration_year")) == _count_years(records)


def test_month_totals_match_processed_rows(populated) -> None:
    connection, records, _ = populated
    assert dict(_pairs(connection, "analytics_monthly_registrations", "registration_year_month")) == _count_months(records)


def test_manufacturer_totals_match_maker_clean(populated) -> None:
    connection, records, processed = populated
    glob = (processed / "registrations" / "*" / "registrations.parquet").as_posix()
    direct = connection.execute(
        f"""
        SELECT maker_clean, count(*)::BIGINT
        FROM read_parquet('{glob}', hive_partitioning = false, union_by_name = true)
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    view = connection.execute(
        "SELECT maker_clean, registration_count FROM analytics_manufacturer ORDER BY 1"
    ).fetchall()
    assert view == direct
    assert connection.execute("SELECT count(*) FROM fact_registrations WHERE maker = 'Bmw'").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM analytics_manufacturer WHERE maker_clean = 'Bmw'").fetchone()[0] == 0
    assert connection.execute(
        "SELECT registration_count FROM analytics_manufacturer WHERE maker_clean = 'BMW'"
    ).fetchone()[0] == 2
    assert sum(count for _, count in view) == _row_count(records)


def test_model_month_keeps_the_same_model_under_different_manufacturers(populated) -> None:
    connection, records, _ = populated
    rows = connection.execute(
        """
        SELECT maker_clean, registration_rank
        FROM analytics_model_month
        WHERE model_clean = 'Myvi' AND registration_year_month = '2024-01'
        ORDER BY maker_clean
        """
    ).fetchall()
    assert rows == [("Perodua", 1), ("Proton", 1)]
    fact_groups = connection.execute(
        """
        SELECT count(*) FROM (
            SELECT 1 FROM fact_registrations
            GROUP BY maker_clean, model_clean, registration_year_month
        )
        """
    ).fetchone()[0]
    view_groups, view_rows = connection.execute(
        "SELECT count(*), sum(registration_count) FROM analytics_model_month"
    ).fetchone()
    assert view_groups == fact_groups
    assert view_rows == _row_count(records)


def test_fuel_categories_are_not_merged(populated) -> None:
    connection, records, _ = populated
    assert dict(_pairs(connection, "analytics_fuel_month", "fuel_category")) == Counter(
        row["fuel"] for rows in records.values() for row in rows
    )
    present = {row[0] for row in connection.execute("SELECT DISTINCT fuel_category FROM analytics_fuel_month").fetchall()}
    assert {"greendiesel", "diesel", "hybrid_petrol", "hybrid_diesel", "electric"} <= present
    shares = connection.execute(
        """
        SELECT registration_share
        FROM analytics_fuel_month
        WHERE registration_year_month = '2024-06'
        ORDER BY fuel_category
        """
    ).fetchall()
    assert [share[0] for share in shares] == pytest.approx([0.5, 0.5])


def test_state_channel_keeps_rakan_niaga_separate(populated) -> None:
    connection, records, _ = populated
    assert dict(_pairs(connection, "analytics_state_month", "state_category")) == Counter(
        row["state"] for rows in records.values() for row in rows
    )
    rakan = connection.execute(
        """
        SELECT sum(registration_count)
        FROM analytics_state_month
        WHERE state_category = 'Rakan Niaga'
        """
    ).fetchone()[0]
    assert rakan == 2
    assert "Rakan Niaga" in {
        row[0] for row in connection.execute("SELECT DISTINCT state_category FROM analytics_state_month").fetchall()
    }


def test_vehicle_type_totals_match_processed_rows(populated) -> None:
    connection, records, _ = populated
    assert dict(_pairs(connection, "analytics_vehicle_type_month", "type")) == Counter(
        row["type"] for rows in records.values() for row in rows
    )


def test_electric_registrations_match_the_electric_flag(populated) -> None:
    connection, records, _ = populated
    expected = sum(row["fuel"] == "electric" for rows in records.values() for row in rows)
    flag, fuel, monthly = connection.execute(
        """
        SELECT
            (SELECT sum(is_electric) FROM fact_registrations),
            (SELECT count(*) FROM fact_registrations WHERE fuel_category = 'electric'),
            (SELECT sum(electric_registrations) FROM analytics_monthly_registrations)
        """
    ).fetchone()
    assert flag == fuel == monthly == expected


def test_hybrid_registrations_match_hybrid_fuel_categories(populated) -> None:
    connection, records, _ = populated
    expected = sum(row["fuel"] in {"hybrid_petrol", "hybrid_diesel"} for rows in records.values() for row in rows)
    flag, fuels = connection.execute(
        """
        SELECT
            sum(is_hybrid),
            sum(CASE WHEN fuel_category IN ('hybrid_petrol', 'hybrid_diesel') THEN 1 ELSE 0 END)
        FROM fact_registrations
        """
    ).fetchone()
    assert flag == fuels == expected
    assert connection.execute(
        "SELECT count(*) FROM analytics_fuel_month WHERE fuel_category = 'hybrid_petrol'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM analytics_fuel_month WHERE fuel_category = 'hybrid_diesel'"
    ).fetchone()[0] == 1


def test_rakan_niaga_registrations_match_the_channel_flag(populated) -> None:
    connection, _, _ = populated
    flag, state_rows = connection.execute(
        """
        SELECT
            sum(is_rakan_niaga),
            sum(CASE WHEN state_category = 'Rakan Niaga' THEN 1 ELSE 0 END)
        FROM fact_registrations
        """
    ).fetchone()
    assert flag == state_rows == 2


def test_required_analytical_fields_have_no_nulls(populated) -> None:
    connection, _, _ = populated
    profile = _query_file(connection, "validation/fact_profile.sql")
    assert profile["null_required_rows"] == 0
    assert profile["month_number_mismatches"] == 0


def test_full_year_yoy_is_withheld_for_a_partial_latest_year(populated) -> None:
    connection, _, _ = populated
    rows = {
        row[0]: row
        for row in connection.execute(
            """
            SELECT registration_year, yoy_basis, yoy_absolute_change, yoy_percentage_change, registration_count
            FROM analytics_year_registrations
            ORDER BY registration_year
            """
        ).fetchall()
    }
    assert rows[2024][1:] == ("no_prior_year", None, None, 5)
    assert rows[2025][1] == "full_year"
    assert rows[2025][2] == -1
    assert rows[2025][3] == pytest.approx(-0.2)
    assert rows[2026][1:] == ("withheld_partial_year", None, None, 4)
    year_sql = (SQL_DIR / "analytics" / "11_year_registrations.sql").read_text(encoding="utf-8")
    like_sql = (SQL_DIR / "analytics" / "12_like_for_like_year.sql").read_text(encoding="utf-8")
    assert "prior_year_registrations = 0 THEN NULL" in year_sql
    assert "prior.registration_count = 0 THEN NULL" in like_sql
    zero_prior = duckdb.connect().execute(
        """
        SELECT CASE
            WHEN prior_count IS NULL OR prior_count = 0 THEN NULL
            ELSE (current_count - prior_count)::DOUBLE / prior_count
        END
        FROM (SELECT 4 AS current_count, 0 AS prior_count)
        """
    ).fetchone()[0]
    assert zero_prior is None


def test_registration_share_is_the_period_total(populated) -> None:
    connection, _, _ = populated
    shares = connection.execute(
        """
        SELECT maker_clean, registration_count, registration_share
        FROM analytics_manufacturer_month
        WHERE registration_year_month = '2024-01'
        ORDER BY maker_clean
        """
    ).fetchall()
    assert [row[0] for row in shares] == ["Perodua", "Proton"]
    assert [row[1] for row in shares] == [1, 1]
    assert [row[2] for row in shares] == pytest.approx([0.5, 0.5])
    month_total = connection.execute(
        """
        SELECT sum(registration_share)
        FROM analytics_manufacturer_month
        WHERE registration_year_month = '2024-01'
        """
    ).fetchone()[0]
    assert month_total == pytest.approx(1)
    perodua_share = connection.execute(
        """
        SELECT registration_count::DOUBLE / sum(registration_count) OVER ()
        FROM analytics_manufacturer
        QUALIFY maker_clean = 'Perodua'
        """
    ).fetchone()[0]
    stored_share = connection.execute(
        "SELECT registration_share FROM analytics_manufacturer WHERE maker_clean = 'Perodua'"
    ).fetchone()[0]
    assert stored_share == pytest.approx(perodua_share)


def test_partial_latest_month_is_excluded_from_like_for_like_yoy(tmp_path) -> None:
    complete = _build(tmp_path / "complete", 31)
    label, through, latest, prior, basis = complete.execute(
        """
        SELECT comparison_label, through_month, latest_period_registrations,
               prior_period_registrations, yoy_basis
        FROM analytics_like_for_like_year
        """
    ).fetchone()
    assert through == 8
    assert latest == 4
    assert prior == 3
    assert basis == "partial_year_like_for_like"
    assert "January through August" in label
    assert "not a full-year comparison" in label
    complete.close()

    incomplete = _build(tmp_path / "incomplete", 15)
    through, latest, prior, basis = incomplete.execute(
        """
        SELECT through_month, latest_period_registrations, prior_period_registrations, yoy_basis
        FROM analytics_like_for_like_year
        """
    ).fetchone()
    assert through == 7
    assert latest == 2
    assert prior == 2
    assert basis == "partial_year_like_for_like"
    august = incomplete.execute(
        """
        SELECT yoy_basis, yoy_absolute_change, yoy_percentage_change, registration_count
        FROM analytics_monthly_registrations
        WHERE registration_year_month = '2026-08'
        """
    ).fetchone()
    assert august == ("withheld_incomplete_month", None, None, 2)
    january = incomplete.execute(
        """
        SELECT yoy_basis, yoy_absolute_change
        FROM analytics_monthly_registrations
        WHERE registration_year_month = '2026-01'
        """
    ).fetchone()
    assert january == ("same_month_prior_year", 0)
    retained = incomplete.execute(
        "SELECT count(*) FROM fact_registrations WHERE registration_year_month = '2026-08'"
    ).fetchone()[0]
    assert retained == 2
    incomplete.close()


def test_reconciliation_report_matches_a_phase2_baseline(tmp_path) -> None:
    processed = tmp_path / "processed"
    records = _records(31)
    _write_processed(processed, records)
    quality = tmp_path / "quality"
    quality.mkdir()
    baseline = _phase2_baseline(records)
    (quality / "phase2.json").write_text(json.dumps(baseline), encoding="utf-8")
    with (quality / "mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_value", "clean_value", "field", "reason", "row_count"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_value": "Bmw",
                "clean_value": "BMW",
                "field": "maker",
                "reason": "test mapping",
                "row_count": "1",
            }
        )
    report = run_phase3(
        processed_dir=processed,
        database_path=tmp_path / "registrations.duckdb",
        quality_dir=quality,
        phase2_report_path=quality / "phase2.json",
        mapping_path=quality / "mapping.csv",
    )
    assert report["status"] == "PASS"
    assert report["difference"] == 0
    assert report["phase3_fact_rows"] == _row_count(records)
    assert report["performance"]["loaded_all_rows_into_python_memory"] is False
    failed = [check["name"] for check in report["checks"] if check["status"] != "PASS"]
    assert failed == []


@pytest.mark.skipif(
    not (PROCESSED_DIR / "registrations" / "2026" / "registrations.parquet").exists()
    or not PHASE2_REPORT_JSON.exists(),
    reason="Processed Parquet and the Phase 2 report are required for snapshot reconciliation.",
)
def test_snapshot_reconciliation_matches_phase2() -> None:
    report = run_phase3()
    assert report["status"] == "PASS"
    assert report["difference"] == 0
    assert report["performance"]["loaded_all_rows_into_python_memory"] is False
    failed = [check["name"] for check in report["checks"] if check["status"] != "PASS"]
    assert failed == []
    assert "not a full-year comparison" in report["like_for_like"]["comparison_label"]


def _build(root: Path, august_day: int) -> duckdb.DuckDBPyConnection:
    processed = root / "processed"
    _write_processed(processed, _records(august_day))
    return build_database(processed_dir=processed, database_path=root / "registrations.duckdb")


def _write_processed(processed: Path, records: dict[int, list[dict[str, object]]]) -> None:
    for year, rows in records.items():
        source = pa.table(
            {
                "date_reg": pa.array([row["date_reg"] for row in rows], type=pa.timestamp("us")),
                "type": pa.array([row["type"] for row in rows], type=pa.large_string()),
                "maker": pa.array([row["maker"] for row in rows], type=pa.large_string()),
                "model": pa.array([row["model"] for row in rows], type=pa.large_string()),
                "colour": pa.array([row["colour"] for row in rows], type=pa.large_string()),
                "fuel": pa.array([row["fuel"] for row in rows], type=pa.large_string()),
                "state": pa.array([row["state"] for row in rows], type=pa.large_string()),
            }
        )
        destination = processed / "registrations" / str(year) / "registrations.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(transform_table(source, {"Bmw": "BMW"}), destination)


def _records(august_day: int) -> dict[int, list[dict[str, object]]]:
    return {
        2024: [
            registration(datetime(2024, 1, 10), maker="Perodua", model="Myvi"),
            registration(datetime(2024, 1, 20), maker="Proton", model="Myvi"),
            registration(datetime(2024, 6, 1), maker="Perodua", model="Alza", fuel="greendiesel", state="Johor"),
            registration(
                datetime(2024, 6, 2),
                maker="Isuzu",
                model="D-Max",
                fuel="diesel",
                state="Johor",
                vehicle_type="pick_up",
            ),
            registration(
                datetime(2024, 9, 1),
                maker="Tesla",
                model="Model Y",
                fuel="electric",
                state="Rakan Niaga",
                vehicle_type="jip",
            ),
        ],
        2025: [
            registration(datetime(2025, 1, 5), maker="Perodua", model="Myvi", state="Johor"),
            registration(datetime(2025, 1, 6), maker="Perodua", model="Myvi", fuel="hybrid_petrol", state="Johor"),
            registration(datetime(2025, 8, 15), maker="Honda", model="City"),
            registration(
                datetime(2025, 12, 20),
                maker="BMW",
                model="iX",
                fuel="electric",
                state="W.P. Kuala Lumpur",
                vehicle_type="jip",
            ),
        ],
        2026: [
            registration(datetime(2026, 1, 8), maker="Bmw", model="iX"),
            registration(datetime(2026, 1, 9), maker="Proton", model="Saga"),
            registration(
                datetime(2026, 8, 10),
                maker="Toyota",
                model="Hybrid",
                fuel="hybrid_diesel",
                vehicle_type="jip",
            ),
            registration(
                datetime(2026, 8, august_day),
                maker="Ora",
                model="Good Cat",
                fuel="electric",
                state="Rakan Niaga",
            ),
        ],
    }


def _phase2_baseline(records: dict[int, list[dict[str, object]]]) -> dict[str, object]:
    by_year: Counter[str] = Counter()
    by_month: Counter[str] = Counter()
    by_fuel: Counter[str] = Counter()
    by_maker: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    dates = []
    electric = hybrid = rakan = 0
    for rows in records.values():
        for row in rows:
            when = row["date_reg"]
            assert isinstance(when, datetime)
            dates.append(when.date())
            by_year[str(when.year)] += 1
            by_month[f"{when.year}-{when.month:02d}"] += 1
            by_fuel[str(row["fuel"])] += 1
            by_maker[str(row["maker"])] += 1
            by_state[str(row["state"])] += 1
            by_type[str(row["type"])] += 1
            electric += row["fuel"] == "electric"
            hybrid += row["fuel"] in {"hybrid_petrol", "hybrid_diesel"}
            rakan += row["state"] == "Rakan Niaga"
    latest = max(dates)
    return {
        "processed_row_count": _row_count(records),
        "date_range": {"minimum": min(dates).isoformat(), "maximum": latest.isoformat()},
        "partial_years": [{"year": latest.year, "maximum_date": latest.isoformat()}],
        "electric_rows": electric,
        "hybrid_rows": hybrid,
        "rakan_niaga_rows": rakan,
        "reconciliation": {
            "by_year": dict(by_year),
            "by_month": dict(by_month),
            "by_fuel": dict(by_fuel),
            "by_maker": dict(by_maker),
            "by_state": dict(by_state),
            "by_type": dict(by_type),
        },
    }


def _query_file(connection: duckdb.DuckDBPyConnection, relative: str) -> dict[str, object]:
    cursor = connection.execute((SQL_DIR / relative).read_text(encoding="utf-8"))
    row = cursor.fetchone()
    assert row is not None
    return dict(zip((item[0] for item in cursor.description), row))


def _pairs(connection: duckdb.DuckDBPyConnection, view: str, key: str) -> list[tuple[object, int]]:
    return connection.execute(
        f"SELECT {key}, sum(registration_count)::BIGINT FROM {view} GROUP BY 1"
    ).fetchall()


def _count_years(records: dict[int, list[dict[str, object]]]) -> dict[int, int]:
    return {year: len(rows) for year, rows in records.items()}


def _count_months(records: dict[int, list[dict[str, object]]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for rows in records.values():
        for row in rows:
            when = row["date_reg"]
            assert isinstance(when, datetime)
            counts[f"{when.year}-{when.month:02d}"] += 1
    return dict(counts)


def _row_count(records: dict[int, list[dict[str, object]]]) -> int:
    return sum(len(rows) for rows in records.values())


def test_sql_directory_is_inside_the_project() -> None:
    assert SQL_DIR == PROJECT_ROOT / "sql"
    assert (SQL_DIR / "schema" / "01_fact_registrations.sql").exists()
