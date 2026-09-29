-- analytics_manufacturer
-- Grain: one row per maker_clean.
-- registration_share = this manufacturer's registrations / all recorded
-- registrations. electric_registration_share and hybrid_registration_share
-- use that manufacturer's own registrations as the denominator.
-- first_registration_year and latest_registration_year are the earliest and
-- latest years with at least one of that manufacturer's registrations.
-- None of these figures are sales.

CREATE OR REPLACE VIEW analytics_manufacturer AS
WITH grouped AS (
    SELECT
        maker_clean,
        count(*)::BIGINT AS registration_count,
        min(registration_year) AS first_registration_year,
        max(registration_year) AS latest_registration_year,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations
    GROUP BY maker_clean
)
SELECT
    maker_clean,
    registration_count,
    first_registration_year,
    latest_registration_year,
    electric_registrations,
    hybrid_registrations,
    electric_registrations::DOUBLE / nullif(registration_count, 0) AS electric_registration_share,
    hybrid_registrations::DOUBLE / nullif(registration_count, 0) AS hybrid_registration_share,
    registration_count::DOUBLE / nullif(sum(registration_count) OVER (), 0) AS registration_share
FROM grouped;
