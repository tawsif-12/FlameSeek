"""NASA FIRMS Area API client and sensor normalization boundary."""

from __future__ import annotations

import asyncio
import math
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
    CACHE_DIR,
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


_KEY_PLACEHOLDERS = {"", "DEMO_KEY", "YOUR_FIRMS_MAP_KEY_HERE", "YOUR_NASA_FIRMS_KEY"}


def firms_key_configured() -> bool:
    """True only for a non-placeholder key; validity is ultimately checked by NASA."""
    return FIRMS_MAP_KEY.strip().upper() not in _KEY_PLACEHOLDERS


def _require_firms_key() -> None:
    if not firms_key_configured():
        raise FirmsAPIError(
            503,
            "NASA FIRMS_MAP_KEY is not configured. Create backend/.env, set FIRMS_MAP_KEY to your free key from https://firms.modaps.eosdis.nasa.gov/api/map_key/, then restart the backend.",
            "configuration",
        )


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


# Set while a request is being held back by the MAP_KEY transaction limit.
_quota_wait: dict[str, Any] = {"since": None, "usage": None}


def quota_wait_status() -> dict[str, Any] | None:
    """Seconds a FIRMS request has been waiting for transaction budget, or None when nothing is waiting."""
    if _quota_wait["since"] is None:
        return None
    return {"seconds": round(time.monotonic() - _quota_wait["since"]), "usage": _quota_wait["usage"]}


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
                _quota_wait["since"] = None
                return
            _quota_wait["since"] = _quota_wait["since"] or time.monotonic()
            _quota_wait["usage"] = usage
        # Sleep outside the lock so interactive requests can fail fast meanwhile.
        if time.monotonic() - started >= wait_budget:
            raise FirmsAPIError(429, "FIRMS MAP_KEY transaction limit reached (5000 per 10 minutes); try again in a few minutes.", "limit")
        await asyncio.sleep(20)


async def load_availability() -> dict[str, tuple[date, date]]:
    """FIRMS source date ranges (e.g. MODIS_SP 2000-11-01..2026-06-30), refreshed every 6 h."""
    global _availability_loaded_at
    if _availability and time.time() - _availability_loaded_at < 6 * 3600:
        return _availability
    # Availability is only an optimization. Offline runs can still resolve the
    # source split from FIRMS_NRT_START_DATE and read archived chunks from disk.
    if not firms_key_configured():
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


_CHUNK_EPOCH = date(2000, 1, 1)


def _chunks(start_date: date, end_date: date) -> list[tuple[date, int]]:
    """Request chunks on a fixed calendar grid (every MAX_DAY_RANGE_PER_REQUEST days from 2000-01-01).
    Interior chunks are then identical for any two periods that overlap, so a 1-year quick look and a
    10-year history reuse the same cached downloads. Only the first and last chunk may be partial."""
    chunks = []
    cursor = start_date
    step = MAX_DAY_RANGE_PER_REQUEST
    while cursor <= end_date:
        to_boundary = step - ((cursor - _CHUNK_EPOCH).days % step)
        days = min(to_boundary, (end_date - cursor).days + 1)
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
                "fire_type": int(row["type"]) if str(row.get("type") or "").strip().isdigit() else None,
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


_IN_FLIGHT: dict[tuple[str, str, int, str], "asyncio.Future[str]"] = {}


