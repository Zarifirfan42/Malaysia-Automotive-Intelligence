"""Invariant tests for the processed layer. Totals are not hard-coded."""

from __future__ import annotations

from datetime import datetime

import pyarrow.parquet as pq
import pytest

from src.transformation.build import run_phase2
from src.transformation.rules import (
    AmbiguousMakerStandardisation,
    invariant_violations,
    standardise_makers,
    transform_table,
)
from src.validation.validate import sha256_file
from tests.support import registration, write_official_parquet


def test_case_variant_maps_to_the_dominant_spelling_and_preserves_distinct_names() -> None:
    overrides, changes = standardise_makers({"BMW": 10, "Bmw": 1, "McLaren": 4, "Mclaren": 2, "Perodua": 7})
    assert overrides == {"Bmw": "BMW", "Mclaren": "McLaren"}
    assert {change.source_value for change in changes} == {"Bmw", "Mclaren"}
    assert standardise_makers({"Great Wall": 3, "GreatWall": 9})[0] == {}


def test_equal_frequency_case_variants_stop_the_standardisation() -> None:
    with pytest.raises(AmbiguousMakerStandardisation):
        standardise_makers({"Aaa": 2, "AAA": 2})


def test_transform_preserves_rows_and_source_values() -> None:
    records = [
        registration(datetime(2000, 1, 15), maker="Bmw", model=" E Advance ", fuel="electric"),
        registration(datetime(2000, 1, 15), maker="Bmw", model=" E Advance ", fuel="electric"),
        registration(datetime(2000, 4, 2), maker="BMW", model="TF 160 ", fuel="hybrid_petrol", state="Rakan Niaga"),
        registration(datetime(2000, 12, 31), maker="Perodua", model="Unknown", fuel="greendiesel"),
        registration(datetime(2000, 6, 1), maker="Tesla", model="Hybrid", fuel="petrol_ng", state="Selangor"),
        registration(datetime(2000, 7, 1), fuel="hybrid_diesel"),
        registration(datetime(2000, 8, 1), fuel="unknown"),
        registration(datetime(2000, 9, 1), fuel="other"),
    ]
    source = _table(records)
    processed = transform_table(source, {"Bmw": "BMW"})
    assert invariant_violations(source, processed) == []
    assert processed.num_rows == len(records)
    assert processed.column("maker").to_pylist()[0] == "Bmw"
    assert processed.column("maker_clean").to_pylist()[:3] == ["BMW", "BMW", "BMW"]
    assert processed.column("model").to_pylist()[0] == " E Advance "
    assert processed.column("model_clean").to_pylist()[0] == "E Advance"
    assert processed.column("model_clean").to_pylist()[2] == "TF 160"
    assert processed.column("model").to_pylist()[3] == "Unknown"
    assert processed.column("fuel").to_pylist()[3] == "greendiesel"
    assert processed.column("fuel_category").to_pylist()[3] == "greendiesel"
    assert processed.column("state_category").to_pylist()[2] == "Rakan Niaga"
    assert processed.column("is_electric").to_pylist() == [1, 1, 0, 0, 0, 0, 0, 0]
    assert processed.column("is_hybrid").to_pylist() == [0, 0, 1, 0, 0, 1, 0, 0]
    assert processed.column("is_rakan_niaga").to_pylist()[2] == 1
    assert "is_internal_combustion" not in processed.column_names
    january = processed.slice(0, 1).to_pydict()
    assert january["registration_year"] == [2000]
    assert january["registration_month"] == [1]
    assert january["registration_month_number"] == [1]
    assert january["registration_month_name"] == ["January"]
    assert january["registration_quarter"] == [1]
    assert january["registration_year_month"] == ["2000-01"]
    april = processed.slice(2, 1).to_pydict()
    assert april["registration_quarter"] == [2]
    assert april["registration_year_month"] == ["2000-04"]


