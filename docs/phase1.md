# Phase 1 — acquisition and validation

Phase 1 establishes a raw-data foundation. It does not clean categories, build a SQL model, or fit a forecast.

## Command

From the project root:

```bash
python -m src
```

The command downloads `cars_2000.parquet` through `cars_2026.parquet` from `storage.data.gov.my`, then writes:

- `data/quality/source_manifest.json`
- `data/quality/data_quality_report.json`
- `data/quality/data_quality_report.md`

## Status values

| Status | Meaning |
| --- | --- |
| PASS | The check holds for this download. |
| WARN | The file is usable, and the condition should stay visible. Examples: a partial latest year, low-volume months, spelling variants, whitespace, or rare fuel codes. Nothing in the raw file is changed. |
| FAIL | The schema contract, file readability, year alignment, or row reconciliation failed. The run stops rather than adapting the schema. |

The process exit code is 0 for PASS or WARN, and 1 for FAIL or a download error.

## Rules that are reported, not fixed

- `Rakan Niaga` stays a channel.
- `greendiesel` stays a separate fuel code.
- Duplicate signatures are counted and kept.
- `Unknown` models, `other` / `unknown` fuel codes, surrounding whitespace, and maker case variants are reported.
- A month is flagged when its row count is below 10% of the median monthly count. That threshold is a rule in `src/config.py`, not a stored national total.
