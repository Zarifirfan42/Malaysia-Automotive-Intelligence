# Phase 2 — cleaning and transformation

Phase 2 reads `data/raw/` and writes `data/processed/`. The raw Parquet files stay unchanged. Identical registration rows are kept, because the source has no vehicle or transaction identifier.

The processed layer standardizes analytical representations while preserving the original JPJ source fields for traceability.

## Layout

```text
data/processed/registrations/<year>/registrations.parquet
```

Each official file is one registration year. Phase 2 writes that year on its own instead of concatenating every year in memory. A full concatenation previously failed with a memory allocation error. The folders are plain year directories. A hive path such as `registration_year=2000` would collide with the `registration_year` column stored in the file.

## Rules

| Output | Rule |
| --- | --- |
| `maker_clean` | Trim surrounding whitespace. If several values differ only by case, use the spelling with the higher row count. Equal counts stop the run. Other manufacturers are not merged. |
| `model_clean` | Trim surrounding whitespace only. Internal spaces stay. `Unknown` stays `Unknown`. |
| `fuel_category` | Copy of `fuel`. `greendiesel` is not diesel. Dual-fuel codes are not folded into petrol or diesel. |
| `state_category` | Copy of `state`. |
| `is_rakan_niaga` | 1 when `state` is exactly `Rakan Niaga`, otherwise 0. This is a registration channel, not a geographic state. |
| `is_electric` | 1 only when `fuel` is `electric`. |
| `is_hybrid` | 1 only when `fuel` is `hybrid_petrol` or `hybrid_diesel`. |
| `registration_year` | Year of `date_reg`. |
| `registration_month` | Month number of `date_reg`, from 1 to 12. |
| `registration_month_number` | Same value as `registration_month`. |
| `registration_month_name` | English month name from a fixed list. |
| `registration_quarter` | Calendar quarter of `date_reg`. |
| `registration_year_month` | `YYYY-MM` from `date_reg`. |

`is_internal_combustion` is not created. `greendiesel`, dual-fuel codes, hydrogen, natural gas, `other`, and `unknown` do not justify that label.

No dates are imputed. Rows in a partial latest year stay in the file. A year is partial only when it is the latest year and its maximum `date_reg` is before 31 December. Low-volume months are reported and retained. Their cause is not claimed from this dataset.

Changes that actually alter an analytical value are listed in `data/quality/transformation_mapping.csv`. Unchanged fuel and state values are not listed there, because no transformation was applied.

## Run

```bash
python -m src.transformation
```

The command stops if the processed row count or the source-field totals differ from the raw files. Status values are PASS, WARN, and FAIL. WARN means the data were kept and the condition is visible. FAIL means the run did not publish a reconciled processed layer.
