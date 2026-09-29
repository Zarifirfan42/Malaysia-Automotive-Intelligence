"""Download official JPJ car registration Parquet files without modifying them."""

from src.ingestion.download import (
    CorruptParquetError,
    DownloadError,
    DownloadResult,
    download_all,
    download_year,
)

__all__ = [
    "CorruptParquetError",
    "DownloadError",
    "DownloadResult",
    "download_all",
    "download_year",
]
