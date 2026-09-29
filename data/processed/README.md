# Processed registrations

Phase 2 writes one Parquet file per registration year:

```text
registrations/<year>/registrations.parquet
```

Each file keeps the JPJ source columns and adds analytical columns beside them. `dataset_metadata.json` records the derived-field definitions, the partial latest year, and the low-volume months found in that run.

Rebuild from the raw files with:

```bash
python -m src.transformation
```

Do not edit `data/raw/` to correct a processed value. Change the transformation rule, then rebuild.

Phase 3 reads these Parquet files through DuckDB. It does not rewrite them.
