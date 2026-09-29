-- analytics_year_registrations
-- Grain: one row per registration year.
-- Full-year change compares a year with the previous calendar year only when
-- the later year is complete. The latest year is complete only when its
-- maximum registration date is 31 December. Otherwise yoy_basis is
-- withheld_partial_year and the change columns are null.
-- Use analytics_like_for_like_year for that partial year.
-- Percentage change is null when the prior year has no rows or zero rows.

CREATE OR REPLACE VIEW analytics_year_registrations AS
WITH yearly AS (
    SELECT
        registration_year,
        count(*)::BIGINT AS registration_count,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations,
        min(date_reg) AS first_date_reg,
        max(date_reg) AS last_date_reg
    FROM fact_registrations
    GROUP BY registration_year
),
compared AS (
    SELECT
        yearly.*,
        (
            yearly.registration_year = coverage.latest_year
            AND coverage.latest_year_is_partial
        ) AS is_partial_year,
        prior.registration_count AS prior_year_registrations
    FROM yearly
    CROSS JOIN dim_dataset_coverage AS coverage
    LEFT JOIN yearly AS prior
        ON prior.registration_year = yearly.registration_year - 1
)
SELECT
    registration_year,
    first_date_reg,
    last_date_reg,
    is_partial_year,
    registration_count,
    electric_registrations,
    hybrid_registrations,
    CASE
        WHEN is_partial_year THEN NULL
        ELSE prior_year_registrations
    END AS prior_full_year_registrations,
    CASE
        WHEN is_partial_year OR prior_year_registrations IS NULL THEN NULL
        ELSE registration_count - prior_year_registrations
    END AS yoy_absolute_change,
    CASE
        WHEN is_partial_year
            OR prior_year_registrations IS NULL
            OR prior_year_registrations = 0 THEN NULL
        ELSE (registration_count - prior_year_registrations)::DOUBLE
            / prior_year_registrations
    END AS yoy_percentage_change,
    CASE
        WHEN is_partial_year THEN 'withheld_partial_year'
        WHEN prior_year_registrations IS NULL THEN 'no_prior_year'
        WHEN prior_year_registrations = 0 THEN 'undefined_prior_zero'
        ELSE 'full_year'
    END AS yoy_basis
FROM compared;
