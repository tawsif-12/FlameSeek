from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from config import ANOMALY_THRESHOLD, MAX_AOI_DEGREES_SPAN, MAX_DATE_RANGE_DAYS
from critical_periods import find_critical_periods
from firms_client import FirmsAPIError, fetch_hotspots_with_report, recent_source_status
from geo import AOI, location_uncertainty_km
from harmonize import build_harmonized_series, filter_low_confidence, summarize_daily_series
from schemas import CriticalPeriodsResponse, GenerateCalendarRequest, GenerateCalendarResponse


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
