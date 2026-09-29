"""Pydantic contracts shared by routers and OpenAPI."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from config import DEFAULT_SENSORS


SensorName = Literal["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]
AnySensor = Literal["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21", "goes", "landsat"]
BBox = tuple[float, float, float, float]


class AOIModel(BaseModel):
    """Area of interest: bbox, polygon (GeoJSON geometry from drawing or place search), or radius."""

    bbox: BBox | None = Field(default=None, description="west, south, east, north")
    geometry: dict[str, Any] | None = Field(default=None, description="GeoJSON Polygon or MultiPolygon")
    center: tuple[float, float] | None = Field(default=None, description="lon, lat for radius search")
    radius_km: float | None = Field(default=None, gt=0, le=500)
    name: str | None = None
    kind: Literal["bbox", "polygon", "radius", "place"] | None = None


class GenerateCalendarRequest(BaseModel):
    bbox: BBox = Field(description="west, south, east, north")
    start_date: date
    end_date: date
    sensors: list[SensorName] = Field(default_factory=lambda: list(DEFAULT_SENSORS))
    geometry: dict[str, Any] | None = None


class FireMemoryRequest(BaseModel):
    aoi: AOIModel
    history_years: int = Field(default=10, ge=1, le=26)
    end_date: date | None = None
    sensors: list[SensorName] = Field(default_factory=lambda: ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"])
    comparison_window_days: int = Field(default=30, ge=7, le=120)


class DailyRecord(BaseModel):
    date: date
    hotspot_count: int
    mean_frp: float | None = None
    fire_power_index: float
    active_cell_count: int
    anomaly_score: float
    baseline_method: str = "flat"
    anomaly_basis: str = "harmonized_activity"
    anomaly_category: str = "Normal"
    harmonized_activity: float = 0.0
    harmonized_low: float = 0.0
    harmonized_high: float = 0.0
    modis_count: int = 0
    viirs_count: int = 0
    modis_active_cells: float = 0.0
    viirs_active_cells: float = 0.0
    max_frp: float | None = None
    sensor_agreement: str = ""
    baseline_median: float = 0.0
    observation: dict[str, Any] = Field(default_factory=dict)


class CalendarSummary(BaseModel):
    total_hotspots: int
    peak_day: date | None = None
    high_anomaly_days: int
    total_harmonized_activity: float = 0.0
    category_counts: dict[str, int] = Field(default_factory=dict)


class GenerateCalendarResponse(BaseModel):
    daily_series: list[DailyRecord]
    summary: CalendarSummary
    metadata: dict


class CriticalPeriod(BaseModel):
    start_date: date
    end_date: date
    duration_days: int
    max_anomaly: float
    avg_hotspot_count: float
    total_hotspots: int


class CriticalPeriodsResponse(BaseModel):
    periods: list[CriticalPeriod]
    metadata: dict


class HotspotRecord(BaseModel):
    lat: float
    lon: float
    acq_datetime: datetime
    confidence_pct: float
    frp: float | None = None
    sensor: AnySensor
    satellite: str = ""
    daynight: str = ""
    scan_km: float | None = None
    track_km: float | None = None
    brightness_k: float | None = None
    brightness_2_k: float | None = None
    version: str = ""
    source: str = ""
    location_uncertainty_km: float | None = None
    place_hint: str | None = None


class VerificationEvidence(BaseModel):
    source: str
    signal: str
    weight: int | float


class HotspotVerification(BaseModel):
    score: int
    verdict: Literal["strong_satellite_signal", "needs_review", "weak_satellite_signal"]
    evidence: list[VerificationEvidence]
    warnings: list[str]
    imagery_url: str
    news_url: str
    national_news_url: str
    country_code: str | None = None
    country_name: str
    place_name: str
    next_step: str
    sensor_family: str


class VerifiedHotspotRecord(HotspotRecord):
    verification: HotspotVerification


class CurrentHotspotsResponse(BaseModel):
    hotspots: list[HotspotRecord]
    metadata: dict


class VerifiedHotspotsResponse(BaseModel):
    hotspots: list[VerifiedHotspotRecord]
    metadata: dict


class HotspotEvidenceRequest(HotspotRecord):
    refresh: bool = False


class JobResponse(BaseModel):
    id: str
    kind: str
    status: str
    progress: float
    message: str
    error: str | None = None
    created_at: str
    finished_at: str | None = None
    result: Any = None
