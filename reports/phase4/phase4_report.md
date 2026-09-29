# Phase 4 — exploratory data analysis and statistical analysis

Status: **PASS**

## 1. Objective

The question for this phase is which patterns, distributions, and differences are visible in Malaysian vehicle registration transactions.
The results are a base for later forecasting, anomaly detection, and BI. This phase does not forecast, score anomalies, or build a dashboard.

## 2. Dataset

The source is the official JPJ car registration transaction file published through data.gov.my.
Phase 4 reads the Phase 3 DuckDB views, which read the processed Parquet files. Raw files and processed files are not rewritten.

- Recorded registrations: 15,950,189
- Earliest registration date: 2000-01-02
- Latest registration date: 2026-08-31
- Registration years: 27
- Observed months: 320
- Manufacturers (`maker_clean`): 200
- Model names (`model_clean`): 1660
- Manufacturer-model pairs: 1886
- Fuel categories: 15
- Vehicle types: 5
- State/channel categories: 17
- Electric registrations: 131,117
- Hybrid registrations: 208,646
- Of the hybrid registrations, hybrid_petrol is 205,849 and hybrid_diesel is 2,797

A row is one registration transaction. Registration counts are not vehicle sales, purchases, customers, revenue, or a direct measure of demand.

## 3. Methodology

DuckDB aggregates the Phase 3 views. Python receives those aggregates. The registration fact is not loaded into pandas.
Descriptive shares are group registrations divided by all recorded registrations in the stated period. The name used here is share of recorded registrations.
The Herfindahl-Hirschman index (HHI) is the sum of squared shares. Equal shares across n groups give 1/n. A single group gives 1. The 0–10,000 scale is the same index multiplied by 10,000. It describes concentration of recorded registrations. It is not a sales-market definition.
The primary tests use a Bonferroni adjustment. The family size is 4 and the adjusted threshold is 0.0125.
The observation in the month and year tests is a month or a complete year. That choice avoids treating the census of transactions as if each row were an independent draw.
The chi-square test does count transactions. Its p-value is therefore easy to make small, and the report reads Cramér's V and the share changes alongside it.
Effect-size labels use conventional benchmarks as a reading aid: epsilon-squared cuts at 0.01, 0.06, and 0.14; absolute Spearman rho cuts at 0.10, 0.30, and 0.50; Cramér's V cuts depend on the smaller degrees of freedom.

## 4. Temporal findings

Observed months: 320. Mean monthly registrations: 49,844.3. Median: 48,663.0. Standard deviation of the observed months: 14,091.1.
Lowest month in the series and highest month in the series are identified from these 320 months. Coefficient of variation: 0.2827.
Months below 10% of the median monthly count: 2020-04 (129), 2021-06 (2,063).
These months have unusually low recorded registration volume and may materially affect aggregate statistics. The dataset does not establish why they are low.
Keeping them, the mean is 49,844.3 and the standard deviation is 14,091.1. Setting them aside only as a sensitivity check, the mean is 50,150.9 and the standard deviation is 13,592.7. The primary figures keep them.
Median month-to-month percentage change: 0.2%. The largest month-to-month decline lands on 2020-04.
Partial registration years: 2026. Full-year percentage change is withheld for those years.
Like-for-like comparison: January-August 2026 has 566,616 recorded registrations, against 551,365 in January-August 2025. Absolute change: 15,251. Percentage change: 2.8%. This is not a full-year comparison.
The coefficient of variation of the mean within-year month shares, using complete years only, is 0.07246.
Calendar-month averages and the Kruskal-Wallis test below are the evidence about a repeating month pattern. The word seasonality is not used as a label for that evidence.

