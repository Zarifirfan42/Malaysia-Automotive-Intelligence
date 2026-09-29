-- analytics_state_month
-- Grain: one row per state_category and registration month.
-- Rakan Niaga stays its own category. It is a registration channel, not a
-- geographic state, and it is not assigned to one.
-- registration_share = this category's registrations / all registrations in
-- the same month.

CREATE OR REPLACE VIEW analytics_state_month AS
WITH monthly AS (
    SELECT
        state_category,
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations
    GROUP BY state_category, registration_year, registration_month_number, registration_year_month
)
SELECT
    monthly.*,
    registration_count::DOUBLE
        / nullif(sum(registration_count) OVER (PARTITION BY registration_year_month), 0)
        AS registration_share
FROM monthly;
