"""Build DuckDB views over Phase 2 Parquet and reconcile them to that layer.

The database stores view definitions. Registration rows stay in Parquet.
Python receives aggregate results only.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from src.config import (
    DATASET_ID,
    DUCKDB_PATH,
    PHASE2_REPORT_JSON,
    PHASE3_REPORT_JSON,
    PHASE3_REPORT_MD,
    PROCESSED_DIR,
    QUALITY_DIR,
    SQL_DIR,
    TRANSFORMATION_MAPPING_PATH,
)

logger = logging.getLogger(__name__)

PASS = "PASS"
FAIL = "FAIL"
SHARE_TOLERANCE = 1e-6
YOY_TOLERANCE = 1e-9

_VIEW_ROW_FIELDS = (
    ("monthly_rows", "monthly_view"),
    ("model_rows", "model_view"),
    ("manufacturer_month_rows", "manufacturer_month_view"),
    ("manufacturer_rows", "manufacturer_view"),
    ("state_rows", "state_view"),
    ("fuel_rows", "fuel_view"),
    ("type_rows", "vehicle_type_view"),
)


def build_database(
    *,
    processed_dir: Path | None = None,
    database_path: Path | None = None,
    sql_dir: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB file whose fact view reads the processed Parquet files."""
    source_dir = PROCESSED_DIR if processed_dir is None else processed_dir
    output = DUCKDB_PATH if database_path is None else database_path
    scripts = SQL_DIR if sql_dir is None else sql_dir
    parquet_glob = _processed_glob(source_dir)
    _reset_database(output)
    connection = duckdb.connect(str(output))
    connection.execute("SET enable_progress_bar = false")
    for path in _sql_files(scripts, "schema", "analytics"):
        sql = path.read_text(encoding="utf-8").replace("{{PROCESSED_GLOB}}", _sql_literal(parquet_glob))
        try:
            connection.execute(sql)
        except Exception as exc:
            connection.close()
            raise RuntimeError(f"{path.as_posix()} failed: {exc}") from exc
    return connection