| Year | Recorded registrations | Full-year absolute change | Full-year percentage change | Basis |
| --- | ---: | ---: | ---: | --- |
| 2000 | 352,355 |  |  | no_prior_year |
| 2001 | 406,148 | 53,793 | 15.3% | full_year |
| 2002 | 446,610 | 40,462 | 10.0% | full_year |
| 2003 | 431,669 | -14,941 | -3.3% | full_year |
| 2004 | 489,224 | 57,555 | 13.3% | full_year |
| 2005 | 566,565 | 77,341 | 15.8% | full_year |
| 2006 | 475,487 | -91,078 | -16.1% | full_year |
| 2007 | 480,644 | 5,157 | 1.1% | full_year |
| 2008 | 551,099 | 70,455 | 14.7% | full_year |
| 2009 | 539,187 | -11,912 | -2.2% | full_year |
| 2010 | 608,561 | 69,374 | 12.9% | full_year |
| 2011 | 607,491 | -1,070 | -0.2% | full_year |
| 2012 | 633,063 | 25,572 | 4.2% | full_year |
| 2013 | 664,711 | 31,648 | 5.0% | full_year |
| 2014 | 677,214 | 12,503 | 1.9% | full_year |
| 2015 | 678,031 | 817 | 0.1% | full_year |
| 2016 | 588,054 | -89,977 | -13.3% | full_year |
| 2017 | 579,618 | -8,436 | -1.4% | full_year |
| 2018 | 608,982 | 29,364 | 5.1% | full_year |
| 2019 | 612,963 | 3,981 | 0.7% | full_year |
| 2020 | 552,345 | -60,618 | -9.9% | full_year |
| 2021 | 530,046 | -22,299 | -4.0% | full_year |
| 2022 | 744,752 | 214,706 | 40.5% | full_year |
| 2023 | 832,329 | 87,577 | 11.8% | full_year |
| 2024 | 856,237 | 23,908 | 2.9% | full_year |
| 2025 | 870,188 | 13,951 | 1.6% | full_year |
| 2026 | 566,616 |  |  | withheld_partial_year |

## 5. Manufacturer findings

Manufacturers: 200. Top 5 share of recorded registrations: 85.0%. Top 10 share: 91.9%.
HHI: 0.2014 (2,014.1 on a 0–10,000 scale).
The January-August comparison below is for the ten largest manufacturers. A blank percentage means the prior window has no recorded registrations for that manufacturer.

| Manufacturer | Recorded registrations | Share |
| --- | ---: | ---: |
| Perodua | 5,376,247 | 33.7% |
| Proton | 3,672,252 | 23.0% |
| Toyota | 2,455,785 | 15.4% |
| Honda | 1,453,848 | 9.1% |
| Nissan | 595,758 | 3.7% |
| Mitsubishi | 269,597 | 1.7% |
| Mercedes Benz | 264,471 | 1.7% |
| Mazda | 203,837 | 1.3% |
| BMW | 198,084 | 1.2% |
| Ford | 160,691 | 1.0% |
| Naza | 139,421 | 0.9% |
| Kia | 122,619 | 0.8% |
| Isuzu | 122,069 | 0.8% |
| Hyundai | 107,230 | 0.7% |
| Volkswagen | 94,986 | 0.6% |

| Manufacturer | Jan-Aug 2025 | Jan-Aug 2026 | Absolute change | Percentage change |
| --- | ---: | ---: | ---: | ---: |
| Perodua | 231,700 | 219,559 | -12,141 | -5.2% |
| Proton | 97,578 | 135,169 | 37,591 | 38.5% |
| Toyota | 80,479 | 72,942 | -7,537 | -9.4% |
| Honda | 46,674 | 37,194 | -9,480 | -20.3% |
| Nissan | 4,340 | 2,981 | -1,359 | -31.3% |
| Mitsubishi | 9,207 | 8,824 | -383 | -4.2% |
| Mercedes Benz | 6,291 | 4,979 | -1,312 | -20.9% |
| Mazda | 5,582 | 7,852 | 2,270 | 40.7% |
| BMW | 5,084 | 3,989 | -1,095 | -21.5% |
| Ford | 3,382 | 1,791 | -1,591 | -47.0% |

Largest electric registration counts, with each manufacturer's electric share of its own registrations:

| Manufacturer | Registrations in this class | Share of that manufacturer's registrations |
| --- | ---: | ---: |
| BYD | 34,954 | 100.0% |
| Proton | 30,750 | 0.8% |
| Tesla | 18,393 | 100.0% |
| BMW | 8,596 | 4.3% |
| Chery | 5,625 | 6.3% |
| Zeekr | 5,592 | 100.0% |
| Xpeng | 2,853 | 100.0% |
| Mini | 2,528 | 9.4% |
| Mercedes Benz | 2,394 | 0.9% |
| Volvo | 2,388 | 7.1% |

