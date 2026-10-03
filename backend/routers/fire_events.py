"""Fire Identity / Evidence / Past / Future / Exposure for reconstructed events."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from analogues import find_analogues
from config import DEFAULT_SENSORS, HISTORY_SENSORS
from demo_data import cloud_at, scenario_for
from demo_outlook import scenario_outlook
from environment import daily_weather, hourly_weather
from events import event_summary, reconstruct_events
from evidence import build_evidence, subject_from_event
from exposure import analyze_exposure
from firms_client import FirmsAPIError, fetch_recent_hotspots, sensor_available
from forecast import forecast_event
from harmonize import filter_low_confidence
from history import regional_history
from http_utils import ExternalServiceError
from jobs import Job, start_job
from geo import location_uncertainty_km
from quality import sufficiency_score
from routers.analysis import _parse_bbox


router = APIRouter()
_EVENTS: dict[str, dict[str, Any]] = {}
_DETECTION_INDEX: dict[str, str] = {}
_CASES: dict[str, dict[str, Any]] = {}
STREAM_NAMES = {"B": "regional satellites", "C": "news and official reports"}
_SET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
SET_TTL = 15 * 60


def detection_key(sensor: str, lat: float, lon: float, when: Any) -> str:
    t = when if isinstance(when, datetime) else datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    return f"{sensor}|{lat:.4f}|{lon:.4f}|{t.astimezone(timezone.utc).strftime('%Y%m%d%H%M')}"


def _store(events: list[dict[str, Any]]) -> None:
    for ev in events:
        _EVENTS[ev["event_id"]] = ev
        for d in ev["detections"]:
            _DETECTION_INDEX[detection_key(d["sensor"], d["lat"], d["lon"], d["acq_datetime"])] = ev["event_id"]


def _provisional_marker(ev: dict[str, Any]) -> dict[str, Any]:
    """Marker for an event whose case has not gathered external evidence yet."""
    since = ev["behaviour"]["metrics"]["hours_since_last_detection"]
    state = "Ended" if since > 48 else "Growing" if ev["behaviour"]["state"] in {"Expanding", "Intensifying"} else "Weakening" if ev["behaviour"]["state"] == "Decaying" else "Active"
    return {"kind": "unknown", "reality": "No external confirmation yet", "state": state, "provisional": True, "evidence_checked": False}


def _layer_row(ev: dict[str, Any]) -> dict[str, Any]:
    s = event_summary(ev)
    s["behaviour_state"] = ev["behaviour"]["state"]
    s["behaviour"] = {"state": ev["behaviour"]["state"], "label_type": ev["behaviour"]["label_type"]}
    case = _CASES.get(ev["event_id"])
    s["case"] = {**case["marker"], "evidence_checked": True, "updated_at": case["updated_at"]} if case else _provisional_marker(ev)
    s["featured"] = any(d.get("place_hint") for d in ev["detections"])
    s["place_hint"] = next((d["place_hint"] for d in ev["detections"] if d.get("place_hint")), None)
    if ev["observation_count"] == 1:
        s["hull"] = []
    return s


@router.get("/events")
async def list_events(
    bbox: str | None = Query(default=None, description="west,south,east,north; omit for world"),
    days: int = Query(default=2, ge=1, le=5),
    limit: int = Query(default=2500, ge=1, le=20000),
    min_detections: int = Query(default=1, ge=1),
) -> dict[str, Any]:
    key = f"{bbox}|{days}"
    cached = _SET_CACHE.get(key)
    if cached and time.time() - cached[0] < SET_TTL:
        result = cached[1]
    else:
        try:
            rows = await fetch_recent_hotspots(_parse_bbox(bbox), DEFAULT_SENSORS, days)
        except FirmsAPIError as exc:
            raise HTTPException(status_code=502, detail={"error": "firms_api_error", "message": exc.message}) from exc
        rows = filter_low_confidence(rows)
        started = time.perf_counter()
        events = await asyncio.to_thread(reconstruct_events, rows)
        _store(events)
        result = {"events": events, "detections": len(rows), "elapsed_ms": round((time.perf_counter() - started) * 1000)}
        _SET_CACHE[key] = (time.time(), result)
    events = [e for e in result["events"] if e["observation_count"] >= min_detections]
    # Featured (demo scenario) events are always returned, ahead of the strongest-by-FRP cut.
    events.sort(key=lambda e: not any(d.get("place_hint") for d in e["detections"]))
    return {
        "events": [_layer_row(e) for e in events[:limit]],
        "metadata": {
            "detections": result["detections"],
            "events_total": len(result["events"]),
            "events_returned": min(limit, len(events)),
            "multi_detection_events": sum(1 for e in result["events"] if e["observation_count"] > 1),
            "behaviour_counts": dict(Counter(e["behaviour"]["state"] for e in result["events"])),
            "days": days,
            "clustering": "Linked if <= 48 h apart and within both pixels' location uncertainty + 0.5 km + 2 km/day spread allowance (max 6 km).",
            "reconstruction_ms": result["elapsed_ms"],
        },
    }


@router.get("/events/lookup")
async def lookup_event(sensor: str, lat: float, lon: float, acq_datetime: str) -> dict[str, Any]:
    event_id = _DETECTION_INDEX.get(detection_key(sensor, lat, lon, acq_datetime))
    if not event_id:
        # Load the recent world set, which indexes every current detection.
        await list_events(bbox=None, days=2, limit=1, min_detections=1)
        event_id = _DETECTION_INDEX.get(detection_key(sensor, lat, lon, acq_datetime))
    if not event_id:
        await list_events(bbox=None, days=5, limit=1, min_detections=1)
        event_id = _DETECTION_INDEX.get(detection_key(sensor, lat, lon, acq_datetime))
    if not event_id:
        raise HTTPException(status_code=404, detail={"error": "event_not_found", "message": "This detection is not part of the currently loaded event set."})
    return {"event_id": event_id}


def _get(event_id: str) -> dict[str, Any]:
    ev = _EVENTS.get(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail={"error": "event_not_found", "message": "Event not loaded; refresh the globe."})
    return ev


async def _observation_quality(ev: dict[str, Any]) -> dict[str, Any]:
    c = ev["centroid"]
    now = datetime.now(timezone.utc)
    cloud_rows = []
    scenario = scenario_for({"lat": c["lat"], "lon": c["lon"], "detections": ev["detections"]})
    if scenario:
        cloud_rows = [{"cloud_cover": cloud_at(scenario, now - timedelta(hours=h), now)} for h in range(24)]
    else:
        try:
            cloud_rows = [r for r in await hourly_weather(c["lat"], c["lon"], (now - timedelta(days=1)).date(), now.date()) if r["time"] <= now.strftime("%Y-%m-%dT%H:00")][-24:]
        except ExternalServiceError:
            pass
    clouds = [r["cloud_cover"] for r in cloud_rows if r.get("cloud_cover") is not None]
    cloud = round(sum(clouds) / len(clouds), 1) if clouds else None
    available = [s for s in DEFAULT_SENSORS if sensor_available(s, now.date())]
    families = set(ev["sensor_families"])
    n = ev["observation_count"]
    if n == 1:
        uncertainty = "high"
    elif {"MODIS", "VIIRS"} <= families and n >= 5:
        uncertainty = "low"
    else:
        uncertainty = "moderate"
    return {
        "sensor_agreement": "MODIS and VIIRS both detected this event" if {"MODIS", "VIIRS"} <= families else f"Only {', '.join(sorted(families))} detected this event",
        "platforms_available": available,
        "recent_cloud_cover_pct": cloud,
        "observation_sufficiency_score": sufficiency_score(len(available), cloud),
        "location_uncertainty_km": round(max(location_uncertainty_km(d) for d in ev["detections"]), 2) if ev["detections"] else None,
        "uncertainty": uncertainty,
        "uncertainty_note": "Low when multiple sensors and many detections agree; high for a single detection.",
        "status_if_absent": "UNKNOWN" if cloud is not None and cloud >= 70 else "valid observation",
        "provenance": {
            "sources": sorted({d.get("source") or d["sensor"] for d in ev["detections"]}),
            "cloud_cover_source": "Open-Meteo forecast model, mean of the last 24 h at the event centroid (proxy for satellite cloud masking)",
        },
    }


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    ev = _get(event_id)
    for d in ev["detections"]:
        d.setdefault("location_uncertainty_km", location_uncertainty_km(d))
    return {**ev, "observation_quality": await _observation_quality(ev)}


async def _run_evidence(job: Job, ev: dict[str, Any], refresh: bool) -> dict[str, Any]:
    await job.update("Reverse geocoding and querying satellites, agencies and news", 0.1)
    subject = subject_from_event(ev)
    subject["observation_quality"] = await _observation_quality(ev)

    async def on_partial(case: dict[str, Any]) -> None:
        # Publish each provisional answer so the map marker updates after every stream.
        now = datetime.now(timezone.utc).isoformat()
        _CASES[ev["event_id"]] = {**case, "updated_at": now}
        job.partial = {"fire_case": case, "updated_at": now}
        pending = case["streams"]["pending"]
        await job.update("Waiting for " + ", ".join(STREAM_NAMES[s] for s in pending) if pending else "Combining all evidence", 0.2 + 0.6 * (2 - len(pending)) / 2)

    result = await build_evidence(subject, refresh=refresh, on_partial=on_partial)
    _CASES[ev["event_id"]] = {**result["fire_case"], "updated_at": result["generated_at"]}
    return result


@router.get("/events/{event_id}/case")
async def get_case(event_id: str) -> dict[str, Any]:
    case = _CASES.get(event_id)
    if not case:
        ev = _get(event_id)
        return {"case_id": event_id, "status": "open", "provisional": True, "marker": _provisional_marker(ev), "note": "No evidence gathered yet; run POST /events/{id}/evidence."}
    return case


@router.post("/events/{event_id}/evidence")
async def event_evidence(event_id: str, refresh: bool = False) -> dict[str, Any]:
    ev = _get(event_id)
    return start_job("evidence", {"event_id": event_id}, lambda job: _run_evidence(job, ev, refresh)).to_dict()


async def _run_outlook(job: Job, ev: dict[str, Any], years: int) -> dict[str, Any]:
    c = ev["centroid"]
    scenario = scenario_for({"lat": c["lat"], "lon": c["lon"], "detections": ev["detections"]})
    if scenario:
        # Demo scenario: scripted analogues, forecast and exposure, staged so the progress bar is visible.
        steps = [("Fetching the same season in earlier years from the FIRMS archive", 0.25), ("Searching historical analogues", 0.5), ("Training and validating forecast models", 0.75), ("Overlaying the corridor with population and infrastructure", 0.93)]
        for message, fraction in steps:
            await job.update(message, fraction)
            await asyncio.sleep(1.4)
        return scenario_outlook(scenario, ev)
    today = datetime.now(timezone.utc).date()

    async def progress(message: str, fraction: float) -> None:
        await job.update(message, 0.05 + 0.45 * fraction)

    history = await regional_history(c["lat"], c["lon"], today, years=years, progress=progress)
    await job.update("Searching historical analogues", 0.52)
    start_day = ev["first_detection"].date() if isinstance(ev["first_detection"], datetime) else today
    try:
        weather_rows = await daily_weather(c["lat"], c["lon"], start_day, start_day)
    except ExternalServiceError:
        weather_rows = []
    analogues = await asyncio.to_thread(find_analogues, ev, history, weather_rows[0] if weather_rows else None)

    await job.update("Loading recent detections for the forecast domain", 0.58)
    west, south, east, north = history["bbox"]
    try:
        recent = filter_low_confidence(await fetch_recent_hotspots((west, south, east, north), HISTORY_SENSORS, 3))
    except FirmsAPIError:
        recent = [d for d in ev["detections"] if d["sensor"] in HISTORY_SENSORS]
    quality = await _observation_quality(ev)

    async def fprogress(message: str, fraction: float) -> None:
        await job.update(message, 0.6 + 0.3 * fraction)

    forecast = await forecast_event(ev, history, recent, quality, progress=fprogress)
    await job.update("Overlaying the corridor with population and infrastructure", 0.93)
    exposure = await analyze_exposure(forecast)
    return {
        "event_id": ev["event_id"],
        "history": {k: history[k] for k in ("bbox", "radius_km", "years", "window_days", "per_year", "failed_years", "sensors")} | {"detections": len(history["rows"])},
        "analogues": analogues,
        "forecast": forecast,
        "exposure": exposure,
    }


@router.post("/events/{event_id}/outlook")
async def event_outlook(event_id: str, years: int = Query(default=8, ge=3, le=14)) -> dict[str, Any]:
    ev = _get(event_id)
    return start_job("outlook", {"event_id": event_id, "years": years}, lambda job: _run_outlook(job, ev, years)).to_dict()