def snap_bbox(bbox: tuple[float, float, float, float], step: float = 0.5) -> tuple[float, float, float, float]:
    """Expand a box outward to a fixed grid so nearby and repeated searches download (and cache) the
    same FIRMS chunks; callers still filter detections to the exact area afterwards."""
    w, s, e, n = bbox
    snap_down = lambda v: math.floor(v / step) * step  # noqa: E731
    snap_up = lambda v: math.ceil(v / step) * step  # noqa: E731
    return (max(-180.0, snap_down(w)), max(-90.0, snap_down(s)), min(180.0, snap_up(e)), min(90.0, snap_up(n)))


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

    # A MAP key is needed only for a cache miss. This keeps previously fetched
    # immutable science archives usable during demos and offline development.
    _require_firms_key()

    # Two analyses asking for the same chunk at the same moment share one NASA request.
    pending = _IN_FLIGHT.get(cache_key)
    if pending is not None:
        return await asyncio.shield(pending), source

    async def download() -> str:
        url = f"{FIRMS_BASE_URL}/{FIRMS_MAP_KEY}/{source}/{area}/{days}/{start.isoformat()}"
        started = time.perf_counter()
        text = await _get_with_retries(client, url)
        print(f"firms_request source={source} chunk_start={start} days={days} elapsed_ms={round((time.perf_counter() - started) * 1000, 1)}")
        _CSV_CACHE[cache_key] = (time.time(), text)
        if ttl is None or ttl >= 86400:
            disk_write("firms", disk_key, text, ".csv")
        return text

    task = asyncio.ensure_future(download())
    _IN_FLIGHT[cache_key] = task
    try:
        return await asyncio.shield(task), source
    finally:
        if task.done():
            _IN_FLIGHT.pop(cache_key, None)
        else:
            task.add_done_callback(lambda _t: _IN_FLIGHT.pop(cache_key, None))


async def _fetch_recent_csv(client: httpx.AsyncClient, sensor: str, area: str, days: int) -> tuple[str, str]:
    source = FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)
    cache_key = (source, area, days, "recent")
    cached = _CSV_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < FIRMS_RECENT_CACHE_TTL_SECONDS:
        return cached[1], source

    _require_firms_key()
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
    concurrency: int = 16,
    raw_sink: list[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch every sensor/chunk in a window. With raw_sink, the original FIRMS CSV text of every
    chunk is also collected as (source, text) for the FlameSeek pipeline. Failed chunks are reported, not fatal,
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
                text, source = await _fetch_csv(client, sensor, bbox, chunk_start, days)
                sources_used.add(source)
                if raw_sink is not None:
                    raw_sink.append((source, text))
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

    # One pooled client for the whole window: connections and TLS sessions are reused across chunks.
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    # Most archive chunks answer in under a second; a short read timeout lets a stalled one be retried quickly.
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), headers={"User-Agent": HTTP_USER_AGENT}, verify=SSL_CONTEXT, limits=limits) as client:
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
_FIRMS_RECENT_LIVE_TIMEOUT_SECONDS = 90.0
_LAST_RECENT_SOURCE = "live"


def recent_source_status() -> str:
    return _LAST_RECENT_SOURCE


def _sensor_for_source(source: str) -> str | None:
    for source_map in (FIRMS_NRT_SENSOR_SOURCES, FIRMS_SP_SENSOR_SOURCES):
        for sensor, configured in source_map.items():
            if configured == source:
                return sensor
    return None


def _cached_actual_hotspots(
    bbox: tuple[float, float, float, float] | None,
    sensors: list[str],
    days: int,
    max_files: int = 2000,
) -> list[dict[str, Any]]:
    """Newest real FIRMS rows already cached on disk, used only when live FIRMS is unreachable.

    This never reads demo_data.py, and it intentionally ignores `place_hint`.
    """
    root = CACHE_DIR / "firms"
    if not root.exists():
        return []
    files = sorted(root.rglob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    rows: list[dict[str, Any]] = []
    for path in files:
        source = next((part for part in path.name.split("_") if part in {*FIRMS_NRT_SENSOR_SOURCES.values(), *FIRMS_SP_SENSOR_SOURCES.values()}), "")
        # Filenames start with sources such as MODIS_NRT_...; split matching above can miss because of underscores.
        if not source:
            source = next((src for src in [*FIRMS_NRT_SENSOR_SOURCES.values(), *FIRMS_SP_SENSOR_SOURCES.values()] if path.name.startswith(f"{src}_")), "")
        sensor = _sensor_for_source(source)
        if not sensor or sensor not in sensors:
            continue
        try:
            parsed = _parse_csv(path.read_text(encoding="utf-8"), sensor, source)
        except OSError:
            continue
        rows.extend(parsed)

    if bbox is not None:
        west, south, east, north = bbox
        rows = [row for row in rows if west <= row["lon"] <= east and south <= row["lat"] <= north]
    if not rows:
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    recent = [row for row in rows if cutoff <= row["acq_datetime"] <= now]
    # De-duplicate rows that appear in overlapping cache chunks.
    deduped: dict[tuple[str, float, float, datetime], dict[str, Any]] = {}
    for row in recent:
        row.pop("place_hint", None)
        deduped[(row["sensor"], round(row["lat"], 5), round(row["lon"], 5), row["acq_datetime"])] = row
    return list(deduped.values())


_WORLD_PARSED: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}


