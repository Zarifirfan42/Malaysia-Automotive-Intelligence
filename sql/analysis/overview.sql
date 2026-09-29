-- One row. Distinct counts and totals come from fact_registrations.
-- The query returns aggregates only.

SELECT
    count(*)::BIGINT AS registration_count,
    min(date_reg) AS minimum_date_reg,
    max(date_reg) AS maximum_date_reg,
    count(DISTINCT registration_year)::BIGINT AS registration_years,
    count(DISTINCT registration_year_month)::BIGINT AS observed_months,
    count(DISTINCT maker_clean)::BIGINT AS manufacturers,
    count(DISTINCT model_clean)::BIGINT AS model_names,
    count(DISTINCT fuel_category)::BIGINT AS fuel_categories,
    count(DISTINCT type)::BIGINT AS vehicle_types,
    count(DISTINCT state_category)::BIGINT AS state_channels,
    sum(is_electric)::BIGINT AS electric_registrations,
    sum(is_hybrid)::BIGINT AS hybrid_registrations,
    sum(CASE WHEN fuel_category = 'hybrid_petrol' THEN 1 ELSE 0 END)::BIGINT AS hybrid_petrol_registrations,
    sum(CASE WHEN fuel_category = 'hybrid_diesel' THEN 1 ELSE 0 END)::BIGINT AS hybrid_diesel_registrations
FROM fact_registrations;
