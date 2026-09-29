"""Weather, terrain and population context from free public APIs.

- Weather: Open-Meteo (ERA5 reanalysis archive for the past, forecast model for
  the recent past and next days). ERA5 cloud cover is a proxy for whether an
  optical/thermal overpass could see the surface; it is not a satellite cloud mask.
- Terrain: Open-Meteo elevation (Copernicus DEM 90 m).
- Population: WorldPop 2020 constrained estimates via the WorldPop stats API.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from http_utils import ExternalServiceError, request_json


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
WORLDPOP_URL = "https://api.worldpop.org/v1/services/stats"

DAILY_VARS = "temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,wind_direction_10m_dominant,precipitation_sum,cloud_cover_mean"
HOURLY_VARS = "wind_speed_10m,wind_direction_10m,relative_humidity_2m,temperature_2m,cloud_cover"
# ERA5 in the archive API lags real time by about five days.
ARCHIVE_LAG_DAYS = 6


def _round_coord(value: float) -> float:
    # ~10 km: finer than ERA5 (~25 km), coarse enough to share cache entries.
    return round(value * 10) / 10


def _zip_series(block: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not block or "time" not in block:
        return []
    keys = [k for k in block if k != "time"]
    return [{"time": t, **{k: block[k][i] for k in keys}} for i, t in enumerate(block["time"])]


async def daily_weather(lat: float, lon: float, start: date, end: date) -> list[dict[str, Any]]:
    """Daily weather rows {time, temperature_2m_max, ..., cloud_cover_mean} for a point."""
    lat, lon = _round_coord(lat), _round_coord(lon)
    today = datetime.now(timezone.utc).date()
    archive_end = min(end, today - timedelta(days=ARCHIVE_LAG_DAYS))
    rows: list[dict[str, Any]] = []
    if start <= archive_end:
        data = await request_json(
            ARCHIVE_URL,
            service="Open-Meteo archive",
            params={"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": archive_end.isoformat(), "daily": DAILY_VARS, "timezone": "GMT"},
            ttl_seconds=None,
            disk_namespace="openmeteo",
            timeout=60,
        )
        rows += _zip_series((data or {}).get("daily"))
    if end > archive_end:
        recent_start = max(start, archive_end + timedelta(days=1))
        past_days = max(0, (today - recent_start).days)
        forecast_days = max(1, min(16, (end - today).days + 1))
        data = await request_json(
            FORECAST_URL,
            service="Open-Meteo forecast",
            params={"latitude": lat, "longitude": lon, "daily": DAILY_VARS, "past_days": min(past_days, 92), "forecast_days": forecast_days, "timezone": "GMT"},
            ttl_seconds=3 * 3600,
        )
        rows += [r for r in _zip_series((data or {}).get("daily")) if recent_start.isoformat() <= r["time"] <= end.isoformat()]
    return rows


async def hourly_weather(lat: float, lon: float, start: date, end: date) -> list[dict[str, Any]]:
    lat, lon = _round_coord(lat), _round_coord(lon)
    today = datetime.now(timezone.utc).date()
    archive_end = min(end, today - timedelta(days=ARCHIVE_LAG_DAYS))
    rows: list[dict[str, Any]] = []
    if start <= archive_end:
        data = await request_json(
            ARCHIVE_URL,
            service="Open-Meteo archive",
            params={"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": archive_end.isoformat(), "hourly": HOURLY_VARS, "timezone": "GMT"},
            ttl_seconds=None,
            disk_namespace="openmeteo",
            timeout=60,
        )
        rows += _zip_series((data or {}).get("hourly"))
    if end > archive_end:
        recent_start = max(start, archive_end + timedelta(days=1))
        past_days = max(0, (today - recent_start).days + 1)
        forecast_days = max(1, min(16, (end - today).days + 2))
        data = await request_json(
            FORECAST_URL,
            service="Open-Meteo forecast",
            params={"latitude": lat, "longitude": lon, "hourly": HOURLY_VARS, "past_days": min(past_days, 92), "forecast_days": forecast_days, "timezone": "GMT"},
            ttl_seconds=3600,
        )
        rows += [r for r in _zip_series((data or {}).get("hourly")) if r["time"][:10] >= recent_start.isoformat()]
    return rows


def weather_at(hourly: list[dict[str, Any]], when: datetime) -> dict[str, Any] | None:
    """Nearest hourly weather row to a UTC time."""
    if not hourly:
        return None
    key = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
    best = None
    for row in hourly:
        if row["time"] <= key:
            best = row
        else:
            break
    return best or hourly[0]


async def elevations(points: list[tuple[float, float]]) -> list[float | None]:
    """Elevation (m) for (lat, lon) points, batched 100 per request."""
    result: list[float | None] = []
    for i in range(0, len(points), 100):
        batch = points[i : i + 100]
        try:
            data = await request_json(
                ELEVATION_URL,
                service="Open-Meteo elevation",
                params={"latitude": ",".join(f"{p[0]:.4f}" for p in batch), "longitude": ",".join(f"{p[1]:.4f}" for p in batch)},
                ttl_seconds=None,
                disk_namespace="elevation",
            )
            values = (data or {}).get("elevation") or [None] * len(batch)
        except ExternalServiceError:
            values = [None] * len(batch)
        result += [float(v) if v is not None else None for v in values]
    return result


async def worldpop_population(geometry: dict[str, Any]) -> dict[str, Any]:
    """Estimated resident population inside a GeoJSON Polygon/MultiPolygon (WorldPop 2020)."""
    import json

    feature_collection = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": geometry}]}
    try:
        data = await request_json(
            WORLDPOP_URL,
            service="WorldPop",
            params={"dataset": "wpgppop", "year": 2020, "geojson": json.dumps(feature_collection, separators=(",", ":")), "runasync": "false"},
            ttl_seconds=30 * 86400,
            disk_namespace="worldpop",
            timeout=90,
            retries=1,
        )
    except ExternalServiceError as exc:
        return {"status": "unavailable", "population": None, "note": str(exc)}
    if not data or data.get("error"):
        return {"status": "unavailable", "population": None, "note": (data or {}).get("error_message") or "no response"}
    total = (data.get("data") or {}).get("total_population")
    return {
        "status": "ok" if total is not None else "unavailable",
        "population": round(total) if total is not None else None,
        "dataset": "WorldPop Global 2020 (100 m, unconstrained)",
        "note": "Modelled residential population estimate, not a census count.",
    }
