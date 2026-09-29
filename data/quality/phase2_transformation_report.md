# Phase 2 transformation report

Status: **WARN**

The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.

## Reconciliation

- Raw rows: 15950189
- Processed rows: 15950189
- Earliest date_reg: 2000-01-02
- Latest date_reg: 2026-08-31
- Elapsed seconds: 50.208
- Electric rows: 131117
- Hybrid rows: 208646
- Rakan Niaga rows: 6746287

## Partitioning

data/processed/registrations/<year>/registrations.parquet

Each official file is already one registration year, and Phase 1 found no date_reg year outside its file. Writing one year at a time avoids a second in-memory copy of the full dataset. Concatenating every year previously failed with a memory allocation error. Year folders are plain directories rather than registration_year=<year> hive keys, because that key collides with the registration_year column stored in the file.

## Maker transformations

| Source | Analytical value | Rows | Reason |
| --- | --- | ---: | --- |
| `Mclaren` | `McLaren` | 9 | mapped case variant to the dominant spelling McLaren (332 trimmed rows); source maker preserved |
| `Bmw` | `BMW` | 1 | mapped case variant to the dominant spelling BMW (198083 trimmed rows); source maker preserved |

## Model transformations

| Source | Analytical value | Rows | Reason |
| --- | --- | ---: | --- |
| `E Advance ` | `E Advance` | 29 | trimmed surrounding whitespace; internal spacing preserved; source model preserved |
| `TF 160 ` | `TF 160` | 1 | trimmed surrounding whitespace; internal spacing preserved; source model preserved |

## Fuel categories

Source fuel codes were not merged.

| Value | Registration transactions |
| --- | ---: |
| petrol | 14403324 |
| greendiesel | 1062440 |
| hybrid_petrol | 205849 |
| electric | 131117 |
| diesel | 78130 |
| petrol_ng | 65641 |
| hybrid_diesel | 2797 |
| ng | 695 |
| petrol_lng | 85 |
| greendiesel_ng | 55 |
| diesel_ng | 23 |
| other | 20 |
| unknown | 7 |
| hydrogen | 3 |
| lng | 3 |

## Derived fields

- `maker_clean`: maker with surrounding whitespace removed. A case variant is mapped to the single most frequent spelling of that same case-folded name. The source maker column is unchanged.
- `model_clean`: model with surrounding whitespace removed. Internal spaces are kept. Models are not renamed, and Unknown is not converted to null.
- `fuel_category`: Exact copy of the source fuel code. greendiesel is not merged into diesel, and dual-fuel codes are not merged into petrol or diesel.
- `state_category`: Exact copy of the source state value. Rakan Niaga stays Rakan Niaga and is not assigned to a geographic state.
- `is_rakan_niaga`: 1 when state is exactly Rakan Niaga, otherwise 0.
- `is_electric`: 1 when fuel is exactly electric, otherwise 0. Maker and model are not used.
- `is_hybrid`: 1 when fuel is hybrid_petrol or hybrid_diesel, otherwise 0.
- `registration_year`: Calendar year of date_reg.
- `registration_month`: Calendar month of date_reg as an integer from 1 to 12.
- `registration_month_number`: Same value as registration_month. Both names are stored so either can be used.
- `registration_month_name`: English month name of date_reg, from a fixed list rather than the machine locale.
- `registration_quarter`: Calendar quarter of date_reg, from 1 to 4.
- `registration_year_month`: date_reg formatted as YYYY-MM.

## Limitations

- is_internal_combustion is not created. greendiesel, dual-fuel codes, hydrogen, natural gas, other, and unknown cannot be classified as internal combustion from this dataset without an extra assumption. Electric and hybrid flags are set only from explicit source fuel values.
- Rakan Niaga is a registration channel, not a geographic state.
- Low-volume months are observed registration periods. This dataset does not establish their cause.
- A latest year that ends before 31 December is partial. Earlier years that miss a single calendar day are not labelled partial.
- The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.

## Checks

- PASS `raw_files_unchanged`: Raw SHA-256 hashes were unchanged.
- PASS `row_count`: Processed rows equal raw rows: 15950189.
- PASS `source_columns_preserved`: date_reg, type, maker, model, colour, fuel, and state were copied unchanged.
- PASS `reconciliation`: Year, month, fuel, maker, state, and vehicle-type totals match the raw files.
- WARN `maker_standardisation`: maker analytical values differ for 10 rows: 'Mclaren' -> 'McLaren' (9), 'Bmw' -> 'BMW' (1).
- WARN `model_standardisation`: model analytical values differ for 30 rows: 'E Advance ' -> 'E Advance' (29), 'TF 160 ' -> 'TF 160' (1).
- PASS `fuel_classification`: fuel_category is an exact copy of fuel. No source fuel codes were merged.
- PASS `electric_flag`: is_electric rows: 131117. Source fuel electric rows: 131117.
- PASS `hybrid_flag`: is_hybrid rows: 208646. hybrid_petrol plus hybrid_diesel rows: 208646.
- PASS `rakan_niaga_channel`: Rakan Niaga remains a channel on 6746287 rows. state_category was not assigned to a geographic state.
- PASS `date_features`: registration_year, month, quarter, and year-month were derived from date_reg on every row.
- PASS `latest_year_retained`: Latest processed year 2026 retains its raw rows.
- PASS `unknown_values_retained`: Unknown model rows: 941. fuel unknown: 7. fuel other: 20. None were removed or nulled.
- WARN `partial_latest_year`: 2026 is partial through 2026-08-31. Its rows were retained and it is not a complete calendar year.
- WARN `low_volume_months`: Unusually low registration months were retained and not interpolated: 2020-04 (129), 2021-06 (2063). The dataset does not establish the cause.
- PASS `future_dates`: No processed file has date_reg after the run date 2026-09-29.
- PASS `internal_combustion_omitted`: is_internal_combustion is not created. greendiesel, dual-fuel codes, hydrogen, natural gas, other, and unknown cannot be classified as internal combustion from this dataset without an extra assumption. Electric and hybrid flags are set only from explicit source fuel values.
- PASS `duplicates_retained`: No registration transactions were deduplicated. Processed rows equal raw rows.
