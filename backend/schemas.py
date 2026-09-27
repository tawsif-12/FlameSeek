"""Pydantic contracts shared by routers and OpenAPI."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from config import DEFAULT_SENSORS


SensorName = Literal["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]
BBox = tuple[float, float, float, float]


class GenerateCalendarRequest(BaseModel):
    bbox: BBox = Field(description="west, south, east, north")
    start_date: date
    end_date: date
    sensors: list[SensorName] = Field(default_factory=lambda: list(DEFAULT_SENSORS))


class DailyRecord(BaseModel):
    date: date
    hotspot_count: int
    mean_frp: float | None = None
    fire_power_index: float
    active_cell_count: int
    anomaly_score: float
    baseline_method: str = "flat"
    anomaly_basis: str = "fire_power_index"


class CalendarSummary(BaseModel):
    total_hotspots: int
    peak_day: date | None = None
    high_anomaly_days: int


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
    sensor: SensorName
    satellite: str = ""
    daynight: str = ""


class VerificationEvidence(BaseModel):
    source: str
    signal: str
    weight: int | float


class HotspotVerification(BaseModel):
    score: int
    verdict: Literal["confirmed_fire", "needs_review", "likely_false_positive"]
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


class HotspotEvidenceResponse(BaseModel):
    hotspot: HotspotRecord
    place: dict
    stages: list[dict]
    satellite_evidence: dict
    government_evidence: dict
    news_evidence: dict
    fusion: dict
    source_transparency: dict
    cache: dict
