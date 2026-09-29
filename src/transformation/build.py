"""Write one processed Parquet file per registration year.

Each official yearly file is read, extended, and written on its own. The raw
file is hashed before and after that work. Rows are not filtered or deduplicated.
A full in-memory concatenation of every year is avoided because that allocation
failed during Phase 1 reconnaissance.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.config import (
    CATALOGUE_URL,
    DATASET_ID,
    EXPECTED_COLUMNS,
    PHASE2_REPORT_JSON,
    PHASE2_REPORT_MD,
    PROCESSED_DIR,
    QUALITY_DIR,
    PROCESSED_METADATA_PATH,
    RAW_DIR,
    TRANSFORMATION_MAPPING_PATH,
    dataset_years,
    ensure_directories,
    parquet_filename,
)
from src.transformation.rules import (
    CHANNEL_STATE,
    DERIVED_COLUMNS,
    FIELD_DEFINITIONS,
    INTERNAL_COMBUSTION_OMISSION,
    AmbiguousMakerStandardisation,
    ValueChange,
    count_differences,
    count_map,
    invariant_violations,
    model_changes,
    standardise_makers,
    year_month_labels,
    transform_table,
)
from src.validation.validate import find_low_volume_months, sha256_file

logger = logging.getLogger(__name__)

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


def run_phase2(
    *,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
    quality_dir: Path | None = None,
    years: Iterable[int] | None = None,
    run_date: date | None = None,
) -> dict[str, Any]:
    """Build the processed layer and write the Phase 2 audit. Raw files are read only."""
    source_dir = RAW_DIR if raw_dir is None else raw_dir
    output_dir = PROCESSED_DIR if processed_dir is None else processed_dir
    audit_dir = quality_dir
    chosen_years = tuple(dataset_years() if years is None else years)
    observed_on = run_date or datetime.now(timezone.utc).date()
    started = time.perf_counter()
    started_at = _utcnow()
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)

    missing = [year for year in chosen_years if not (source_dir / parquet_filename(year)).exists()]
    if missing:
        report = _failed_report(
            f"Raw files are missing: {missing}. Phase 2 does not download or fabricate them.",
            started_at=started_at,
            elapsed_seconds=time.perf_counter() - started,
        )
        _write_reports(report, mapping=[], quality_dir=audit_dir)
        return report

    raw_hashes = {
        year: sha256_file(source_dir / parquet_filename(year)) for year in chosen_years
    }
    try:
        maker_counts = _maker_counts(source_dir, chosen_years)
        case_overrides, maker_audit = standardise_makers(maker_counts)
    except AmbiguousMakerStandardisation as exc:
        logger.error("%s", exc)
        report = _failed_report(
            str(exc),
            started_at=started_at,
            elapsed_seconds=time.perf_counter() - started,
            details={"ambiguous_maker_groups": exc.groups},
        )
        _write_reports(report, mapping=[], quality_dir=audit_dir)
        return report
    except (OSError, pa.ArrowException, TypeError, ValueError) as exc:
        logger.error("Maker standardisation failed: %s", exc)
        report = _failed_report(
            f"Maker standardisation failed: {exc}",
            started_at=started_at,
            elapsed_seconds=time.perf_counter() - started,
        )
        _write_reports(report, mapping=[], quality_dir=audit_dir)
        return report

    building = output_dir / "_building"
    if building.exists():
        shutil.rmtree(building)
    building.mkdir(parents=True)
    profiles: list[dict[str, Any]] = []
    model_audit: list[ValueChange] = []
    try:
        for year in chosen_years:
            year_started = time.perf_counter()
            profile, year_model_changes = _transform_year(
                year,
                source_dir / parquet_filename(year),
                building,
                case_overrides,
            )
            profile["seconds"] = round(time.perf_counter() - year_started, 3)
            profiles.append(profile)
            model_audit = _merge_changes(model_audit, year_model_changes)
            logger.info(
                "Processed %s rows=%s in %.2fs",
                year,
                profile["rows"],
                profile["seconds"],
            )
    except (OSError, pa.ArrowException, ValueError, RuntimeError) as exc:
        shutil.rmtree(building, ignore_errors=True)
        logger.error("Phase 2 stopped: %s", exc)
        report = _failed_report(
            str(exc),
            started_at=started_at,
            elapsed_seconds=time.perf_counter() - started,
        )
        _write_reports(report, mapping=[], quality_dir=audit_dir)
        return report

    hash_changes = [
        year
        for year in chosen_years
        if sha256_file(source_dir / parquet_filename(year)) != raw_hashes[year]
    ]
    if hash_changes:
        shutil.rmtree(building, ignore_errors=True)
        report = _failed_report(
            f"Raw files changed during Phase 2: {hash_changes}",
            started_at=started_at,
            elapsed_seconds=time.perf_counter() - started,
        )
        _write_reports(report, mapping=[], quality_dir=audit_dir)
        return report

    _publish(building, output_dir / "registrations")
    elapsed = time.perf_counter() - started
    report = _success_report(
        profiles=profiles,
        maker_audit=maker_audit,
        model_audit=model_audit,
        maker_counts=maker_counts,
        started_at=started_at,
        elapsed_seconds=elapsed,
        run_date=observed_on,
        raw_hashes=raw_hashes,
    )
    mapping = _sorted_changes([*maker_audit, *model_audit])
    _write_reports(report, mapping=mapping, quality_dir=audit_dir)
    if report["validation_status"] != FAIL:
        _write_metadata(report, output_dir)
    logger.info(
        "Phase 2 status=%s rows=%s seconds=%.2f",
        report["validation_status"],
        report["processed_row_count"],
        elapsed,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 for PASS or WARN, and 1 for FAIL."""
    parser = argparse.ArgumentParser(
        prog="python -m src.transformation",
        description="Phase 2: build the processed registration layer from immutable raw files.",
    )
    parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    report = run_phase2()
    return 0 if report["validation_status"] in {PASS, WARN} else 1


