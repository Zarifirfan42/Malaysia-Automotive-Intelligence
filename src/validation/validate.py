"""Schema, quality, manifest, and reconciliation checks for the raw JPJ files.

This module reads data/raw and writes data/quality. It does not edit Parquet
files, delete duplicate rows, or start later-phase analytics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import (
    CATALOGUE_URL,
    COLUMN_ROLES,
    DATASET_ID,
    DATASET_NAME,
    EXPECTED_COLUMNS,
    EXPECTED_PHYSICAL_TYPES,
    LICENCE,
    LOW_VOLUME_MONTH_FRACTION,
    MANIFEST_PATH,
    PARQUET_URL_TEMPLATE,
    PUBLISHER,
    QUALITY_REPORT_JSON,
    QUALITY_REPORT_MD,
    RAW_DIR,
    YEAR_END,
    YEAR_START,
    dataset_years,
    ensure_directories,
)
from src.ingestion.download import DownloadError, DownloadResult, download_all

logger = logging.getLogger(__name__)

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

STRING_COLUMNS = tuple(column for column in EXPECTED_COLUMNS if column != "date_reg")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assess_schema(schema: pa.Schema) -> dict[str, Any]:
    """Compare a Parquet schema with the Phase 1 source contract."""
    names = list(schema.names)
    expected = list(EXPECTED_COLUMNS)
    missing = [column for column in expected if column not in names]
    unexpected = [column for column in names if column not in expected]
    physical = {field.name: str(field.type) for field in schema}
    type_problems: list[str] = []
    for column, expected_type in EXPECTED_PHYSICAL_TYPES.items():
        observed = physical.get(column)
        if observed is not None and observed != expected_type:
            type_problems.append(f"{column}: expected {expected_type}, found {observed}")

    problems: list[str] = []
    if missing:
        problems.append(f"missing columns: {missing}")
    if unexpected:
        problems.append(f"unexpected columns: {unexpected}")
    if not missing and not unexpected and names != expected:
        problems.append(f"column order is {names}, expected {expected}")
    problems.extend(type_problems)

    return {
        "status": FAIL if problems else PASS,
        "missing_columns": missing,
        "unexpected_columns": unexpected,
        "type_problems": type_problems,
        "column_order": names,
        "physical_types": physical,
        "nullable": {field.name: bool(field.nullable) for field in schema},
        "message": "; ".join(problems) if problems else "Schema matches the Phase 1 contract.",
    }


def metrics_from_frame(frame: pd.DataFrame, file_year: int) -> dict[str, Any]:
    """Measure one yearly frame. The frame is not modified and rows are not dropped."""
    row_count = int(len(frame))
    dates = pd.to_datetime(frame["date_reg"], errors="coerce")
    nulls = {column: int(frame[column].isna().sum()) for column in EXPECTED_COLUMNS}
    blanks = {column: _blank_count(frame[column]) for column in STRING_COLUMNS}

    valid_dates = dates.dropna()
    min_date = valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else None
    max_date = valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else None

    years = dates.dt.year
    mismatch = years.isna() | years.ne(file_year)
    breakdown: dict[str, int] = {}
    if bool(mismatch.any()):
        labelled = years.where(~years.isna(), other=-1).astype("int64").astype(str)
        labelled = labelled.where(~years.isna(), other="<null>")
        breakdown = {
            str(key): int(value)
            for key, value in labelled.loc[mismatch].value_counts().items()
        }

    by_month: dict[str, int] = {}
    distinct_dates: list[str] = []
    if not valid_dates.empty:
        by_month = {
            str(key): int(value)
            for key, value in valid_dates.dt.strftime("%Y-%m").value_counts().items()
        }
        distinct_dates = sorted(valid_dates.dt.strftime("%Y-%m-%d").unique().tolist())

    model_text = frame["model"]
    whitespace_models = _whitespace_model_counts(model_text)
    model_counts = _count_map(model_text)
    unknown_exact = int(model_counts.get("Unknown", 0))
    unknown_casefold = int(
        sum(count for label, count in model_counts.items() if label.casefold() == "unknown")
    )
    distinct_models = sorted(
        label for label in model_counts if label != "<null>"
    )

    duplicates = _duplicate_stats(frame)

    return {
        "year": int(file_year),
        "row_count": row_count,
        "nulls": nulls,
        "blanks": blanks,
        "min_date": min_date,
        "max_date": max_date,
        "year_mismatch_rows": int(mismatch.sum()),
        "year_mismatch_breakdown": breakdown,
        "by_fuel": _count_map(frame["fuel"]),
        "by_type": _count_map(frame["type"]),
        "by_state": _count_map(frame["state"]),
        "by_maker": _count_map(frame["maker"]),
        "by_month": by_month,
        "distinct_models": distinct_models,
        "unknown_model_rows": unknown_exact,
        "unknown_model_rows_casefold": unknown_casefold,
        "whitespace_models": whitespace_models,
        "distinct_dates": distinct_dates,
        "duplicates": duplicates,
    }


def casefold_collisions(counts: dict[str, int]) -> list[dict[str, Any]]:
    """Find labels that differ only by case or surrounding whitespace."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for label, count in counts.items():
        if label == "<null>":
            continue
        key = " ".join(str(label).casefold().split())
        groups.setdefault(key, []).append({"value": str(label), "rows": int(count)})
    collisions = []
    for key, variants in sorted(groups.items()):
        if len(variants) > 1:
            collisions.append(
                {
                    "key": key,
                    "variants": sorted(variants, key=lambda item: (-item["rows"], item["value"])),
                }
            )
    return collisions


