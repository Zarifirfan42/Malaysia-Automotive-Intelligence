-- analytics_like_for_like_year
-- Grain: one row.
-- Compares the latest year with the previous year over January through the
-- last complete month of the latest year. When the latest date is the last
-- day of August, the window is January through August of both years.
-- It is not a full-year comparison. An incomplete latest month is left out
-- of both years. Percentage change is null when the prior window is missing
-- or zero.

CREATE OR REPLACE VIEW analytics_like_for_like_year AS
WITH coverage AS (
    SELECT
        *,
        CASE like_for_like_through_month
            WHEN 1 THEN 'January'
            WHEN 2 THEN 'February'
            WHEN 3 THEN 'March'
            WHEN 4 THEN 'April'
            WHEN 5 THEN 'May'
            WHEN 6 THEN 'June'
            WHEN 7 THEN 'July'
            WHEN 8 THEN 'August'
            WHEN 9 THEN 'September'
            WHEN 10 THEN 'October'
            WHEN 11 THEN 'November'
            WHEN 12 THEN 'December'
            ELSE NULL
        END AS through_month_name
    FROM dim_dataset_coverage
),
counts AS (
    SELECT
        fact.registration_year,
        count(*)::BIGINT AS registration_count,
        sum(fact.is_electric)::BIGINT AS electric_registrations,
        sum(fact.is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations AS fact
    CROSS JOIN coverage
    WHERE coverage.like_for_like_through_month >= 1
        AND fact.registration_year IN (coverage.latest_year, coverage.latest_year - 1)
        AND fact.registration_month_number <= coverage.like_for_like_through_month
    GROUP BY fact.registration_year
)
SELECT
    coverage.latest_year,
    coverage.latest_year - 1 AS prior_year,
    coverage.like_for_like_through_month AS through_month,
    coverage.latest_year_is_partial,
    coverage.latest_month_is_partial,
    coverage.latest_date_reg,
    CASE
        WHEN coverage.like_for_like_through_month < 1 THEN
            'No complete month is available for a like-for-like comparison.'
        ELSE
            'January through ' || coverage.through_month_name || ' '
            || coverage.latest_year::VARCHAR
            || ' compared with January through ' || coverage.through_month_name || ' '
            || (coverage.latest_year - 1)::VARCHAR
            || '. This is not a full-year comparison.'
    END AS comparison_label,
    latest.registration_count AS latest_period_registrations,
    prior.registration_count AS prior_period_registrations,
    latest.electric_registrations AS latest_period_electric_registrations,
    prior.electric_registrations AS prior_period_electric_registrations,
    latest.hybrid_registrations AS latest_period_hybrid_registrations,
    prior.hybrid_registrations AS prior_period_hybrid_registrations,
    CASE
        WHEN coverage.like_for_like_through_month < 1
            OR latest.registration_count IS NULL
            OR prior.registration_count IS NULL THEN NULL
        ELSE latest.registration_count - prior.registration_count
    END AS yoy_absolute_change,
    CASE
        WHEN coverage.like_for_like_through_month < 1
            OR latest.registration_count IS NULL
            OR prior.registration_count IS NULL
            OR prior.registration_count = 0 THEN NULL
        ELSE (latest.registration_count - prior.registration_count)::DOUBLE
            / prior.registration_count
    END AS yoy_percentage_change,
    CASE
        WHEN coverage.like_for_like_through_month < 1 THEN 'no_complete_month'
        WHEN prior.registration_count IS NULL THEN 'no_prior_year'
        WHEN prior.registration_count = 0 THEN 'undefined_prior_zero'
        WHEN coverage.latest_year_is_partial THEN 'partial_year_like_for_like'
        ELSE 'same_months_both_years'
    END AS yoy_basis
FROM coverage
LEFT JOIN counts AS latest ON latest.registration_year = coverage.latest_year
LEFT JOIN counts AS prior ON prior.registration_year = coverage.latest_year - 1;
