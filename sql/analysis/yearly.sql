SELECT
    registration_year,
    is_partial_year,
    registration_count,
    electric_registrations,
    hybrid_registrations,
    prior_full_year_registrations,
    yoy_absolute_change,
    yoy_percentage_change,
    yoy_basis
FROM analytics_year_registrations
ORDER BY registration_year;