def find_missing_months(month_counts: dict[str, int]) -> list[str]:
    """Return YYYY-MM values missing between the earliest and latest observed months."""
    if not month_counts:
        return []
    start = datetime.strptime(min(month_counts), "%Y-%m")
    end = datetime.strptime(max(month_counts), "%Y-%m")
    missing: list[str] = []
    cursor = start
    while cursor <= end:
        key = cursor.strftime("%Y-%m")
        if key not in month_counts:
            missing.append(key)
        cursor = _next_month(cursor)
    return missing


def find_missing_days(observed_days: Iterable[str], min_date: str | None, max_date: str | None) -> list[str]:
    """Return calendar days with no rows between the observed minimum and maximum dates."""
    if min_date is None or max_date is None:
        return []
    observed = set(observed_days)
    start = date.fromisoformat(min_date)
    end = date.fromisoformat(max_date)
    missing: list[str] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        if key not in observed:
            missing.append(key)
        cursor += timedelta(days=1)
    return missing


def find_low_volume_months(
    month_counts: dict[str, int],
    fraction: float = LOW_VOLUME_MONTH_FRACTION,
) -> dict[str, Any]:
    """Flag months below `fraction` of the median monthly row count."""
    if not month_counts:
        return {
            "fraction_of_median": fraction,
            "median_monthly_rows": None,
            "threshold": None,
            "months": {},
        }
    median = float(statistics.median(month_counts.values()))
    threshold = fraction * median
    flagged = {
        month: int(count)
        for month, count in sorted(month_counts.items())
        if count < threshold
    }
    return {
        "fraction_of_median": fraction,
        "median_monthly_rows": median,
        "threshold": threshold,
        "months": flagged,
    }


def build_quality_report(
    profiles: list[dict[str, Any]],
    *,
    started_at: str,
    finished_at: str,
    latest_expected_year: int = YEAR_END,
    extra_raw_files: list[str] | None = None,
) -> dict[str, Any]:
    """Turn yearly profiles into the Phase 1 quality report. No constants are imposed."""
    aggregated = _aggregate(profiles)
    checks = _build_checks(
        aggregated,
        latest_expected_year=latest_expected_year,
        extra_raw_files=extra_raw_files or [],
    )
    status = _overall(checks)
    report = {
        "dataset_identity": _identity(),
        "source": {
            "catalogue_url": CATALOGUE_URL,
            "file_url_template": PARQUET_URL_TEMPLATE,
            "configured_year_start": YEAR_START,
            "configured_year_end": YEAR_END,
            "years_profiled": sorted(profile["metrics"]["year"] for profile in profiles),
        },
        "run": {
            "started_at": started_at,
            "finished_at": finished_at,
            "phase": 1,
        },
        "validation_status": status,
        "files": [_file_summary(profile) for profile in profiles],
        "row_counts": {
            "total": aggregated["total_rows"],
            "by_year": aggregated["by_year"],
            "by_month": aggregated["by_month"],
            "by_fuel": aggregated["by_fuel"],
            "by_state": aggregated["by_state"],
            "by_maker": aggregated["by_maker"],
            "by_type": aggregated["by_type"],
        },
        "schema": {
            "expected_columns": list(EXPECTED_COLUMNS),
            "expected_physical_types": dict(EXPECTED_PHYSICAL_TYPES),
            "column_roles": dict(COLUMN_ROLES),
            "observed_by_file": [
                {
                    "year": profile["metrics"]["year"],
                    "column_names": profile["schema"]["column_order"],
                    "physical_types": profile["schema"]["physical_types"],
                    "status": profile["schema"]["status"],
                }
                for profile in profiles
            ],
        },
        "date_coverage": aggregated["date_coverage"],
        "null_profile": aggregated["nulls"],
        "blank_profile": aggregated["blanks"],
        "category_profile": {
            "fuel": list(aggregated["by_fuel"]),
            "type": list(aggregated["by_type"]),
            "state": list(aggregated["by_state"]),
            "maker_count": len(aggregated["by_maker"]),
            "model_count": aggregated["model_count"],
        },
        "duplicate_profile": aggregated["duplicates"],
        "known_observations": [check for check in checks if check["id"] in _OBSERVATION_IDS],
        "checks": checks,
        "warnings": [check for check in checks if check["status"] == WARN],
        "errors": [check for check in checks if check["status"] == FAIL],
    }
    return report


