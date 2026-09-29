"""Malaysia Automotive Intelligence.

Phase 1 downloads and validates the official JPJ car registration files.
Phase 2 builds the processed Parquet layer. Phase 3 adds DuckDB views on
that layer. Phase 4 explores those views and runs a small set of tests.
Forecasting, anomaly detection, and Power BI are later phases.
"""

__version__ = "0.1.0"
