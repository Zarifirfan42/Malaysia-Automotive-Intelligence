-- One row: maker_clean and model_clean pairs, not model names alone.

SELECT count(*)::BIGINT AS manufacturer_model_pairs
FROM (
    SELECT DISTINCT maker_clean, model_clean
    FROM fact_registrations
);
