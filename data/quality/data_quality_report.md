# Phase 1 data-quality report

Status: **WARN**

Figures in this report were calculated from the downloaded files during this run.

## Dataset

- Project: Malaysia Automotive Intelligence
- Dataset: Car Registration Transactions
- Dataset ID: registration_transactions_car
- Publisher: Jabatan Pengangkutan Jalan (JPJ) / Ministry of Transport Malaysia
- Catalogue: https://data.gov.my/data-catalogue/registration_transactions_car
- Licence: CC BY 4.0
- Started: 2026-09-29T09:23:45.251177+00:00
- Finished: 2026-09-29T09:27:10.734734+00:00

## Interpretation

- These are registration transactions, not vehicle sales, purchases, customers, or demand.
- date_reg is the registration date and may differ from a purchase date.
- Rakan Niaga is retained as a registration channel and is not treated as a geographic state.
- greendiesel remains a separate source fuel category.
- The latest yearly file may be a partial year.

## Coverage

- Files profiled: 27
- Total registration transactions: 15950189
- Earliest date_reg: 2000-01-02
- Latest date_reg: 2026-08-31
- Observed months: 320
- Missing months inside the span: 0
- Distinct dates: 8973
- Calendar days in the span with no rows: 766

## Rows by year

| Value | Registration transactions |
| --- | ---: |
| 2000 | 352355 |
| 2001 | 406148 |
| 2002 | 446610 |
| 2003 | 431669 |
| 2004 | 489224 |
| 2005 | 566565 |
| 2006 | 475487 |
| 2007 | 480644 |
| 2008 | 551099 |
| 2009 | 539187 |
| 2010 | 608561 |
| 2011 | 607491 |
| 2012 | 633063 |
| 2013 | 664711 |
| 2014 | 677214 |
| 2015 | 678031 |
| 2016 | 588054 |
| 2017 | 579618 |
| 2018 | 608982 |
| 2019 | 612963 |
| 2020 | 552345 |
| 2021 | 530046 |
| 2022 | 744752 |
| 2023 | 832329 |
| 2024 | 856237 |
| 2025 | 870188 |
| 2026 | 566616 |

## Rows by fuel

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

## Rows by vehicle type

| Value | Registration transactions |
| --- | ---: |
| motokar | 11062335 |
| jip | 1787309 |
| motokar_pelbagai_utiliti | 1548313 |
| pick_up | 949877 |
| window_van | 602355 |

## Rows by state or channel

| Value | Registration transactions |
| --- | ---: |
| Rakan Niaga | 6746287 |
| W.P. Kuala Lumpur | 3349968 |
| Johor | 1119732 |
| Pulau Pinang | 817469 |
| Selangor | 725274 |
| Sarawak | 676587 |
| Sabah | 548696 |
| Perak | 507641 |
| Pahang | 277157 |
| Melaka | 253762 |
| Kedah | 248513 |
| Kelantan | 232337 |
| Negeri Sembilan | 223704 |
| Terengganu | 156035 |
| W.P. Labuan | 43796 |
| Perlis | 22897 |
| W.P. Putrajaya | 334 |

## Duplicate signatures

Identical source rows were counted and retained. There is no vehicle or transaction identifier, so matching rows are indistinguishable registration transactions rather than rows to delete. Yearly signature counts are added together because date_reg is part of the signature and each date_reg year matches its file year.

- Distinct signatures: 4816249
- Extra copies retained: 11133940
- Rows that share a signature: 13046885
- Largest identical signature: 937

Full month and maker counts are in `data/quality/data_quality_report.json`.

## Checks

- PASS `positive_row_count`: Profiled registration transactions: 15950189.
- PASS `raw_files_unchanged`: Raw Parquet hashes were unchanged by validation.
- PASS `nulls`: Null counts by column are recorded in null_profile.
- PASS `blanks`: Blank-string counts by column are recorded in blank_profile.
- PASS `year_consistency`: Rows whose date_reg year differs from the file year: 0.
- PASS `missing_months`: No calendar month is missing between the first and last observed month.
- PASS `category_reconciliation`: Fuel, type, state, maker, and year counts each sum to the profiled row total.
- PASS `duplicates`: Identical source rows were counted and retained. There is no vehicle or transaction identifier, so matching rows are indistinguishable registration transactions rather than rows to delete. Yearly signature counts are added together because date_reg is part of the signature and each date_reg year matches its file year.
- WARN `partial_latest_year`: The latest date_reg is 2026-08-31. 2026 is a partial year and is not treated as a full calendar year.
- WARN `low_volume_months`: Months below 10% of the median monthly count (4866.3): 2020-04 (129), 2021-06 (2063).
- PASS `missing_days`: 766 calendar days between 2000-01-02 and 2026-08-31 have no registration rows. Weekend and holiday gaps are expected and are not treated as missing files.
- PASS `rakan_niaga`: Rakan Niaga accounts for 6746287 registration transactions and is retained as a channel, not a geographic state.
- PASS `greendiesel`: greendiesel accounts for 1062440 registration transactions and is retained as its own fuel code.
- WARN `model_whitespace`: Model values with surrounding whitespace: 30 rows.
- WARN `maker_spelling`: Maker labels that collide after case-folding are reported and were not merged.
- WARN `unknown_model`: Model values case-folding to 'unknown': 941 rows. They were not removed.
- WARN `residual_fuel_codes`: Fuel code other=20, unknown=7. These source codes were retained.
- PASS `unexpected_raw_files`: No unexpected Parquet files were found in data/raw.