def build_manifest(profiles: list[dict[str, Any]], *, generated_at: str) -> dict[str, Any]:
    """Build the source manifest from measured file profiles."""
    return {
        "dataset_id": DATASET_ID,
        "dataset_name": DATASET_NAME,
        "catalogue_url": CATALOGUE_URL,
        "generated_at": generated_at,
        "complete": True,
        "files": [_manifest_record(profile) for profile in profiles],
    }


def run_phase1(*, force: bool = False) -> dict[str, Any]:
    """Download the official yearly files, validate them, and write the quality outputs."""
    ensure_directories()
    started = _utcnow()
    logger.info("Phase 1 acquisition starting for %s-%s", dataset_years()[0], dataset_years()[-1])
    downloads = download_all(force=force)
    return _validate_downloads(downloads, started_at=started)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 for PASS or WARN, and 1 for FAIL or a download error."""
    parser = argparse.ArgumentParser(
        prog="python -m src",
        description="Phase 1: download and validate JPJ car registration Parquet files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload a year even when a readable Parquet file is already present.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        report = run_phase1(force=args.force)
    except DownloadError as exc:
        logger.error("%s", exc)
        return 1
    status = report["validation_status"]
    logger.info("Phase 1 validation status: %s", status)
    logger.info("Manifest: %s", MANIFEST_PATH)
    logger.info("Quality report: %s", QUALITY_REPORT_JSON)
    return 0 if status in {PASS, WARN} else 1


def profile_downloaded_file(item: DownloadResult) -> dict[str, Any]:
    """Read one downloaded file and return its manifest fields plus quality metrics.

    The file hash is taken before and after the read. A change fails the profile.
    """
    path = item.local_path
    digest_before = sha256_file(path)
    schema = pq.read_schema(path)
    assessment = assess_schema(schema)
    if assessment["status"] == FAIL:
        raise SchemaValidationError(item.year, assessment)

    frame = pd.read_parquet(path)
    try:
        metrics = metrics_from_frame(frame, item.year)
    finally:
        del frame
    digest_after = sha256_file(path)
    if digest_before != digest_after:
        raise RawFileChangedError(path)

    downloaded_at = item.completed_at if item.acquisition == "downloaded" else item.file_mtime
    return {
        "year": item.year,
        "source_url": item.source_url,
        "local_filename": path.name,
        "local_path": str(path),
        "acquisition": item.acquisition,
        "download_timestamp": _isoformat(downloaded_at),
        "observed_at": _isoformat(item.completed_at),
        "file_size_bytes": item.file_size_bytes,
        "sha256": digest_before,
        "schema": assessment,
        "metrics": metrics,
        "raw_unchanged": True,
    }


class SchemaValidationError(Exception):
    """The Parquet schema does not match the Phase 1 contract."""

    def __init__(self, year: int, assessment: dict[str, Any]) -> None:
        self.year = year
        self.assessment = assessment
        super().__init__(f"Schema validation failed for cars_{year}.parquet: {assessment['message']}")


class RawFileChangedError(Exception):
    """A raw file hash changed while it was being read."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Raw file changed during validation: {path}")


