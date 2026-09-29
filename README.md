# Malaysia Automotive Intelligence

Malaysian vehicle registration, market trends, and predictive analytics.

This portfolio project uses the public **Car Registration Transactions** dataset published by Jabatan Pengangkutan Jalan (JPJ) through [data.gov.my](https://data.gov.my/data-catalogue/registration_transactions_car). It is not Global Turbine Asia data, aviation data, customer data, or private industry data.

| | |
| --- | --- |
| Dataset | JPJ Car Registration Transactions |
| Dataset ID | `registration_transactions_car` |
| Source | data.gov.my |
| Licence | CC BY 4.0 |
| Files | `https://storage.data.gov.my/transportation/cars_{year}.parquet` |
| Years | 2000 through 2026 |

## How to read the data

Each row is one car **registration transaction**. It is not a sale, a purchase, a customer, or a measure of demand. `date_reg` is the registration date and may differ from a purchase date.

`Rakan Niaga` is retained as a registration channel. It is not treated as a Malaysian geographic state, and it is not imputed into a state.

`greendiesel` remains its own source fuel category. It is not merged into `diesel`.

The latest yearly file may end before 31 December. That partial year is detected from `date_reg` and is not treated as a complete year.

Identical source rows are retained. The files have no vehicle or transaction identifier, so matching rows can be separate registrations.

The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.

## Raw and processed data

`data/raw/` is the immutable JPJ snapshot. Phase 2 reads those files and writes `data/processed/`. It does not overwrite raw Parquet, delete transactions, or deduplicate identical rows.

| Source field | Analytical field | Rule |
| --- | --- | --- |
| `maker` | `maker_clean` | Trim surrounding whitespace. Map a case variant only when one spelling of that same name is strictly more frequent. |
| `model` | `model_clean` | Trim surrounding whitespace. Keep internal spaces. Do not rename `Unknown`. |
| `fuel` | `fuel_category` | Exact copy. `greendiesel` stays separate from `diesel`. |
| `state` | `state_category` | Exact copy. `Rakan Niaga` stays a channel and is not assigned to a state. |

`is_electric` is 1 only when `fuel` is `electric`. `is_hybrid` is 1 only when `fuel` is `hybrid_petrol` or `hybrid_diesel`. Maker and model names are not used. `is_internal_combustion` is omitted because dual-fuel, gas, hydrogen, `greendiesel`, `other`, and `unknown` are not clearly internal combustion.

`registration_year`, `registration_month`, `registration_month_number`, `registration_month_name`, `registration_quarter`, and `registration_year_month` come from `date_reg`. `registration_month` and `registration_month_number` are both the month number 1–12.

The latest registration year is partial when its maximum `date_reg` is before 31 December. Those rows stay in the data. Unusually low months, including any month below 10% of the median monthly count, also stay. The dataset does not establish why a month is low.

## Run

```bash
pip install -r requirements.txt
python -m src
python -m src.transformation
python -m src.analytical
python -m src.analysis
python -m pytest
```

`python -m src --force` redownloads a readable raw file. A failed download stops Phase 1. Phase 2 stops if processed totals do not match the raw files.

## Analytical layer

Phase 3 adds DuckDB views over the processed Parquet. `fact_registrations` has one row per processed registration transaction and does not add a transaction id. Rebuild the gitignored database with `python -m src.analytical`. Definitions, share formulas, and the partial-year comparison are in `docs/phase3.md`.

A registration share is group registrations divided by all recorded registrations in the same period. It is not a share of vehicle sales.

Phase 4 writes an exploratory report from those views with `python -m src.analysis`. The findings are in `reports/phase4/phase4_report.md`. Forecasting, anomaly detection, and Power BI are later phases.

## Layout

```text
data/raw/          official Parquet files, not committed
data/processed/    one directory per registration year, Parquet not committed
data/analytical/   gitignored DuckDB views, rebuilt from sql/
data/quality/      acquisition, transformation, and reconciliation audits
sql/               fact, analytical views, validation, and analysis extracts
src/ingestion/     download
src/validation/    Phase 1 checks
src/transformation Phase 2 cleaning
src/analytical/    Phase 3 DuckDB build
src/analysis/      Phase 4 exploratory and statistical analysis
reports/phase4/    generated Phase 4 report and charts
tests/             invariant tests
```
