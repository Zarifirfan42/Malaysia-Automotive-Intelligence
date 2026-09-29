-- analytics_monthly_registrations
-- Grain: one row per registration month.
-- electric_registration_share and hybrid_registration_share are
-- electric or hybrid registrations divided by all registrations in that month.
-- They are shares of recorded registrations.
-- Same-month year-over-year change is withheld only when the latest observed
-- month does not reach its last calendar day. A partial year still has
-- month-level comparisons for its complete months.

CREATE OR REPLACE VIEW analytics_monthly_registrations AS
WITH monthly AS (
    SELECT
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations
    GROUP BY registration_year, registration_month_number, registration_year_month
)
SELECT
    current_month.registration_year,
    current_month.registration_month_number,
    current_month.registration_month_name,
    current_month.registration_quarter,
    current_month.registration_year_month,
    current_month.registration_count,
    current_month.electric_registrations,
    current_month.hybrid_registrations,
    current_month.electric_registrations::DOUBLE
        / nullif(current_month.registration_count, 0) AS electric_registration_share,
    current_month.hybrid_registrations::DOUBLE
        / nullif(current_month.registration_count, 0) AS hybrid_registration_share,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_month.registration_year_month = coverage.latest_year_month
            THEN NULL
        ELSE prior_month.registration_count
    END AS prior_year_same_month_registrations,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_month.registration_year_month = coverage.latest_year_month
            THEN NULL
        WHEN prior_month.registration_count IS NULL THEN NULL
        ELSE current_month.registration_count - prior_month.registration_count
    END AS yoy_absolute_change,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_month.registration_year_month = coverage.latest_year_month
            THEN NULL
        WHEN prior_month.registration_count IS NULL OR prior_month.registration_count = 0 THEN NULL
        ELSE (current_month.registration_count - prior_month.registration_count)::DOUBLE
            / prior_month.registration_count
    END AS yoy_percentage_change,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_month.registration_year_month = coverage.latest_year_month
            THEN 'withheld_incomplete_month'
        WHEN prior_month.registration_count IS NULL THEN 'no_prior_year'
        WHEN prior_month.registration_count = 0 THEN 'undefined_prior_zero'
        ELSE 'same_month_prior_year'
    END AS yoy_basis
FROM monthly AS current_month
CROSS JOIN dim_dataset_coverage AS coverage
LEFT JOIN monthly AS prior_month
    ON prior_month.registration_year = current_month.registration_year - 1
    AND prior_month.registration_month_number = current_month.registration_month_number;
