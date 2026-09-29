# Phase 4 — exploratory and statistical analysis

Phase 4 reads the Phase 3 DuckDB views. It does not rebuild the raw files, the processed Parquet, or the analytical views, and it does not forecast.

```bash
python -m src.analysis
```

The command writes:

- `reports/phase4/phase4_report.md`
- `reports/phase4/figures/`
- `data/analysis/phase4_results.json`
- summary CSV files under `data/analysis/`

DuckDB returns aggregates. The registration fact is not loaded into pandas.

National totals include the Rakan Niaga channel. Charts that exclude it say so and are not the national total. Full-year change for a partial latest year is withheld. The like-for-like window is January through the last complete month.

The primary tests are a Kruskal-Wallis test of monthly registration counts by calendar month, Spearman correlations of complete-year electric share and hybrid share with year, and a chi-square comparison of fuel composition between 2017–2019 and the latest three complete years. Those four tests share a Bonferroni adjustment. Effect sizes are reported because a small p-value is not treated as practical importance by itself.

Low-volume months stay in the primary statistics. The report also shows the mean and standard deviation with those months set aside, as a sensitivity check. The dataset does not establish why those months are low.
