from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from config import ANOMALY_THRESHOLD, CONFIDENCE_THRESHOLD, MAX_AOI_DEGREES_SPAN, MAX_DATE_RANGE_DAYS
from critical_periods import find_critical_periods
from evidence import build_hotspot_evidence
from firms_client import FirmsAPIError, fetch_hotspots_with_report, fetch_recent_hotspots
from geo import AOI, location_uncertainty_km
from harmonize import build_harmonized_series, filter_low_confidence, summarize_daily_series
from schemas import (
    CriticalPeriodsResponse,
    CurrentHotspotsResponse,
    GenerateCalendarRequest,
    GenerateCalendarResponse,
    HotspotEvidenceRequest,
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
        raise HTTPException(status_code=400, detail={"error": "aoi_too_large", "message": f"Draw a smaller area of interest (maximum {MAX_AOI_DEGREES_SPAN} degrees in either direction)."})
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail={"error": "invalid_date_range", "message": "Start date must be before or equal to end date."})
    if (payload.end_date - payload.start_date).days > MAX_DATE_RANGE_DAYS:
        raise HTTPException(status_code=400, detail={"error": "date_range_too_large", "message": "Date range must be five years or less; use Fire Memory for longer records."})


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        parsed = tuple(float(part.strip()) for part in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain four comma-separated numbers."}) from exc
    if len(parsed) != 4:
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox must contain west,south,east,north."})
    west, south, east, north = parsed
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(status_code=400, detail={"error": "invalid_bbox", "message": "BBox values are outside valid latitude/longitude ranges."})
    return parsed  # type: ignore[return-value]


async def _calendar(payload: GenerateCalendarRequest) -> GenerateCalendarResponse:
    _validate_request(payload)
    aoi = AOI.from_payload({"bbox": payload.bbox, "geometry": payload.geometry})
    try:
        hotspots, report = await fetch_hotspots_with_report(payload.bbox, payload.start_date, payload.end_date, [str(sensor) for sensor in payload.sensors])
    except FirmsAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "firms_api_error", "message": exc.message, "detail": {"status_code": exc.status_code, "url": exc.url}}) from exc
    hotspots = aoi.filter(hotspots)
    west, south, east, north = aoi.bbox
    daily, calibration = build_harmonized_series(hotspots, payload.start_date, payload.end_date, [str(s) for s in payload.sensors], area_km2=aoi.area_km2(), lat_center=(south + north) / 2)
    calibration.pop("witness")
    summary = summarize_daily_series(daily)
    return GenerateCalendarResponse(
        daily_series=daily,
        summary=summary,
        metadata={
            "sensors": payload.sensors,
            "raw_hotspot_count": len(hotspots),
            "anomaly_threshold": ANOMALY_THRESHOLD,
            "baseline_methods": sorted({row["baseline_method"] for row in daily}),
            "anomaly_basis": "harmonized_activity",
            "calibration": calibration,
            "failed_chunks": report["failed_chunks"],
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
    bbox_tuple = _parse_bbox(bbox)
    payload = GenerateCalendarRequest(bbox=bbox_tuple, start_date=start_date, end_date=end_date, sensors=sensors)  # type: ignore[arg-type]
    return await critical_periods(payload)


@router.get("/current_hotspots", response_model=CurrentHotspotsResponse)
async def current_hotspots(
    bbox: str | None = Query(default=None, description="Optional comma-separated west,south,east,north. Omit for world."),
    days: int = Query(default=1, ge=1, le=5),
    limit: int = Query(default=3000, ge=1, le=20000),
    sensors: list[str] = Query(default=["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]),
    date_: date | None = Query(default=None, alias="date", description="Historical start date (UTC). Omit for the most recent days."),
) -> CurrentHotspotsResponse:
    bbox_tuple = _parse_bbox(bbox)
    try:
        if date_ is None:
            rows = await fetch_recent_hotspots(bbox_tuple, [str(sensor) for sensor in sensors], days)
            failed = []
        else:
            rows, report = await fetch_hotspots_with_report(bbox_tuple or "world", date_, date_ + timedelta(days=days - 1), [str(s) for s in sensors])
            failed = report["failed_chunks"]
    except FirmsAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "firms_api_error", "message": exc.message, "detail": {"status_code": exc.status_code}}) from exc

    filtered = filter_low_confidence(rows, CONFIDENCE_THRESHOLD)
    for row in filtered:
        row["location_uncertainty_km"] = location_uncertainty_km(row)
    # Sample evenly by FRP rank rather than only newest, so a limit keeps the strongest fires visible.
    sorted_filtered = sorted(filtered, key=lambda row: (row.get("frp") or 0), reverse=True)
    returned = sorted_filtered[:limit]
    return CurrentHotspotsResponse(
        hotspots=[HotspotRecord(**row) for row in returned],
        metadata={
            "raw_hotspot_count": len(rows),
            "filtered_hotspot_count": len(filtered),
            "returned_hotspot_count": len(returned),
            "raw_by_sensor": dict(Counter(row["sensor"] for row in rows)),
            "filtered_by_sensor": dict(Counter(row["sensor"] for row in filtered)),
            "returned_by_sensor": dict(Counter(row["sensor"] for row in returned)),
            "days": days,
            "date": date_.isoformat() if date_ else None,
            "mode": "historical" if date_ else "recent",
            "scope": "world" if bbox_tuple is None else "bbox",
            "sensors": sensors,
            "selection": f"strongest {len(returned)} by FRP" if len(returned) < len(filtered) else "all",
            "failed_chunks": failed,
        },
    )


@router.get("/verified_hotspots", response_model=VerifiedHotspotsResponse)
async def verified_hotspots(
    bbox: str | None = Query(default=None, description="Optional comma-separated west,south,east,north. Omit for world."),
    days: int = Query(default=1, ge=1, le=5),
    limit: int = Query(default=300, ge=1, le=1000),
    sensors: list[str] = Query(default=["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]),
) -> VerifiedHotspotsResponse:
    response = await current_hotspots(bbox=bbox, days=days, limit=limit, sensors=sensors, date_=None)
    verified = [verify_hotspot(row.model_dump()) for row in response.hotspots]
    return VerifiedHotspotsResponse(
        hotspots=verified,
        metadata={
            **response.metadata,
            "verification_model": "firms_metadata_screen_v2",
            "verdict_counts": dict(Counter(row["verification"]["verdict"] for row in verified)),
            "note": "Metadata screening grades only the satellite signal. It never confirms a fire.",
        },
    )


@router.post("/hotspot_evidence")
async def hotspot_evidence(payload: HotspotEvidenceRequest) -> dict:
    hotspot = HotspotRecord(**payload.model_dump(exclude={"refresh"}))
    return await build_hotspot_evidence(hotspot, refresh=payload.refresh)
