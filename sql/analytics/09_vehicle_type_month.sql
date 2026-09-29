-- analytics_vehicle_type_month
-- Grain: one row per source vehicle type and registration month.
-- registration_share = this type's registrations / all registrations in the
-- same month.

CREATE OR REPLACE VIEW analytics_vehicle_type_month AS
WITH monthly AS (
    SELECT
        type,
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count
    FROM fact_registrations
    GROUP BY type, registration_year, registration_month_number, registration_year_month
)
SELECT
    monthly.*,
    registration_count::DOUBLE
        / nullif(sum(registration_count) OVER (PARTITION BY registration_year_month), 0)
        AS registration_share
FROM monthly;