def test_pipeline_reconciles_without_changing_raw_files(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    records = _complete_records()
    source = raw_dir / "cars_2000.parquet"
    write_official_parquet(source, records)
    before = sha256_file(source)

    report = run_phase2(
        raw_dir=raw_dir,
        processed_dir=tmp_path / "processed",
        quality_dir=tmp_path / "quality",
        years=[2000],
    )

    assert sha256_file(source) == before
    assert report["validation_status"] == "PASS"
    assert report["raw_row_count"] == len(records)
    assert report["processed_row_count"] == len(records)
    assert report["reconciliation"]["match"] is True
    assert report["electric_rows"] == 1
    assert report["hybrid_rows"] == 2
    assert report["rakan_niaga_rows"] == 1
    assert report["unknown_model_rows"] == 1
    written = pq.ParquetFile(
        tmp_path / "processed" / "registrations" / "2000" / "registrations.parquet"
    ).read()
    assert written.num_rows == len(records)
    assert "is_internal_combustion" not in written.column_names


def test_partial_year_and_case_changes_are_warnings_and_rows_remain(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    write_official_parquet(
        raw_dir / "cars_2026.parquet",
            [
                registration(datetime(2026, 8, 31), maker="Bmw", model="E Advance "),
                registration(datetime(2026, 1, 2), maker="BMW", model="Saga"),
                registration(datetime(2026, 3, 1), maker="BMW", model="Saga"),
            ],
    )
    report = run_phase2(
        raw_dir=raw_dir,
        processed_dir=tmp_path / "processed",
        quality_dir=tmp_path / "quality",
        years=[2026],
        run_date=datetime(2026, 9, 29).date(),
    )
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["validation_status"] == "WARN"
    assert statuses["reconciliation"] == "PASS"
    assert statuses["partial_latest_year"] == "WARN"
    assert statuses["maker_standardisation"] == "WARN"
    assert statuses["model_standardisation"] == "WARN"
    assert statuses["latest_year_retained"] == "PASS"
    assert report["processed_row_count"] == 3
    assert report["partial_years"][0]["maximum_date"] == "2026-08-31"
    assert report["maker_transformations"][0]["source_value"] == "Bmw"
    assert report["maker_transformations"][0]["clean_value"] == "BMW"


def test_ambiguous_makers_do_not_publish_a_processed_dataset(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    write_official_parquet(
        raw_dir / "cars_2000.parquet",
        [
            registration(datetime(2000, 12, 31), maker="Aaa"),
            registration(datetime(2000, 12, 30), maker="AAA"),
        ],
    )
    report = run_phase2(
        raw_dir=raw_dir,
        processed_dir=tmp_path / "processed",
        quality_dir=tmp_path / "quality",
        years=[2000],
    )
    assert report["validation_status"] == "FAIL"
    assert report["complete"] is False
    assert not (tmp_path / "processed" / "registrations").exists()


def _complete_records() -> list[dict[str, object]]:
    records = [registration(datetime(2000, month, 15)) for month in range(1, 12)]
    records.extend(
        [
            registration(datetime(2000, 12, 31), fuel="electric"),
            registration(datetime(2000, 12, 31), fuel="hybrid_petrol", state="Rakan Niaga"),
            registration(datetime(2000, 12, 30), fuel="hybrid_diesel"),
            registration(datetime(2000, 12, 29), model="Unknown", fuel="unknown"),
            registration(datetime(2000, 12, 28), fuel="other"),
            registration(datetime(2000, 12, 27), fuel="greendiesel"),
            registration(datetime(2000, 1, 15)),
        ]
    )
    return records


def _table(records: list[dict[str, object]]):
    import pyarrow as pa

    from tests.support import official_fields

    columns = {
        "date_reg": pa.array([row["date_reg"] for row in records], type=pa.timestamp("us")),
        "type": pa.array([row["type"] for row in records], type=pa.large_string()),
        "maker": pa.array([row["maker"] for row in records], type=pa.large_string()),
        "model": pa.array([row["model"] for row in records], type=pa.large_string()),
        "colour": pa.array([row["colour"] for row in records], type=pa.large_string()),
        "fuel": pa.array([row["fuel"] for row in records], type=pa.large_string()),
        "state": pa.array([row["state"] for row in records], type=pa.large_string()),
    }
    del official_fields
    return pa.table(columns)
