-- dim_dataset_coverage
-- Grain: one row describing the dates present in fact_registrations.
-- A latest year is partial when its maximum registration date is before
-- 31 December. The latest month is incomplete when that maximum date is
-- before the last calendar day of its month. Earlier months are not judged
-- this way: registration activity already skips some calendar days.
-- like_for_like_through_month is the last complete month of the latest year.

CREATE OR REPLACE VIEW dim_dataset_coverage AS
WITH bounds AS (
    SELECT
        min(date_reg) AS first_date_reg,
        max(date_reg) AS latest_date_reg,
        min(registration_year) AS first_year,
        max(registration_year) AS latest_year
    FROM fact_registrations
)
SELECT
    first_date_reg,
    latest_date_reg,
    first_year,
    latest_year,
    month(latest_date_reg) AS latest_month_number,
    strftime(latest_date_reg, '%Y-%m') AS latest_year_month,
    latest_date_reg::DATE < make_date(year(latest_date_reg), 12, 31) AS latest_year_is_partial,
    latest_date_reg::DATE < last_day(latest_date_reg::DATE) AS latest_month_is_partial,
    CASE
        WHEN latest_date_reg::DATE < last_day(latest_date_reg::DATE)
            THEN month(latest_date_reg) - 1
        ELSE month(latest_date_reg)
    END AS like_for_like_through_month
FROM bounds;
