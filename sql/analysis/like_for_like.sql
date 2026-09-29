SELECT
    latest_year,
    prior_year,
    through_month,
    latest_year_is_partial,
    comparison_label,
    latest_period_registrations,
    prior_period_registrations,
    latest_period_electric_registrations,
    prior_period_electric_registrations,
    latest_period_hybrid_registrations,
    prior_period_hybrid_registrations,
    yoy_absolute_change,
    yoy_percentage_change,
    yoy_basis
FROM analytics_like_for_like_year;