def run_phase3(
    *,
    processed_dir: Path | None = None,
    database_path: Path | None = None,
    quality_dir: Path | None = None,
    sql_dir: Path | None = None,
    phase2_report_path: Path | None = None,
    mapping_path: Path | None = None,
) -> dict[str, Any]:
    """Rebuild the analytical views and write the Phase 3 reconciliation report."""
    source_dir = PROCESSED_DIR if processed_dir is None else processed_dir
    output = DUCKDB_PATH if database_path is None else database_path
    audit_dir = QUALITY_DIR if quality_dir is None else quality_dir
    scripts = SQL_DIR if sql_dir is None else sql_dir
    baseline_path = PHASE2_REPORT_JSON if phase2_report_path is None else phase2_report_path
    changes_path = TRANSFORMATION_MAPPING_PATH if mapping_path is None else mapping_path
    started = datetime.now().astimezone()
    build_started = datetime.now().astimezone()
    connection = build_database(processed_dir=source_dir, database_path=output, sql_dir=scripts)
    view_build_seconds = _elapsed(build_started)
    try:
        report = _reconcile(
            connection,
            processed_dir=source_dir,
            database_path=output,
            sql_dir=scripts,
            phase2_report=_read_json(baseline_path),
            mapping_rows=_read_mapping(changes_path),
            view_build_seconds=view_build_seconds,
            started=started,
        )
    finally:
        connection.close()
    _write_json(audit_dir / PHASE3_REPORT_JSON.name, report)
    _write_markdown(audit_dir / PHASE3_REPORT_MD.name, report)
    logger.info(
        "Phase 3 %s. Fact rows %s. Difference %s.",
        report["status"],
        report["phase3_fact_rows"],
        report["difference"],
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 for PASS and 1 for FAIL."""
    parser = argparse.ArgumentParser(
        prog="python -m src.analytical",
        description="Phase 3: build DuckDB analytical views from processed registration Parquet.",
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    report = run_phase3()
    return 0 if report["status"] == PASS else 1


def _reconcile(
    connection: duckdb.DuckDBPyConnection,
    *,
    processed_dir: Path,
    database_path: Path,
    sql_dir: Path,
    phase2_report: dict[str, Any],
    mapping_rows: list[dict[str, str]],
    view_build_seconds: float,
    started: datetime,
) -> dict[str, Any]:
    timings: list[dict[str, Any]] = []
    profile = _timed_query(connection, sql_dir / "validation" / "fact_profile.sql", "fact_profile", timings)
    dimensions = _timed_maps(connection, sql_dir / "validation" / "dimension_counts.sql", "dimension_counts", timings)
    consistency = _timed_query(
        connection, sql_dir / "validation" / "view_consistency.sql", "view_consistency", timings
    )
    years = _timed_rows(
        connection,
        """
        SELECT
            registration_year,
            is_partial_year,
            registration_count,
            prior_full_year_registrations,
            yoy_absolute_change,
            yoy_percentage_change,
            yoy_basis
        FROM analytics_year_registrations
        ORDER BY registration_year
        """,
        "year_registrations",
        timings,
    )
    like_for_like = _timed_query(
        connection,
        "SELECT * FROM analytics_like_for_like_year",
        "like_for_like_year",
        timings,
    )
    latest_month = _timed_query(
        connection,
        """
        SELECT registration_year_month, yoy_basis, yoy_absolute_change, yoy_percentage_change
        FROM analytics_monthly_registrations
        WHERE registration_year_month = (SELECT latest_year_month FROM dim_dataset_coverage)
        """,
        "latest_month_yoy",
        timings,
    )
    representative = _representative_queries(connection, timings)
    footer_rows, file_count = _parquet_footer_rows(processed_dir)
    direct_rows = _direct_parquet_count(connection, _processed_glob(processed_dir), timings)
    fact_columns = [row[0] for row in connection.execute("DESCRIBE fact_registrations").fetchall()]
    model_columns = [row[0] for row in connection.execute("DESCRIBE analytics_model_month").fetchall()]

    phase2_rows = int(phase2_report["processed_row_count"])
    fact_rows = int(profile["registration_count"])
    reconciliation_block = phase2_report["reconciliation"]
    checks: list[dict[str, Any]] = [
        _scalar_check("fact_row_count", phase2_rows, fact_rows, "Phase 3 fact rows against the Phase 2 processed row count."),
        _scalar_check("parquet_footer_row_count", footer_rows, fact_rows, "Fact rows against Parquet footer row counts. Footers do not load registration rows into Python."),
        _scalar_check("direct_parquet_row_count", direct_rows, fact_rows, "Fact view rows against a direct read_parquet count."),
        _equal_check(
            "date_minimum",
            phase2_report["date_range"]["minimum"],
            _as_date(profile["minimum_date_reg"]),
            "Minimum registration date.",
        ),
        _equal_check(
            "date_maximum",
            phase2_report["date_range"]["maximum"],
            _as_date(profile["maximum_date_reg"]),
            "Maximum registration date.",
        ),
        _map_check("year", reconciliation_block["by_year"], dimensions["year"], "Registration counts by year."),
        _map_check("month", reconciliation_block["by_month"], dimensions["month"], "Registration counts by year-month."),
        _map_check("fuel", reconciliation_block["by_fuel"], dimensions["fuel"], "Registration counts by fuel_category. Source fuel categories are not merged."),
        _map_check("state", reconciliation_block["by_state"], dimensions["state"], "Registration counts by state_category. Rakan Niaga stays its own category."),
        _map_check("vehicle_type", reconciliation_block["by_type"], dimensions["type"], "Registration counts by vehicle type."),
        _map_check("maker_source", reconciliation_block["by_maker"], dimensions["maker"], "Source maker counts. This is the Phase 2 maker field, before maker_clean."),
        _map_check(
            "maker_clean",
            _expected_maker_clean(reconciliation_block["by_maker"], mapping_rows),
            dimensions["maker_clean"],
            "maker_clean counts. Expected values apply the Phase 2 maker case mappings to the source maker counts.",
        ),
        _scalar_check("electric", int(phase2_report["electric_rows"]), int(profile["electric_registrations"]), "is_electric registrations against the Phase 2 electric total."),
        _scalar_check("electric_fuel_flag", int(profile["electric_fuel_registrations"]), int(profile["electric_registrations"]), "is_electric against rows whose fuel_category is electric."),
        _scalar_check("hybrid", int(phase2_report["hybrid_rows"]), int(profile["hybrid_registrations"]), "is_hybrid registrations against the Phase 2 hybrid total."),
        _scalar_check(
            "hybrid_fuel_composition",
            int(profile["hybrid_petrol_registrations"]) + int(profile["hybrid_diesel_registrations"]),
            int(profile["hybrid_registrations"]),
            "is_hybrid against hybrid_petrol plus hybrid_diesel. Those fuel categories stay separate.",
        ),
        _scalar_check("rakan_niaga", int(phase2_report["rakan_niaga_rows"]), int(profile["rakan_niaga_registrations"]), "is_rakan_niaga against the Phase 2 Rakan Niaga total."),
        _scalar_check("rakan_niaga_flag", int(profile["rakan_niaga_state_registrations"]), int(profile["rakan_niaga_registrations"]), "is_rakan_niaga against rows whose state_category is Rakan Niaga."),
        _scalar_check("null_required_fields", 0, int(profile["null_required_rows"]), "Nulls in the analytical fields required by the views."),
        _scalar_check("month_number_fields", 0, int(profile["month_number_mismatches"]), "Rows where registration_month differs from registration_month_number."),
    ]
    for field, name in _VIEW_ROW_FIELDS:
        checks.append(_scalar_check(name, fact_rows, int(consistency[field]), f"Sum of {name} registration_count against the fact row count."))
    checks.append(_scalar_check("model_groups", int(consistency["fact_model_groups"]), int(consistency["model_groups"]), "Model-month groups against distinct maker_clean, model_clean, and month on the fact."))
    checks.append(_scalar_check("monthly_groups", int(consistency["fact_months"]), int(consistency["monthly_groups"]), "Monthly view rows against distinct registration months."))
    checks.append(_share_check(consistency["max_manufacturer_share_gap"]))
    checks.append(_model_grain_check(model_columns))
    checks.append(_surrogate_check(fact_columns))
    checks.extend(_yoy_checks(years, like_for_like, latest_month, phase2_report))
    unexpected = dimensions.get("unexpected", {})
    checks.append(_scalar_check("dimension_grains", 0, sum(unexpected.values()), "Rows from an unrecognised grouping set."))

    status = FAIL if any(check["status"] == FAIL for check in checks) else PASS
    finished = datetime.now().astimezone()
    return {
        "dataset_id": DATASET_ID,
        "phase": 3,
        "status": status,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "phase2_rows": phase2_rows,
        "phase3_fact_rows": fact_rows,
        "difference": fact_rows - phase2_rows,
        "processed_parquet_files": file_count,
        "date_range": {
            "minimum": _as_date(profile["minimum_date_reg"]),
            "maximum": _as_date(profile["maximum_date_reg"]),
        },
        "models_with_multiple_manufacturers": int(consistency["models_with_multiple_makers"]),
        "like_for_like": _jsonable(like_for_like),
        "checks": checks,
        "performance": {
            "view_build_seconds": round(view_build_seconds, 3),
            "reconciliation_seconds": round(sum(item["seconds"] for item in timings), 3),
            "loaded_all_rows_into_python_memory": False,
            "queries": timings,
            "representative_results": representative,
        },
        "database": {
            "path": database_path.as_posix(),
            "gitignored": True,
            "fact_storage": "DuckDB view over Phase 2 Parquet",
            "rebuild": "python -m src.analytical",
        },
        "definitions": _definitions(),
        "limitations": _limitations(),
    }


def _yoy_checks(
    years: list[dict[str, Any]],
    like_for_like: dict[str, Any],
    latest_month: dict[str, Any],
    phase2_report: dict[str, Any],
) -> list[dict[str, Any]]:
    maximum = date.fromisoformat(phase2_report["date_range"]["maximum"])
    reported_partial = {int(item["year"]) for item in phase2_report["partial_years"]}
    sql_partial = {int(row["registration_year"]) for row in years if row["is_partial_year"]}
    checks = [
        _equal_check(
            "partial_years",
            sorted(reported_partial),
            sorted(sql_partial),
            "Partial years in the year view against the Phase 2 partial-year list.",
        )
    ]
    yoy_problems: list[str] = []
    for row in years:
        year = int(row["registration_year"])
        basis = row["yoy_basis"]
        if year in reported_partial:
            if basis != "withheld_partial_year" or row["yoy_absolute_change"] is not None or row["yoy_percentage_change"] is not None:
                yoy_problems.append(f"{year} full-year change was not withheld")
            continue
        if basis == "no_prior_year":
            if row["yoy_absolute_change"] is not None or row["yoy_percentage_change"] is not None:
                yoy_problems.append(f"{year} has a change without a prior year")
            continue
        if basis != "full_year":
            yoy_problems.append(f"{year} has yoy_basis {basis}")
            continue
        if row["prior_full_year_registrations"] is None or row["yoy_absolute_change"] is None or row["yoy_percentage_change"] is None:
            yoy_problems.append(f"{year} full-year comparison is incomplete")
            continue
        prior = int(row["prior_full_year_registrations"])
        change = int(row["registration_count"]) - prior
        if int(row["yoy_absolute_change"]) != change:
            yoy_problems.append(f"{year} absolute change is not current minus prior")
        if prior == 0:
            yoy_problems.append(f"{year} calculated a percentage from a zero prior year")
        elif abs(float(row["yoy_percentage_change"]) - (change / prior)) > YOY_TOLERANCE:
            yoy_problems.append(f"{year} percentage change does not match current minus prior, divided by prior")
    checks.append(
        _equal_check(
            "full_year_yoy",
            [],
            yoy_problems,
            "Full-year change is withheld for a partial latest year. Complete years use the previous calendar year. A zero prior year does not produce a percentage.",
        )
    )

    through_month = _through_month(maximum)
    by_month = {str(key): int(value) for key, value in phase2_report["reconciliation"]["by_month"].items()}
    latest_year = maximum.year
    expected_latest = _window_total(by_month, latest_year, through_month)
    expected_prior = _window_total(by_month, latest_year - 1, through_month)
    checks.append(_scalar_check("like_for_like_through_month", through_month, int(like_for_like["through_month"]), "Like-for-like window ends at the last complete month of the latest year."))
    checks.append(_scalar_check("like_for_like_latest", expected_latest, int(like_for_like["latest_period_registrations"]), "Latest like-for-like registrations against the same months in the Phase 2 month totals."))
    checks.append(_scalar_check("like_for_like_prior", expected_prior, int(like_for_like["prior_period_registrations"]), "Prior like-for-like registrations against the same months in the Phase 2 month totals."))
    label = str(like_for_like["comparison_label"])
    checks.append(
        _equal_check(
            "like_for_like_label",
            True,
            "not a full-year comparison" in label.lower(),
            "The like-for-like row states that it is not a full-year comparison.",
        )
    )
    if bool(like_for_like["latest_month_is_partial"]):
        latest_ok = latest_month["yoy_basis"] == "withheld_incomplete_month" and latest_month["yoy_percentage_change"] is None
    else:
        latest_ok = latest_month["yoy_basis"] != "withheld_incomplete_month"
    checks.append(
        _equal_check(
            "latest_month_yoy",
            True,
            latest_ok,
            "Month-level year-over-year change is withheld only when the latest observed month is incomplete.",
        )
    )
    return checks


def _representative_queries(
    connection: duckdb.DuckDBPyConnection,
    timings: list[dict[str, Any]],
) -> dict[str, Any]:
    monthly = _timed_query(
        connection,
        """
        SELECT
            count(*)::BIGINT AS months,
            sum(registration_count)::BIGINT AS registration_count,
            sum(electric_registrations)::BIGINT AS electric_registrations,
            sum(hybrid_registrations)::BIGINT AS hybrid_registrations
        FROM analytics_monthly_registrations
        """,
        "representative_monthly",
        timings,
    )
    manufacturers = _timed_rows(
        connection,
        """
        SELECT maker_clean, registration_count, registration_share
        FROM analytics_manufacturer
        ORDER BY registration_count DESC, maker_clean
        LIMIT 5
        """,
        "representative_manufacturers",
        timings,
    )
    return {
        "monthly": _jsonable(monthly),
        "largest_manufacturer_registration_counts": _jsonable(manufacturers),
    }


def _expected_maker_clean(by_maker: dict[str, Any], mapping_rows: list[dict[str, str]]) -> dict[str, int]:
    expected = {str(key): int(value) for key, value in by_maker.items()}
    for row in mapping_rows:
        if row["field"] != "maker":
            continue
        moved = int(row["row_count"])
        source = row["source_value"]
        clean = row["clean_value"]
        expected[source] = expected.get(source, 0) - moved
        expected[clean] = expected.get(clean, 0) + moved
    return {key: value for key, value in expected.items() if value != 0}


def _window_total(by_month: dict[str, int], year: int, through_month: int) -> int:
    if through_month < 1:
        return 0
    total = 0
    for month in range(1, through_month + 1):
        total += by_month.get(f"{year}-{month:02d}", 0)
    return total


def _through_month(maximum: date) -> int:
    last_day = calendar.monthrange(maximum.year, maximum.month)[1]
    if maximum.day < last_day:
        return maximum.month - 1
    return maximum.month


def _share_check(gap: Any) -> dict[str, Any]:
    value = None if gap is None else float(gap)
    passed = value is not None and abs(value) <= SHARE_TOLERANCE
    return {
        "name": "manufacturer_registration_share",
        "expected": 0,
        "actual": value,
        "difference": value,
        "status": PASS if passed else FAIL,
        "message": "Within each month, manufacturer registration shares sum to 1. Share is group registrations divided by all registrations in that month.",
    }


def _model_grain_check(columns: list[str]) -> dict[str, Any]:
    required = {"maker_clean", "model_clean", "registration_year_month", "registration_count"}
    missing = sorted(required - set(columns))
    return _equal_check("model_grain", [], missing, "Model analysis keeps maker_clean with model_clean.")


def _surrogate_check(columns: list[str]) -> dict[str, Any]:
    blocked = sorted(set(columns) & {"transaction_id", "jpj_transaction_id", "registration_id"})
    return _equal_check("surrogate_transaction_id", [], blocked, "The fact view has no invented JPJ transaction identifier.")


def _map_check(name: str, expected: dict[str, Any], actual: dict[str, int], message: str) -> dict[str, Any]:
    expected_counts = {str(key): int(value) for key, value in expected.items()}
    mismatches = []
    for key in sorted(set(expected_counts) | set(actual)):
        expected_value = expected_counts.get(key, 0)
        actual_value = int(actual.get(key, 0))
        if expected_value != actual_value:
            mismatches.append(
                {
                    "key": key,
                    "expected": expected_value,
                    "actual": actual_value,
                    "difference": actual_value - expected_value,
                }
            )
    expected_total = sum(expected_counts.values())
    actual_total = sum(actual.values())
    return {
        "name": name,
        "expected": expected_total,
        "actual": actual_total,
        "difference": actual_total - expected_total,
        "groups_expected": len(expected_counts),
        "groups_actual": len(actual),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:25],
        "status": PASS if not mismatches else FAIL,
        "message": message,
    }


def _scalar_check(name: str, expected: int, actual: int, message: str) -> dict[str, Any]:
    difference = int(actual) - int(expected)
    return {
        "name": name,
        "expected": int(expected),
        "actual": int(actual),
        "difference": difference,
        "status": PASS if difference == 0 else FAIL,
        "message": message,
    }


def _equal_check(name: str, expected: Any, actual: Any, message: str) -> dict[str, Any]:
    passed = expected == actual
    return {
        "name": name,
        "expected": expected,
        "actual": actual,
        "difference": 0 if passed else 1,
        "status": PASS if passed else FAIL,
        "message": message,
    }


def _timed_query(
    connection: duckdb.DuckDBPyConnection,
    sql: str | Path,
    name: str,
    timings: list[dict[str, Any]],
) -> dict[str, Any]:
    started = datetime.now().astimezone()
    text = sql.read_text(encoding="utf-8") if isinstance(sql, Path) else sql
    cursor = connection.execute(text)
    row = cursor.fetchone()
    columns = [item[0] for item in cursor.description]
    _record_timing(timings, name, started, 1)
    if row is None:
        raise RuntimeError(f"{name} returned no row")
    return dict(zip(columns, row))


def _timed_rows(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    name: str,
    timings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    started = datetime.now().astimezone()
    cursor = connection.execute(sql)
    columns = [item[0] for item in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    _record_timing(timings, name, started, len(rows))
    return rows


def _timed_maps(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    name: str,
    timings: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    started = datetime.now().astimezone()
    cursor = connection.execute(path.read_text(encoding="utf-8"))
    grouped: dict[str, dict[str, int]] = defaultdict(dict)
    count = 0
    for grain, key, registration_count in cursor.fetchall():
        count += 1
        grouped[str(grain)][str(key)] = int(registration_count)
    _record_timing(timings, name, started, count)
    return grouped


def _direct_parquet_count(
    connection: duckdb.DuckDBPyConnection,
    parquet_glob: str,
    timings: list[dict[str, Any]],
) -> int:
    started = datetime.now().astimezone()
    sql = (
        "SELECT count(*)::BIGINT FROM read_parquet("
        f"'{_sql_literal(parquet_glob)}', hive_partitioning = false, union_by_name = true)"
    )
    count = int(connection.execute(sql).fetchone()[0])
    _record_timing(timings, "direct_parquet_count", started, 1)
    return count


def _record_timing(timings: list[dict[str, Any]], name: str, started: datetime, rows_returned: int) -> None:
    timings.append(
        {
            "name": name,
            "seconds": round(_elapsed(started), 3),
            "rows_returned": rows_returned,
        }
    )


def _parquet_footer_rows(processed_dir: Path) -> tuple[int, int]:
    files = sorted((processed_dir / "registrations").glob("*/registrations.parquet"))
    total = 0
    for path in files:
        total += pq.ParquetFile(path).metadata.num_rows
    return total, len(files)


def _processed_glob(processed_dir: Path) -> str:
    files = sorted((processed_dir / "registrations").glob("*/registrations.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No processed Parquet files under {(processed_dir / 'registrations').as_posix()}"
        )
    return (processed_dir / "registrations" / "*" / "registrations.parquet").resolve().as_posix()


def _sql_files(sql_dir: Path, *groups: str) -> list[Path]:
    files: list[Path] = []
    for group in groups:
        found = sorted((sql_dir / group).glob("*.sql"))
        if not found:
            raise FileNotFoundError(f"No SQL files in {(sql_dir / group).as_posix()}")
        files.extend(found)
    return files


def _reset_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for candidate in (path, Path(str(path) + ".wal")):
        if candidate.exists():
            candidate.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_mapping(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_jsonable(payload), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Phase 3 reconciliation",
        "",
        f"Status: **{report['status']}**",
        "",
        "Phase 3 reads the processed Parquet files through DuckDB views. It does not copy registration rows into a database table, and it does not modify Phase 2.",
        "",
        "## Reconciliation",
        "",
        f"- Phase 2 rows: {report['phase2_rows']}",
        f"- Phase 3 fact rows: {report['phase3_fact_rows']}",
        f"- Difference: {report['difference']}",
        f"- Date range: {report['date_range']['minimum']} through {report['date_range']['maximum']}",
        "",
        "| Check | Expected | Actual | Difference | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {check['expected']} | {check['actual']} | {check['difference']} | {check['status']} |"
        )
    like = report["like_for_like"]
    lines.extend(
        [
            "",
            "## Like-for-like period",
            "",
            str(like["comparison_label"]),
            "",
            f"- Latest period registrations: {like['latest_period_registrations']}",
            f"- Prior period registrations: {like['prior_period_registrations']}",
            f"- Absolute change: {like['yoy_absolute_change']}",
            f"- Percentage change: {like['yoy_percentage_change']}",
            "",
            "## Performance",
            "",
            f"- View build seconds: {report['performance']['view_build_seconds']}",
            f"- Reconciliation seconds: {report['performance']['reconciliation_seconds']}",
            "- All registration rows loaded into Python memory: no",
            "",
            "## Limitations",
            "",
        ]
    )
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _definitions() -> dict[str, str]:
    return {
        "registration_transaction": "One row in the JPJ source. It is not a sale, a purchase, or a customer.",
        "electric": "is_electric is 1 when fuel is electric.",
        "hybrid": "is_hybrid is 1 when fuel is hybrid_petrol or hybrid_diesel. Those two categories remain separate.",
        "registration_share": "Registrations in a group divided by all recorded registrations in the same period.",
        "rakan_niaga": "A JPJ partner registration channel. It is not a geographic state.",
        "partial_year": "The latest year is partial when its maximum date_reg is before 31 December. Full-year change is withheld. The like-for-like view compares January through the last complete month.",
    }


def _limitations() -> list[str]:
    return [
        "Registration transactions are not vehicle sales, purchases, or a direct measure of demand.",
        "date_reg may differ from a purchase date.",
        "The latest year is partial when it ends before 31 December. Full-year change for that year is null.",
        "Rakan Niaga is not geographic state data and is not assigned to a state.",
        "Unknown, other, and the source fuel categories are retained. Fuel categories are not merged.",
        "Registration counts alone do not support a causal conclusion, including for months with unusually low counts.",
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return value
    if hasattr(value, "item") and callable(value.item):
        return _jsonable(value.item())
    return value


def _as_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _elapsed(started: datetime) -> float:
    return (datetime.now().astimezone() - started).total_seconds()
