"""Turn mixed MODIS/VIIRS hotspots into a harmonized daily burning-activity record.

The harmonized value is the Four-Witness consistent record (see witness.py): what
Aqua MODIS would have recorded at 13:30 local solar time per clear look, built from
de-duplicated MODIS detections and VIIRS clusters weighted by the learned MODIS
detection profile. Footprint-weighted active cells are kept as descriptive fields.
Anomalies are robust z-scores, (x - median) / (1.4826 * MAD), against the same
season in other years, falling back to a rolling window for short records.

Harmonized values are the best comparable estimate from the observations; they
are not ground truth.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import Any

from config import ANOMALY_THRESHOLD, CONFIDENCE_THRESHOLD, GRID_RES
from geo import footprint_cell_fractions
from quality import classify_observation, sensor_family
from witness import run_witness_pipeline


ANOMALY_CATEGORIES = [(5.0, "Highly Unusual"), (3.5, "Unusual"), (ANOMALY_THRESHOLD, "Above Normal")]


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


def record_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _family_cells(rows: list[dict[str, Any]]) -> dict[tuple[float, float], float]:
    """Cell -> occupancy (0..1) from footprint fractions; overlapping passes saturate at 1."""
    cells: dict[tuple[float, float], float] = defaultdict(float)
    for row in rows:
        for cell_lat, cell_lon, fraction in footprint_cell_fractions(row, GRID_RES):
            cells[(cell_lat, cell_lon)] = min(1.0, cells[(cell_lat, cell_lon)] + fraction)
    return cells


def robust_scale(values: list[float]) -> tuple[float, float]:
    """Median and robust scale (1.4826*MAD, then 1.2533*mean absolute deviation, floor 1 cell)."""
    if not values:
        return 0.0, 1.0
    med = median(values)
    deviations = [abs(v - med) for v in values]
    scale = 1.4826 * median(deviations)
    if scale == 0:
        scale = 1.2533 * mean(deviations)
    # Floor of one detection: stops a single detection in an otherwise empty
    # season from reading as extreme purely because MAD is zero.
    return med, max(scale, 1.0)


def anomaly_category(z: float) -> str:
    for threshold, label in ANOMALY_CATEGORIES:
        if z >= threshold:
            return label
    return "Normal"


def compute_anomaly_scores(daily: list[dict[str, Any]], field: str = "harmonized_activity", min_years: int = 3, window_days: int = 7) -> list[dict[str, Any]]:
    by_year_doy: dict[int, dict[int, float]] = defaultdict(dict)
    for row in daily:
        d = row["date"]
        by_year_doy[d.year][d.timetuple().tm_yday] = float(row.get(field) or 0)

    scored = []
    for idx, row in enumerate(daily):
        d = row["date"]
        doy = d.timetuple().tm_yday
        value = float(row.get(field) or 0)
        seasonal = []
        years_used = set()
        for year, doys in by_year_doy.items():
            if year == d.year:
                continue
            window = [doys[k] for k in range(doy - window_days, doy + window_days + 1) if k in doys]
            if window:
                seasonal += window
                years_used.add(year)
        if len(years_used) >= min_years:
            method, baseline = "seasonal_same_window_other_years", seasonal
        else:
            lo, hi = max(0, idx - 15), min(len(daily), idx + 16)
            method = "rolling_31_day"
            baseline = [float(item.get(field) or 0) for item in daily[lo:idx] + daily[idx + 1 : hi]]
        med, scale = robust_scale(baseline)
        z = (value - med) / scale if baseline else 0.0
        item = dict(row)
        item["anomaly_score"] = round(z, 3)
        item["baseline_median"] = round(med, 3)
        item["baseline_method"] = method
        item["baseline_years"] = len(years_used) if method.startswith("seasonal") else 0
        item["anomaly_basis"] = field
        unobservable = row.get("observation", {}).get("status") in {"cloud_obscured", "missing_observation"}
        item["anomaly_category"] = "Not assessed (insufficient observation)" if unobservable and value == 0 else anomaly_category(z)
        scored.append(item)
    return scored


def build_harmonized_series(
    hotspots: list[dict[str, Any]],
    start_date: date,
    end_date: date,
    sensors: list[str] | None = None,
    availability: dict[date, list[str]] | None = None,
    cloud_cover: dict[date, float | None] | None = None,
    area_km2: float | None = None,
    lat_center: float | None = None,
    validate: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    filtered = filter_low_confidence(hotspots)
    rows_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        rows_by_day[record_date(row["acq_datetime"])].append(row)
    sensors = sensors or sorted({str(r["sensor"]) for r in filtered})
    witness = run_witness_pipeline(hotspots, start_date, end_date, sensors, availability, cloud_cover, area_km2, lat_center, validate)
    tiers, fused = witness["tiers"], witness["fused"]
    profile = witness["summary"]["detection_profile"]
    calibration = {
        "status": "learned" if profile["source"] == "learned" else "prior",
        "viirs_to_modis_factor": witness["summary"]["modis_fraction_of_viirs_fires"],
        "factor_iqr": None,
        "pairs": profile["matchups"],
        "note": "Four-Witness harmonization: " + profile["note"],
        "witness": {
            "summary": witness["summary"],
            "validation": witness["validation"],
            "cell_days_recent": sorted(witness["cell_days"], key=lambda r: r["local_day"])[-300:],
        },
    }

    daily = []
    cursor = start_date
    while cursor <= end_date:
        rows = rows_by_day.get(cursor, [])
        modis_rows = [r for r in rows if sensor_family(str(r["sensor"])) == "MODIS"]
        viirs_rows = [r for r in rows if sensor_family(str(r["sensor"])) == "VIIRS"]
        m = sum(_family_cells(modis_rows).values())
        v = sum(_family_cells(viirs_rows).values())
        available = availability.get(cursor, sensors) if availability is not None else sensors
        fams = {sensor_family(s) for s in available}
        cloud = (cloud_cover or {}).get(cursor)
        tier = tiers[cursor]
        harmonized, low, high = tier["consistent"], tier["low"], tier["high"]
        observation = classify_observation(available, rows, cloud)

        cells_any = {(snap_value(float(r["lat"])), snap_value(float(r["lon"]))) for r in rows}
        frps = [float(r["frp"]) for r in rows if r.get("frp") is not None]
        cell_frp: dict[tuple[float, float], list[float]] = defaultdict(list)
        for r in rows:
            if r.get("frp") is not None:
                cell_frp[(snap_value(float(r["lat"])), snap_value(float(r["lon"])))].append(float(r["frp"]))
        daily.append(
            {
                "date": cursor,
                "hotspot_count": len(rows),
                "modis_count": len(modis_rows),
                "viirs_count": len(viirs_rows),
                "modis_active_cells": round(m, 3),
                "viirs_active_cells": round(v, 3),
                "harmonized_activity": round(harmonized, 3),
                "harmonized_low": round(low, 3),
                "harmonized_high": round(high, 3),
                "detailed_activity": tier["detailed"],
                "fused_fire_cells": fused[cursor]["fused_fire_cells"],
                "frp_aqua_equiv": tier["frp_aqua_equiv"],
                "effort_looks": tier["effort_looks"],
                "detections_by_witness": tier["detections_by_witness"],
                "active_cell_count": len(cells_any),
                "mean_frp": round(mean(frps), 3) if frps else None,
                "max_frp": round(max(frps), 3) if frps else None,
                "fire_power_index": round(sum(mean(v_) for v_ in cell_frp.values()), 3),
                "sensor_agreement": _agreement(fams, bool(modis_rows), bool(viirs_rows)),
                "observation": observation,
            }
        )
        cursor += timedelta(days=1)
    scored = compute_anomaly_scores(daily)
    return scored, calibration


def _agreement(families: set[str], modis_hit: bool, viirs_hit: bool) -> str:
    if not ({"MODIS", "VIIRS"} <= families):
        return "single_sensor_available" if families else "no_sensor_available"
    if modis_hit and viirs_hit:
        return "both_detected"
    if modis_hit:
        return "modis_only"
    if viirs_hit:
        return "viirs_only"
    return "neither_detected"


def build_daily_series(hotspots: list[dict[str, Any]], start_date: date, end_date: date) -> list[dict[str, Any]]:
    daily, _ = build_harmonized_series(hotspots, start_date, end_date)
    return daily


def summarize_daily_series(daily: list[dict[str, Any]]) -> dict[str, Any]:
    if not daily:
        return {"total_hotspots": 0, "peak_day": None, "high_anomaly_days": 0}
    peak = max(daily, key=lambda row: row["harmonized_activity"])
    return {
        "total_hotspots": sum(row["hotspot_count"] for row in daily),
        "total_harmonized_activity": round(sum(row["harmonized_activity"] for row in daily), 2),
        "peak_day": peak["date"] if peak["harmonized_activity"] else None,
        "high_anomaly_days": sum(1 for row in daily if row["anomaly_score"] > ANOMALY_THRESHOLD),
        "category_counts": {label: sum(1 for row in daily if row["anomaly_category"] == label) for label in ["Normal", "Above Normal", "Unusual", "Highly Unusual"]},
    }