Largest hybrid registration counts:

| Manufacturer | Registrations in this class | Share of that manufacturer's registrations |
| --- | ---: | ---: |
| Honda | 63,108 | 4.3% |
| Toyota | 57,227 | 2.3% |
| Mercedes Benz | 30,121 | 11.4% |
| Nissan | 16,202 | 2.7% |
| Great Wall | 9,921 | 50.5% |
| Volvo | 8,934 | 26.7% |
| Chery | 6,057 | 6.7% |
| Proton | 5,576 | 0.2% |
| Lexus | 4,154 | 8.3% |
| Hyundai | 2,361 | 2.2% |

## 6. Model findings

Model names: 1660. Manufacturer-model pairs: 1886.
Model names that appear under more than one manufacturer: 123. Counts below keep `maker_clean` with `model_clean`.
Top 10 manufacturer-model pairs account for 46.1% of recorded registrations. Pair HHI: 0.03075.

| Manufacturer | Model | Recorded registrations | Share |
| --- | --- | ---: | ---: |
| Perodua | Myvi | 1,599,487 | 10.0% |
| Proton | Saga | 1,049,151 | 6.6% |
| Perodua | Axia | 882,563 | 5.5% |
| Perodua | Bezza | 709,433 | 4.4% |
| Toyota | Vios | 603,665 | 3.8% |
| Perodua | Alza | 575,724 | 3.6% |
| Honda | City | 538,471 | 3.4% |
| Proton | Wira | 482,671 | 3.0% |
| Toyota | Hilux | 459,241 | 2.9% |
| Proton | Persona | 458,291 | 2.9% |
| Perodua | Kancil | 450,287 | 2.8% |
| Perodua | Viva | 448,078 | 2.8% |
| Proton | Iswara | 370,423 | 2.3% |
| Proton | Waja | 295,828 | 1.9% |
| Honda | Civic | 212,412 | 1.3% |

Largest electric manufacturer-model pairs:

| Manufacturer | Model | Electric registrations |
| --- | --- | ---: |
| Proton | e.MAS 5 | 18,050 |
| BYD | Atto 3 | 13,255 |
| Proton | e.MAS 7 | 12,681 |
| Tesla | Model 3 | 9,335 |
| Tesla | Model Y | 8,945 |
| BYD | Sealion | 6,551 |
| BYD | Seal | 4,203 |
| Zeekr | 7X | 3,959 |
| BMW | iX | 2,897 |
| BYD | Dolphin | 2,831 |

Largest hybrid manufacturer-model pairs:

| Manufacturer | Model | Hybrid registrations |
| --- | --- | ---: |
| Toyota | Corolla Cross | 32,021 |
| Honda | HR-V | 15,437 |
| Honda | City | 15,205 |
| Nissan | Serena | 14,551 |
| Mercedes Benz | C-Class | 12,181 |
| Honda | Jazz | 11,573 |
| Toyota | Camry | 10,142 |
| Great Wall | Haval H6 | 7,849 |
| Toyota | Prius | 7,671 |
| Mercedes Benz | E-Class | 7,529 |

## 7. Vehicle-type findings

Vehicle-type HHI: 0.508. Shares use the national registration total.

| Vehicle type | Recorded registrations | Share |
| --- | ---: | ---: |
| motokar | 11,062,335 | 69.4% |
| jip | 1,787,309 | 11.2% |
| motokar_pelbagai_utiliti | 1,548,313 | 9.7% |
| pick_up | 949,877 | 6.0% |
| window_van | 602,355 | 3.8% |

Yearly type counts for complete years are in the vehicle-type trend chart. The partial year is omitted from that line chart.

## 8. Fuel findings

`greendiesel` registrations: 1,062,440. `diesel` registrations: 78,130. These codes are not combined.
Fuel-category HHI: 0.8202. A high value means the counts concentrate in few source codes, which the table shows directly.

