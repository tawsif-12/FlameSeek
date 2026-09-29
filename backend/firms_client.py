"""NASA FIRMS Area API client and sensor normalization boundary."""

from __future__ import annotations

import asyncio
import contextvars
import csv
import io
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx

from config import (
    DEFAULT_SENSORS,
    FIRMS_AVAILABILITY_URL,
    FIRMS_BASE_URL,
    FIRMS_MAP_KEY,
    FIRMS_NRT_SENSOR_SOURCES,
    FIRMS_NRT_START_DATE,
    FIRMS_RECENT_CACHE_TTL_SECONDS,
    FIRMS_SP_SENSOR_SOURCES,
    FIRMS_TRANSACTION_BUDGET,
    FIRMS_TRANSACTION_WINDOW_SECONDS,
    HTTP_USER_AGENT,
    LANDSAT_CONFIDENCE_MAP,
    MAX_DAY_RANGE_PER_REQUEST,
    SENSOR_START_DATES,
    VIIRS_CONFIDENCE_MAP,
)
from http_utils import SSL_CONTEXT, disk_read, disk_write


class FirmsAPIError(RuntimeError):
    def __init__(self, status_code: int | None, message: str, url: str):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"FIRMS request failed ({status_code}): {message} [{url}]")


ProgressCallback = Callable[[int, int], Awaitable[None] | None]

_CSV_CACHE: dict[tuple[str, str, int, str], tuple[float, str]] = {}
_availability: dict[str, tuple[date, date]] = {}
_availability_loaded_at = 0.0
_transactions: deque[float] = deque()
_transaction_lock = asyncio.Lock()
_usage: tuple[int, int] | None = None
_usage_checked_at = -1e9
FIRMS_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"
# Seconds a FIRMS request may wait for transaction budget; background jobs raise it.
FIRMS_WAIT_SECONDS: contextvars.ContextVar[float] = contextvars.ContextVar("firms_wait_seconds", default=0.0)


def _redact_url(url: str) -> str:
    if FIRMS_MAP_KEY and FIRMS_MAP_KEY in url:
        return url.replace(FIRMS_MAP_KEY, "REDACTED_MAP_KEY")
    return url


async def _key_usage() -> tuple[int, int] | None:
    """(current, limit) transactions reported by FIRMS; checked at most every 15 s.

    FIRMS weights large requests (e.g. whole-world queries) as several
    transactions, so counting our own requests alone underestimates usage.
    """
    global _usage_checked_at, _usage
    if time.monotonic() - _usage_checked_at < 15:
        return _usage
    _usage_checked_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=SSL_CONTEXT) as client:
            response = await client.get(FIRMS_STATUS_URL, params={"MAP_KEY": FIRMS_MAP_KEY})
        data = response.json()
        _usage = (int(data["current_transactions"]), int(data["transaction_limit"]))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        _usage = None
    return _usage


async def _spend_transaction() -> None:
    """Keep below the MAP_KEY limit. Interactive calls fail fast when it is nearly
    spent; long jobs (FIRMS_WAIT_SECONDS > 0) wait for the window to roll over."""
    global _usage
    wait_budget = FIRMS_WAIT_SECONDS.get()
    started = time.monotonic()
    while True:
        async with _transaction_lock:
            now = time.monotonic()
            while _transactions and now - _transactions[0] > FIRMS_TRANSACTION_WINDOW_SECONDS:
                _transactions.popleft()
            usage = await _key_usage()
            key_full = usage is not None and usage[0] >= 0.97 * usage[1]
            if len(_transactions) < FIRMS_TRANSACTION_BUDGET and not key_full:
                _transactions.append(now)
                if usage is not None:
                    _usage = (usage[0] + 1, usage[1])
                return
        # Sleep outside the lock so interactive requests can fail fast meanwhile.
        if time.monotonic() - started >= wait_budget:
            raise FirmsAPIError(429, "FIRMS MAP_KEY transaction limit reached (5000 per 10 minutes); try again in a few minutes.", "limit")
        await asyncio.sleep(20)


