SELECT
    registration_year,
    registration_month_number,
    registration_month_name,
    registration_quarter,
    registration_year_month,
    registration_count,
    electric_registrations,
    hybrid_registrations,
    electric_registration_share,
    hybrid_registration_share
FROM analytics_monthly_registrations
ORDER BY registration_year, registration_month_number;