| Fuel category | Recorded registrations | Share |
| --- | ---: | ---: |
| petrol | 14,403,324 | 90.3% |
| greendiesel | 1,062,440 | 6.7% |
| hybrid_petrol | 205,849 | 1.3% |
| electric | 131,117 | 0.8% |
| diesel | 78,130 | 0.5% |
| petrol_ng | 65,641 | 0.4% |
| hybrid_diesel | 2,797 | 0.0% |
| ng | 695 | 0.0% |
| petrol_lng | 85 | 0.0% |
| greendiesel_ng | 55 | 0.0% |
| diesel_ng | 23 | 0.0% |
| other | 20 | 0.0% |
| unknown | 7 | 0.0% |
| hydrogen | 3 | 0.0% |
| lng | 3 | 0.0% |

Share of recorded registrations in 2017-2019 and 2023-2025. The change is in percentage points.

| Fuel category | Earlier share | Recent share | Percentage-point change |
| --- | ---: | ---: | ---: |
| petrol | 90.7% | 87.1% | -3.6 |
| electric | 0.0% | 3.1% | 3.1 |
| hybrid_petrol | 1.3% | 3.0% | 1.8 |
| greendiesel | 7.5% | 6.2% | -1.3 |
| diesel | 0.5% | 0.6% | 0.1 |
| petrol_ng | 0.0% | 0.0% | -0.0 |
| petrol_lng | 0.0% | 0.0% | -0.0 |
| other | 0.0% | 0.0% | -0.0 |
| hydrogen | 0.0% | 0.0% | -0.0 |
| greendiesel_ng | 0.0% | 0.0% | 0.0 |
| ng | 0.0% | 0.0% | -0.0 |
| diesel_ng | 0.0% | 0.0% | 0.0 |
| hybrid_diesel | 0.0% | 0.0% | -0.0 |

## 9. EV and hybrid findings

Electric registrations: 131,117. Hybrid registrations: 208,646.
Hybrid registrations consist of 205,849 hybrid_petrol and 2,797 hybrid_diesel.
The first complete year with an electric registration is 2009.
In 2025, the electric share of that year's recorded registrations is 5.1% and the hybrid share is 3.6%.
January-August 2026 electric registrations: 47,508, against 23,396 in January-August 2025.
January-August 2026 hybrid registrations: 34,733, against 19,545 in January-August 2025.
These shares are shares of recorded registrations classified as electric or hybrid. They are not described here as consumer adoption.

Electric registrations by state or channel, and by manufacturer, are in the state table and the manufacturer section.

## 10. State and channel findings

National recorded registrations, including Rakan Niaga: 15,950,189.
Rakan Niaga registrations: 6,746,287 (42.3% of the national total).
Geographic registration offices, excluding Rakan Niaga: 9,203,902. This subtotal is not the national total.
HHI across all channels: 0.2379. HHI across geographic offices only: 0.1773.

| State or channel | Recorded registrations | Share of national total | Electric registrations | Electric share of this category | Hybrid registrations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rakan Niaga | 6,746,287 | 42.3% | 100,250 | 1.5% | 134,216 |
| W.P. Kuala Lumpur | 3,349,968 | 21.0% | 14,672 | 0.4% | 38,566 |
| Johor | 1,119,732 | 7.0% | 2,824 | 0.3% | 8,513 |
| Pulau Pinang | 817,469 | 5.1% | 2,389 | 0.3% | 6,131 |
| Selangor | 725,274 | 4.5% | 5,070 | 0.7% | 6,585 |
| Sarawak | 676,587 | 4.2% | 1,013 | 0.1% | 2,755 |
| Sabah | 548,696 | 3.4% | 1,061 | 0.2% | 2,025 |
| Perak | 507,641 | 3.2% | 968 | 0.2% | 2,740 |
| Pahang | 277,157 | 1.7% | 567 | 0.2% | 1,142 |
| Melaka | 253,762 | 1.6% | 760 | 0.3% | 1,799 |
| Kedah | 248,513 | 1.6% | 603 | 0.2% | 1,112 |
| Kelantan | 232,337 | 1.5% | 263 | 0.1% | 824 |
| Negeri Sembilan | 223,704 | 1.4% | 439 | 0.2% | 1,345 |
| Terengganu | 156,035 | 1.0% | 144 | 0.1% | 592 |
| W.P. Labuan | 43,796 | 0.3% | 23 | 0.1% | 87 |
| Perlis | 22,897 | 0.1% | 70 | 0.3% | 213 |
| W.P. Putrajaya | 334 | 0.0% | 1 | 0.3% | 1 |