def _maker_counts(raw_dir: Path, years: tuple[int, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for year in years:
        column = pq.read_table(raw_dir / parquet_filename(year), columns=["maker"]).column("maker")
        if column.null_count:
            raise ValueError(f"cars_{year}.parquet has null maker values; Phase 2 does not impute them")
        counts.update(count_map(column))
    return dict(counts)


def _transform_year(
    year: int,
    source_path: Path,
    building: Path,
    case_overrides: dict[str, str],
) -> tuple[dict[str, Any], list[ValueChange]]:
    source = pq.read_table(source_path)
    if source.column("date_reg").null_count:
        raise ValueError(f"cars_{year}.parquet has null date_reg values; Phase 2 does not impute them")
    observed_years = {int(value) for value in pc.unique(pc.year(source.column("date_reg"))).to_pylist()}
    if observed_years != {year}:
        raise ValueError(
            f"cars_{year}.parquet contains date_reg years {sorted(observed_years)}. "
            "Rows were not moved or dropped."
        )

    processed = transform_table(source, case_overrides)
    violations = invariant_violations(source, processed)
    if violations:
        raise ValueError(f"cars_{year}.parquet failed derived-field checks: {violations}")

    raw_profile = _profile(source)
    processed_profile = _profile(processed)
    differences = {
        name: count_differences(raw_profile[name], processed_profile[name])
        for name in ("by_fuel", "by_maker", "by_state", "by_type", "by_month")
    }
    if raw_profile["rows"] != processed_profile["rows"] or any(differences.values()):
        raise ValueError(f"cars_{year}.parquet processed totals do not reconcile: {differences}")
    if raw_profile["min_date"] != processed_profile["min_date"] or raw_profile["max_date"] != processed_profile["max_date"]:
        raise ValueError(f"cars_{year}.parquet date range changed during transformation")

    destination = building / str(year) / "registrations.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".parquet.partial")
    processed = processed.replace_schema_metadata(
        {
            b"mai.phase": b"2",
            b"mai.registration_year": str(year).encode("ascii"),
            b"mai.source_rows": str(source.num_rows).encode("ascii"),
            b"mai.source_file": source_path.name.encode("utf-8"),
        }
    )
    pq.write_table(processed, partial)
    reread = pq.ParquetFile(partial).read()
    reread_profile = _profile(reread)
    if reread.num_rows != source.num_rows or count_differences(processed_profile["by_fuel"], reread_profile["by_fuel"]):
        partial.unlink(missing_ok=True)
        raise ValueError(f"Reread of processed {year} did not match the table written in memory")
    os.replace(partial, destination)

    year_model_changes = model_changes(count_map(source.column("model")))
    profile = {
        "year": year,
        "rows": source.num_rows,
        "min_date": raw_profile["min_date"],
        "max_date": raw_profile["max_date"],
        "by_fuel": raw_profile["by_fuel"],
        "by_maker": raw_profile["by_maker"],
        "by_state": raw_profile["by_state"],
        "by_type": raw_profile["by_type"],
        "by_month": raw_profile["by_month"],
        "electric_rows": int(pc.sum(processed.column("is_electric")).as_py() or 0),
        "hybrid_rows": int(pc.sum(processed.column("is_hybrid")).as_py() or 0),
        "rakan_niaga_rows": int(pc.sum(processed.column("is_rakan_niaga")).as_py() or 0),
        "unknown_model_rows": int(raw_profile["by_model"].get("Unknown", 0)),
        "unknown_fuel_rows": int(raw_profile["by_fuel"].get("unknown", 0)),
        "other_fuel_rows": int(raw_profile["by_fuel"].get("other", 0)),
        "output": str(destination),
    }
    return profile, year_model_changes


def _profile(table: pa.Table) -> dict[str, Any]:
    date_min, date_max = _date_bounds(table.column("date_reg"))
    return {
        "rows": table.num_rows,
        "min_date": date_min,
        "max_date": date_max,
        "by_fuel": count_map(table.column("fuel")),
        "by_maker": count_map(table.column("maker")),
        "by_state": count_map(table.column("state")),
        "by_type": count_map(table.column("type")),
        "by_model": count_map(table.column("model")),
        "by_month": count_map(year_month_labels(table.column("date_reg"))),
    }


def _success_report(
    *,
    profiles: list[dict[str, Any]],
    maker_audit: list[ValueChange],
    model_audit: list[ValueChange],
    maker_counts: dict[str, int],
    started_at: datetime,
    elapsed_seconds: float,
    run_date: date,
    raw_hashes: dict[int, str],
) -> dict[str, Any]:
    by_year = {str(profile["year"]): profile["rows"] for profile in profiles}
    by_month: Counter[str] = Counter()
    by_fuel: Counter[str] = Counter()
    by_maker: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    for profile in profiles:
        by_month.update(profile["by_month"])
        by_fuel.update(profile["by_fuel"])
        by_maker.update(profile["by_maker"])
        by_state.update(profile["by_state"])
        by_type.update(profile["by_type"])

    total_rows = sum(by_year.values())
    min_date = min(profile["min_date"] for profile in profiles)
    max_date = max(profile["max_date"] for profile in profiles)
    future_rows = sum(1 for profile in profiles if profile["max_date"] > run_date.isoformat())
    partial = _partial_latest_year(profiles)
    low_volume = find_low_volume_months(dict(by_month))
    electric_rows = sum(profile["electric_rows"] for profile in profiles)
    hybrid_rows = sum(profile["hybrid_rows"] for profile in profiles)
    rakan_rows = sum(profile["rakan_niaga_rows"] for profile in profiles)
    unknown_model_rows = sum(profile["unknown_model_rows"] for profile in profiles)
    unknown_fuel_rows = sum(profile["unknown_fuel_rows"] for profile in profiles)
    other_fuel_rows = sum(profile["other_fuel_rows"] for profile in profiles)
    raw_electric = int(by_fuel.get("electric", 0))
    raw_hybrid = int(by_fuel.get("hybrid_petrol", 0) + by_fuel.get("hybrid_diesel", 0))
    raw_rakan = int(by_state.get(CHANNEL_STATE, 0))

    checks = [
        _check("raw_files_unchanged", PASS, "Raw SHA-256 hashes were unchanged."),
        _check("row_count", PASS if total_rows > 0 else FAIL, f"Processed rows equal raw rows: {total_rows}."),
        _check(
            "source_columns_preserved",
            PASS,
            "date_reg, type, maker, model, colour, fuel, and state were copied unchanged.",
        ),
        _check(
            "reconciliation",
            PASS,
            "Year, month, fuel, maker, state, and vehicle-type totals match the raw files.",
        ),
        _check(
            "maker_standardisation",
            WARN if maker_audit else PASS,
            _change_message("maker", maker_audit),
            {"changes": [_change_dict(change) for change in maker_audit]},
        ),
        _check(
            "model_standardisation",
            WARN if model_audit else PASS,
            _change_message("model", model_audit),
            {"changes": [_change_dict(change) for change in model_audit]},
        ),
        _check(
            "fuel_classification",
            PASS,
            "fuel_category is an exact copy of fuel. No source fuel codes were merged.",
            {"categories": _sorted_counts(by_fuel)},
        ),
        _check(
            "electric_flag",
            PASS if electric_rows == raw_electric else FAIL,
            f"is_electric rows: {electric_rows}. Source fuel electric rows: {raw_electric}.",
        ),
        _check(
            "hybrid_flag",
            PASS if hybrid_rows == raw_hybrid else FAIL,
            f"is_hybrid rows: {hybrid_rows}. hybrid_petrol plus hybrid_diesel rows: {raw_hybrid}.",
        ),
        _check(
            "rakan_niaga_channel",
            PASS if rakan_rows == raw_rakan else FAIL,
            (
                f"Rakan Niaga remains a channel on {rakan_rows} rows. "
                "state_category was not assigned to a geographic state."
            ),
        ),
        _check(
            "date_features",
            PASS,
            "registration_year, month, quarter, and year-month were derived from date_reg on every row.",
        ),
        _check(
            "latest_year_retained",
            PASS if by_year.get(str(max(int(year) for year in by_year)), 0) > 0 else FAIL,
            f"Latest processed year {max(int(year) for year in by_year)} retains its raw rows.",
        ),
        _check(
            "unknown_values_retained",
            PASS,
            (
                f"Unknown model rows: {unknown_model_rows}. "
                f"fuel unknown: {unknown_fuel_rows}. fuel other: {other_fuel_rows}. None were removed or nulled."
            ),
        ),
        _check(
            "partial_latest_year",
            WARN if partial else PASS,
            partial["message"] if partial else "The latest registration year extends through 31 December.",
            partial or {},
        ),
        _check(
            "low_volume_months",
            WARN if low_volume["months"] else PASS,
            _low_volume_message(low_volume),
            low_volume,
        ),
        _check(
            "future_dates",
            WARN if future_rows else PASS,
            (
                f"{future_rows} yearly files contain a date_reg after {run_date.isoformat()}. Rows were kept."
                if future_rows
                else f"No processed file has date_reg after the run date {run_date.isoformat()}."
            ),
        ),
        _check(
            "internal_combustion_omitted",
            PASS,
            INTERNAL_COMBUSTION_OMISSION,
        ),
        _check(
            "duplicates_retained",
            PASS,
            "No registration transactions were deduplicated. Processed rows equal raw rows.",
        ),
    ]
    status = _overall(checks)
    return {
        "dataset_id": DATASET_ID,
        "catalogue_url": CATALOGUE_URL,
        "phase": 2,
        "validation_status": status,
        "complete": True,
        "run": {
            "started_at": _isoformat(started_at),
            "finished_at": _isoformat(_utcnow()),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "run_date": run_date.isoformat(),
        },
        "partitioning": {
            "layout": "data/processed/registrations/<year>/registrations.parquet",
            "reason": (
                "Each official file is already one registration year, and Phase 1 found no "
                "date_reg year outside its file. Writing one year at a time avoids a second "
                "in-memory copy of the full dataset. Concatenating every year previously "
                "failed with a memory allocation error. Year folders are plain directories "
                "rather than registration_year=<year> hive keys, because that key collides "
                "with the registration_year column stored in the file."
            ),
        },
        "raw_row_count": total_rows,
        "processed_row_count": total_rows,
        "date_range": {"minimum": min_date, "maximum": max_date},
        "reconciliation": {
            "match": True,
            "by_year": by_year,
            "by_month": _sorted_counts(by_month, by_key=True),
            "by_fuel": _sorted_counts(by_fuel),
            "by_maker": _sorted_counts(by_maker),
            "by_state": _sorted_counts(by_state),
            "by_type": _sorted_counts(by_type),
            "differences": [],
        },
        "maker_transformations": [_change_dict(change) for change in _sorted_changes(maker_audit)],
        "model_transformations": [_change_dict(change) for change in _sorted_changes(model_audit)],
        "maker_frequency_observed": len(maker_counts),
        "fuel_classification": _sorted_counts(by_fuel),
        "electric_rows": electric_rows,
        "hybrid_rows": hybrid_rows,
        "rakan_niaga_rows": rakan_rows,
        "unknown_model_rows": unknown_model_rows,
        "unknown_fuel_rows": unknown_fuel_rows,
        "other_fuel_rows": other_fuel_rows,
        "derived_field_definitions": list(FIELD_DEFINITIONS),
        "omitted_fields": [{"field": "is_internal_combustion", "reason": INTERNAL_COMBUSTION_OMISSION}],
        "partial_years": [partial] if partial else [],
        "low_volume_months": low_volume,
        "duplicate_policy": "Identical source rows are retained. There is no vehicle or transaction identifier.",
        "raw_sha256": {str(year): digest for year, digest in raw_hashes.items()},
        "files": [
            {
                "year": profile["year"],
                "rows": profile["rows"],
                "seconds": profile["seconds"],
                "minimum_date": profile["min_date"],
                "maximum_date": profile["max_date"],
                "output": f"registrations/{profile['year']}/registrations.parquet",
            }
            for profile in profiles
        ],
        "checks": checks,
        "warnings": [check for check in checks if check["status"] == WARN],
        "errors": [check for check in checks if check["status"] == FAIL],
        "limitations": [
            INTERNAL_COMBUSTION_OMISSION,
            "Rakan Niaga is a registration channel, not a geographic state.",
            "Low-volume months are observed registration periods. This dataset does not establish their cause.",
            "A latest year that ends before 31 December is partial. Earlier years that miss a single calendar day are not labelled partial.",
            "The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.",
        ],
    }


def _failed_report(
    message: str,
    *,
    started_at: datetime,
    elapsed_seconds: float,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure = _check("pipeline_stopped", FAIL, message, details or {})
    return {
        "dataset_id": DATASET_ID,
        "catalogue_url": CATALOGUE_URL,
        "phase": 2,
        "validation_status": FAIL,
        "complete": False,
        "run": {
            "started_at": _isoformat(started_at),
            "finished_at": _isoformat(_utcnow()),
            "elapsed_seconds": round(elapsed_seconds, 3),
        },
        "raw_row_count": None,
        "processed_row_count": None,
        "checks": [failure],
        "warnings": [],
        "errors": [failure],
        "limitations": [INTERNAL_COMBUSTION_OMISSION],
    }


def _partial_latest_year(profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest = max(profiles, key=lambda profile: profile["year"])
    maximum = date.fromisoformat(latest["max_date"])
    year_end = date(int(latest["year"]), 12, 31)
    if maximum < year_end:
        return {
            "year": int(latest["year"]),
            "minimum_date": latest["min_date"],
            "maximum_date": latest["max_date"],
            "message": (
                f"{latest['year']} is partial through {latest['max_date']}. "
                "Its rows were retained and it is not a complete calendar year."
            ),
        }
    return None


def _publish(building: Path, final: Path) -> None:
    previous = final.parent / "_previous"
    if previous.exists():
        shutil.rmtree(previous)
    if final.exists():
        final.rename(previous)
    building.rename(final)
    if previous.exists():
        shutil.rmtree(previous)


def _write_reports(
    report: dict[str, Any],
    *,
    mapping: list[ValueChange],
    quality_dir: Path | None,
) -> None:
    audit_dir = QUALITY_DIR if quality_dir is None else quality_dir
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / PHASE2_REPORT_JSON.name, report)
    (audit_dir / PHASE2_REPORT_MD.name).write_text(_render_markdown(report), encoding="utf-8")
    with (audit_dir / TRANSFORMATION_MAPPING_PATH.name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_value", "clean_value", "field", "reason", "row_count"],
        )
        writer.writeheader()
        for change in mapping:
            writer.writerow(
                {
                    "source_value": change.source_value,
                    "clean_value": change.clean_value,
                    "field": change.field,
                    "reason": change.reason,
                    "row_count": change.row_count,
                }
            )


def _write_metadata(report: dict[str, Any], processed_dir: Path) -> None:
    metadata = {
        "dataset_id": DATASET_ID,
        "phase": 2,
        "validation_status": report["validation_status"],
        "partitioning": report["partitioning"],
        "raw_row_count": report["raw_row_count"],
        "processed_row_count": report["processed_row_count"],
        "date_range": report["date_range"],
        "partial_years": report["partial_years"],
        "low_volume_months": report["low_volume_months"],
        "derived_field_definitions": report["derived_field_definitions"],
        "omitted_fields": report["omitted_fields"],
        "duplicate_policy": report["duplicate_policy"],
        "electric_rows": report["electric_rows"],
        "hybrid_rows": report["hybrid_rows"],
        "rakan_niaga_rows": report["rakan_niaga_rows"],
        "statement": (
            "The processed layer standardizes analytical representations while "
            "preserving the original JPJ source fields for traceability."
        ),
    }
    _write_json(processed_dir / PROCESSED_METADATA_PATH.name, metadata)


def _render_markdown(report: dict[str, Any]) -> str:
    if report["validation_status"] == FAIL and not report.get("complete", False):
        lines = [
            "# Phase 2 transformation report",
            "",
            f"Status: **{report['validation_status']}**",
            "",
            report["errors"][0]["message"],
            "",
        ]
        return "\n".join(lines)

    lines = [
        "# Phase 2 transformation report",
        "",
        f"Status: **{report['validation_status']}**",
        "",
        "The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.",
        "",
        "## Reconciliation",
        "",
        f"- Raw rows: {report['raw_row_count']}",
        f"- Processed rows: {report['processed_row_count']}",
        f"- Earliest date_reg: {report['date_range']['minimum']}",
        f"- Latest date_reg: {report['date_range']['maximum']}",
        f"- Elapsed seconds: {report['run']['elapsed_seconds']}",
        f"- Electric rows: {report['electric_rows']}",
        f"- Hybrid rows: {report['hybrid_rows']}",
        f"- Rakan Niaga rows: {report['rakan_niaga_rows']}",
        "",
        "## Partitioning",
        "",
        report["partitioning"]["layout"],
        "",
        report["partitioning"]["reason"],
        "",
        "## Maker transformations",
        "",
    ]
    lines.extend(_mapping_lines(report["maker_transformations"]))
    lines.extend(["", "## Model transformations", ""])
    lines.extend(_mapping_lines(report["model_transformations"]))
    lines.extend(["", "## Fuel categories", "", "Source fuel codes were not merged.", ""])
    lines.extend(_count_table(report["fuel_classification"]))
    lines.extend(["", "## Derived fields", ""])
    for definition in report["derived_field_definitions"]:
        lines.append(f"- `{definition['field']}`: {definition['definition']}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## Checks", ""])
    for check in report["checks"]:
        lines.append(f"- {check['status']} `{check['id']}`: {check['message']}")
    lines.append("")
    return "\n".join(lines)


def _mapping_lines(changes: list[dict[str, Any]]) -> list[str]:
    if not changes:
        return ["No values changed."]
    lines = ["| Source | Analytical value | Rows | Reason |", "| --- | --- | ---: | --- |"]
    for change in changes:
        source = str(change["source_value"]).replace("|", "\\|")
        clean = str(change["clean_value"]).replace("|", "\\|")
        reason = str(change["reason"]).replace("|", "\\|")
        lines.append(f"| `{source}` | `{clean}` | {change['row_count']} | {reason} |")
    return lines


def _count_table(counts: dict[str, int]) -> list[str]:
    lines = ["| Value | Registration transactions |", "| --- | ---: |"]
    for key, value in counts.items():
        lines.append(f"| {str(key).replace('|', '\\|')} | {value} |")
    return lines


def _change_message(field: str, changes: list[ValueChange]) -> str:
    if not changes:
        return f"No {field} values changed."
    preview = ", ".join(
        f"{change.source_value!r} -> {change.clean_value!r} ({change.row_count})"
        for change in _sorted_changes(changes)
    )
    return f"{field} analytical values differ for {sum(change.row_count for change in changes)} rows: {preview}."


def _change_dict(change: ValueChange) -> dict[str, Any]:
    return {
        "source_value": change.source_value,
        "clean_value": change.clean_value,
        "field": change.field,
        "reason": change.reason,
        "row_count": change.row_count,
    }


def _merge_changes(existing: list[ValueChange], new_changes: list[ValueChange]) -> list[ValueChange]:
    combined: dict[tuple[str, str, str], ValueChange] = {}
    for change in [*existing, *new_changes]:
        key = (change.field, change.source_value, change.clean_value)
        current = combined.get(key)
        if current is None:
            combined[key] = change
        else:
            combined[key] = ValueChange(
                field=change.field,
                source_value=change.source_value,
                clean_value=change.clean_value,
                row_count=current.row_count + change.row_count,
                reason=change.reason,
            )
    return list(combined.values())


def _sorted_changes(changes: Iterable[ValueChange]) -> list[ValueChange]:
    return sorted(changes, key=lambda change: (change.field, -change.row_count, change.source_value))


def _sorted_counts(counts: Counter[str] | dict[str, int], *, by_key: bool = False) -> dict[str, int]:
    items = list(counts.items())
    if by_key:
        items.sort(key=lambda item: item[0])
    else:
        items.sort(key=lambda item: (-item[1], str(item[0])))
    return {str(key): int(value) for key, value in items}


def _low_volume_message(low: dict[str, Any]) -> str:
    if not low["months"]:
        return "No month is below 10% of the median monthly registration count."
    listed = ", ".join(f"{month} ({count})" for month, count in low["months"].items())
    return (
        "Unusually low registration months were retained and not interpolated: "
        f"{listed}. The dataset does not establish the cause."
    )


def _check(check_id: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": check_id, "status": status, "message": message, "details": details or {}}


def _overall(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == FAIL for check in checks):
        return FAIL
    if any(check["status"] == WARN for check in checks):
        return WARN
    return PASS


def _date_bounds(column: pa.ChunkedArray) -> tuple[str, str]:
    minimum = pc.min(column).as_py()
    maximum = pc.max(column).as_py()
    return _as_date(minimum), _as_date(maximum)


def _as_date(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
