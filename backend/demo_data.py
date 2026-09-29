"""Demo fire cluster and evidence stubs for hackathon walkthroughs.

A dense multi-sensor MODIS+VIIRS cluster is injected around Ashulia (Dhaka
industrial belt) so the Fire Now globe always has an event to open, and
`DEMO_NEWS` can be filled with the user's own news items to demonstrate the
Fire Evidence validation pipeline.

Injection points:
- ``firms_client.fetch_recent_hotspots`` appends ``dhaka_demo_hotspots()`` when
  the bbox covers Dhaka (or is world).
- ``evidence.news_evidence`` appends ``DEMO_NEWS`` articles whose subject is
  within ~40 km of the demo centre.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

DEMO_TAG = "DEMO_DHAKA"
DEMO_MATCH_RADIUS_KM = 40.0
DHAKA_DEMO_SEED = 42

# Ashulia (Dhaka industrial belt) is the "flagship" demo fire — it is what the
# Fire Evidence walkthrough opens onto. The other spots give the map a realistic
# spread of activity across the country: forest fires, coastal mangrove smoke,
# tea-garden burns and brick-kiln plumes.
DEMO_CENTER_LAT = 23.850
DEMO_CENTER_LON = 90.380

# Every centre is a known industrial or urban landmark on solid ground.
# Scatter is deliberately tight (a few hundred metres) so no detection
# drifts into water, forest reserves or the Bay of Bengal.
# (lat, lon, label, count, peak_frp, spread_deg, hours_span)
DEMO_CLUSTERS: list[tuple[float, float, str, int, float, float, float]] = [
    # Flagship: Dhaka Export Processing Zone (DEPZ) at Ashulia — garment/textile cluster.
    (23.8835, 90.3345, "Ashulia DEPZ garment cluster (Dhaka)", 12, 185.0, 0.0055, 30.0),
    # Narayanganj dense industrial city (jute mills, dyeing plants).
    (23.6175, 90.5000, "Narayanganj textile & dyeing mills",    6,  85.0, 0.0050, 24.0),
    # Chittagong Export Processing Zone + port — heavy industry on land.
    (22.3010, 91.7860, "Chittagong EPZ & port industry",        7,  95.0, 0.0070, 26.0),
    # Mongla port industrial estate — solid ground, not the Sundarbans river.
    (22.4800, 89.5920, "Mongla port industrial estate (Khulna)", 5,  60.0, 0.0060, 22.0),
    # Rajshahi brick-kiln belt on the Barind dry-land plateau.
    (24.3720, 88.6180, "Rajshahi brick-kiln belt",               6,  48.0, 0.0100, 24.0),
    # Sylhet city / Osmani area — urban plus surrounding tea estates.
    (24.8950, 91.8720, "Sylhet city / Osmani zone",              4,  55.0, 0.0060, 20.0),
    # Bogura crop-residue burns — dense agricultural land north-central Bangladesh.
    (24.8500, 89.3710, "Bogura crop-residue burns",              5,  38.0, 0.0090, 18.0),
]


def _sensor_meta(sensor: str, rnd: random.Random) -> tuple[str, float, float]:
    if sensor == "modis":
        return rnd.choice(["Aqua", "Terra"]), 1.0, 1.0
    if sensor == "viirs_snpp":
        return "N", 0.375, 0.375
    if sensor == "viirs_noaa20":
        return "N20", 0.375, 0.375
    if sensor == "viirs_noaa21":
        return "N21", 0.375, 0.375
    return "", 1.0, 1.0


_FIRMS_SOURCE_BY_SENSOR = {
    "modis": "MODIS_NRT",
    "viirs_snpp": "VIIRS_SNPP_NRT",
    "viirs_noaa20": "VIIRS_NOAA20_NRT",
    "viirs_noaa21": "VIIRS_NOAA21_NRT",
}


def _row(sensor: str, lat: float, lon: float, when: datetime, frp: float, confidence: float, place_hint: str, rnd: random.Random) -> dict[str, Any]:
    sat, scan, track = _sensor_meta(sensor, rnd)
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "acq_datetime": when,
        "confidence_pct": round(confidence, 1),
        "frp": round(frp, 2),
        "sensor": sensor,
        "satellite": sat,
        "daynight": "D" if 6 <= when.hour <= 18 else "N",
        "scan_km": scan,
        "track_km": track,
        "brightness_k": round(320 + frp * 0.5 + rnd.uniform(-5, 15), 1),
        "brightness_2_k": round(295 + rnd.uniform(-3, 8), 1),
        "version": "6.1NRT",
        "source": _FIRMS_SOURCE_BY_SENSOR.get(sensor, sensor.upper() + "_NRT"),
        "place_hint": place_hint,
    }


def dhaka_demo_hotspots(now: datetime | None = None) -> list[dict[str, Any]]:
    """Small multi-sensor fire clusters spread across Bangladesh.

    The Ashulia (Dhaka) cluster is the flagship demo fire used for the Fire
    Evidence walkthrough; the rest give the map a realistic country-wide
    spread. Timestamps are rebuilt relative to ``now`` so every point falls
    inside the "Last 24 h" / "Last 48 h" period selectors.
    """
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    rnd = random.Random(DHAKA_DEMO_SEED)
    rows: list[dict[str, Any]] = []

    sensors_cycle = [
        "modis", "viirs_snpp", "viirs_noaa20",
        "modis", "viirs_snpp", "viirs_noaa21",
    ]

    for c_lat, c_lon, label, count, peak_frp, spread, hours_span in DEMO_CLUSTERS:
        for i in range(count):
            hours_ago = max(2.0, hours_span - i * (hours_span - 2.0) / max(1, count - 1))
            drift = i * (spread * 0.02)
            lat = c_lat + drift + rnd.uniform(-spread * 0.6, spread * 0.6)
            lon = c_lon + drift + rnd.uniform(-spread * 0.8, spread * 0.8)
            sensor = sensors_cycle[i % len(sensors_cycle)]
            recency = max(0.0, 1.0 - hours_ago / hours_span)
            frp = max(8.0, (peak_frp * 0.25) + peak_frp * 0.75 * recency + rnd.uniform(-peak_frp * 0.10, peak_frp * 0.15))
            confidence = 86.0 + rnd.uniform(-6, 10)
            when = now - timedelta(hours=hours_ago)
            rows.append(_row(sensor, lat, lon, when, frp, confidence, label, rnd))

    return rows


def bbox_covers_dhaka(bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    west, south, east, north = bbox
    return west <= DEMO_CENTER_LON <= east and south <= DEMO_CENTER_LAT <= north


# ---------------------------------------------------------------------------
# Demo news articles for the Fire Evidence walkthrough.
#
# Fill this list with dicts shaped like:
#   {
#       "title": "Massive fire at Ashulia garment factory ...",
#       "description": "...",
#       "published": "2026-09-30T10:15:00Z",   # ISO 8601 UTC
#       "url": "https://example.com/...",
#       "publication": "The Daily Star",
#       "domain": "thedailystar.net",
#       "provider": "demo",
#   }
# ---------------------------------------------------------------------------
DEMO_NEWS: list[dict[str, Any]] = []