async def load_availability() -> dict[str, tuple[date, date]]:
    """FIRMS source date ranges (e.g. MODIS_SP 2000-11-01..2026-06-30), refreshed every 6 h."""
    global _availability_loaded_at
    if _availability and time.time() - _availability_loaded_at < 6 * 3600:
        return _availability
    url = f"{FIRMS_AVAILABILITY_URL}/{FIRMS_MAP_KEY}/ALL"
    try:
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": HTTP_USER_AGENT}, verify=SSL_CONTEXT) as client:
            response = await client.get(url)
        if response.status_code < 400:
            parsed = {}
            for row in csv.DictReader(io.StringIO(response.text)):
                try:
                    parsed[row["data_id"]] = (date.fromisoformat(row["min_date"]), date.fromisoformat(row["max_date"]))
                except (KeyError, ValueError):
                    continue
            if parsed:
                _availability.clear()
                _availability.update(parsed)
                _availability_loaded_at = time.time()
    except httpx.HTTPError:
        pass
    return _availability


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
    if sensor == "landsat":
        return LANDSAT_CONFIDENCE_MAP.get(raw[:1], 0.0)
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _sp_boundary(sensor: str) -> date:
    """Last day served by the science-processing (SP) archive for this sensor."""
    sp = FIRMS_SP_SENSOR_SOURCES.get(sensor)
    if sp and sp in _availability:
        return _availability[sp][1]
    return FIRMS_NRT_START_DATE - timedelta(days=1)


def _source_for_sensor(sensor: str, start: date) -> str:
    if sensor in FIRMS_SP_SENSOR_SOURCES and start <= _sp_boundary(sensor):
        return FIRMS_SP_SENSOR_SOURCES[sensor]
    return FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)


def sensor_available(sensor: str, day: date) -> bool:
    """Whether FIRMS can provide an observation opportunity for this sensor and day."""
    start = SENSOR_START_DATES.get(sensor)
    if start and day < start:
        return False
    if not _availability:
        return True
    sources = [FIRMS_SP_SENSOR_SOURCES.get(sensor), FIRMS_NRT_SENSOR_SOURCES.get(sensor)]
    return any(src in _availability and _availability[src][0] <= day <= _availability[src][1] for src in sources if src)


def _source_segments(sensor: str, start_date: date, end_date: date) -> list[tuple[date, date]]:
    """Split a window at the SP/NRT boundary so no request straddles two archives."""
    boundary = _sp_boundary(sensor)
    if sensor in FIRMS_SP_SENSOR_SOURCES and start_date <= boundary < end_date:
        return [(start_date, boundary), (boundary + timedelta(days=1), end_date)]
    return [(start_date, end_date)]


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    clean_time = str(acq_time).zfill(4)
    value = f"{acq_date}T{clean_time[:2]}:{clean_time[2:]}:00+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _valid_coordinates(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number <= -900 else number


def _parse_csv(text: str, sensor: str, source: str = "") -> list[dict[str, Any]]:
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
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "acq_datetime": acq_datetime,
                "confidence_pct": _normalize_confidence(row.get("confidence", ""), sensor),
                "frp": _float_or_none(row.get("frp")),
                "sensor": sensor,
                "satellite": row.get("satellite", ""),
                "daynight": row.get("daynight", ""),
                "scan_km": _float_or_none(row.get("scan")),
                "track_km": _float_or_none(row.get("track")),
                "brightness_k": _float_or_none(row.get("brightness") or row.get("bright_ti4")),
                "brightness_2_k": _float_or_none(row.get("bright_t31") or row.get("bright_ti5")),
                "version": row.get("version", ""),
                "source": source,
            }
        )
    return rows


