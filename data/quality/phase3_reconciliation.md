# Phase 3 reconciliation

Status: **PASS**

Phase 3 reads the processed Parquet files through DuckDB views. It does not copy registration rows into a database table, and it does not modify Phase 2.

## Reconciliation

- Phase 2 rows: 15950189
- Phase 3 fact rows: 15950189
- Difference: 0
- Date range: 2000-01-02 through 2026-08-31

| Check | Expected | Actual | Difference | Status |
| --- | --- | --- | --- | --- |
| fact_row_count | 15950189 | 15950189 | 0 | PASS |
| parquet_footer_row_count | 15950189 | 15950189 | 0 | PASS |
| direct_parquet_row_count | 15950189 | 15950189 | 0 | PASS |
| date_minimum | 2000-01-02 | 2000-01-02 | 0 | PASS |
| date_maximum | 2026-08-31 | 2026-08-31 | 0 | PASS |
| year | 15950189 | 15950189 | 0 | PASS |
| month | 15950189 | 15950189 | 0 | PASS |
| fuel | 15950189 | 15950189 | 0 | PASS |
| state | 15950189 | 15950189 | 0 | PASS |
| vehicle_type | 15950189 | 15950189 | 0 | PASS |
| maker_source | 15950189 | 15950189 | 0 | PASS |
| maker_clean | 15950189 | 15950189 | 0 | PASS |
| electric | 131117 | 131117 | 0 | PASS |
| electric_fuel_flag | 131117 | 131117 | 0 | PASS |
| hybrid | 208646 | 208646 | 0 | PASS |
| hybrid_fuel_composition | 208646 | 208646 | 0 | PASS |
| rakan_niaga | 6746287 | 6746287 | 0 | PASS |
| rakan_niaga_flag | 6746287 | 6746287 | 0 | PASS |
| null_required_fields | 0 | 0 | 0 | PASS |
| month_number_fields | 0 | 0 | 0 | PASS |
| monthly_view | 15950189 | 15950189 | 0 | PASS |
| model_view | 15950189 | 15950189 | 0 | PASS |
| manufacturer_month_view | 15950189 | 15950189 | 0 | PASS |
| manufacturer_view | 15950189 | 15950189 | 0 | PASS |
| state_view | 15950189 | 15950189 | 0 | PASS |
| fuel_view | 15950189 | 15950189 | 0 | PASS |
| vehicle_type_view | 15950189 | 15950189 | 0 | PASS |
| model_groups | 80781 | 80781 | 0 | PASS |
| monthly_groups | 320 | 320 | 0 | PASS |
| manufacturer_registration_share | 0 | 3.3306690738754696e-16 | 3.3306690738754696e-16 | PASS |
| model_grain | [] | [] | 0 | PASS |
| surrogate_transaction_id | [] | [] | 0 | PASS |
| partial_years | [2026] | [2026] | 0 | PASS |
| full_year_yoy | [] | [] | 0 | PASS |
| like_for_like_through_month | 8 | 8 | 0 | PASS |
| like_for_like_latest | 566616 | 566616 | 0 | PASS |
| like_for_like_prior | 551365 | 551365 | 0 | PASS |
| like_for_like_label | True | True | 0 | PASS |
| latest_month_yoy | True | True | 0 | PASS |
| dimension_grains | 0 | 0 | 0 | PASS |

## Like-for-like period

January through August 2026 compared with January through August 2025. This is not a full-year comparison.

- Latest period registrations: 566616
- Prior period registrations: 551365
- Absolute change: 15251
- Percentage change: 0.02766044271943268

## Performance

- View build seconds: 0.123
- Reconciliation seconds: 3.199
- All registration rows loaded into Python memory: no

## Limitations

- Registration transactions are not vehicle sales, purchases, or a direct measure of demand.
- date_reg may differ from a purchase date.
- The latest year is partial when it ends before 31 December. Full-year change for that year is null.
- Rakan Niaga is not geographic state data and is not assigned to a state.
- Unknown, other, and the source fuel categories are retained. Fuel categories are not merged.
- Registration counts alone do not support a causal conclusion, including for months with unusually low counts.
