# Analytical database

`registrations.duckdb` is a local DuckDB file of views over `data/processed/`. The registration rows stay in Parquet. The database file is gitignored and is rebuilt with:

```bash
python -m src.analytical
```

See `docs/phase3.md` for the grain of each view and the year-over-year rules.
