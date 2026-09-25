"""Pure functions for turning mixed-sensor hotspots into a daily fire calendar.

The core harmonization step snaps MODIS and VIIRS detections onto a common
roughly kilometer-scale grid so the app reports active cells, not only raw
sensor-biased point counts. Confidence filtering suppresses marginal detections
before aggregation. Anomaly scores use day-of-year climatology when enough
history exists, then fall back to rolling and flat baselines for short demos.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import mean, pstdev
from typing import Any

from config import ANOMALY_THRESHOLD, CONFIDENCE_THRESHOLD, GRID_RES


def filter_low_confidence(hotspots: list[dict[str, Any]], threshold: float = CONFIDENCE_THRESHOLD) -> list[dict[str, Any]]:
    return [row for row in hotspots if float(row.get("confidence_pct", 0)) >= threshold]


def snap_value(value: float, grid_res: float = GRID_RES) -> float:
    return round(round(value / grid_res) * grid_res, 6)


def snap_to_grid(hotspots: list[dict[str, Any]], grid_res: float = GRID_RES) -> list[dict[str, Any]]:
    snapped = []
    for row in hotspots:
        item = dict(row)
        item["grid_lat"] = snap_value(float(item["lat"]), grid_res)
        item["grid_lon"] = snap_value(float(item["lon"]), grid_res)
        snapped.append(item)
    return snapped


def _record_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def aggregate_cell_days(hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[date, float, float], list[dict[str, Any]]] = defaultdict(list)
    for row in hotspots:
        groups[(_record_date(row["acq_datetime"]), row["grid_lat"], row["grid_lon"])].append(row)

    cell_days = []
    for (day, grid_lat, grid_lon), rows in groups.items():
        frps = [float(row["frp"]) for row in rows if row.get("frp") is not None]
        cell_days.append(
            {
                "date": day,
                "grid_lat": grid_lat,
                "grid_lon": grid_lon,
                "hotspot_count": len(rows),
                "mean_frp": mean(frps) if frps else None,
            }
        )
    return sorted(cell_days, key=lambda row: (row["date"], row["grid_lat"], row["grid_lon"]))


def aggregate_aoi_daily(cell_days: list[dict[str, Any]], start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in cell_days:
        by_day[row["date"]].append(row)

    if start_date is None or end_date is None:
        if not by_day:
            return []
        start_date = min(by_day)
        end_date = max(by_day)

    daily = []
    cursor = start_date
    while cursor <= end_date:
        rows = by_day.get(cursor, [])
        hotspot_count = sum(row["hotspot_count"] for row in rows)
        frp_values = [row["mean_frp"] for row in rows if row.get("mean_frp") is not None]
        fire_power_index = sum(row["mean_frp"] for row in rows if row.get("mean_frp") is not None)
        daily.append(
            {
                "date": cursor,
                "hotspot_count": hotspot_count,
                "mean_frp": mean(frp_values) if frp_values else None,
                "fire_power_index": round(fire_power_index, 3),
                "active_cell_count": len(rows),
            }
        )
        cursor += timedelta(days=1)
    return daily


def _z_score(value: float, samples: list[float]) -> float:
    if len(samples) < 2:
        return 0.0
    sigma = pstdev(samples)
    if sigma == 0:
        return 0.0
    return (value - mean(samples)) / sigma


def compute_anomaly_scores(daily: list[dict[str, Any]], min_years_for_doy_baseline: int = 3) -> list[dict[str, Any]]:
    anomaly_field = "fire_power_index" if any(float(row.get("fire_power_index", 0)) > 0 for row in daily) else "active_cell_count"
    values_by_doy: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
    for row in daily:
        day = row["date"]
        values_by_doy[(day.month, day.day)].append((day.year, float(row.get(anomaly_field, 0))))

    scored = []
    all_values = [float(row.get(anomaly_field, 0)) for row in daily]
    for idx, row in enumerate(daily):
        day = row["date"]
        value = float(row.get(anomaly_field, 0))
        same_doy = [v for year, v in values_by_doy[(day.month, day.day)] if year != day.year]
        method = "day_of_year"
        baseline = same_doy

        if len({year for year, _ in values_by_doy[(day.month, day.day)] if year != day.year}) < min_years_for_doy_baseline:
            method = "rolling_30_day"
            lo = max(0, idx - 15)
            hi = min(len(daily), idx + 16)
            baseline = [float(item.get(anomaly_field, 0)) for item in daily[lo:idx] + daily[idx + 1 : hi]]

        if len(baseline) < 2:
            method = "flat"
            baseline = [v for pos, v in enumerate(all_values) if pos != idx]

        item = dict(row)
        item["anomaly_score"] = round(_z_score(value, baseline), 3)
        item["baseline_method"] = method
        item["anomaly_basis"] = anomaly_field
        scored.append(item)
    return scored


def build_daily_series(hotspots: list[dict[str, Any]], start_date: date, end_date: date) -> list[dict[str, Any]]:
    filtered = filter_low_confidence(hotspots)
    snapped = snap_to_grid(filtered)
    cell_days = aggregate_cell_days(snapped)
    daily = aggregate_aoi_daily(cell_days, start_date, end_date)
    return compute_anomaly_scores(daily)


def summarize_daily_series(daily: list[dict[str, Any]]) -> dict[str, Any]:
    if not daily:
        return {"total_hotspots": 0, "peak_day": None, "high_anomaly_days": 0}
    peak = max(daily, key=lambda row: row["hotspot_count"])
    return {
        "total_hotspots": sum(row["hotspot_count"] for row in daily),
        "peak_day": peak["date"] if peak["hotspot_count"] else None,
        "high_anomaly_days": sum(1 for row in daily if row["anomaly_score"] > ANOMALY_THRESHOLD),
    }