def _validate_downloads(downloads: list[DownloadResult], *, started_at: datetime) -> dict[str, Any]:
    extra_raw_files = _unexpected_parquet_names({item.local_path.name for item in downloads})
    profiles: list[dict[str, Any]] = []
    for item in downloads:
        logger.info("Validating %s", item.local_path.name)
        try:
            profiles.append(profile_downloaded_file(item))
        except SchemaValidationError as exc:
            logger.error("%s", exc)
            return _write_stopped_report(
                str(exc),
                profiles,
                started_at=started_at,
                extra_raw_files=extra_raw_files,
                year=exc.year,
                assessment=exc.assessment,
            )
        except RawFileChangedError as exc:
            logger.error("%s", exc)
            return _write_stopped_report(
                str(exc),
                profiles,
                started_at=started_at,
                extra_raw_files=extra_raw_files,
            )
        except (OSError, pa.ArrowException, ValueError) as exc:
            logger.error("Unreadable Parquet for %s: %s", item.local_path.name, exc)
            return _write_stopped_report(
                f"Unreadable Parquet for {item.local_path.name}: {exc}",
                profiles,
                started_at=started_at,
                extra_raw_files=extra_raw_files,
                year=item.year,
            )
        logger.info(
            "Profiled %s rows=%s range=%s..%s",
            item.local_path.name,
            profiles[-1]["metrics"]["row_count"],
            profiles[-1]["metrics"]["min_date"],
            profiles[-1]["metrics"]["max_date"],
        )

    finished = _utcnow()
    report = build_quality_report(
        profiles,
        started_at=_isoformat(started_at),
        finished_at=_isoformat(finished),
        extra_raw_files=extra_raw_files,
    )
    manifest = build_manifest(profiles, generated_at=_isoformat(finished))
    _write_outputs(report, manifest)
    logger.info(
        "Validation complete status=%s rows=%s",
        report["validation_status"],
        report["row_counts"]["total"],
    )
    return report


def _write_stopped_report(
    message: str,
    profiles: list[dict[str, Any]],
    *,
    started_at: datetime,
    extra_raw_files: list[str],
    year: int | None = None,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finished = _isoformat(_utcnow())
    report = build_quality_report(
        profiles,
        started_at=_isoformat(started_at),
        finished_at=finished,
        extra_raw_files=extra_raw_files,
    )
    report["validation_status"] = FAIL
    report["complete"] = False
    report["errors"].append(
        {
            "id": "pipeline_stopped",
            "status": FAIL,
            "message": message,
            "details": {"year": year, "assessment": assessment},
        }
    )
    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_name": DATASET_NAME,
        "catalogue_url": CATALOGUE_URL,
        "generated_at": finished,
        "complete": False,
        "message": message,
        "files": [_manifest_record(profile) for profile in profiles],
    }
    _write_outputs(report, manifest)
    return report


