# Phase 3 — analytical data model

Phase 3 reads the processed Parquet files and exposes them through DuckDB views. It does not modify `data/raw/`, does not change Phase 2 transformation rules, and does not copy the registration rows into a database table.

Rebuild it with:

```bash
python -m src.analytical
```

That command recreates `data/analytical/registrations.duckdb` from `sql/` and the processed files, then writes:

- `data/quality/phase3_reconciliation.json`
- `data/quality/phase3_reconciliation.md`

The DuckDB file is gitignored. The SQL and the processed Parquet are enough to rebuild it. Python receives aggregate query results only.

## Architecture

```text
data/raw/                         immutable JPJ Parquet
data/processed/registrations/     Phase 2 Parquet, one directory per year
sql/schema/                       fact and coverage views
sql/analytics/                    monthly and summary views
sql/validation/                   reconciliation queries
data/analytical/registrations.duckdb
```

`fact_registrations` is a view:

```sql
read_parquet('.../registrations/*/*.parquet', hive_partitioning = false)
```

The year directories are plain folders, not hive partitions. The view lists the Phase 2 columns it uses. It does not filter rows and it does not deduplicate them.

There is no transaction identifier. The source does not provide one, and Phase 3 does not invent a JPJ transaction id.

## Grain

| Object | Grain |
| --- | --- |
| `fact_registrations` | One processed registration transaction |
| `dim_dataset_coverage` | One row for the whole fact |
| `dim_registration_month` | One observed registration month |
| `analytics_monthly_registrations` | One registration month |
| `analytics_manufacturer_month` | `maker_clean` × registration month |
| `analytics_model_month` | `maker_clean` × `model_clean` × registration month |
| `analytics_state_month` | `state_category` × registration month |
| `analytics_fuel_month` | `fuel_category` × registration month |
| `analytics_vehicle_type_month` | `type` × registration month |
| `analytics_manufacturer` | `maker_clean` |
| `analytics_year_registrations` | One registration year |
| `analytics_like_for_like_year` | One comparison of the latest year with the previous year |

`dim_registration_month` contains months that appear in the fact. It does not invent months with no registrations.

The same `model_clean` under two manufacturers stays two rows. `analytics_model_month.registration_rank` ranks maker-model pairs inside the month by registration count. Equal counts share a rank.

## Phase 2 month fields

Phase 2 stores `registration_month` and `registration_month_number` as the same month number, 1 through 12. `registration_month_name` is already the English month name. Phase 3 uses those columns as stored. Phase 2 was not changed.

Reconciliation fails if any fact row has `registration_month` different from `registration_month_number`.

## Definitions

**Registration transaction.** One source row. It is not a sale, a purchase, a customer, or a direct measure of demand. `date_reg` may differ from a purchase date.

**Electric.** `is_electric` is 1 when `fuel` is `electric`.

**Hybrid.** `is_hybrid` is 1 when `fuel` is `hybrid_petrol` or `hybrid_diesel`. Those two fuel categories remain separate in `analytics_fuel_month`.

**Registration share.** Registrations in a group divided by all recorded registrations in the same period. A manufacturer-month share uses that month as the period. A manufacturer summary share uses every fact row as the period. Electric and hybrid shares on the manufacturer summary use that manufacturer's own registrations as the denominator. These are shares of recorded registrations.

**Rakan Niaga.** A JPJ partner registration channel. `state_category` keeps the value `Rakan Niaga`. It is not assigned to a geographic state.

**Partial year.** The latest registration year is partial when its maximum `date_reg` is before 31 December. On the current processed snapshot that year is 2026 and the maximum date is 2026-08-31. The rule is calculated from the data. It is not stored as a fixed year in the SQL.

## Year-over-year change

Absolute change is current registrations minus prior registrations. Percentage change is that difference divided by the prior registrations.

The percentage is null when the prior value is missing or zero.

`analytics_year_registrations` compares a year with the previous calendar year only when the later year runs through 31 December. For a partial latest year, `yoy_basis` is `withheld_partial_year` and the full-year change columns are null. That avoids comparing a partial year with a full previous year.

`analytics_like_for_like_year` is the comparison to use for a partial latest year. Its window is January through the last complete month of the latest year, for both that year and the previous year. When the latest date is the last calendar day of its month, that month is included. When the latest date falls before the last calendar day, that month is left out of both years. The comparison label says that this is not a full-year comparison.

Month-level views compare the same month number in the previous year. That change is withheld only for an incomplete latest month. Earlier months of a partial year keep their month-level comparison. A manufacturer with no registrations in the prior month gets a null change, not a change from zero.

## What this layer does not do

- It does not treat registrations as sales or demand.
- It does not infer why a month has a low registration count.
- It does not merge fuel categories.
- It does not map `Rakan Niaga` to a state.
- It does not remove `unknown` or `other`.
- It does not deduplicate source rows.
- It does not forecast, score anomalies, or build a dashboard.
