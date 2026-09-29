-- fact_registrations
-- Grain: one row is one processed registration transaction.
-- The view reads Phase 2 Parquet. It does not filter, deduplicate, or add an
-- identifier. There is no JPJ transaction id in the source, and this layer
-- does not invent one.
-- registration_month and registration_month_number are both the month number
-- 1-12, as stored by Phase 2. The English name is registration_month_name.
-- Phase 2 is not modified here.

CREATE OR REPLACE VIEW fact_registrations AS
SELECT
    date_reg,
    registration_year,
    registration_month,
    registration_month_number,
    registration_month_name,
    registration_quarter,
    registration_year_month,
    type,
    maker,
    maker_clean,
    model,
    model_clean,
    colour,
    fuel,
    fuel_category,
    state,
    state_category,
    is_electric,
    is_hybrid,
    is_rakan_niaga
FROM read_parquet(
    '{{PROCESSED_GLOB}}',
    hive_partitioning = false,
    union_by_name = true
);
