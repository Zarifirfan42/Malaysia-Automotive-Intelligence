-- dim_registration_month
-- Grain: one row per observed registration month.
-- Attributes come from Phase 2. Months with no registrations are not invented.

CREATE OR REPLACE VIEW dim_registration_month AS
WITH months AS (
    SELECT
        registration_year_month,
        any_value(registration_year) AS registration_year,
        any_value(registration_month) AS registration_month,
        any_value(registration_month_number) AS registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter
    FROM fact_registrations
    GROUP BY registration_year_month
)
SELECT
    months.registration_year_month,
    months.registration_year,
    months.registration_month,
    months.registration_month_number,
    months.registration_month_name,
    months.registration_quarter,
    (
        months.registration_year = coverage.latest_year
        AND coverage.latest_year_is_partial
    ) AS is_partial_year,
    months.registration_year_month = coverage.latest_year_month AS is_latest_observed_month,
    (
        months.registration_year_month = coverage.latest_year_month
        AND coverage.latest_month_is_partial
    ) AS is_incomplete_month
FROM months
CROSS JOIN dim_dataset_coverage AS coverage;
