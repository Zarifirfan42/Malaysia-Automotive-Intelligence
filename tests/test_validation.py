"""Invariant tests for schema checks, duplicates, manifests, and raw-file preservation."""

from __future__ import annotations

from datetime import datetime, timezone

import pyarrow as pa
import pytest

from src.ingestion.download import DownloadResult
from src.validation.validate import (
    assess_schema,
    build_manifest,
    build_quality_report,
    casefold_collisions,
    find_low_volume_months,
    find_missing_months,
    metrics_from_frame,
    profile_downloaded_file,
    sha256_file,
)
from tests.support import official_fields, registration, write_official_parquet


def _download_result(path, year: int = 2000) -> DownloadResult:
    moment = datetime(2026, 9, 29, tzinfo=timezone.utc)
    return DownloadResult(
        year=year,
        source_url=f"https://storage.data.gov.my/transportation/cars_{year}.parquet",
        local_path=path,
        acquisition="downloaded",
        completed_at=moment,
        file_size_bytes=path.stat().st_size,
        file_mtime=moment,
    )


def _complete_year_records() -> list[dict[str, object]]:
    records = []
    for month in range(1, 13):
        records.append(registration(datetime(2000, month, 15)))
    records.append(registration(datetime(2000, 1, 15)))
    records.append(
        registration(
            datetime(2000, 12, 31),
            fuel="greendiesel",
            state="Rakan Niaga",
        )
    )
    return records


def _report_for(path, records: list[dict[str, object]], year: int = 2000):
    write_official_parquet(path, records)
    profile = profile_downloaded_file(_download_result(path, year))
    report = build_quality_report(
        [profile],
        started_at="2026-09-29T00:00:00+00:00",
        finished_at="2026-09-29T00:01:00+00:00",
        latest_expected_year=year,
    )
    return profile, report


def test_schema_accepts_the_official_contract() -> None:
    assessment = assess_schema(pa.schema(official_fields()))
    assert assessment["status"] == "PASS"
    assert assessment["column_order"] == [
        "date_reg",
        "type",
        "maker",
        "model",
        "colour",
        "fuel",
        "state",
    ]


def test_schema_rejects_missing_unexpected_and_retyped_columns() -> None:
    missing = [field for field in official_fields() if field.name != "fuel"]
    missing_assessment = assess_schema(pa.schema(missing))
    assert missing_assessment["status"] == "FAIL"
    assert missing_assessment["missing_columns"] == ["fuel"]

    unexpected = official_fields() + [pa.field("price", pa.int64())]
    unexpected_assessment = assess_schema(pa.schema(unexpected))
    assert unexpected_assessment["status"] == "FAIL"
    assert unexpected_assessment["unexpected_columns"] == ["price"]

    retyped = [
        pa.field("date_reg", pa.timestamp("ns")) if field.name == "date_reg" else field
        for field in official_fields()
    ]
    retyped_assessment = assess_schema(pa.schema(retyped))
    assert retyped_assessment["status"] == "FAIL"
    assert any("date_reg" in problem for problem in retyped_assessment["type_problems"])


def test_file_year_must_match_date_reg_year() -> None:
    frame = _frame(
        [
            registration(datetime(2000, 1, 15)),
            registration(datetime(2001, 6, 1)),
        ]
    )
    metrics = metrics_from_frame(frame, 2000)
    assert metrics["year_mismatch_rows"] == 1


def test_duplicate_rows_are_counted_and_retained() -> None:
    records = [
        registration(datetime(2000, 1, 15)),
        registration(datetime(2000, 1, 15)),
        registration(datetime(2000, 1, 15)),
        registration(datetime(2000, 2, 15), model="Saga", maker="Proton"),
    ]
    frame = _frame(records)
    metrics = metrics_from_frame(frame, 2000)
    assert len(frame) == 4
    assert metrics["row_count"] == 4
    assert metrics["duplicates"]["distinct_signatures"] == 2
    assert metrics["duplicates"]["extra_duplicate_rows"] == 2
    assert metrics["duplicates"]["rows_in_duplicate_groups"] == 3
    assert metrics["duplicates"]["max_signature_frequency"] == 3


