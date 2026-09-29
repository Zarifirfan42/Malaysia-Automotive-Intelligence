-- Registration counts by the Phase 2 analytical keys.
-- One scan. The Python reconciliation compares each grain with the Phase 2 report.

SELECT
    CASE
        WHEN grouping(registration_year) = 0
            AND grouping(registration_year_month) = 1
            AND grouping(fuel_category) = 1
            AND grouping(state_category) = 1
            AND grouping(type) = 1
            AND grouping(maker) = 1
            AND grouping(maker_clean) = 1
            THEN 'year'
        WHEN grouping(registration_year_month) = 0 THEN 'month'
        WHEN grouping(fuel_category) = 0 THEN 'fuel'
        WHEN grouping(state_category) = 0 THEN 'state'
        WHEN grouping(type) = 0 THEN 'type'
        WHEN grouping(maker) = 0 AND grouping(maker_clean) = 1 THEN 'maker'
        WHEN grouping(maker_clean) = 0 AND grouping(maker) = 1 THEN 'maker_clean'
        ELSE 'unexpected'
    END AS grain,
    CASE
        WHEN grouping(registration_year) = 0
            AND grouping(registration_year_month) = 1
            AND grouping(fuel_category) = 1
            AND grouping(state_category) = 1
            AND grouping(type) = 1
            AND grouping(maker) = 1
            AND grouping(maker_clean) = 1
            THEN cast(registration_year AS VARCHAR)
        WHEN grouping(registration_year_month) = 0 THEN registration_year_month
        WHEN grouping(fuel_category) = 0 THEN fuel_category
        WHEN grouping(state_category) = 0 THEN state_category
        WHEN grouping(type) = 0 THEN type
        WHEN grouping(maker) = 0 AND grouping(maker_clean) = 1 THEN maker
        WHEN grouping(maker_clean) = 0 AND grouping(maker) = 1 THEN maker_clean
        ELSE NULL
    END AS dimension_key,
    count(*)::BIGINT AS registration_count
FROM fact_registrations
GROUP BY GROUPING SETS (
    (registration_year),
    (registration_year_month),
    (fuel_category),
    (state_category),
    (type),
    (maker),
    (maker_clean)
);
