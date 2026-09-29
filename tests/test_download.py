"""Tests for official URL construction and safe downloads."""

from __future__ import annotations

import io
from datetime import datetime

import pyarrow.parquet as pq
import pytest

from src.config import parquet_url
from src.ingestion.download import CorruptParquetError, DownloadError, download_all, download_year
from tests.support import parquet_bytes, registration, write_official_parquet


class _Response(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200) -> None:
        super().__init__(data)
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def test_parquet_url_uses_official_storage_pattern() -> None:
    assert parquet_url(2000) == "https://storage.data.gov.my/transportation/cars_2000.parquet"
    assert parquet_url(2026) == "https://storage.data.gov.my/transportation/cars_2026.parquet"


def test_parquet_url_rejects_years_outside_the_official_range() -> None:
    with pytest.raises(ValueError):
        parquet_url(1999)
    with pytest.raises(ValueError):
        parquet_url(2027)


def test_download_reuses_a_readable_file_without_touching_the_network(tmp_path) -> None:
    dest_dir = tmp_path / "raw"
    dest = dest_dir / "cars_2000.parquet"
    write_official_parquet(dest, [registration(datetime(2000, 1, 15))])
    before = dest.read_bytes()

    def fail_if_called(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("network should not be used when a readable file exists")

    result = download_year(2000, dest_dir=dest_dir, urlopen=fail_if_called)

    assert result.acquisition == "reused_existing"
    assert dest.read_bytes() == before


def test_download_does_not_keep_a_corrupt_response(tmp_path) -> None:
    dest_dir = tmp_path / "raw"

    def fake_open(*_args: object, **_kwargs: object) -> _Response:
        return _Response(b"this is not a parquet file")

    with pytest.raises(CorruptParquetError):
        download_year(2000, dest_dir=dest_dir, urlopen=fake_open)

    assert not (dest_dir / "cars_2000.parquet").exists()
    assert not (dest_dir / "cars_2000.parquet.partial").exists()


def test_download_reports_http_errors(tmp_path) -> None:
    import urllib.error

    def fake_open(request: object, timeout: int = 0) -> _Response:
        raise urllib.error.HTTPError(request.full_url, 404, "missing", hdrs=None, fp=None)

    with pytest.raises(DownloadError, match="HTTP 404"):
        download_year(2000, dest_dir=tmp_path, urlopen=fake_open)


def test_download_reports_timeouts(tmp_path) -> None:
    def fake_open(*_args: object, **_kwargs: object) -> _Response:
        raise TimeoutError("timed out")

    with pytest.raises(DownloadError, match="Timed out"):
        download_year(2000, dest_dir=tmp_path, urlopen=fake_open)


def test_download_writes_readable_parquet(tmp_path) -> None:
    payload = [
        registration(datetime(2000, 1, 15)),
        registration(datetime(2000, 1, 16)),
    ]

    def fake_open(*_args: object, **_kwargs: object) -> _Response:
        return _Response(parquet_bytes(payload))

    result = download_year(2000, dest_dir=tmp_path, urlopen=fake_open)

    assert result.acquisition == "downloaded"
    assert pq.read_table(result.local_path).num_rows == 2


def test_download_all_stops_after_the_first_failure(tmp_path) -> None:
    good = parquet_bytes([registration(datetime(2000, 1, 15))])
    calls = {"count": 0}

    def fake_open(*_args: object, **_kwargs: object) -> _Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return _Response(good)
        raise TimeoutError("timed out")

    with pytest.raises(DownloadError):
        download_all(years=[2000, 2001], dest_dir=tmp_path, urlopen=fake_open)

    assert (tmp_path / "cars_2000.parquet").exists()
    assert not (tmp_path / "cars_2001.parquet").exists()
