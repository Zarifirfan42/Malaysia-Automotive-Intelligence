# Data directories

`raw/` holds the official yearly JPJ Parquet files (`cars_2000.parquet` through `cars_2026.parquet`). Do not edit, deduplicate, or resample these files. They are gitignored and can be downloaded again with `python -m src`.

`quality/` holds the generated source manifest and data-quality report. Those files are calculated from `raw/` during validation. They are not a second copy of the registrations.

Processed analytical tables are not created in Phase 1.
