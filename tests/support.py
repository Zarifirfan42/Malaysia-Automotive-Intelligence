"""Tiny official-schema Parquet fixtures for Phase 1 tests."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.config import EXPECTED_COLUMNS, EXPECTED_PHYSICAL_TYPES


def official_fields() -> list[pa.Field]:
    types = {
        "timestamp[us]": pa.timestamp("us"),
        "large_string": pa.large_string(),
    }
    return [
        pa.field(name, types[EXPECTED_PHYSICAL_TYPES[name]])
        for name in EXPECTED_COLUMNS
    ]


def write_official_parquet(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = {
        "date_reg": pa.array([row["date_reg"] for row in records], type=pa.timestamp("us")),
        "type": pa.array([row["type"] for row in records], type=pa.large_string()),
        "maker": pa.array([row["maker"] for row in records], type=pa.large_string()),
        "model": pa.array([row["model"] for row in records], type=pa.large_string()),
        "colour": pa.array([row["colour"] for row in records], type=pa.large_string()),
        "fuel": pa.array([row["fuel"] for row in records], type=pa.large_string()),
        "state": pa.array([row["state"] for row in records], type=pa.large_string()),
    }
    pq.write_table(pa.table(columns), path)


def parquet_bytes(records: list[dict[str, object]]) -> bytes:
    buffer = io.BytesIO()
    columns = {
        "date_reg": pa.array([row["date_reg"] for row in records], type=pa.timestamp("us")),
        "type": pa.array([row["type"] for row in records], type=pa.large_string()),
        "maker": pa.array([row["maker"] for row in records], type=pa.large_string()),
        "model": pa.array([row["model"] for row in records], type=pa.large_string()),
        "colour": pa.array([row["colour"] for row in records], type=pa.large_string()),
        "fuel": pa.array([row["fuel"] for row in records], type=pa.large_string()),
        "state": pa.array([row["state"] for row in records], type=pa.large_string()),
    }
    pq.write_table(pa.table(columns), buffer)
    return buffer.getvalue()


def registration(
    when: datetime,
    *,
    vehicle_type: str = "motokar",
    maker: str = "Perodua",
    model: str = "Myvi",
    colour: str = "grey",
    fuel: str = "petrol",
    state: str = "Selangor",
) -> dict[str, object]:
    return {
        "date_reg": when,
        "type": vehicle_type,
        "maker": maker,
        "model": model,
        "colour": colour,
        "fuel": fuel,
        "state": state,
    }
