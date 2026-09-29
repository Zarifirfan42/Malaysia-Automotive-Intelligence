-- Checks that each analytical view still adds up to the fact row count,
-- and that manufacturer registration shares in each month sum to 1.

SELECT
    (SELECT count(*)::BIGINT FROM fact_registrations) AS fact_rows,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_monthly_registrations) AS monthly_rows,
    (SELECT count(*)::BIGINT FROM analytics_monthly_registrations) AS monthly_groups,
    (SELECT count(DISTINCT registration_year_month)::BIGINT FROM fact_registrations) AS fact_months,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_model_month) AS model_rows,
    (SELECT count(*)::BIGINT FROM analytics_model_month) AS model_groups,
    (
        SELECT count(*)::BIGINT
        FROM (
            SELECT 1
            FROM fact_registrations
            GROUP BY maker_clean, model_clean, registration_year_month
        ) AS fact_model_groups
    ) AS fact_model_groups,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_manufacturer_month) AS manufacturer_month_rows,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_manufacturer) AS manufacturer_rows,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_state_month) AS state_rows,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_fuel_month) AS fuel_rows,
    (SELECT coalesce(sum(registration_count), 0)::BIGINT FROM analytics_vehicle_type_month) AS type_rows,
    (
        SELECT max(abs(share_total - 1))
        FROM (
            SELECT sum(registration_share) AS share_total
            FROM analytics_manufacturer_month
            GROUP BY registration_year_month
        ) AS month_shares
    ) AS max_manufacturer_share_gap,
    (
        SELECT count(*)::BIGINT
        FROM (
            SELECT model_clean
            FROM fact_registrations
            GROUP BY model_clean
            HAVING count(DISTINCT maker_clean) > 1
        ) AS shared_names
    ) AS models_with_multiple_makers;
