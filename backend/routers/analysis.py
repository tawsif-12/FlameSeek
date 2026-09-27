from __future__ import annotations

from datetime import date
from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from config import ANOMALY_THRESHOLD, MAX_AOI_DEGREES_SPAN, MAX_DATE_RANGE_DAYS
from critical_periods import find_critical_periods
from config import CONFIDENCE_THRESHOLD
from firms_client import FirmsAPIError, fetch_hotspots_for_window, fetch_recent_hotspots
from harmonize import build_daily_series, filter_low_confidence, summarize_daily_series
from evidence import build_hotspot_evidence
from schemas import (
    CriticalPeriodsResponse,
    CurrentHotspotsResponse,
    GenerateCalendarRequest,
    GenerateCalendarResponse,
    HotspotEvidenceRequest,
    HotspotEvidenceResponse,
    HotspotRecord,
    VerifiedHotspotsResponse,
)
from verification import verify_hotspot


router = APIRouter()


def _validate_request(payload: GenerateCalendarRequest) -> None:
    west, south, east, north = payload.bbox
    if not (-180 <= west < east <= 180):
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "West must be less than east and both must be valid longitudes."})
    if not (-90 <= south < north <= 90):
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "South must be less than north and both must be valid latitudes."})
    if (east - west) > MAX_AOI_DEGREES_SPAN or (north - south) > MAX_AOI_DEGREES_SPAN:
        raise HTTPException(status_code=400, detail={"error": "aoi_too_large", "message": "Draw a smaller area of interest (maximum 20 degrees in either direction)."})
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail={"error": "invalid_date_range", "message": "Start date must be before or equal to end date."})
    if (payload.end_date - payload.start_date).days > MAX_DATE_RANGE_DAYS:
        raise HTTPException(status_code=400, detail={"error": "date_range_too_large", "message": "Date range must be five years or less."})


async def _calendar(payload: GenerateCalendarRequest) -> GenerateCalendarResponse:
    _validate_request(payload)
    try:
        hotspots = await fetch_hotspots_for_window(payload.bbox, payload.start_date, payload.end_date, [str(sensor) for sensor in payload.sensors])
    except FirmsAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "firms_api_error", "message": exc.message, "detail": {"status_code": exc.status_code, "url": exc.url}}) from exc

    daily = build_daily_series(hotspots, payload.start_date, payload.end_date)
    summary = summarize_daily_series(daily)
    methods = sorted({row["baseline_method"] for row in daily})
    return GenerateCalendarResponse(
        daily_series=daily,
        summary=summary,
        metadata={
            "sensors": payload.sensors,
            "raw_hotspot_count": len(hotspots),
            "anomaly_threshold": ANOMALY_THRESHOLD,
            "baseline_methods": methods,
            "anomaly_basis": daily[0]["anomaly_basis"] if daily else "fire_power_index",
        },
    )


@router.post("/generate_calendar", response_model=GenerateCalendarResponse)
async def generate_calendar(payload: GenerateCalendarRequest) -> GenerateCalendarResponse:
    return await _calendar(payload)


@router.post("/critical_periods", response_model=CriticalPeriodsResponse)
async def critical_periods(payload: GenerateCalendarRequest) -> CriticalPeriodsResponse:
    calendar = await _calendar(payload)
    periods = find_critical_periods([row.model_dump() for row in calendar.daily_series])
    total_days = len(calendar.daily_series)
    critical_days = sum(period["duration_days"] for period in periods)
    return CriticalPeriodsResponse(
        periods=periods,
        metadata={
            "total_days_in_range": total_days,
            "pct_days_critical": round((critical_days / total_days) * 100, 2) if total_days else 0,
            "anomaly_threshold": ANOMALY_THRESHOLD,
        },
    )