def _write_outputs(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    ensure_directories()
    report.setdefault("complete", True)
    _write_json(QUALITY_REPORT_JSON, report)
    QUALITY_REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    _write_json(MANIFEST_PATH, manifest)


def render_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable view of the quality report."""
    identity = report["dataset_identity"]
    counts = report["row_counts"]
    coverage = report["date_coverage"]
    duplicates = report["duplicate_profile"]
    lines = [
        "# Phase 1 data-quality report",
        "",
        f"Status: **{report['validation_status']}**",
        "",
        "Figures in this report were calculated from the downloaded files during this run.",
        "",
        "## Dataset",
        "",
        f"- Project: {identity['project']}",
        f"- Dataset: {identity['dataset_name']}",
        f"- Dataset ID: {identity['dataset_id']}",
        f"- Publisher: {identity['publisher']}",
        f"- Catalogue: {identity['catalogue_url']}",
        f"- Licence: {identity['licence']}",
        f"- Started: {report['run']['started_at']}",
        f"- Finished: {report['run']['finished_at']}",
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {note}" for note in identity["interpretation"])
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Files profiled: {len(report['files'])}",
            f"- Total registration transactions: {counts['total']}",
            f"- Earliest date_reg: {coverage.get('min_date')}",
            f"- Latest date_reg: {coverage.get('max_date')}",
            f"- Observed months: {coverage.get('month_count')}",
            f"- Missing months inside the span: {len(coverage.get('missing_months', []))}",
            f"- Distinct dates: {coverage.get('distinct_dates')}",
            f"- Calendar days in the span with no rows: {coverage.get('missing_day_count')}",
            "",
            "## Rows by year",
            "",
        ]
    )
    lines.extend(_markdown_table(counts["by_year"]))
    lines.extend(["", "## Rows by fuel", ""])
    lines.extend(_markdown_table(counts["by_fuel"]))
    lines.extend(["", "## Rows by vehicle type", ""])
    lines.extend(_markdown_table(counts["by_type"]))
    lines.extend(["", "## Rows by state or channel", ""])
    lines.extend(_markdown_table(counts["by_state"]))
    lines.extend(
        [
            "",
            "## Duplicate signatures",
            "",
            duplicates.get("note", ""),
            "",
            f"- Distinct signatures: {duplicates.get('distinct_signatures')}",
            f"- Extra copies retained: {duplicates.get('extra_duplicate_rows')}",
            f"- Rows that share a signature: {duplicates.get('rows_in_duplicate_groups')}",
            f"- Largest identical signature: {duplicates.get('max_signature_frequency')}",
            "",
            "Full month and maker counts are in `data/quality/data_quality_report.json`.",
            "",
            "## Checks",
            "",
        ]
    )
    for check in report["checks"]:
        lines.append(f"- {check['status']} `{check['id']}`: {check['message']}")
    lines.append("")
    return "\n".join(lines)


def _identity() -> dict[str, Any]:
    return {
        "project": "Malaysia Automotive Intelligence",
        "dataset_id": DATASET_ID,
        "dataset_name": DATASET_NAME,
        "publisher": PUBLISHER,
        "catalogue_url": CATALOGUE_URL,
        "licence": LICENCE,
        "grain": "One row is one car registration transaction.",
        "interpretation": [
            "These are registration transactions, not vehicle sales, purchases, customers, or demand.",
            "date_reg is the registration date and may differ from a purchase date.",
            "Rakan Niaga is retained as a registration channel and is not treated as a geographic state.",
            "greendiesel remains a separate source fuel category.",
            "The latest yearly file may be a partial year.",
        ],
    }


def _aggregate(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    by_year: dict[str, int] = {}
    by_month: Counter[str] = Counter()
    by_fuel: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    by_maker: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    nulls: Counter[str] = Counter()
    blanks: Counter[str] = Counter()
    models: set[str] = set()
    days: set[str] = set()
    mismatch_rows = 0
    unknown_exact = 0
    unknown_casefold = 0
    whitespace: Counter[str] = Counter()
    rakan_by_year: dict[str, int] = {}
    greendiesel_by_year: dict[str, int] = {}
    distinct = 0
    extra = 0
    in_groups = 0
    max_frequency = 0
    duplicate_by_year: dict[str, Any] = {}
    min_date: str | None = None
    max_date: str | None = None
    raw_unchanged = True

    for profile in profiles:
        metrics = profile["metrics"]
        year = str(metrics["year"])
        total += metrics["row_count"]
        by_year[year] = metrics["row_count"]
        by_month.update(metrics["by_month"])
        by_fuel.update(metrics["by_fuel"])
        by_state.update(metrics["by_state"])
        by_maker.update(metrics["by_maker"])
        by_type.update(metrics["by_type"])
        nulls.update(metrics["nulls"])
        blanks.update(metrics["blanks"])
        models.update(metrics["distinct_models"])
        days.update(metrics["distinct_dates"])
        mismatch_rows += metrics["year_mismatch_rows"]
        unknown_exact += metrics["unknown_model_rows"]
        unknown_casefold += metrics["unknown_model_rows_casefold"]
        whitespace.update(metrics["whitespace_models"])
        rakan_by_year[year] = int(metrics["by_state"].get("Rakan Niaga", 0))
        greendiesel_by_year[year] = int(metrics["by_fuel"].get("greendiesel", 0))
        file_duplicates = metrics["duplicates"]
        distinct += file_duplicates["distinct_signatures"]
        extra += file_duplicates["extra_duplicate_rows"]
        in_groups += file_duplicates["rows_in_duplicate_groups"]
        max_frequency = max(max_frequency, file_duplicates["max_signature_frequency"])
        duplicate_by_year[year] = file_duplicates
        raw_unchanged = raw_unchanged and bool(profile.get("raw_unchanged", False))
        if metrics["min_date"] is not None:
            min_date = metrics["min_date"] if min_date is None else min(min_date, metrics["min_date"])
        if metrics["max_date"] is not None:
            max_date = metrics["max_date"] if max_date is None else max(max_date, metrics["max_date"])

    month_counts = _count_dict(by_month, by_key=True)
    missing_months = find_missing_months(month_counts)
    missing_days = find_missing_days(days, min_date, max_date)
    additive = mismatch_rows == 0
    return {
        "total_rows": total,
        "by_year": dict(sorted(by_year.items())),
        "by_month": month_counts,
        "by_fuel": _count_dict(by_fuel),
        "by_state": _count_dict(by_state),
        "by_maker": _count_dict(by_maker),
        "by_type": _count_dict(by_type),
        "nulls": {column: int(nulls.get(column, 0)) for column in EXPECTED_COLUMNS},
        "blanks": {column: int(blanks.get(column, 0)) for column in STRING_COLUMNS},
        "model_count": len(models),
        "mismatch_rows": mismatch_rows,
        "unknown_model_rows": unknown_exact,
        "unknown_model_rows_casefold": unknown_casefold,
        "whitespace_models": dict(sorted(whitespace.items(), key=lambda item: (-item[1], item[0]))),
        "rakan_niaga_rows": int(by_state.get("Rakan Niaga", 0)),
        "rakan_niaga_by_year": dict(sorted(rakan_by_year.items())),
        "greendiesel_rows": int(by_fuel.get("greendiesel", 0)),
        "greendiesel_by_year": dict(sorted(greendiesel_by_year.items())),
        "fuel_other_rows": int(by_fuel.get("other", 0)),
        "fuel_unknown_rows": int(by_fuel.get("unknown", 0)),
        "maker_collisions": casefold_collisions(dict(by_maker)),
        "raw_unchanged": raw_unchanged,
        "date_coverage": {
            "min_date": min_date,
            "max_date": max_date,
            "month_count": len(month_counts),
            "missing_months": missing_months,
            "distinct_dates": len(days),
            "missing_day_count": len(missing_days),
            "missing_days_sample": missing_days[:20],
        },
        "low_volume": find_low_volume_months(month_counts),
        "duplicates": {
            "distinct_signatures": distinct if additive else None,
            "extra_duplicate_rows": extra if additive else None,
            "rows_in_duplicate_groups": in_groups if additive else None,
            "max_signature_frequency": max_frequency if additive else None,
            "rows_were_deleted": False,
            "global_totals_are_additive": additive,
            "by_year": duplicate_by_year,
            "note": (
                "Identical source rows were counted and retained. There is no vehicle or "
                "transaction identifier, so matching rows are indistinguishable registration "
                "transactions rather than rows to delete. Yearly signature counts are added "
                "together because date_reg is part of the signature and each date_reg year "
                "matches its file year."
                if additive
                else "Yearly signature counts were not added. At least one date_reg year "
                "does not match its file year, so a signature could repeat across files."
            ),
        },
    }


_OBSERVATION_IDS = {
    "rakan_niaga",
    "greendiesel",
    "unknown_model",
    "residual_fuel_codes",
    "model_whitespace",
    "maker_spelling",
    "partial_latest_year",
    "missing_days",
    "low_volume_months",
    "duplicates",
}


def _build_checks(
    aggregated: dict[str, Any],
    *,
    latest_expected_year: int,
    extra_raw_files: list[str],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    total = aggregated["total_rows"]

    def add(check_id: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
        checks.append(
            {
                "id": check_id,
                "status": status,
                "message": message,
                "details": details or {},
            }
        )

    add(
        "positive_row_count",
        PASS if total > 0 else FAIL,
        f"Profiled registration transactions: {total}.",
    )
    add(
        "raw_files_unchanged",
        PASS if aggregated["raw_unchanged"] else FAIL,
        "Raw Parquet hashes were unchanged by validation."
        if aggregated["raw_unchanged"]
        else "A raw Parquet hash changed during validation.",
    )
    add(
        "nulls",
        PASS if sum(aggregated["nulls"].values()) == 0 else WARN,
        "Null counts by column are recorded in null_profile.",
        aggregated["nulls"],
    )
    add(
        "blanks",
        PASS if sum(aggregated["blanks"].values()) == 0 else WARN,
        "Blank-string counts by column are recorded in blank_profile.",
        aggregated["blanks"],
    )
    add(
        "year_consistency",
        PASS if aggregated["mismatch_rows"] == 0 else FAIL,
        f"Rows whose date_reg year differs from the file year: {aggregated['mismatch_rows']}.",
    )
    missing_months = aggregated["date_coverage"]["missing_months"]
    add(
        "missing_months",
        PASS if not missing_months else FAIL,
        "No calendar month is missing between the first and last observed month."
        if not missing_months
        else f"Missing months inside the observed span: {missing_months}.",
        {"missing_months": missing_months},
    )
    recon_ok = _reconciliation_ok(aggregated)
    add(
        "category_reconciliation",
        PASS if recon_ok else FAIL,
        "Fuel, type, state, maker, and year counts each sum to the profiled row total."
        if recon_ok
        else "A category total does not reconcile to the profiled row total.",
    )
    duplicates = aggregated["duplicates"]
    per_file_duplicates_ok = all(
        item["distinct_signatures"] + item["extra_duplicate_rows"] == aggregated["by_year"][year]
        for year, item in duplicates["by_year"].items()
    )
    global_duplicates_ok = (
        duplicates["global_totals_are_additive"]
        and duplicates["distinct_signatures"] + duplicates["extra_duplicate_rows"] == total
    )
    duplicate_ok = per_file_duplicates_ok and (
        global_duplicates_ok or not duplicates["global_totals_are_additive"]
    )
    add(
        "duplicates",
        PASS if duplicate_ok else FAIL,
        duplicates["note"],
        {
            "distinct_signatures": duplicates["distinct_signatures"],
            "extra_duplicate_rows": duplicates["extra_duplicate_rows"],
            "rows_in_duplicate_groups": duplicates["rows_in_duplicate_groups"],
            "max_signature_frequency": duplicates["max_signature_frequency"],
            "rows_were_deleted": False,
        },
    )

    coverage = aggregated["date_coverage"]
    partial = _partial_year(coverage.get("max_date"), latest_expected_year)
    add(
        "partial_latest_year",
        WARN if partial else PASS,
        partial["message"] if partial else f"{latest_expected_year} covers through 31 December.",
        partial or {},
    )
    low = aggregated["low_volume"]
    add(
        "low_volume_months",
        WARN if low["months"] else PASS,
        _low_volume_message(low),
        low,
    )
    add(
        "missing_days",
        PASS,
        (
            f"{coverage['missing_day_count']} calendar days between {coverage['min_date']} and "
            f"{coverage['max_date']} have no registration rows. Weekend and holiday gaps are "
            "expected and are not treated as missing files."
        ),
        {
            "missing_day_count": coverage["missing_day_count"],
            "sample": coverage["missing_days_sample"],
        },
    )
    rakan = aggregated["rakan_niaga_rows"]
    add(
        "rakan_niaga",
        PASS if rakan > 0 else WARN,
        (
            f"Rakan Niaga accounts for {rakan} registration transactions and is retained as a "
            "channel, not a geographic state."
            if rakan
            else "Rakan Niaga was not present in state. The channel code was not imputed."
        ),
        {"rows": rakan, "by_year": aggregated["rakan_niaga_by_year"]},
    )
    green = aggregated["greendiesel_rows"]
    add(
        "greendiesel",
        PASS if green > 0 else WARN,
        (
            f"greendiesel accounts for {green} registration transactions and is retained as its own fuel code."
            if green
            else "greendiesel was not present. It was not created or merged into diesel."
        ),
        {"rows": green, "by_year": aggregated["greendiesel_by_year"]},
    )
    whitespace = aggregated["whitespace_models"]
    add(
        "model_whitespace",
        WARN if whitespace else PASS,
        f"Model values with surrounding whitespace: {sum(whitespace.values())} rows."
        if whitespace
        else "No model values have surrounding whitespace.",
        {"values": whitespace},
    )
    collisions = aggregated["maker_collisions"]
    add(
        "maker_spelling",
        WARN if collisions else PASS,
        "Maker labels that collide after case-folding are reported and were not merged."
        if collisions
        else "No maker labels collide after case-folding.",
        {"collisions": collisions},
    )
    unknown_model = aggregated["unknown_model_rows_casefold"]
    add(
        "unknown_model",
        WARN if unknown_model else PASS,
        f"Model values case-folding to 'unknown': {unknown_model} rows. They were not removed.",
        {
            "unknown_exact": aggregated["unknown_model_rows"],
            "unknown_casefold": unknown_model,
        },
    )
    residual = aggregated["fuel_other_rows"] + aggregated["fuel_unknown_rows"]
    add(
        "residual_fuel_codes",
        WARN if residual else PASS,
        (
            f"Fuel code other={aggregated['fuel_other_rows']}, unknown={aggregated['fuel_unknown_rows']}. "
            "These source codes were retained."
        ),
        {
            "other": aggregated["fuel_other_rows"],
            "unknown": aggregated["fuel_unknown_rows"],
        },
    )
    add(
        "unexpected_raw_files",
        WARN if extra_raw_files else PASS,
        "No unexpected Parquet files were found in data/raw."
        if not extra_raw_files
        else f"Unexpected Parquet files were ignored: {extra_raw_files}.",
        {"files": extra_raw_files},
    )
    return checks


def _reconciliation_ok(aggregated: dict[str, Any]) -> bool:
    total = aggregated["total_rows"]
    if total == 0:
        return False
    sums = [
        sum(aggregated["by_year"].values()),
        sum(aggregated["by_fuel"].values()),
        sum(aggregated["by_type"].values()),
        sum(aggregated["by_state"].values()),
        sum(aggregated["by_maker"].values()),
        sum(aggregated["by_month"].values()) + aggregated["nulls"]["date_reg"],
    ]
    return all(value == total for value in sums)


def _partial_year(max_date: str | None, latest_expected_year: int) -> dict[str, Any] | None:
    if max_date is None:
        return {
            "year": latest_expected_year,
            "max_date": None,
            "message": f"No date_reg values were available for {latest_expected_year}.",
        }
    observed = date.fromisoformat(max_date)
    year_end = date(latest_expected_year, 12, 31)
    if observed < year_end:
        return {
            "year": latest_expected_year,
            "max_date": max_date,
            "message": (
                f"The latest date_reg is {max_date}. {latest_expected_year} is a partial year "
                "and is not treated as a full calendar year."
            ),
        }
    return None


def _low_volume_message(low: dict[str, Any]) -> str:
    if not low["months"]:
        return (
            "No month is below "
            f"{low['fraction_of_median']:.0%} of the median monthly row count."
        )
    listed = ", ".join(f"{month} ({count})" for month, count in low["months"].items())
    return (
        "Months below "
        f"{low['fraction_of_median']:.0%} of the median monthly count "
        f"({low['threshold']:.1f}): {listed}."
    )


def _duplicate_stats(frame: pd.DataFrame) -> dict[str, int]:
    row_count = int(len(frame))
    if row_count == 0:
        return {
            "distinct_signatures": 0,
            "extra_duplicate_rows": 0,
            "rows_in_duplicate_groups": 0,
            "max_signature_frequency": 0,
        }
    sizes = frame.groupby(list(EXPECTED_COLUMNS), sort=False, dropna=False).size()
    distinct = int(sizes.shape[0])
    return {
        "distinct_signatures": distinct,
        "extra_duplicate_rows": row_count - distinct,
        "rows_in_duplicate_groups": int(sizes[sizes > 1].sum()),
        "max_signature_frequency": int(sizes.max()),
    }


def _blank_count(series: pd.Series) -> int:
    text = series.dropna().astype(str)
    return int(text.str.strip().eq("").sum())


def _whitespace_model_counts(series: pd.Series) -> dict[str, int]:
    text = series.dropna().astype(str)
    stripped = text.str.strip()
    flagged = text[stripped.ne("") & text.ne(stripped)]
    return {repr(value): int(count) for value, count in flagged.value_counts().items()}


def _count_map(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts(dropna=False)
    mapped: dict[str, int] = {}
    for key, value in counts.items():
        label = "<null>" if pd.isna(key) else str(key)
        mapped[label] = int(value)
    return mapped


def _count_dict(counter: Counter[str], *, by_key: bool = False) -> dict[str, int]:
    items = list(counter.items())
    if by_key:
        items.sort(key=lambda item: item[0])
    else:
        items.sort(key=lambda item: (-item[1], str(item[0])))
    return {str(key): int(value) for key, value in items}


def _file_summary(profile: dict[str, Any]) -> dict[str, Any]:
    metrics = profile["metrics"]
    return {
        "year": metrics["year"],
        "local_filename": profile["local_filename"],
        "source_url": profile["source_url"],
        "acquisition": profile["acquisition"],
        "download_timestamp": profile["download_timestamp"],
        "file_size_bytes": profile["file_size_bytes"],
        "sha256": profile["sha256"],
        "row_count": metrics["row_count"],
        "minimum_date": metrics["min_date"],
        "maximum_date": metrics["max_date"],
    }


def _manifest_record(profile: dict[str, Any]) -> dict[str, Any]:
    schema = profile["schema"]
    metrics = profile["metrics"]
    return {
        "year": metrics["year"],
        "source_url": profile["source_url"],
        "local_filename": profile["local_filename"],
        "download_timestamp": profile["download_timestamp"],
        "acquisition": profile["acquisition"],
        "file_size_bytes": profile["file_size_bytes"],
        "sha256": profile["sha256"],
        "row_count": metrics["row_count"],
        "column_names": schema["column_order"],
        "schema": [
            {
                "name": name,
                "type": schema["physical_types"][name],
                "nullable": schema["nullable"][name],
            }
            for name in schema["column_order"]
        ],
        "minimum_date": metrics["min_date"],
        "maximum_date": metrics["max_date"],
    }


def _unexpected_parquet_names(expected_names: set[str]) -> list[str]:
    if not RAW_DIR.exists():
        return []
    return sorted(
        path.name
        for path in RAW_DIR.glob("*.parquet")
        if path.name not in expected_names
    )


def _markdown_table(counts: dict[str, int]) -> list[str]:
    lines = ["| Value | Registration transactions |", "| --- | ---: |"]
    for key, value in counts.items():
        safe = str(key).replace("|", "\\|")
        lines.append(f"| {safe} | {value} |")
    return lines


def _overall(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == FAIL for check in checks):
        return FAIL
    if any(check["status"] == WARN for check in checks):
        return WARN
    return PASS


def _next_month(value: datetime) -> datetime:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return value.replace(year=year, month=month)


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