async def _get_with_retries(client: httpx.AsyncClient, url: str) -> str:
    delays = [1, 2, 4]
    last_error: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        try:
            await _spend_transaction()
            response = await client.get(url)
            if response.status_code >= 400:
                raise FirmsAPIError(response.status_code, response.text[:200], _redact_url(url))
            text = response.text
            # FIRMS reports some errors (bad range, key limit) as HTTP 200 plain text.
            if text and not text.startswith(("latitude", "country_id")) and "," not in text.splitlines()[0]:
                raise FirmsAPIError(400, text[:200], _redact_url(url))
            return text
        except (httpx.HTTPError, FirmsAPIError) as exc:
            last_error = exc
            # Client errors, including "Exceeding allowed transaction limit" (which only
            # clears when the 10-minute window rolls over), are not worth retrying.
            if isinstance(exc, FirmsAPIError) and exc.status_code and exc.status_code < 500:
                raise
            if attempt < len(delays):
                await asyncio.sleep(delay)
    if isinstance(last_error, FirmsAPIError):
        raise last_error
    raise FirmsAPIError(None, str(last_error), _redact_url(url))


def _chunk_ttl(source: str, start: date, days: int) -> float | None:
    """SP archives are immutable; NRT settles after a few days."""
    if source.endswith("_SP"):
        return None
    age_days = (datetime.now(timezone.utc).date() - (start + timedelta(days=days - 1))).days
    return 86400.0 if age_days > 3 else FIRMS_RECENT_CACHE_TTL_SECONDS


async def _fetch_csv(client: httpx.AsyncClient, sensor: str, bbox: tuple[float, float, float, float] | str, start: date, days: int) -> tuple[str, str]:
    area = bbox if isinstance(bbox, str) else _bbox_string(bbox)
    source = _source_for_sensor(sensor, start)
    cache_key = (source, area, days, start.isoformat())
    ttl = _chunk_ttl(source, start, days)
    cached = _CSV_CACHE.get(cache_key)
    if cached and (ttl is None or time.time() - cached[0] < ttl):
        return cached[1], source
    disk_key = f"{source}_{area.replace(',', '_')}_{start.isoformat()}_{days}"
    if ttl is None or ttl >= 86400:
        text = disk_read("firms", disk_key, ".csv", ttl)
        if text is not None:
            _CSV_CACHE[cache_key] = (time.time(), text)
            return text, source

    url = f"{FIRMS_BASE_URL}/{FIRMS_MAP_KEY}/{source}/{area}/{days}/{start.isoformat()}"
    started = time.perf_counter()
    text = await _get_with_retries(client, url)
    print(f"firms_request source={source} chunk_start={start} days={days} elapsed_ms={round((time.perf_counter() - started) * 1000, 1)}")
    _CSV_CACHE[cache_key] = (time.time(), text)
    if ttl is None or ttl >= 86400:
        disk_write("firms", disk_key, text, ".csv")
    return text, source


async def _fetch_recent_csv(client: httpx.AsyncClient, sensor: str, area: str, days: int) -> tuple[str, str]:
    source = FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)
    cache_key = (source, area, days, "recent")
    cached = _CSV_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < FIRMS_RECENT_CACHE_TTL_SECONDS:
        return cached[1], source

    url = f"{FIRMS_BASE_URL}/{FIRMS_MAP_KEY}/{source}/{area}/{days}"
    started = time.perf_counter()
    text = await _get_with_retries(client, url)
    print(f"firms_recent_request source={source} area={area} days={days} elapsed_ms={round((time.perf_counter() - started) * 1000, 1)}")
    _CSV_CACHE[cache_key] = (time.time(), text)
    return text, source


