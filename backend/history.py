"""Regional fire history around a location: the same season in earlier years.

Shared by analogue search (Fire Past) and forecast training (Fire Future). Data
come from FIRMS science-quality archives and are cached on disk, so the first
request for a region takes a minute or two and later requests are instant.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from config import HISTORY_SENSORS
from environment import daily_weather
from firms_client import fetch_hotspots_with_report
from geo import radius_bbox
from harmonize import filter_low_confidence
from http_utils import ExternalServiceError


Progress = Callable[[str, float], Awaitable[None]]


async def regional_history(
    lat: float,
    lon: float,
    center_date: date,
    years: int = 8,
    radius_km: float = 60.0,
    half_window_days: int = 45,
    progress: Progress | None = None,
) -> dict[str, Any]:
    bbox = tuple(round(v, 3) for v in radius_bbox(lat, lon, radius_km))
    today = datetime.now(timezone.utc).date()
    windows = []
    for back in range(1, years + 1):
        try:
            c = center_date.replace(year=center_date.year - back)
        except ValueError:
            c = center_date.replace(year=center_date.year - back, day=28)
        start, end = c - timedelta(days=half_window_days), min(c + timedelta(days=half_window_days), today - timedelta(days=1))
        windows.append((c.year, start, end))

    rows: list[dict[str, Any]] = []
    per_year: dict[int, dict[str, Any]] = {}
    failures = 0
    for i, (year, start, end) in enumerate(windows):
        if progress:
            await progress(f"Fetching {year} season from the FIRMS archive", i / max(1, len(windows)))
        try:
            got, report = await fetch_hotspots_with_report(bbox, start, end, HISTORY_SENSORS)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - one bad year should not sink the analysis
            failures += 1
            per_year[year] = {"status": "failed", "error": str(exc)[:160]}
            continue
        got = filter_low_confidence(got)
        rows += got
        per_year[year] = {"status": "ok", "detections": len(got), "failed_chunks": len(report["failed_chunks"]), "start": start.isoformat(), "end": end.isoformat()}

    weather: dict[str, dict[str, Any]] = {}
    if progress:
        await progress("Fetching historical weather (ERA5)", 0.95)
    for year, start, end in windows:
        try:
            for w in await daily_weather(lat, lon, start, end):
                weather[w["time"]] = w
        except ExternalServiceError:
            continue
    return {
        "bbox": list(bbox),
        "radius_km": radius_km,
        "years": [w[0] for w in windows],
        "window_days": 2 * half_window_days + 1,
        "rows": rows,
        "per_year": per_year,
        "weather_by_date": weather,
        "failed_years": failures,
        "sensors": HISTORY_SENSORS,
    }