def test_blank_and_whitespace_models_are_reported_without_being_rewritten() -> None:
    records = [
        registration(datetime(2000, 3, 15), model="   "),
        registration(datetime(2000, 3, 16), model=" Myvi"),
    ]
    frame = _frame(records)
    metrics = metrics_from_frame(frame, 2000)
    assert metrics["blanks"]["model"] == 1
    assert metrics["whitespace_models"] == {"' Myvi'": 1}
    assert frame.loc[1, "model"] == " Myvi"


def test_manifest_is_built_from_the_file_hash_and_measured_rows(tmp_path) -> None:
    path = tmp_path / "cars_2000.parquet"
    records = _complete_year_records()
    profile, _report = _report_for(path, records)
    manifest = build_manifest([profile], generated_at="2026-09-29T00:01:00+00:00")
    stored = manifest["files"][0]

    assert manifest["complete"] is True
    assert stored["sha256"] == sha256_file(path)
    assert stored["row_count"] == len(records)
    assert stored["column_names"] == [
        "date_reg",
        "type",
        "maker",
        "model",
        "colour",
        "fuel",
        "state",
    ]
    assert stored["minimum_date"] == "2000-01-15"
    assert stored["maximum_date"] == "2000-12-31"
    assert stored["source_url"].endswith("/cars_2000.parquet")


def test_profiling_does_not_change_the_raw_file(tmp_path) -> None:
    path = tmp_path / "cars_2000.parquet"
    write_official_parquet(path, _complete_year_records())
    before = sha256_file(path)
    profile = profile_downloaded_file(_download_result(path))
    assert sha256_file(path) == before
    assert profile["sha256"] == before
    assert profile["raw_unchanged"] is True


def test_clean_file_passes_and_keeps_channel_and_fuel_codes(tmp_path) -> None:
    _profile, report = _report_for(tmp_path / "cars_2000.parquet", _complete_year_records())
    assert report["validation_status"] == "PASS"
    assert report["row_counts"]["by_state"]["Rakan Niaga"] == 1
    assert report["row_counts"]["by_fuel"]["greendiesel"] == 1
    assert report["duplicate_profile"]["rows_were_deleted"] is False
    assert report["duplicate_profile"]["extra_duplicate_rows"] == 1


def test_year_mismatch_fails_the_report(tmp_path) -> None:
    records = [
        registration(datetime(2000, 6, 1)),
        registration(datetime(2001, 6, 1)),
    ]
    _profile, report = _report_for(tmp_path / "cars_2000.parquet", records)
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["year_consistency"] == "FAIL"
    assert report["validation_status"] == "FAIL"


def test_whitespace_and_maker_spelling_are_warnings(tmp_path) -> None:
    records = _complete_year_records()
    records.append(registration(datetime(2000, 5, 20), model=" Axia"))
    records.append(registration(datetime(2000, 5, 21), maker="BMW"))
    records.append(registration(datetime(2000, 5, 22), maker="Bmw"))
    _profile, report = _report_for(tmp_path / "cars_2000.parquet", records)
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["model_whitespace"] == "WARN"
    assert statuses["maker_spelling"] == "WARN"
    assert report["validation_status"] == "WARN"
    assert casefold_collisions({"BMW": 10, "Bmw": 1, "Perodua": 3})[0]["key"] == "bmw"


def test_missing_months_and_low_volume_rules() -> None:
    assert find_missing_months({"2000-01": 10, "2000-03": 10}) == ["2000-02"]
    low = find_low_volume_months({"2000-01": 100, "2000-02": 100, "2000-03": 5})
    assert list(low["months"]) == ["2000-03"]


def _frame(records: list[dict[str, object]]):
    import pandas as pd

    return pd.DataFrame(records)