def _from_fresh_world_cache(bbox: tuple[float, float, float, float], sensors: list[str], days: int) -> list[dict[str, Any]] | None:
    """Rows inside bbox from worldwide recent downloads that are still fresh, or None if any sensor
    is missing or stale (the caller then asks FIRMS for the box itself)."""
    west, south, east, north = bbox
    rows: list[dict[str, Any]] = []
    for sensor in sensors:
        source = FIRMS_NRT_SENSOR_SOURCES.get(sensor, sensor)
        cached = _CSV_CACHE.get((source, "world", days, "recent"))
        if not cached or time.time() - cached[0] >= FIRMS_RECENT_CACHE_TTL_SECONDS:
            return None
        parsed = _WORLD_PARSED.get((source, days))
        if parsed is None or parsed[0] != cached[0]:
            parsed = (cached[0], _parse_csv(cached[1], sensor, source))
            _WORLD_PARSED[(source, days)] = parsed
        rows.extend(r for r in parsed[1] if west <= r["lon"] <= east and south <= r["lat"] <= north)
    return rows


async def fetch_recent_hotspots(
    bbox: tuple[float, float, float, float] | None = None,
    sensors: list[str] = DEFAULT_SENSORS,
    days: int = 1,
    include_demo: bool = False,
) -> list[dict[str, Any]]:
    global _FIRMS_DOWN_UNTIL, _LAST_RECENT_SOURCE
    area = "world" if bbox is None else _bbox_string(bbox)
    semaphore = asyncio.Semaphore(4)

    # A place inside a fresh worldwide download needs no new NASA request: cut it out locally.
    if bbox is not None:
        local = _from_fresh_world_cache(bbox, sensors, days)
        if local is not None:
            _LAST_RECENT_SOURCE = "live"
            return local

    async def guarded(sensor: str) -> list[dict[str, Any]]:
        async with semaphore:
            async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": HTTP_USER_AGENT}, verify=SSL_CONTEXT) as client:
                text, source = await _fetch_recent_csv(client, sensor, area, days)
            return _parse_csv(text, sensor, source)

    # Negative cache: after a recent FIRMS failure, skip live calls for a short window
    # so the UI returns from current cached observations instead of waiting on retries.
    now_ts = time.time()
    firms_down = now_ts < _FIRMS_DOWN_UNTIL

    rows: list[dict[str, Any]] = []
    if not firms_down:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*(guarded(sensor) for sensor in sensors)),
                timeout=_FIRMS_RECENT_LIVE_TIMEOUT_SECONDS,
            )
            rows = [row for batch in results for row in batch]
            _LAST_RECENT_SOURCE = "live"
        except (FirmsAPIError, httpx.HTTPError, asyncio.TimeoutError) as exc:
            _FIRMS_DOWN_UNTIL = now_ts + _FIRMS_DOWN_TTL_SECONDS
            print(f"firms_unavailable reason={type(exc).__name__} muted_for_seconds={_FIRMS_DOWN_TTL_SECONDS}")
            rows = _cached_actual_hotspots(bbox, sensors, days)
            _LAST_RECENT_SOURCE = "cached_actual" if rows else "unavailable"
            if not rows:
                raise FirmsAPIError(502, "Live FIRMS is unavailable and no cached observations cover the requested time window.", area) from exc
    else:
        rows = _cached_actual_hotspots(bbox, sensors, days)
        _LAST_RECENT_SOURCE = "cached_actual" if rows else "unavailable"
    if firms_down and not rows:
        raise FirmsAPIError(502, "Live FIRMS is temporarily unavailable; no current cached observations are available.", area)
    return rows
