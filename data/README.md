# Data directories

`raw/` holds the official yearly JPJ Parquet files (`cars_2000.parquet` through `cars_2026.parquet`). Do not edit, deduplicate, or resample these files. They are gitignored and can be downloaded again with `python -m src`.

`quality/` holds the Phase 1 manifest, the Phase 2 transformation audit, and the Phase 3 reconciliation. Those files are calculated from the data. They are not a second copy of the registrations.

`processed/` holds the registration tables written by Phase 2. Source columns are still present. Raw files are not modified to produce them. The Parquet files are gitignored because they can be rebuilt with `python -m src.transformation`.

`analytical/` holds the DuckDB file created by Phase 3. It is a set of views over `processed/` and is gitignored. Rebuild it with `python -m src.analytical`.

`analysis/` holds the Phase 4 summary tables and machine-readable results. Rebuild them with `python -m src.analysis`.
