"""Overpass prediction for the polar-orbiting fire witnesses.

Uses CelesTrak two-line elements and skyfield to find each satellite's closest
approach to a point, then checks whether the point fell inside the instrument
swath. If CelesTrak is unreachable it falls back to nominal sun-synchronous
overpass times, which say when a pass is likely but not whether it covers the point.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from geo import haversine_km
from http_utils import ExternalServiceError, request_json, request_text
from witness import SWATH_KM, WITNESS_LABEL, WITNESS_START, WITNESSES, looks_per_pass, nominal_hours


NORAD_IDS = {"terra": 25994, "aqua": 27424, "snpp": 37849, "noaa20": 43013, "noaa21": 54234}
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"


TLE_MIRROR_URL = "https://tle.ivanstanojevic.me/api/tle"


async def _tle(witness: str) -> tuple[str, str] | None:
    """Current elements from CelesTrak, or from a public CelesTrak mirror when it is unreachable."""
    try:
        text = await request_text(CELESTRAK_URL, service="CelesTrak", params={"CATNR": NORAD_IDS[witness], "FORMAT": "TLE"}, ttl_seconds=12 * 3600, disk_namespace="celestrak", timeout=15, retries=0)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        l1 = next((ln for ln in lines if ln.startswith("1 ")), None)
        l2 = next((ln for ln in lines if ln.startswith("2 ")), None)
        if l1 and l2:
            return l1, l2
    except ExternalServiceError:
        pass
    try:
        data = await request_json(f"{TLE_MIRROR_URL}/{NORAD_IDS[witness]}", service="TLE mirror", ttl_seconds=12 * 3600, disk_namespace="celestrak", timeout=15, retries=1)
    except ExternalServiceError:
        return None
    if data and data.get("line1") and data.get("line2"):
        return data["line1"], data["line2"]
    return None


def _swath_position(off_nadir_km: float, witness: str) -> str:
    frac = off_nadir_km / (SWATH_KM[witness] / 2)
    return "near nadir" if frac < 0.35 else "mid swath" if frac < 0.75 else "swath edge"


def _local_hour(t: datetime, lon: float) -> float:
    solar = t + timedelta(hours=lon / 15)
    return round(solar.hour + solar.minute / 60, 2)


def _skyfield_passes(tles: dict[str, tuple[str, str]], lat: float, lon: float, t0: datetime, t1: datetime) -> list[dict[str, Any]]:
    from skyfield.api import EarthSatellite, load, wgs84

    ts = load.timescale(builtin=True)
    site = wgs84.latlon(lat, lon)
    out = []
    for witness, (l1, l2) in tles.items():
        sat = EarthSatellite(l1, l2, witness, ts)
        times, events = sat.find_events(site, ts.from_datetime(t0), ts.from_datetime(t1), altitude_degrees=5.0)
        for t, ev in zip(times, events):
            if ev != 1:
                continue
            sub = wgs84.subpoint_of(sat.at(t))
            off = haversine_km(lat, lon, sub.latitude.degrees, sub.longitude.degrees)
            when = t.utc_datetime()
            out.append(
                {
                    "witness": witness,
                    "label": WITNESS_LABEL[witness],
                    "time": when,
                    "off_nadir_km": round(off, 1),
                    "in_swath": off <= SWATH_KM[witness] / 2 - 10,
                    "coverage_probability": 1.0 if off <= SWATH_KM[witness] / 2 - 10 else 0.0,
                    "swath_position": _swath_position(off, witness),
                    "local_solar_hour": _local_hour(when, lon),
                    "method": "skyfield + current TLEs (CelesTrak)",
                }
            )
    return out


def _nominal_passes(witnesses: list[str], lat: float, lon: float, t0: datetime, t1: datetime) -> list[dict[str, Any]]:
    out = []
    day = (t0 + timedelta(hours=lon / 15)).date() - timedelta(days=1)
    last = (t1 + timedelta(hours=lon / 15)).date() + timedelta(days=1)
    while day <= last:
        for w in witnesses:
            coverage = min(1.0, looks_per_pass(w, lat))
            for hour in nominal_hours(w, day):
                when = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=hour - lon / 15)
                if t0 <= when <= t1:
                    out.append(
                        {
                            "witness": w,
                            "label": WITNESS_LABEL[w],
                            "time": when,
                            "off_nadir_km": None,
                            "in_swath": coverage >= 0.95,
                            "coverage_probability": round(coverage, 2),
                            "swath_position": "unknown",
                            "local_solar_hour": round(hour % 24, 2),
                            "method": "nominal orbit (TLEs unavailable)",
                        }
                    )
        day += timedelta(days=1)
    return out


async def predict_passes(lat: float, lon: float, t0: datetime, t1: datetime, on: date | None = None) -> dict[str, Any]:
    """Passes of every witness operating on `on` between t0 and t1, sorted by time."""
    on = on or t0.date()
    witnesses = [w for w in WITNESSES if on >= WITNESS_START[w]]
    fetched = await asyncio.gather(*(_tle(w) for w in witnesses))
    tles = {w: tle for w, tle in zip(witnesses, fetched) if tle}
    missing = [w for w in witnesses if w not in tles]
    passes: list[dict[str, Any]] = []
    errors = []
    if tles:
        try:
            passes = await asyncio.to_thread(_skyfield_passes, tles, lat, lon, t0, t1)
        except Exception as exc:  # noqa: BLE001 - fall back to nominal times on any propagation failure
            errors.append(f"orbit propagation failed: {exc.__class__.__name__}")
            missing = witnesses
    if missing:
        passes += _nominal_passes(missing, lat, lon, t0, t1)
        errors.append("No current orbital elements for: " + ", ".join(WITNESS_LABEL[w] for w in missing) + " (nominal overpass times used).")
    passes.sort(key=lambda p: p["time"])
    return {"passes": passes, "witnesses": witnesses, "method": "skyfield + current TLEs (CelesTrak)" if tles and not missing else "partial: nominal times for some satellites" if tles else "nominal orbit", "errors": errors}