@router.get("/critical_periods", response_model=CriticalPeriodsResponse)
async def critical_periods_get(
    bbox: str = Query(description="Comma-separated west,south,east,north"),
    start_date: date = Query(),
    end_date: date = Query(),
    sensors: list[str] = Query(default=["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]),
) -> CriticalPeriodsResponse:
    try:
        bbox_tuple = tuple(float(part.strip()) for part in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain four comma-separated numbers."}) from exc
    if len(bbox_tuple) != 4:
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain west,south,east,north."})
    payload = GenerateCalendarRequest(bbox=bbox_tuple, start_date=start_date, end_date=end_date, sensors=sensors)
    return await critical_periods(payload)


@router.get("/current_hotspots", response_model=CurrentHotspotsResponse)
async def current_hotspots(
    bbox: str | None = Query(default=None, description="Optional comma-separated west,south,east,north. Omit for world."),
    days: int = Query(default=1, ge=1, le=5),
    limit: int = Query(default=3000, ge=1, le=10000),
    sensors: list[str] = Query(default=["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]),
) -> CurrentHotspotsResponse:
    bbox_tuple = None
    if bbox:
        try:
            parsed = tuple(float(part.strip()) for part in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain four comma-separated numbers."}) from exc
        if len(parsed) != 4:
            raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain west,south,east,north."})
        west, south, east, north = parsed
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox values are outside valid latitude/longitude ranges."})
        bbox_tuple = parsed
    try:
        rows = await fetch_recent_hotspots(bbox_tuple, [str(sensor) for sensor in sensors], days)
    except FirmsAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "firms_api_error", "message": exc.message, "detail": {"status_code": exc.status_code}}) from exc

    filtered = filter_low_confidence(rows, CONFIDENCE_THRESHOLD)
    sorted_filtered = sorted(filtered, key=lambda row: row["acq_datetime"], reverse=True)
    returned = sorted_filtered[:limit]
    raw_by_sensor = dict(Counter(row["sensor"] for row in rows))
    filtered_by_sensor = dict(Counter(row["sensor"] for row in filtered))
    returned_by_sensor = dict(Counter(row["sensor"] for row in returned))
    return CurrentHotspotsResponse(
        hotspots=[HotspotRecord(**row) for row in returned],
        metadata={
            "raw_hotspot_count": len(rows),
            "filtered_hotspot_count": len(filtered),
            "returned_hotspot_count": len(returned),
            "raw_by_sensor": raw_by_sensor,
            "filtered_by_sensor": filtered_by_sensor,
            "returned_by_sensor": returned_by_sensor,
            "days": days,
            "scope": "world" if bbox_tuple is None else "bbox",
            "sensors": sensors,
        },
    )


@router.get("/verified_hotspots", response_model=VerifiedHotspotsResponse)
async def verified_hotspots(
    bbox: str | None = Query(default=None, description="Optional comma-separated west,south,east,north. Omit for world."),
    days: int = Query(default=1, ge=1, le=5),
    limit: int = Query(default=300, ge=1, le=1000),
    sensors: list[str] = Query(default=["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]),
) -> VerifiedHotspotsResponse:
    response = await current_hotspots(bbox=bbox, days=days, limit=limit, sensors=sensors)
    verified = [verify_hotspot(row.model_dump()) for row in response.hotspots]
    verdict_counts = dict(Counter(row["verification"]["verdict"] for row in verified))
    metadata = {
        **response.metadata,
        "verification_model": "firms_metadata_rules_v1",
        "verdict_counts": verdict_counts,
        "imagery_source": "NASA Worldview/GIBS",
        "news_source": "GDELT DOC API",
    }
    return VerifiedHotspotsResponse(hotspots=verified, metadata=metadata)


@router.post("/hotspot_evidence", response_model=HotspotEvidenceResponse)
async def hotspot_evidence(payload: HotspotEvidenceRequest) -> HotspotEvidenceResponse:
    hotspot = HotspotRecord(**payload.model_dump(exclude={"refresh"}))
    evidence = await build_hotspot_evidence(hotspot, refresh=payload.refresh)
    return HotspotEvidenceResponse(**evidence)