Geographic offices only. Shares in this second table use the geographic subtotal as the denominator.

| Registration office | Recorded registrations | Share of geographic subtotal |
| --- | ---: | ---: |
| W.P. Kuala Lumpur | 3,349,968 | 36.4% |
| Johor | 1,119,732 | 12.2% |
| Pulau Pinang | 817,469 | 8.9% |
| Selangor | 725,274 | 7.9% |
| Sarawak | 676,587 | 7.4% |
| Sabah | 548,696 | 6.0% |
| Perak | 507,641 | 5.5% |
| Pahang | 277,157 | 3.0% |
| Melaka | 253,762 | 2.8% |
| Kedah | 248,513 | 2.7% |
| Kelantan | 232,337 | 2.5% |
| Negeri Sembilan | 223,704 | 2.4% |
| Terengganu | 156,035 | 1.7% |
| W.P. Labuan | 43,796 | 0.5% |
| Perlis | 22,897 | 0.2% |
| W.P. Putrajaya | 334 | 0.0% |

## 11. Statistical tests

### Kruskal-Wallis: calendar_month_volume

- Research question: Do recorded monthly registration volumes differ by calendar month?
- Null hypothesis: The distribution of year-month registration counts is the same for every calendar month.
- Alternative hypothesis: At least one calendar month has a different distribution.
- Variables: Response: registration count for one year-month. Factor: calendar month number.
- Test: Kruskal-Wallis
- Assumptions: Each observation is one year-month, not one registration transaction. The test does not assume a normal distribution. Year-months are treated as separate observations, although successive years are not fully independent. Low-volume months stay in this primary test.
- Sample size: 320
- Statistic: 21.92
- p-value: 0.0250
- Bonferroni-adjusted p-value: 0.0999
- Effect size (epsilon_squared): 0.06872 (medium)
- Confidence interval: not calculated
- Result: The null hypothesis is not rejected at the Bonferroni-adjusted 5% level.
- Interpretation: The null hypothesis is not rejected at the Bonferroni-adjusted 5% level. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: A difference between month distributions can reflect level changes across eras as well as a repeating within-year pattern. The year-normalized month shares are the descriptive check for a within-year pattern. This is not an anomaly-detection result.

### Kruskal-Wallis sensitivity: calendar_month_volume_sensitivity

- Research question: Does the calendar-month comparison change if the low-volume months are set aside?
- Null hypothesis: The distribution of the remaining year-month counts is the same for every calendar month.
- Alternative hypothesis: At least one calendar month still has a different distribution.
- Variables: Same as the primary calendar-month test, after removing months below 10% of the median monthly count.
- Test: Kruskal-Wallis sensitivity
- Assumptions: This is a sensitivity check. It is not in the Bonferroni family and it does not remove the months from the dataset.
- Sample size: 318
- Statistic: 21.87
- p-value: 0.0254
- Bonferroni-adjusted p-value: not calculated
- Effect size (epsilon_squared): 0.06899 (medium)
- Confidence interval: not calculated
- Result: The unadjusted p-value is below 5%. This test is outside the Bonferroni family. The effect size is medium.
- Interpretation: The unadjusted p-value is below 5%. This test is outside the Bonferroni family. The effect size is medium. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: Setting unusual months aside changes the question being asked. The primary result keeps those months.

### Spearman rank correlation: electric_share_trend

- Research question: Does the annual share of recorded registrations classified as electric change monotonically across complete years?
- Null hypothesis: The Spearman rank correlation between year and annual electric registration share is zero.
- Alternative hypothesis: The rank correlation is not zero.
- Variables: Paired observations are complete registration years. The share is electric registrations divided by that year's registrations.
- Test: Spearman rank correlation
- Assumptions: The correlation describes a monotonic association. Partial years are excluded. Years are ordered but are not a random sample from a larger population of years.
- Sample size: 26
- Statistic: 0.9464
- p-value: 2.821e-13
- Bonferroni-adjusted p-value: 1.128e-12
- Effect size (absolute_spearman_rho): 0.9464 (large)
- Confidence interval: [0.8826, 0.976]
- Result: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large.
- Interpretation: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: A rank correlation with year does not identify a cause. It does not estimate a future share.

