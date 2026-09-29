-- analytics_fuel_month
-- Grain: one row per fuel_category and registration month.
-- fuel_category is the Phase 2 copy of the source fuel code. Categories are
-- not merged. greendiesel stays separate from diesel.
-- registration_share = this fuel category's registrations / all registrations
-- in the same month.

CREATE OR REPLACE VIEW analytics_fuel_month AS
WITH monthly AS (
    SELECT
        fuel_category,
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count
    FROM fact_registrations
    GROUP BY fuel_category, registration_year, registration_month_number, registration_year_month
)
SELECT
    monthly.*,
    registration_count::DOUBLE
        / nullif(sum(registration_count) OVER (PARTITION BY registration_year_month), 0)
        AS registration_share
FROM monthly;
