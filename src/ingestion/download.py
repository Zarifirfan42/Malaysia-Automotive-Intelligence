"""Stream official yearly Parquet files into data/raw.

A readable file already on disk is left untouched unless force=True.
A failed or unreadable download is deleted and raised; the batch stops.
"""

from __future__ import annotations

import logging
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pyarrow.parquet as pq

from src.config import (
    DOWNLOAD_CHUNK_BYTES,
    DOWNLOAD_TIMEOUT_SECONDS,
    RAW_DIR,
    USER_AGENT,
    dataset_years,
    parquet_filename,
    parquet_url,
)

logger = logging.getLogger(__name__)

UrlOpen = Callable[..., object]


class DownloadError(Exception):
    """A yearly file could not be downloaded or verified."""


class CorruptParquetError(DownloadError):
    """The file is not readable Parquet."""


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of one yearly acquisition attempt."""

    year: int
    source_url: str
    local_path: Path
    acquisition: str
    completed_at: datetime
    file_size_bytes: int
    file_mtime: datetime


def download_all(
    years: Iterable[int] | None = None,
    dest_dir: Path | None = None,
    *,
    force: bool = False,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> list[DownloadResult]:
    """Download every requested year. Stop at the first failure."""
    chosen = tuple(dataset_years() if years is None else years)
    target = RAW_DIR if dest_dir is None else dest_dir
    target.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []
    for year in chosen:
        results.append(
            download_year(
                year,
                dest_dir=target,
                force=force,
                timeout=timeout,
                urlopen=urlopen,
            )
        )
    return results


def download_year(
    year: int,
    dest_dir: Path | None = None,
    *,
    force: bool = False,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> DownloadResult:
    """Download one yearly file, or reuse a readable file already on disk."""
    url = parquet_url(year)
    target = RAW_DIR if dest_dir is None else dest_dir
    target.mkdir(parents=True, exist_ok=True)
    dest = target / parquet_filename(year)

    if dest.exists() and not force:
        _require_readable_parquet(dest)
        completed = _utcnow()
        logger.info("Reusing readable file %s", dest.name)
        return _result(year, url, dest, "reused_existing", completed)

    partial = dest.with_suffix(".parquet.partial")
    if partial.exists():
        partial.unlink()

    logger.info("Downloading %s", url)
    try:
        written = _stream_to_path(url, partial, timeout, urlopen)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    if written <= 0:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"Download for {url} produced an empty file")

    try:
        _require_readable_parquet(partial)
    except CorruptParquetError:
        partial.unlink(missing_ok=True)
        raise

    os.replace(partial, dest)
    completed = _utcnow()
    logger.info("Saved %s (%s bytes)", dest.name, dest.stat().st_size)
    return _result(year, url, dest, "downloaded", completed)


def assert_readable_parquet(path: Path) -> None:
    """Raise CorruptParquetError if path is missing Parquet magic or a readable footer."""
    _require_readable_parquet(path)


def _require_readable_parquet(path: Path) -> None:
    if not path.is_file():
        raise CorruptParquetError(f"Parquet file does not exist: {path}")
    if path.stat().st_size < 12:
        raise CorruptParquetError(f"File is too small to be Parquet: {path}")
    with path.open("rb") as handle:
        head = handle.read(4)
        handle.seek(-4, os.SEEK_END)
        tail = handle.read(4)
    if head != b"PAR1" or tail != b"PAR1":
        raise CorruptParquetError(f"File is not Parquet (missing PAR1 magic): {path}")
    try:
        parquet = pq.ParquetFile(path)
        _ = parquet.schema_arrow
        if parquet.metadata is None:
            raise CorruptParquetError(f"Parquet metadata is missing: {path}")
        _ = parquet.metadata.num_rows
    except CorruptParquetError:
        raise
    except Exception as exc:
        raise CorruptParquetError(f"Parquet file is unreadable: {path}") from exc


def _stream_to_path(url: str, dest: Path, timeout: int, urlopen: UrlOpen) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    written = 0
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status is not None and int(status) >= 400:
                raise DownloadError(f"HTTP {status} for {url}")
            with dest.open("wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
    except DownloadError:
        raise
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} for {url}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise DownloadError(f"Timed out after {timeout}s downloading {url}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise DownloadError(f"Timed out after {timeout}s downloading {url}") from exc
        raise DownloadError(f"Could not download {url}: {reason}") from exc
    return written


def _result(
    year: int,
    url: str,
    dest: Path,
    acquisition: str,
    completed_at: datetime,
) -> DownloadResult:
    mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc)
    return DownloadResult(
        year=year,
        source_url=url,
        local_path=dest,
        acquisition=acquisition,
        completed_at=completed_at,
        file_size_bytes=dest.stat().st_size,
        file_mtime=mtime,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
