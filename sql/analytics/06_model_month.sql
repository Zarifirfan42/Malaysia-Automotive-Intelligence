-- analytics_model_month
-- Grain: one row per maker_clean, model_clean, and registration month.
-- The same model_clean under two manufacturers stays two rows.
-- registration_rank ranks maker-model pairs within the month by registration
-- count. Equal counts share a rank. The rank is not a sales rank.

CREATE OR REPLACE VIEW analytics_model_month AS
WITH grouped AS (
    SELECT
        maker_clean,
        model_clean,
        registration_year,
        registration_month_number,
        any_value(registration_month_name) AS registration_month_name,
        any_value(registration_quarter) AS registration_quarter,
        registration_year_month,
        count(*)::BIGINT AS registration_count,
        sum(is_electric)::BIGINT AS electric_registrations,
        sum(is_hybrid)::BIGINT AS hybrid_registrations
    FROM fact_registrations
    GROUP BY
        maker_clean,
        model_clean,
        registration_year,
        registration_month_number,
        registration_year_month
)
SELECT
    grouped.*,
    rank() OVER (
        PARTITION BY registration_year_month
        ORDER BY registration_count DESC
    ) AS registration_rank
FROM grouped;
