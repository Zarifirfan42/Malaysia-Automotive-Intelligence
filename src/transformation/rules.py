"""Deterministic cleaning rules for the processed registration layer.

Source values are never overwritten. A change is recorded only when the
analytical value differs from the source value. Case merges are allowed
only when every variant is the same spelling apart from case, and one
spelling is strictly more frequent. Equal frequencies stop the pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

ELECTRIC_FUEL = "electric"
HYBRID_FUELS = frozenset({"hybrid_petrol", "hybrid_diesel"})
CHANNEL_STATE = "Rakan Niaga"

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

DERIVED_COLUMNS: tuple[str, ...] = (
    "maker_clean",
    "model_clean",
    "fuel_category",
    "state_category",
    "registration_year",
    "registration_month",
    "registration_month_number",
    "registration_month_name",
    "registration_quarter",
    "registration_year_month",
    "is_electric",
    "is_hybrid",
    "is_rakan_niaga",
)

INTERNAL_COMBUSTION_OMISSION = (
    "is_internal_combustion is not created. greendiesel, dual-fuel codes, "
    "hydrogen, natural gas, other, and unknown cannot be classified as "
    "internal combustion from this dataset without an extra assumption. "
    "Electric and hybrid flags are set only from explicit source fuel values."
)

FIELD_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "field": "maker_clean",
        "definition": (
            "maker with surrounding whitespace removed. A case variant is mapped "
            "to the single most frequent spelling of that same case-folded name. "
            "The source maker column is unchanged."
        ),
    },
    {
        "field": "model_clean",
        "definition": (
            "model with surrounding whitespace removed. Internal spaces are kept. "
            "Models are not renamed, and Unknown is not converted to null."
        ),
    },
    {
        "field": "fuel_category",
        "definition": (
            "Exact copy of the source fuel code. greendiesel is not merged into "
            "diesel, and dual-fuel codes are not merged into petrol or diesel."
        ),
    },
    {
        "field": "state_category",
        "definition": (
            "Exact copy of the source state value. Rakan Niaga stays Rakan Niaga "
            "and is not assigned to a geographic state."
        ),
    },
    {
        "field": "is_rakan_niaga",
        "definition": "1 when state is exactly Rakan Niaga, otherwise 0.",
    },
    {
        "field": "is_electric",
        "definition": "1 when fuel is exactly electric, otherwise 0. Maker and model are not used.",
    },
    {
        "field": "is_hybrid",
        "definition": "1 when fuel is hybrid_petrol or hybrid_diesel, otherwise 0.",
    },
    {
        "field": "registration_year",
        "definition": "Calendar year of date_reg.",
    },
    {
        "field": "registration_month",
        "definition": "Calendar month of date_reg as an integer from 1 to 12.",
    },
    {
        "field": "registration_month_number",
        "definition": "Same value as registration_month. Both names are stored so either can be used.",
    },
    {
        "field": "registration_month_name",
        "definition": "English month name of date_reg, from a fixed list rather than the machine locale.",
    },
    {
        "field": "registration_quarter",
        "definition": "Calendar quarter of date_reg, from 1 to 4.",
    },
    {
        "field": "registration_year_month",
        "definition": "date_reg formatted as YYYY-MM.",
    },
)


class AmbiguousMakerStandardisation(Exception):
    """Two maker spellings differ only by case and have the same frequency."""

    def __init__(self, groups: list[dict[str, Any]]) -> None:
        self.groups = groups
        rendered = "; ".join(
            f"{group['casefold']}: " + ", ".join(
                f"{item['value']} ({item['rows']})" for item in group["variants"]
            )
            for group in groups
        )
        super().__init__(
            "Maker case variants have equal frequency, so no dominant spelling was chosen: "
            + rendered
        )


@dataclass(frozen=True)
class ValueChange:
    """One source value that differs from its analytical value."""

    field: str
    source_value: str
    clean_value: str
    row_count: int
    reason: str


def standardise_makers(counts: Mapping[str, int]) -> tuple[dict[str, str], list[ValueChange]]:
    """Return case overrides and the maker changes that will actually be applied.

    The override map is keyed by the whitespace-trimmed spelling and is applied
    after trimming. Unchanged makers are omitted from the audit.
    """
    stripped_counts: dict[str, int] = {}
    for source, count in counts.items():
        if not isinstance(source, str):
            raise TypeError(f"maker value must be a string, got {type(source).__name__}")
        stripped = source.strip()
        stripped_counts[stripped] = stripped_counts.get(stripped, 0) + int(count)

    grouped: dict[str, list[str]] = {}
    for stripped in stripped_counts:
        grouped.setdefault(stripped.casefold(), []).append(stripped)

    clean_for_stripped: dict[str, str] = {}
    ambiguous: list[dict[str, Any]] = []
    for casefold, variants in grouped.items():
        if len(variants) == 1:
            clean_for_stripped[variants[0]] = variants[0]
            continue
        ranked = sorted(variants, key=lambda value: (-stripped_counts[value], value))
        top_count = stripped_counts[ranked[0]]
        tied = [value for value in variants if stripped_counts[value] == top_count]
        if len(tied) > 1:
            ambiguous.append(
                {
                    "casefold": casefold,
                    "variants": [
                        {"value": value, "rows": stripped_counts[value]} for value in sorted(tied)
                    ],
                }
            )
            continue
        dominant = ranked[0]
        for variant in variants:
            clean_for_stripped[variant] = dominant

    if ambiguous:
        raise AmbiguousMakerStandardisation(ambiguous)

    changes: list[ValueChange] = []
    for source, count in counts.items():
        stripped = source.strip()
        clean = clean_for_stripped[stripped]
        if source == clean:
            continue
        reasons: list[str] = []
        if source != stripped:
            reasons.append("trimmed surrounding whitespace")
        if stripped != clean:
            reasons.append(
                f"mapped case variant to the dominant spelling {clean} "
                f"({stripped_counts[clean]} trimmed rows)"
            )
        changes.append(
            ValueChange(
                field="maker",
                source_value=source,
                clean_value=clean,
                row_count=int(count),
                reason="; ".join(reasons) + "; source maker preserved",
            )
        )
    case_overrides = {
        variant: clean for variant, clean in clean_for_stripped.items() if variant != clean
    }
    return case_overrides, changes


def model_changes(counts: Mapping[str, int]) -> list[ValueChange]:
    """Return model values whose analytical form only strips surrounding whitespace."""
    changes: list[ValueChange] = []
    for source, count in counts.items():
        if not isinstance(source, str):
            raise TypeError(f"model value must be a string, got {type(source).__name__}")
        clean = source.strip()
        if source == clean:
            continue
        changes.append(
            ValueChange(
                field="model",
                source_value=source,
                clean_value=clean,
                row_count=int(count),
                reason="trimmed surrounding whitespace; internal spacing preserved; source model preserved",
            )
        )
    return changes


def transform_table(table: pa.Table, maker_case_overrides: Mapping[str, str]) -> pa.Table:
    """Add analytical columns. The returned table has the same row count as the input."""
    from src.config import EXPECTED_COLUMNS

    missing = [name for name in EXPECTED_COLUMNS if name not in table.column_names]
    if missing:
        raise ValueError(f"processed transform is missing source columns: {missing}")

    date_reg = table.column("date_reg")
    maker = table.column("maker")
    model = table.column("model")
    fuel = table.column("fuel")
    state = table.column("state")

    maker_clean = _apply_case_overrides(pc.utf8_trim_whitespace(maker), maker_case_overrides)
    model_clean = pc.utf8_trim_whitespace(model)
    month_number = pc.month(date_reg)
    zero = pa.scalar(0, type=pa.int8())
    one = pa.scalar(1, type=pa.int8())

    columns: dict[str, pa.ChunkedArray | pa.Array] = {name: table.column(name) for name in EXPECTED_COLUMNS}
    columns.update(
        {
            "maker_clean": maker_clean,
            "model_clean": model_clean,
            "fuel_category": fuel,
            "state_category": state,
            "registration_year": pc.year(date_reg),
            "registration_month": month_number,
            "registration_month_number": month_number,
            "registration_month_name": _month_names(month_number),
            "registration_quarter": pc.quarter(date_reg),
            "registration_year_month": year_month_labels(date_reg),
            "is_electric": pc.if_else(pc.equal(fuel, ELECTRIC_FUEL), one, zero),
            "is_hybrid": pc.if_else(_is_hybrid_fuel(fuel), one, zero),
            "is_rakan_niaga": pc.if_else(pc.equal(state, CHANNEL_STATE), one, zero),
        }
    )
    return pa.table(columns)


def invariant_violations(source: pa.Table, processed: pa.Table) -> list[str]:
    """Return human-readable breaks in the Phase 2 row-preservation contract."""
    from src.config import EXPECTED_COLUMNS

    problems: list[str] = []
    if source.num_rows != processed.num_rows:
        problems.append(f"row count changed from {source.num_rows} to {processed.num_rows}")
    if "is_internal_combustion" in processed.column_names:
        problems.append("is_internal_combustion was created despite the omission rule")
    for name in list(EXPECTED_COLUMNS) + list(DERIVED_COLUMNS):
        if name not in processed.column_names:
            problems.append(f"missing column {name}")
    if problems:
        return problems

    for name in EXPECTED_COLUMNS:
        problems.extend(_equal_problem(name, source.column(name), processed.column(name)))

    problems.extend(
        _equal_problem(
            "maker_clean whitespace",
            processed.column("maker_clean"),
            pc.utf8_trim_whitespace(processed.column("maker_clean")),
        )
    )
    problems.extend(
        _equal_problem(
            "model_clean",
            processed.column("model_clean"),
            pc.utf8_trim_whitespace(source.column("model")),
        )
    )
    problems.extend(
        _equal_problem("fuel_category", processed.column("fuel_category"), source.column("fuel"))
    )
    problems.extend(
        _equal_problem("state_category", processed.column("state_category"), source.column("state"))
    )

    fuel = source.column("fuel")
    state = source.column("state")
    date_reg = source.column("date_reg")
    zero = pa.scalar(0, type=pa.int8())
    one = pa.scalar(1, type=pa.int8())
    month_number = pc.month(date_reg)
    problems.extend(
        _equal_problem(
            "is_electric",
            processed.column("is_electric"),
            pc.if_else(pc.equal(fuel, ELECTRIC_FUEL), one, zero),
        )
    )
    problems.extend(
        _equal_problem(
            "is_hybrid",
            processed.column("is_hybrid"),
            pc.if_else(_is_hybrid_fuel(fuel), one, zero),
        )
    )
    problems.extend(
        _equal_problem(
            "is_rakan_niaga",
            processed.column("is_rakan_niaga"),
            pc.if_else(pc.equal(state, CHANNEL_STATE), one, zero),
        )
    )
    problems.extend(
        _equal_problem("registration_year", processed.column("registration_year"), pc.year(date_reg))
    )
    problems.extend(
        _equal_problem("registration_month", processed.column("registration_month"), month_number)
    )
    problems.extend(
        _equal_problem(
            "registration_month_number",
            processed.column("registration_month_number"),
            month_number,
        )
    )
    problems.extend(
        _equal_problem(
            "registration_month_name",
            processed.column("registration_month_name"),
            _month_names(month_number),
        )
    )
    problems.extend(
        _equal_problem(
            "registration_quarter",
            processed.column("registration_quarter"),
            pc.quarter(date_reg),
        )
    )
    problems.extend(
        _equal_problem(
            "registration_year_month",
            processed.column("registration_year_month"),
            year_month_labels(date_reg),
        )
    )
    return problems


def year_month_labels(date_reg: pa.ChunkedArray | pa.Array) -> pa.ChunkedArray | pa.Array:
    """Return YYYY-MM labels without using a timezone database."""
    year = pc.cast(pc.year(date_reg), pa.string())
    month = pc.utf8_lpad(pc.cast(pc.month(date_reg), pa.string()), width=2, padding="0")
    return pc.binary_join_element_wise(year, month, "-")


def count_map(column: pa.ChunkedArray | pa.Array) -> dict[str, int]:
    """Count non-missing values. Nulls are returned under the key '<null>'."""
    counts = column.value_counts()
    values = counts.field(0).to_pylist()
    frequencies = counts.field(1).to_pylist()
    mapped: dict[str, int] = {}
    for value, frequency in zip(values, frequencies):
        key = "<null>" if value is None else str(value)
        mapped[key] = mapped.get(key, 0) + int(frequency)
    return mapped


def count_differences(raw_counts: Mapping[str, int], processed_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    """Return keys whose raw and processed counts differ."""
    differences = []
    for key in sorted(set(raw_counts) | set(processed_counts)):
        raw_value = int(raw_counts.get(key, 0))
        processed_value = int(processed_counts.get(key, 0))
        if raw_value != processed_value:
            differences.append({"value": key, "raw": raw_value, "processed": processed_value})
    return differences


def _apply_case_overrides(
    stripped: pa.ChunkedArray | pa.Array,
    overrides: Mapping[str, str],
) -> pa.ChunkedArray | pa.Array:
    cleaned = stripped
    for source, target in sorted(overrides.items()):
        cleaned = pc.if_else(
            pc.equal(cleaned, source),
            pa.scalar(target, type=pa.large_string()),
            cleaned,
        )
    return cleaned


def _month_names(month_number: pa.ChunkedArray | pa.Array) -> pa.Array:
    labels = pa.array(["", *MONTH_NAMES])
    return pc.take(labels, month_number)


def _is_hybrid_fuel(fuel: pa.ChunkedArray | pa.Array) -> pa.ChunkedArray | pa.Array:
    return pc.is_in(fuel, value_set=pa.array(sorted(HYBRID_FUELS)))


def _equal_problem(label: str, actual: pa.ChunkedArray | pa.Array, expected: pa.ChunkedArray | pa.Array) -> list[str]:
    if actual.null_count != expected.null_count:
        return [f"{label} null count differs"]
    unequal = pc.fill_null(pc.not_equal(actual, expected), False)
    mismatches = pc.sum(pc.cast(unequal, pa.int64())).as_py()
    if mismatches:
        return [f"{label} differs on {int(mismatches)} rows"]
    return []
