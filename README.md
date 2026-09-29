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

The 2026 file is a partial year. It is not treated as a full calendar year. The pipeline reports the latest `date_reg` it actually finds.

Identical source rows are retained. The files have no vehicle or transaction identifier, so matching rows can be separate registrations.

## Phase 1

Phase 1 downloads the official yearly Parquet files and validates them. Raw files in `data/raw/` are never edited. Measured counts are written to `data/quality/` and are not hard-coded.

Later phases (cleaning, SQL, exploratory analysis, forecasting, anomaly detection, and Power BI) are not part of this phase.

### Run

```bash
pip install -r requirements.txt
python -m src
```

Use `python -m src --force` to redownload a year that is already stored as readable Parquet. A failed download stops the run. An unreadable file is not kept as a successful download.

```bash
python -m pytest
```

## Layout

```text
data/raw/         official Parquet files, not committed
data/quality/     manifest and validation report
src/ingestion/    download
src/validation/   schema and quality checks
tests/            invariant tests
```