### Spearman rank correlation: hybrid_share_trend

- Research question: Does the annual share of recorded registrations classified as hybrid change monotonically across complete years?
- Null hypothesis: The Spearman rank correlation between year and annual hybrid registration share is zero.
- Alternative hypothesis: The rank correlation is not zero.
- Variables: Paired observations are complete registration years. Hybrid means hybrid_petrol or hybrid_diesel. Those fuel codes stay separate in the fuel tables.
- Test: Spearman rank correlation
- Assumptions: Same design as the electric-share correlation. A partial latest year is excluded.
- Sample size: 26
- Statistic: 0.862
- p-value: 1.524e-08
- Bonferroni-adjusted p-value: 6.097e-08
- Effect size (absolute_spearman_rho): 0.862 (large)
- Confidence interval: [0.7126, 0.9366]
- Result: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large.
- Interpretation: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: A rank correlation with year does not identify a cause and is not a forecast.

### Spearman rank correlation: volume_and_electric_share

- Research question: Are annual registration volume and annual electric registration share associated across complete years?
- Null hypothesis: The Spearman rank correlation between annual registration count and annual electric share is zero.
- Alternative hypothesis: The rank correlation is not zero.
- Variables: Complete years only. Volume is the annual registration count. Electric share uses that same year's count as the denominator.
- Test: Spearman rank correlation
- Assumptions: Two-sided rank correlation. This association is not in the Bonferroni family because volume and electric share can move together through a shared time trend.
- Sample size: 26
- Statistic: 0.7697
- p-value: 4.286e-06
- Bonferroni-adjusted p-value: not calculated
- Effect size (absolute_spearman_rho): 0.7697 (large)
- Confidence interval: [0.5448, 0.8913]
- Result: The unadjusted p-value is below 5%. This test is outside the Bonferroni family. The effect size is large.
- Interpretation: The unadjusted p-value is below 5%. This test is outside the Bonferroni family. The effect size is large. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: An association between volume and electric share is not evidence that one produces the other. Both can follow the same time order.

### Chi-square test of independence: fuel_composition_periods

- Research question: Does the fuel-category composition of recorded registrations differ between 2017-2019 and 2023-2025?
- Null hypothesis: Fuel category and period are independent in the included categories.
- Alternative hypothesis: Fuel category and period are not independent.
- Variables: Counts of registration transactions in two windows of complete years. Each window is three years. The windows are 2017-2019 and the latest three complete years when both exist. 2020 and 2021, which contain the low-volume months, are outside both windows. The partial latest year is outside both windows.
- Test: Chi-square test of independence
- Assumptions: Expected counts must be at least 5. Categories that break that rule are omitted from the test and listed. They remain in the descriptive fuel table. No continuity correction is applied. Omitted from the test: diesel_ng, ng, hydrogen, greendiesel_ng, other.
- Sample size: 4360298
- Statistic: 75,499.9
- p-value: 0.000e+00
- Bonferroni-adjusted p-value: 0.000e+00
- Effect size (cramers_v): 0.1316 (small)
- Confidence interval: not calculated
- Result: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is small.
- Interpretation: The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is small. Statistical significance is separate from practical importance. The effect-size label uses conventional benchmarks only as a reading aid.
- Limitation: The sample size is a count of registration transactions, so a small composition difference can produce a very small p-value. Practical reading uses Cramér's V and the change in shares. The test does not say why the composition differs, and it does not merge the omitted fuel codes into another code.

## 12. Key evidence-based findings

