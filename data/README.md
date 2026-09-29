# Data directories

`raw/` holds the official yearly JPJ Parquet files (`cars_2000.parquet` through `cars_2026.parquet`). Do not edit, deduplicate, or resample these files. They are gitignored and can be downloaded again with `python -m src`.

`quality/` holds the Phase 1 manifest and the Phase 2 transformation audit. Those files are calculated from the data. They are not a second copy of the registrations.

`processed/` holds the registration tables written by Phase 2. Source columns are still present. Raw files are not modified to produce them. The Parquet files are gitignored because they can be rebuilt with `python -m src.transformation`.
