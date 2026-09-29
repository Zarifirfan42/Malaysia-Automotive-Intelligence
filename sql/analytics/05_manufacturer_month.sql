-- analytics_manufacturer_month
-- Grain: one row per maker_clean and registration month.
-- registration_share = this manufacturer's registrations / all registrations
-- in the same month. This is a share of recorded registrations, not sales.
-- Year-over-year uses the same manufacturer and the same month number in the
-- previous year. A missing prior month stays null. It is not treated as zero.

CREATE OR REPLACE VIEW analytics_manufacturer_month AS
WITH monthly AS (
    SELECT
        maker_clean,
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations
    GROUP BY maker_clean, registration_year, registration_month_number, registration_year_month
),
with_share AS (
    SELECT
        monthly.*,
        registration_count::DOUBLE
            / nullif(sum(registration_count) OVER (PARTITION BY registration_year_month), 0)
            AS registration_share
    FROM monthly
)
SELECT
    current_row.maker_clean,
    current_row.registration_year,
    current_row.registration_month_number,
    current_row.registration_month_name,
    current_row.registration_quarter,
    current_row.registration_year_month,
    current_row.registration_count,
    current_row.electric_registrations,
    current_row.hybrid_registrations,
    current_row.registration_share,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_row.registration_year_month = coverage.latest_year_month
            THEN NULL
        ELSE prior_row.registration_count
    END AS prior_year_same_month_registrations,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_row.registration_year_month = coverage.latest_year_month
            THEN NULL
        WHEN prior_row.registration_count IS NULL THEN NULL
        ELSE current_row.registration_count - prior_row.registration_count
    END AS yoy_absolute_change,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_row.registration_year_month = coverage.latest_year_month
            THEN NULL
        WHEN prior_row.registration_count IS NULL OR prior_row.registration_count = 0 THEN NULL
        ELSE (current_row.registration_count - prior_row.registration_count)::DOUBLE
            / prior_row.registration_count
    END AS yoy_percentage_change,
    CASE
        WHEN coverage.latest_month_is_partial
            AND current_row.registration_year_month = coverage.latest_year_month
            THEN 'withheld_incomplete_month'
        WHEN prior_row.registration_count IS NULL THEN 'no_prior_year'
        WHEN prior_row.registration_count = 0 THEN 'undefined_prior_zero'
        ELSE 'same_month_prior_year'
    END AS yoy_basis
FROM with_share AS current_row
CROSS JOIN dim_dataset_coverage AS coverage
LEFT JOIN with_share AS prior_row
    ON prior_row.maker_clean = current_row.maker_clean
    AND prior_row.registration_year = current_row.registration_year - 1
    AND prior_row.registration_month_number = current_row.registration_month_number;