- Descriptive finding: the analytical layer contains 15,950,189 recorded registrations from 2000-01-02 through 2026-08-31.
- Descriptive finding: January-August 2026 has 566,616 recorded registrations, compared with 551,365 in January-August 2025 (2.8%). Full-year 2026 is not compared with full-year 2025.
- Descriptive finding: the five largest manufacturers account for 85.0% of recorded registrations, and the ten largest account for 91.9%.
- Descriptive finding: petrol, greendiesel, and diesel remain separate. greendiesel has 1,062,440 registrations and diesel has 78,130.
- Descriptive finding: 131,117 registrations are classified as electric and 208,646 as hybrid. In 2025, those shares of that year's registrations are 5.1% and 3.6%.
- Descriptive finding: Rakan Niaga accounts for 42.3% of national recorded registrations and is reported apart from geographic offices.
- Statistical finding (calendar_month_volume): The null hypothesis is not rejected at the Bonferroni-adjusted 5% level.
- Statistical finding (electric_share_trend): The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large.
- Statistical finding (hybrid_share_trend): The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is large.
- Statistical finding (fuel_composition_periods): The null hypothesis is rejected at the Bonferroni-adjusted 5% level. The effect size is small.
- Interpretation: the concentration figures describe how recorded registrations are distributed across manufacturers, model pairs, fuel codes, and channels. They do not identify a sales leader or a cause.
- Interpretation: where a test rejects its null hypothesis, the effect-size label is the guide to whether the difference is large enough to matter for a later model. The p-value alone is not that guide.

## 13. Limitations

- Registration transactions are not vehicle sales, purchases, customers, revenue, or a direct measure of demand.
- `date_reg` may differ from a purchase date.
- The latest year is partial when it ends before 31 December. Full-year change for that year is withheld. This phase does not extrapolate it.
- Rakan Niaga is a registration channel. It is not a geographic state. Geographic charts exclude it and are not the national total. National totals keep it.
- Unknown, other, and the source fuel categories remain. `greendiesel` is kept apart from `diesel`.
- Months with unusually low recorded volume remain in the primary statistics. The dataset does not establish why they are low.
- Correlation and association do not establish causation.
- A p-value below 0.05 does not, by itself, make a difference practically important. Several tests use a large census of transactions or a long run of years.
- High and low monthly counts marked in this phase are EDA observations. They are not confirmed anomalies.

## 14. Implications for Phase 5

- A candidate forecasting target is the monthly count of recorded registrations from 2000-01-02 through 2026-08-31. The grain is one month. The series includes every channel and the low-volume months.
- 2026 is observed through August and is a partial year. A later model should not treat that year as a full year equal to the previous full year. This phase does not extend it to a full-year figure.
- Calendar month is not supported as a strong feature by the primary test.
- The national monthly count mixes geographic registration offices and the Rakan Niaga channel. Rakan Niaga accounts for 42.3% of recorded registrations in the full series. Its share in 2014 and in the latest complete year should be read from the annual channel table before a later model treats the national series as one stable process.
- A second candidate target is the monthly count of registrations classified as electric. The first complete year with an electric registration in this snapshot is 2009. Early years are sparse. Electric share is a composition of recorded registrations, not a measure of consumer adoption.
- The rank correlations of electric share and hybrid share with year are exploratory. They do not mean a later model should use year as its main predictor of registration volume.
- Annual electric share, fuel-category share, and manufacturer share are not adopted as forecasting predictors. Any later use would need a time-ordered evaluation and a leakage check. An association with registration volume is not evidence that one series causes the other.
- Low-volume months remain in the series. A later model has to decide how to treat them with that limitation stated, rather than dropping them silently.

## Charts

- `figures/01_annual_registrations.png`
- `figures/02_yoy_complete_years.png`
- `figures/03_like_for_like.png`
- `figures/04_monthly_registrations.png`
- `figures/05_calendar_month_boxplot.png`
- `figures/06_year_normalized_month.png`
- `figures/07_manufacturer_totals.png`
- `figures/08_manufacturer_share_trends.png`
- `figures/09_model_pairs.png`
- `figures/10_vehicle_type_shares.png`
- `figures/11_vehicle_type_trends.png`
- `figures/12_fuel_composition.png`
- `figures/13_ev_hybrid_annual.png`
- `figures/14_ev_hybrid_monthly.png`
- `figures/15_state_channel.png`
- `figures/16_geographic_offices.png`
- `figures/17_rakan_niaga_share.png`
- `figures/18_concentration.png`
