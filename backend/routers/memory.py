"""Fire Memory: long-term burning activity calendar for an area of interest."""

from __future__ import annotations

import asyncio

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from changepoint import detect_monthly_change_points
from config import MAX_AOI_DEGREES_SPAN, SENSOR_START_DATES
from critical_periods import find_critical_periods
from environment import daily_weather
from events import reconstruct_events
from firms_client import fetch_hotspots_with_report, sensor_available
from geo import AOI
from harmonize import build_harmonized_series, filter_low_confidence, summarize_daily_series
from http_utils import ExternalServiceError
from jobs import Job, start_job
from quality import summarize_observations
from schemas import FireMemoryRequest
from seasonal import calendar_grid, compare_current, monthly_series, seasonal_profile


router = APIRouter()


def _compact_daily(row: dict[str, Any]) -> dict[str, Any]:
    obs = row["observation"]
    return {
        "date": row["date"].isoformat(),
        "harmonized_activity": row["harmonized_activity"],
        "harmonized_low": round(row["harmonized_low"], 2),
        "harmonized_high": round(row["harmonized_high"], 2),
        "hotspot_count": row["hotspot_count"],
        "modis_count": row["modis_count"],
        "viirs_count": row["viirs_count"],
        "modis_active_cells": row["modis_active_cells"],
        "viirs_active_cells": row["viirs_active_cells"],
        "active_cell_count": row["active_cell_count"],
        "max_frp": row["max_frp"],
        "fire_power_index": row["fire_power_index"],
        "anomaly_score": row["anomaly_score"],
        "anomaly_category": row["anomaly_category"],
        "baseline_median": row["baseline_median"],
        "baseline_method": row["baseline_method"],
        "sensor_agreement": row["sensor_agreement"],
        "observation_status": obs["status"],
        "observation_display": obs["display"],
        "sufficiency_score": obs["sufficiency_score"],
        "cloud_cover_pct": obs["cloud_cover_pct"],
    }


async def run_fire_memory(job: Job, payload: FireMemoryRequest) -> dict[str, Any]:
    aoi = AOI.from_payload(payload.aoi.model_dump())
    west, south, east, north = aoi.bbox
    if (east - west) > MAX_AOI_DEGREES_SPAN or (north - south) > MAX_AOI_DEGREES_SPAN:
        raise ValueError(f"Area too large: choose an area under {MAX_AOI_DEGREES_SPAN} degrees across (e.g. a state or district instead of a whole country).")
    end = payload.end_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    try:
        start = end.replace(year=end.year - payload.history_years) + timedelta(days=1)
    except ValueError:
        start = end.replace(year=end.year - payload.history_years, day=28) + timedelta(days=1)
    start = max(start, SENSOR_START_DATES["modis"])
    sensors = [str(s) for s in payload.sensors]

    async def on_progress(done: int, total: int) -> None:
        await job.update(f"Downloading MODIS/VIIRS archive: {done}/{total} FIRMS requests", 0.05 + 0.75 * done / max(total, 1))

    await job.update("Planning FIRMS archive requests", 0.02)
    rows, report = await fetch_hotspots_with_report(aoi.bbox, start, end, sensors, progress=on_progress)
    rows = aoi.filter(rows)

    await job.update("Fetching ERA5 cloud cover for observation sufficiency", 0.82)
    lat_c, lon_c = (south + north) / 2, (west + east) / 2
    if aoi.center:
        lon_c, lat_c = aoi.center
    cloud: dict[date, float | None] = {}
    try:
        for w in await daily_weather(lat_c, lon_c, start, end):
            cloud[date.fromisoformat(w["time"])] = w.get("cloud_cover_mean")
        cloud_status = "ok"
    except ExternalServiceError as exc:
        cloud_status = f"unavailable: {exc}"

    failed_days: dict[str, set[date]] = defaultdict(set)
    for f in report["failed_chunks"]:
        d0 = date.fromisoformat(f["start"])
        for k in range(f["days"]):
            failed_days[f["sensor"]].add(d0 + timedelta(days=k))
    availability: dict[date, list[str]] = {}
    cursor = start
    while cursor <= end:
        availability[cursor] = [s for s in sensors if sensor_available(s, cursor) and cursor not in failed_days[s]]
        cursor += timedelta(days=1)

    await job.update("Harmonizing sensors, reconstructing events, building seasonal profile", 0.86)
    end_ref = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    def analyse():
        daily, calibration = build_harmonized_series(rows, start, end, sensors, availability, cloud)
        confident = filter_low_confidence(rows)
        events = reconstruct_events(confident, reference_time=end_ref)
        monthly = monthly_series(daily, confident)
        profile = seasonal_profile(monthly, events)
        return daily, calibration, events, monthly, profile

    daily, calibration, events, monthly, profile = await asyncio.to_thread(analyse)
    comparison = compare_current(daily, profile, payload.comparison_window_days)
    change_points = detect_monthly_change_points(monthly)
    periods = find_critical_periods(daily)[:25]

    return {
        "aoi": aoi.describe(),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "years": payload.history_years, "days": len(daily)},
        "summary": summarize_daily_series(daily),
        "daily": [_compact_daily(r) for r in daily],
        "monthly": monthly,
        "calendar": calendar_grid(monthly),
        "seasonal_profile": profile,
        "current_vs_historical": comparison,
        "change_points": change_points,
        "critical_periods": [{**p, "start_date": p["start_date"].isoformat(), "end_date": p["end_date"].isoformat()} for p in periods],
        "calibration": calibration,
        "observation_quality": summarize_observations(daily),
        "events": {"count": len(events), "multi_detection": sum(1 for e in events if e["observation_count"] > 1)},
        "provenance": {
            "data_sources": report["sources_used"],
            "sensors": sensors,
            "firms_requests": report["requests"],
            "failed_chunks": report["failed_chunks"][:50],
            "raw_detections_in_aoi": len(rows),
            "confidence_threshold_pct": 30,
            "grid": "0.01 deg (~1 km, MODIS-scale) with footprint-weighted attribution from FIRMS scan/track",
            "harmonization": calibration["note"],
            "anomaly_method": "Robust z = (x - median) / (1.4826 * MAD) against the same +/-7-day window in other years (>= 3 years), else a rolling 31-day window.",
            "anomaly_categories": {"Normal": "< 2", "Above Normal": "2 to 3.5", "Unusual": "3.5 to 5", "Highly Unusual": ">= 5"},
            "cloud_cover": f"ERA5 daily mean via Open-Meteo at AOI centre ({lat_c:.2f}, {lon_c:.2f}); {cloud_status}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.post("/fire_memory")
async def fire_memory(payload: FireMemoryRequest) -> dict[str, Any]:
    try:
        AOI.from_payload(payload.aoi.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_aoi", "message": str(exc)}) from exc
    job = start_job("fire_memory", payload.model_dump(mode="json"), lambda job: run_fire_memory(job, payload))
    return job.to_dict()
