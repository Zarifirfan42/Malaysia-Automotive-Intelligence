-- Grain remains maker_clean x model_clean x year.

SELECT
    maker_clean,
    model_clean,
    registration_year,
    sum(registration_count)::BIGINT AS registration_count,
    sum(electric_registrations)::BIGINT AS electric_registrations,
    sum(hybrid_registrations)::BIGINT AS hybrid_registrations
FROM analytics_model_month
GROUP BY maker_clean, model_clean, registration_year;