async def fetch_hotspots_with_report(
    bbox: tuple[float, float, float, float] | str,
    start_date: date,
    end_date: date,
    sensors: list[str] = DEFAULT_SENSORS,
    progress: ProgressCallback | None = None,
    concurrency: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch every sensor/chunk in a window. Failed chunks are reported, not fatal,
    so observation sufficiency can mark those days as missing opportunities."""

    await load_availability()
    semaphore = asyncio.Semaphore(concurrency)
    jobs: list[tuple[str, date, int]] = []
    for sensor in sensors:
        for seg_start, seg_end in _source_segments(sensor, start_date, end_date):
            first_day = max(seg_start, SENSOR_START_DATES.get(sensor, seg_start))
            if first_day > seg_end:
                continue
            jobs.extend((sensor, chunk_start, days) for chunk_start, days in _chunks(first_day, seg_end))

    done = 0
    failures: list[dict[str, Any]] = []
    sources_used: set[str] = set()

    async def guarded(sensor: str, chunk_start: date, days: int) -> list[dict[str, Any]]:
        nonlocal done
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=45.0, headers={"User-Agent": HTTP_USER_AGENT}, verify=SSL_CONTEXT) as client:
                    text, source = await _fetch_csv(client, sensor, bbox, chunk_start, days)
                sources_used.add(source)
                return _parse_csv(text, sensor, source)
            except FirmsAPIError as exc:
                failures.append({"sensor": sensor, "start": chunk_start.isoformat(), "days": days, "status_code": exc.status_code, "message": exc.message[:160]})
                return []
            finally:
                done += 1
                if progress:
                    result = progress(done, len(jobs))
                    if asyncio.iscoroutine(result):
                        await result

    results = await asyncio.gather(*(guarded(*job) for job in jobs))
    rows = [row for batch in results for row in batch]
    if jobs and len(failures) == len(jobs):
        first = failures[0]
        raise FirmsAPIError(first["status_code"], first["message"], "multiple")
    return rows, {"requests": len(jobs), "failed_chunks": failures, "sources_used": sorted(sources_used)}


async def fetch_hotspots_for_window(
    bbox: tuple[float, float, float, float] | str,
    start_date: date,
    end_date: date,
    sensors: list[str] = DEFAULT_SENSORS,
) -> list[dict[str, Any]]:
    rows, _ = await fetch_hotspots_with_report(bbox, start_date, end_date, sensors)
    return rows


_FIRMS_DOWN_UNTIL: float = 0.0
_FIRMS_DOWN_TTL_SECONDS = 120.0


async def fetch_recent_hotspots(
    bbox: tuple[float, float, float, float] | None = None,
    sensors: list[str] = DEFAULT_SENSORS,
    days: int = 1,
) -> list[dict[str, Any]]:
    global _FIRMS_DOWN_UNTIL
    area = "world" if bbox is None else _bbox_string(bbox)
    semaphore = asyncio.Semaphore(4)

    async def guarded(sensor: str) -> list[dict[str, Any]]:
        async with semaphore:
            async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": HTTP_USER_AGENT}, verify=SSL_CONTEXT) as client:
                text, source = await _fetch_recent_csv(client, sensor, area, days)
            return _parse_csv(text, sensor, source)

    # Demo overlay: dense Dhaka (Ashulia) cluster for hackathon walkthroughs.
    from demo_data import bbox_covers_dhaka, dhaka_demo_hotspots
    demo_rows: list[dict[str, Any]] = []
    if bbox_covers_dhaka(bbox):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        demo_rows = [row for row in dhaka_demo_hotspots() if row["sensor"] in sensors and row["acq_datetime"] >= cutoff]

    # Negative cache: after a recent FIRMS failure, skip live calls for a short window
    # so the UI returns instantly from cached/demo data instead of waiting on retries.
    now_ts = time.time()
    firms_down = now_ts < _FIRMS_DOWN_UNTIL

    rows: list[dict[str, Any]] = []
    if not firms_down:
        try:
            results = await asyncio.gather(*(guarded(sensor) for sensor in sensors))
            rows = [row for batch in results for row in batch]
        except (FirmsAPIError, httpx.HTTPError, asyncio.TimeoutError) as exc:
            _FIRMS_DOWN_UNTIL = now_ts + _FIRMS_DOWN_TTL_SECONDS
            print(f"firms_unavailable reason={type(exc).__name__} muted_for_seconds={_FIRMS_DOWN_TTL_SECONDS}")
            if not demo_rows:
                raise
    rows.extend(demo_rows)
    return rows
