"""NASA FIRMS Area API client and sensor normalization boundary."""

from __future__ import annotations

import asyncio
import csv
import io
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    DEFAULT_SENSORS,
    FIRMS_BASE_URL,
    FIRMS_MAP_KEY,
    FIRMS_NRT_SENSOR_SOURCES,
    FIRMS_NRT_START_DATE,
    FIRMS_SP_SENSOR_SOURCES,
    MAX_DAY_RANGE_PER_REQUEST,
    VIIRS_CONFIDENCE_MAP,
)


class FirmsAPIError(RuntimeError):
    def __init__(self, status_code: int | None, message: str, url: str):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"FIRMS request failed ({status_code}): {message} [{url}]")


_CSV_CACHE: dict[tuple[str, str, int, str], str] = {}


def _redact_url(url: str) -> str:
    if FIRMS_MAP_KEY and FIRMS_MAP_KEY in url:
        return url.replace(FIRMS_MAP_KEY, "REDACTED_MAP_KEY")
    return url


def _chunks(start_date: date, end_date: date) -> list[tuple[date, int]]:
    chunks = []
    cursor = start_date
    while cursor <= end_date:
        days = min(MAX_DAY_RANGE_PER_REQUEST, (end_date - cursor).days + 1)
        chunks.append((cursor, days))
        cursor += timedelta(days=days)
    return chunks


def _bbox_string(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{value:.6f}".rstrip("0").rstrip(".") for value in bbox)


def _normalize_confidence(value: str, sensor: str) -> float:
    raw = (value or "").strip().lower()
    if sensor.startswith("viirs"):
        return VIIRS_CONFIDENCE_MAP.get(raw[:1], 0.0)
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _source_for_sensor(sensor: str, start: date) -> str:
    if start < FIRMS_NRT_START_DATE and sensor in FIRMS_SP_SENSOR_SOURCES:
        return FIRMS_SP_SENSOR_SOURCES[sensor]
    return FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    clean_time = str(acq_time).zfill(4)
    value = f"{acq_date}T{clean_time[:2]}:{clean_time[2:]}:00+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _valid_coordinates(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _parse_csv(text: str, sensor: str) -> list[dict[str, Any]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if not row.get("latitude") or not row.get("longitude"):
            continue
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            acq_datetime = _parse_acq_datetime(row.get("acq_date", ""), row.get("acq_time", ""))
        except (TypeError, ValueError):
            continue
        if not _valid_coordinates(lat, lon):
            continue
        frp = row.get("frp")
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "acq_datetime": acq_datetime,
                "confidence_pct": _normalize_confidence(row.get("confidence", ""), sensor),
                "frp": float(frp) if frp not in (None, "") else None,
                "sensor": sensor,
                "satellite": row.get("satellite", ""),
                "daynight": row.get("daynight", ""),
            }
        )
    return rows


async def _fetch_csv(client: httpx.AsyncClient, sensor: str, bbox: tuple[float, float, float, float], start: date, days: int) -> str:
    area = _bbox_string(bbox)
    cache_key = (sensor, area, days, start.isoformat())
    if cache_key in _CSV_CACHE:
        return _CSV_CACHE[cache_key]

    source = _source_for_sensor(sensor, start)
    url = f"{FIRMS_BASE_URL}/{FIRMS_MAP_KEY}/{source}/{area}/{days}/{start.isoformat()}"
    delays = [1, 2, 4]
    last_error: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        started = time.perf_counter()
        try:
            response = await client.get(url)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code >= 500:
                raise FirmsAPIError(response.status_code, response.text[:200], _redact_url(url))
            if response.status_code >= 400:
                raise FirmsAPIError(response.status_code, response.text[:200], _redact_url(url))
            _CSV_CACHE[cache_key] = response.text
            print(f"firms_request sensor={sensor} chunk_start={start} days={days} elapsed_ms={elapsed_ms}")
            return response.text
        except (httpx.HTTPError, FirmsAPIError) as exc:
            last_error = exc
            if isinstance(exc, FirmsAPIError) and exc.status_code and exc.status_code < 500:
                raise
            if attempt < len(delays):
                await asyncio.sleep(delay)
    if isinstance(last_error, FirmsAPIError):
        raise last_error
    raise FirmsAPIError(None, str(last_error), _redact_url(url))


async def _fetch_recent_csv(client: httpx.AsyncClient, sensor: str, area: str, days: int) -> str:
    source = FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)
    cache_key = (sensor, area, days, "recent")
    if cache_key in _CSV_CACHE:
        return _CSV_CACHE[cache_key]

    url = f"{FIRMS_BASE_URL}/{FIRMS_MAP_KEY}/{source}/{area}/{days}"
    delays = [1, 2, 4]
    last_error: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        started = time.perf_counter()
        try:
            response = await client.get(url)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code >= 500:
                raise FirmsAPIError(response.status_code, response.text[:200], _redact_url(url))
            if response.status_code >= 400:
                raise FirmsAPIError(response.status_code, response.text[:200], _redact_url(url))
            _CSV_CACHE[cache_key] = response.text
            print(f"firms_recent_request sensor={sensor} area={area} days={days} elapsed_ms={elapsed_ms}")
            return response.text
        except (httpx.HTTPError, FirmsAPIError) as exc:
            last_error = exc
            if isinstance(exc, FirmsAPIError) and exc.status_code and exc.status_code < 500:
                raise
            if attempt < len(delays):
                await asyncio.sleep(delay)
    if isinstance(last_error, FirmsAPIError):
        raise last_error
    raise FirmsAPIError(None, str(last_error), _redact_url(url))


async def fetch_hotspots_for_window(
    bbox: tuple[float, float, float, float],
    start_date: date,
    end_date: date,
    sensors: list[str] = DEFAULT_SENSORS,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(4)

    async def guarded(sensor: str, chunk_start: date, days: int) -> list[dict[str, Any]]:
        async with semaphore:
            async with httpx.AsyncClient(timeout=30.0) as client:
                text = await _fetch_csv(client, sensor, bbox, chunk_start, days)
            return _parse_csv(text, sensor)

    tasks = [guarded(sensor, chunk_start, days) for sensor in sensors for chunk_start, days in _chunks(start_date, end_date)]
    results = await asyncio.gather(*tasks)
    return [row for batch in results for row in batch]


async def fetch_recent_hotspots(
    bbox: tuple[float, float, float, float] | None = None,
    sensors: list[str] = DEFAULT_SENSORS,
    days: int = 1,
) -> list[dict[str, Any]]:
    area = "world" if bbox is None else _bbox_string(bbox)
    semaphore = asyncio.Semaphore(4)

    async def guarded(sensor: str) -> list[dict[str, Any]]:
        async with semaphore:
            async with httpx.AsyncClient(timeout=45.0) as client:
                text = await _fetch_recent_csv(client, sensor, area, days)
            return _parse_csv(text, sensor)

    results = await asyncio.gather(*(guarded(sensor) for sensor in sensors))
    return [row for batch in results for row in batch]
