"""Read Phase 3 views. Results are aggregates, not the registration fact table."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.config import DUCKDB_PATH, SQL_DIR

QUERY_FILES = (
    "overview.sql",
    "manufacturer_model_pairs.sql",
    "monthly.sql",
    "yearly.sql",
    "like_for_like.sql",
    "manufacturer_month.sql",
    "model_year.sql",
    "state_month.sql",
    "fuel_month.sql",
    "type_month.sql",
)


def extract(database_path: Path | None = None, sql_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Open the analytical database read-only and return aggregated frames."""
    path = DUCKDB_PATH if database_path is None else database_path
    scripts = SQL_DIR / "analysis" if sql_dir is None else sql_dir
    if not path.exists():
        raise FileNotFoundError(
            f"No DuckDB database at {path.as_posix()}. Rebuild the analytical layer with python -m src.analytical."
        )
    connection = duckdb.connect(str(path), read_only=True)
    try:
        frames = {}
        for name in QUERY_FILES:
            sql_path = scripts / name
            frames[name.removesuffix(".sql")] = connection.execute(sql_path.read_text(encoding="utf-8")).fetchdf()
    finally:
        connection.close()
    return frames
