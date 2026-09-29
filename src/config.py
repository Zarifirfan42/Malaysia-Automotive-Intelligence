"""Paths, source contract, and validation rules for Phase 1.

Row counts and other measured statistics are never stored here. Those
values are calculated from the downloaded files at runtime.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
QUALITY_DIR = DATA_DIR / "quality"

DATASET_ID = "registration_transactions_car"
DATASET_NAME = "Car Registration Transactions"
PUBLISHER = "Jabatan Pengangkutan Jalan (JPJ) / Ministry of Transport Malaysia"
CATALOGUE_URL = "https://data.gov.my/data-catalogue/registration_transactions_car"
PARQUET_URL_TEMPLATE = "https://storage.data.gov.my/transportation/cars_{year}.parquet"
LICENCE = "CC BY 4.0"

YEAR_START = 2000
YEAR_END = 2026

EXPECTED_COLUMNS: tuple[str, ...] = (
    "date_reg",
    "type",
    "maker",
    "model",
    "colour",
    "fuel",
    "state",
)

# Physical Parquet types observed on the official files.
# A future upstream change must fail validation rather than be adapted silently.
EXPECTED_PHYSICAL_TYPES: dict[str, str] = {
    "date_reg": "timestamp[us]",
    "type": "large_string",
    "maker": "large_string",
    "model": "large_string",
    "colour": "large_string",
    "fuel": "large_string",
    "state": "large_string",
}

COLUMN_ROLES: dict[str, str] = {
    "date_reg": "Registration date. This may differ from a purchase date.",
    "type": "Vehicle type.",
    "maker": "Manufacturer.",
    "model": "Model.",
    "colour": "Broad colour.",
    "fuel": "Source fuel code. greendiesel is retained as its own category.",
    "state": "JPJ registration office, or the Rakan Niaga partner channel. Not a place of use.",
}

# A month is reported as unusually low when its row count is below this
# fraction of the median monthly row count. This is a rule, not a stored statistic.
LOW_VOLUME_MONTH_FRACTION = 0.10

DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
USER_AGENT = "MalaysiaAutomotiveIntelligence/0.1 (phase-1 dataset validation)"

MANIFEST_PATH = QUALITY_DIR / "source_manifest.json"
QUALITY_REPORT_JSON = QUALITY_DIR / "data_quality_report.json"
QUALITY_REPORT_MD = QUALITY_DIR / "data_quality_report.md"


def dataset_years() -> tuple[int, ...]:
    """Return the inclusive official year range, 2000 through 2026."""
    return tuple(range(YEAR_START, YEAR_END + 1))


def parquet_filename(year: int) -> str:
    """Return the local yearly filename, for example cars_2024.parquet."""
    _require_year(year)
    return f"cars_{year}.parquet"


def parquet_url(year: int) -> str:
    """Return the official storage URL for one yearly Parquet file."""
    _require_year(year)
    return PARQUET_URL_TEMPLATE.format(year=year)


def raw_path(year: int) -> Path:
    """Return the local raw path for one yearly file. The file is never edited in place."""
    return RAW_DIR / parquet_filename(year)


def ensure_directories() -> None:
    """Create the raw and quality directories if they do not exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)


def _require_year(year: int) -> None:
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError(f"year must be an int, got {type(year).__name__}")
    if year < YEAR_START or year > YEAR_END:
        raise ValueError(
            f"year {year} is outside the official file range {YEAR_START}–{YEAR_END}"
        )
