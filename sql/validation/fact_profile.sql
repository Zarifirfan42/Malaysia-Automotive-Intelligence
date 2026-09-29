-- One-row profile of fact_registrations. Used to reconcile Phase 3 with Phase 2.
-- Required fields are the analytical columns a later query needs. A null here
-- fails reconciliation. Source colour is allowed to be checked separately and
-- is not in this null count because the analytical views do not group by it.

SELECT
    count(*)::BIGINT AS registration_count,
    min(date_reg) AS minimum_date_reg,
    max(date_reg) AS maximum_date_reg,
    sum(is_electric)::BIGINT AS electric_registrations,
    sum(is_hybrid)::BIGINT AS hybrid_registrations,
    sum(CASE WHEN fuel_category = 'hybrid_petrol' THEN 1 ELSE 0 END)::BIGINT AS hybrid_petrol_registrations,
    sum(CASE WHEN fuel_category = 'hybrid_diesel' THEN 1 ELSE 0 END)::BIGINT AS hybrid_diesel_registrations,
    sum(CASE WHEN fuel_category = 'electric' THEN 1 ELSE 0 END)::BIGINT AS electric_fuel_registrations,
    sum(CASE WHEN state_category = 'Rakan Niaga' THEN 1 ELSE 0 END)::BIGINT AS rakan_niaga_state_registrations,
    sum(is_rakan_niaga)::BIGINT AS rakan_niaga_registrations,
    count(*) FILTER (
        WHERE date_reg IS NULL
            OR registration_year IS NULL
            OR registration_month IS NULL
            OR registration_month_number IS NULL
            OR registration_month_name IS NULL
            OR registration_quarter IS NULL
            OR registration_year_month IS NULL
            OR type IS NULL
            OR maker IS NULL
            OR maker_clean IS NULL
            OR model IS NULL
            OR model_clean IS NULL
            OR fuel IS NULL
            OR fuel_category IS NULL
            OR state IS NULL
            OR state_category IS NULL
            OR is_electric IS NULL
            OR is_hybrid IS NULL
            OR is_rakan_niaga IS NULL
    )::BIGINT AS null_required_rows,
    count(*) FILTER (
        WHERE registration_month <> registration_month_number
    )::BIGINT AS month_number_mismatches
FROM fact_registrations;
