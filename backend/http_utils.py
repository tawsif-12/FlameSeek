"""Shared outbound HTTP: polite per-host rate limits plus memory and disk caches.

Every external source (FIRMS, Nominatim, Overpass, Open-Meteo, GDELT, ...) goes
through here so usage policies are respected in one place and repeated analysis
of the same area does not hit the network again.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from config import CACHE_DIR, HTTP_USER_AGENT

# Loading the CA bundle costs ~0.3 s; build it once and share it across all clients.
SSL_CONTEXT = httpx.create_ssl_context()


# Minimum seconds between requests to one host, from each provider's usage policy.
HOST_MIN_INTERVAL = {
    "nominatim.openstreetmap.org": 1.1,
    "api.gdeltproject.org": 5.2,
    "overpass-api.de": 1.0,
    "overpass.kumi.systems": 1.0,
    "overpass.private.coffee": 1.0,
    "api.worldpop.org": 1.0,
}

_host_locks: dict[str, asyncio.Lock] = {}
_host_last_call: dict[str, float] = {}
_memory_cache: dict[str, tuple[float, Any]] = {}


class ExternalServiceError(RuntimeError):
    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service}: {message}")


def _cache_key(url: str, params: dict[str, Any] | None, body: Any) -> str:
    raw = json.dumps([url, params or {}, body], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _disk_path(namespace: str, key: str, suffix: str) -> Path:
    return CACHE_DIR / namespace / key[:2] / f"{key}{suffix}"


def disk_read(namespace: str, key: str, suffix: str = ".json", max_age_seconds: float | None = None) -> str | None:
    path = _disk_path(namespace, key, suffix)
    if not path.exists():
        return None
    if max_age_seconds is not None and (time.time() - path.stat().st_mtime) > max_age_seconds:
        return None
    return path.read_text(encoding="utf-8")


def disk_write(namespace: str, key: str, text: str, suffix: str = ".json") -> None:
    path = _disk_path(namespace, key, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


async def _respect_rate_limit(host: str) -> asyncio.Lock | None:
    interval = HOST_MIN_INTERVAL.get(host)
    if interval is None:
        return None
    lock = _host_locks.setdefault(host, asyncio.Lock())
    await lock.acquire()
    wait = interval - (time.monotonic() - _host_last_call.get(host, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    return lock


async def request_text(
    url: str,
    *,
    service: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: float = 30.0,
    ttl_seconds: float | None = 3600,
    disk_namespace: str | None = None,
    retries: int = 2,
) -> str:
    """Fetch text with caching. ttl_seconds=None means cache forever (immutable data)."""

    key = _cache_key(url, params, data)
    cached = _memory_cache.get(key)
    if cached and (ttl_seconds is None or time.time() - cached[0] < ttl_seconds):
        return cached[1]
    if disk_namespace:
        text = disk_read(disk_namespace, key, ".txt", ttl_seconds)
        if text is not None:
            _memory_cache[key] = (time.time(), text)
            return text

    host = urlparse(url).netloc
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        lock = await _respect_rate_limit(host)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": HTTP_USER_AGENT}, follow_redirects=True, verify=SSL_CONTEXT) as client:
                if method == "POST":
                    response = await client.post(url, params=params, data=data)
                else:
                    response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            last_error = ExternalServiceError(service, f"network error: {exc.__class__.__name__}")
        else:
            if response.status_code == 429 or response.status_code >= 500:
                last_error = ExternalServiceError(service, f"HTTP {response.status_code}", response.status_code)
            elif response.status_code >= 400:
                raise ExternalServiceError(service, f"HTTP {response.status_code}: {response.text[:160]}", response.status_code)
            else:
                text = response.text
                _memory_cache[key] = (time.time(), text)
                if disk_namespace:
                    disk_write(disk_namespace, key, text, ".txt")
                return text
        finally:
            if lock is not None:
                _host_last_call[host] = time.monotonic()
                lock.release()
        if attempt < retries:
            # 429 means the provider's own limiter tripped: wait well past its interval.
            throttled = isinstance(last_error, ExternalServiceError) and last_error.status_code == 429
            await asyncio.sleep(max(1.5 * (attempt + 1), 3 * HOST_MIN_INTERVAL.get(host, 1.0)) if throttled else 1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def request_json(url: str, **kwargs: Any) -> Any:
    text = await request_text(url, **kwargs)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExternalServiceError(kwargs.get("service", url), "response was not JSON") from exc
