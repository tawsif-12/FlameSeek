"""Scripted Past / Future / Exposure results for the demo scenarios in demo_data.py.

Shaped exactly like the live outlook (analogues.find_analogues, forecast.forecast_event,
exposure.analyze_exposure) so the same panels and map layers render it. Everything is
synthetic and consistent with each scenario's story; nothing here calls an external service.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from config import HISTORY_SENSORS
from demo_data import frp_at, ignition_time
from forecast import CELL_DEG


# blowing_toward_deg: post-monsoon light northerlies over Bangladesh push smoke and embers south-southwest.
OUTLOOKS: dict[str, dict[str, Any]] = {
    "ashulia_factory": {
        "analogues": {
            "candidates": 37,
            "items": [
                # (year, month, day, dlat, dlon, distance, duration_h, peak_h, peak_frp, final_km2, expanded, detections)
                (2024, 10, 19, 0.031, -0.044, 0.412, 31.0, 10.0, 172.0, 0.9, False, 29),
                (2023, 11, 2, -0.118, 0.162, 0.538, 22.5, 7.5, 141.0, 0.6, False, 21),
                (2021, 9, 27, 0.214, 0.087, 0.701, 44.0, 14.0, 226.0, 1.4, True, 41),
                (2022, 10, 8, -0.052, -0.201, 0.846, 17.0, 6.0, 96.0, 0.5, False, 14),
                (2019, 10, 30, 0.167, -0.139, 1.027, 27.5, 9.0, 158.0, 0.8, False, 24),
            ],
            "most_similar_on": [["max_frp", "extent_km2", "night_fraction"], ["frp_log_slope", "detections", "extent_km2"], ["max_frp", "detections", "wind_speed"]],
        },
        "forecast": {
            "model": "persistence",
            "why": "Persistence baseline chosen: it had the best Brier score on the temporal holdout and LightGBM did not beat it on the spatial holdout. A fire held inside one building keeps appearing at the same cells.",
            "peak": {6: 0.86, 12: 0.71, 24: 0.44},
            "reach_km": {6: 7.0, 12: 8.5, 24: 10.0},
            "elongation": 1.25,
            "wind": {"mean_speed_kmh": 7.4, "blowing_toward_deg": 205.0, "mean_rh_pct": 71.0, "mean_temp_c": 29.6},
            "skill": {"persistence": 0.31, "seasonal": 0.04, "wind_only": 0.11, "lightgbm": 0.27},
            "training": {"samples": 41280, "positives": 1164, "issue_times": 96},
        },
        "exposure": {
            "population_per_km2": 3900,
            "roads": [("Nabinagar-Chandra Highway (N540)", 3.4), ("Abdullahpur-Ashulia-Baipayl Road", 2.7), ("DEPZ Road", 1.9)],
            "assets": {
                "settlements": [("Ashulia", 0.012, 0.018, "town", "inside corridor", "136000"), ("Baipayl", -0.022, -0.031, "village", "inside corridor", None), ("Jamgora", 0.019, -0.008, "village", "inside corridor", None), ("Zirabo", 0.041, 0.052, "village", "within 2 km of corridor", None)],
                "schools": [("Ashulia School and College", 0.009, 0.027, "school", "inside corridor", None), ("DEPZ Public School", -0.006, 0.004, "school", "inside corridor", None), ("Jamgora Government Primary School", 0.022, -0.011, "school", "inside corridor", None), ("Baipayl High School", -0.026, -0.027, "school", "inside corridor", None)],
                "hospitals": [("Ashulia Women and Children Hospital", 0.014, 0.022, "hospital", "inside corridor", None), ("DEPZ Medical Centre", -0.004, 0.006, "clinic", "inside corridor", None)],
                "power": [("DEPZ 132/33 kV grid substation", -0.009, -0.004, "substation", "inside corridor", None), ("Ashulia 33/11 kV substation", 0.028, 0.019, "substation", "inside corridor", None)],
                "critical_facilities": [("DEPZ Fire Station", -0.003, 0.009, "fire_station", "inside corridor", None), ("Ashulia Police Station", 0.016, 0.014, "police", "inside corridor", None), ("Baipayl fuel station", -0.02, -0.024, "fuel", "inside corridor", None)],
                "agriculture": [("Farmland near Zirabo", 0.046, 0.058, "farmland", "within 2 km of corridor", None)],
                "forests": [],
                "protected_areas": [],
            },
        },
    },
    "bogura_straw": {
        "analogues": {
            "candidates": 212,
            "items": [
                (2025, 11, 14, 0.042, 0.066, 0.287, 2.8, 1.5, 17.0, 0.7, False, 6),
                (2024, 11, 21, -0.091, 0.034, 0.341, 3.6, 2.0, 22.0, 0.9, False, 8),
                (2023, 11, 9, 0.133, -0.108, 0.455, 2.2, 1.0, 12.0, 0.5, False, 4),
                (2024, 12, 2, -0.027, -0.152, 0.598, 4.4, 2.5, 26.0, 1.2, True, 9),
                (2022, 11, 26, 0.201, 0.094, 0.733, 3.1, 1.5, 15.0, 0.6, False, 5),
            ],
            "most_similar_on": [["duration_so_far", "max_frp", "hour_of_day"], ["extent_km2", "max_frp", "detections"], ["hour_of_day", "frp_log_slope", "extent_km2"]],
        },
        "forecast": {
            "model": "seasonal",
            "why": "Seasonal baseline chosen: this field has stopped burning, so persistence adds nothing, and LightGBM did not beat the seasonal baseline on the temporal holdout. Activity here follows the daily straw-burning pattern of neighbouring fields.",
            "peak": {6: 0.07, 12: 0.11, 24: 0.38},
            "reach_km": {6: 6.0, 12: 7.0, 24: 12.0},
            "elongation": 1.0,
            "wind": {"mean_speed_kmh": 5.1, "blowing_toward_deg": 190.0, "mean_rh_pct": 64.0, "mean_temp_c": 28.2},
            "skill": {"persistence": 0.02, "seasonal": 0.19, "wind_only": 0.05, "lightgbm": 0.16},
            "training": {"samples": 58920, "positives": 2371, "issue_times": 128},
        },
        "exposure": {
            "population_per_km2": 980,
            "roads": [("Dhaka-Rangpur Highway (N5)", 4.8), ("Mokamtala-Joypurhat Road (R545)", 3.1)],
            "assets": {
                "settlements": [("Mokamtala", 0.012, 0.014, "village", "inside corridor", "9400"), ("Shibganj", -0.034, 0.041, "town", "within 2 km of corridor", "21000"), ("Chandihara", 0.037, -0.019, "village", "inside corridor", None), ("Raynagar", -0.021, -0.033, "village", "inside corridor", None)],
                "schools": [("Mokamtala Government Primary School", 0.011, 0.016, "school", "inside corridor", None), ("Chandihara High School", 0.036, -0.017, "school", "inside corridor", None)],
                "hospitals": [("Mokamtala Union Health Centre", 0.014, 0.012, "clinic", "inside corridor", None)],
                "power": [("Mokamtala 33/11 kV substation", 0.008, 0.021, "substation", "inside corridor", None)],
                "critical_facilities": [],
                "agriculture": [("Paddy fields, Mokamtala", 0.0, 0.0, "farmland", "contains part of the corridor", None), ("Paddy fields, Raynagar", -0.02, -0.03, "farmland", "contains part of the corridor", None), ("Potato and paddy fields, Chandihara", 0.035, -0.02, "farmland", "contains part of the corridor", None)],
                "forests": [],
                "protected_areas": [],
            },
        },
    },
    "sundarbans_forest": {
        "analogues": {
            "candidates": 18,
            "items": [
                (2024, 5, 4, -0.012, 0.021, 0.366, 71.0, 30.0, 284.0, 7.9, True, 96),
                (2021, 5, 3, 0.027, -0.034, 0.492, 52.0, 26.0, 213.0, 4.1, True, 61),
                (2017, 5, 26, -0.041, 0.008, 0.655, 38.0, 20.0, 148.0, 2.6, True, 38),
                (2016, 4, 13, 0.016, 0.047, 0.811, 33.5, 16.0, 121.0, 1.9, False, 27),
                (2021, 2, 8, 0.058, -0.019, 0.974, 27.0, 14.0, 97.0, 1.4, False, 19),
            ],
            "most_similar_on": [["extent_growth", "max_frp", "frp_log_slope"], ["extent_km2", "detections", "max_frp"], ["frp_log_slope", "wind_speed", "extent_growth"]],
        },
        "forecast": {
            "model": "lightgbm",
            "why": "LightGBM chosen: it beat persistence, seasonal and wind-only baselines on Brier score in both the temporal and the spatial holdout, without losing footprint CSI.",
            "peak": {6: 0.9, 12: 0.86, 24: 0.8},
            "reach_km": {6: 8.0, 12: 11.0, 24: 15.0},
            "elongation": 1.9,
            "wind": {"mean_speed_kmh": 12.8, "blowing_toward_deg": 212.0, "mean_rh_pct": 58.0, "mean_temp_c": 30.4},
            "skill": {"persistence": 0.18, "seasonal": 0.06, "wind_only": 0.14, "lightgbm": 0.29},
            "training": {"samples": 23760, "positives": 688, "issue_times": 72},
        },
        "exposure": {
            "population_per_km2": 62,
            "roads": [("Morrelganj-Sarankhola Road (Z7704)", 2.3)],
            "assets": {
                "settlements": [("Amurbunia", 0.027, 0.018, "village", "within 2 km of corridor", "3100"), ("Gulishakhali", 0.041, -0.022, "village", "within 2 km of corridor", "4600"), ("Jiudhara", 0.052, 0.037, "village", "within 2 km of corridor", None)],
                "schools": [("Amurbunia Government Primary School", 0.029, 0.017, "school", "within 2 km of corridor", None), ("Gulishakhali Secondary School", 0.043, -0.02, "school", "within 2 km of corridor", None)],
                "hospitals": [("Jiudhara Community Clinic", 0.051, 0.035, "clinic", "within 2 km of corridor", None)],
                "power": [],
                "critical_facilities": [("Amurbunia Forest Patrol Post", 0.014, 0.011, "ranger_station", "inside corridor", None), ("Dhansagar Forest Station", -0.006, 0.043, "ranger_station", "inside corridor", None)],
                "agriculture": [("Paddy fields, Amurbunia", 0.03, 0.02, "farmland", "within 2 km of corridor", None)],
                "forests": [("Sundarbans Reserved Forest", 0.0, 0.0, "forest", "contains part of the corridor", None)],
                "protected_areas": [("Sundarbans East Wildlife Sanctuary", -0.02, 0.01, "protected_area", "contains part of the corridor", None), ("Sundarbans Reserved Forest", 0.0, 0.0, "protected_area", "contains part of the corridor", None)],
            },
        },
    },
}

CATEGORY_LABELS = {
    "settlements": "Villages and towns",
    "agriculture": "Agricultural areas",
    "forests": "Forests and woodland",
    "protected_areas": "Protected areas",
    "schools": "Schools",
    "hospitals": "Hospitals and clinics",
    "power": "Power infrastructure",
    "critical_facilities": "Critical facilities",
}
MODELS = ["persistence", "seasonal", "wind_only", "lightgbm"]


def _frp_timeline(duration: float, peak_h: float, peak_frp: float) -> list[dict[str, float]]:
    """12-hour-window FRP totals rising to the peak and decaying to the end of the fire."""
    step = 12.0 if duration > 12 else max(0.5, duration / 6)
    out = []
    h = 0.0
    while h <= duration + 1e-6:
        rise = (h / peak_h) if h <= peak_h else max(0.0, 1 - (h - peak_h) / max(duration - peak_h, step))
        out.append({"hours": round(h, 1), "frp": round(peak_frp * (0.12 + 0.88 * rise), 1)})
        h += step
    return out


def _analogues(sc: dict[str, Any], spec: dict[str, Any], age_h: float) -> dict[str, Any]:
    items = []
    for i, (year, month, day, dlat, dlon, dist, duration, peak_h, peak_frp, final_km2, expanded, n) in enumerate(spec["items"]):
        first = datetime(year, month, day, 6 + (i * 2) % 5, 30 + i * 4, tzinfo=timezone.utc)
        matched = min(age_h, duration)
        items.append(
            {
                "event_id": "EV-" + hashlib.sha1(f"{sc['key']}|{year}-{month}-{day}".encode()).hexdigest()[:10].upper(),
                "year": year,
                "first_detection": first.isoformat(),
                "centroid": {"lat": round(sc["lat"] + dlat, 5), "lon": round(sc["lon"] + dlon, 5)},
                "distance": dist,
                "most_similar_on": spec["most_similar_on"][i % len(spec["most_similar_on"])],
                "least_similar_on": ["relative_humidity", "centroid_movement_km"],
                "outcome": {
                    "duration_hours": duration,
                    "total_detections": n,
                    "final_extent_km2": final_km2,
                    "extent_at_matched_age_km2": round(final_km2 * min(1.0, 0.35 + 0.65 * matched / duration) * (0.8 if expanded else 1.0), 2),
                    "expanded_after_matched_age": expanded,
                    "peak_frp_window_hours_from_start": peak_h,
                    "peak_window_frp": peak_frp,
                    "decay_began_hours_from_start": round(peak_h + (12.0 if duration > 12 else 0.5), 1),
                    "remaining_hours_after_matched_age": round(max(0.0, duration - age_h), 1),
                    "frp_timeline": _frp_timeline(duration, peak_h, peak_frp),
                },
                "sensors": ["modis", "viirs_snpp"] + (["viirs_noaa20"] if year >= 2019 else []),
            }
        )
    durations = sorted(a["outcome"]["duration_hours"] for a in items)
    remaining = sorted(a["outcome"]["remaining_hours_after_matched_age"] for a in items)
    peaks = sorted(a["outcome"]["peak_frp_window_hours_from_start"] for a in items)
    return {
        "status": "ok",
        "method": "knn_mahalanobis_shrinkage",
        "matched_age_hours": round(age_h, 1),
        "features_used": ["max_frp", "detections", "extent_km2", "frp_log_slope", "extent_growth", "night_fraction", "hour_of_day", "wind_speed", "relative_humidity"],
        "candidates": spec["candidates"],
        "analogues": items,
        "summary": {
            "median_total_duration_hours": durations[len(durations) // 2],
            "median_remaining_hours": remaining[len(remaining) // 2],
            "expanded_after_this_age": f"{sum(1 for a in items if a['outcome']['expanded_after_matched_age'])} of {len(items)}",
            "median_peak_frp_hours_from_start": peaks[len(peaks) // 2],
            "typical_duration_range_hours": [durations[0], durations[-1]],
        },
        "ecological_context": "Candidates come from the same ~60 km region and season, so they share ecological setting; land-cover similarity is not separately scored.",
        "caveat": "Historical analogues give context about how similar fires behaved. They do not mean the current fire will behave the same way.",
    }


def _metrics(skill: float, rnd: random.Random, positives: int, samples: int) -> dict[str, Any]:
    """Plausible verification scores for a model with this Brier skill against climatology."""
    base_rate = positives / samples
    climatology_brier = base_rate * (1 - base_rate)
    pod = min(0.92, max(0.08, 0.3 + 1.6 * skill + rnd.uniform(-0.04, 0.04)))
    far = min(0.9, max(0.22, 0.78 - 1.3 * skill + rnd.uniform(-0.04, 0.04)))
    csi = 1 / (1 / pod + 1 / (1 - far) - 1)
    ece = max(0.004, 0.03 - 0.06 * skill + rnd.uniform(-0.004, 0.004))
    reliability = []
    for lo, hi, share in [(0.0, 0.1, 0.9), (0.1, 0.3, 0.06), (0.3, 0.5, 0.025), (0.5, 0.7, 0.01), (0.7, 1.0, 0.005)]:
        mean_f = (lo + hi) / 2 * (0.4 if lo == 0 else 1.0)
        reliability.append({"bin": f"{lo:.1f}-{hi:.1f}", "mean_forecast": round(mean_f, 3), "observed_frequency": round(max(0.0, mean_f + rnd.uniform(-1, 1) * ece * 2.2), 3), "n": int(samples * share)})
    return {
        "brier": round(climatology_brier * (1 - skill), 4),
        "brier_skill_vs_climatology": round(skill, 3),
        "auc": round(min(0.97, 0.62 + 1.05 * skill + rnd.uniform(-0.01, 0.01)), 3),
        "probability_of_detection": round(pod, 3),
        "false_alarm_ratio": round(far, 3),
        "critical_success_index": round(csi, 3),
        "footprint_iou_mean": round(csi * 0.82, 3),
        "expected_calibration_error": round(ece, 4),
        "reliability": reliability,
        "positives": positives,
        "samples": samples,
    }


def _validation(spec: dict[str, Any], horizon: int, split: str, seed: str) -> dict[str, Any]:
    test_pos = int(spec["training"]["positives"] * (0.22 if "Temporal" in split else 0.31))
    test_n = int(spec["training"]["samples"] * (0.22 if "Temporal" in split else 0.31))
    fade = {6: 1.0, 12: 0.88, 24: 0.72}[horizon] * (1.0 if "Temporal" in split else 0.9)
    models = {m: _metrics(spec["skill"][m] * fade, random.Random(f"{seed}-{horizon}-{split}-{m}"), test_pos, test_n) for m in MODELS}
    return {"split": split, "status": "ok", "models": models, "train_positives": spec["training"]["positives"] - test_pos, "test_positives": test_pos}


def _cells(sc: dict[str, Any], spec: dict[str, Any], horizon: int) -> list[dict[str, Any]]:
    """Probability field around the fire, stretched downwind."""
    lat0 = round(sc["lat"] / CELL_DEG) * CELL_DEG
    lon0 = round(sc["lon"] / CELL_DEG) * CELL_DEG
    ky, kx = 111.32, 111.32 * math.cos(math.radians(sc["lat"]))
    toward = math.radians(spec["wind"]["blowing_toward_deg"])
    wx, wy = math.sin(toward), math.cos(toward)
    reach, peak, stretch = spec["reach_km"][horizon], spec["peak"][horizon], spec["elongation"]
    shift = reach * (stretch - 1) * 0.45
    cells = []
    n = int(reach * stretch / (CELL_DEG * ky)) + 3
    rnd = random.Random(f"{sc['seed']}-cells-{horizon}")
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = j * CELL_DEG * kx, i * CELL_DEG * ky
            along = x * wx + y * wy - shift
            cross = -x * wy + y * wx
            d2 = (along / (reach * stretch * 0.5)) ** 2 + (cross / (reach * 0.5)) ** 2
            p = peak * math.exp(-1.6 * d2) * rnd.uniform(0.88, 1.08)
            if p >= 0.05:
                p = min(0.97, p)
                cells.append({"lat": round(lat0 + i * CELL_DEG, 4), "lon": round(lon0 + j * CELL_DEG, 4), "p": round(p, 3), "level": "high" if p >= 0.6 else "moderate" if p >= 0.3 else "low"})
    return sorted(cells, key=lambda c: -c["p"])


def _forecast(sc: dict[str, Any], spec: dict[str, Any], now: datetime) -> dict[str, Any]:
    ky, kx = 111.32, 111.32 * math.cos(math.radians(sc["lat"]))
    years = [now.year - k for k in range(8, 0, -1)]
    horizons = {}
    for h in (6, 12, 24):
        cells = _cells(sc, spec, h)
        horizons[str(h)] = {
            "horizon_hours": h,
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(hours=h)).isoformat(),
            "status": "ISSUED",
            "model_used": spec["model"],
            "model_selection": spec["why"],
            "decision_threshold": 0.3,
            "cells": cells,
            "corridor_area_km2": round(sum(1 for c in cells if c["p"] >= 0.1) * (CELL_DEG * kx) * (CELL_DEG * ky), 1),
            "wind": spec["wind"],
            "validation": {
                "temporal": _validation(spec, h, f"Temporal holdout (latest season, {years[-1]})", sc["key"]),
                "spatial": _validation(spec, h, "Spatial holdout (east half trained, west half tested)", sc["key"]),
            },
            "training": {**spec["training"], "years": years[:-1]},
            "feature_importance": {"recent_detections_6km": 0.31, "hours_since_last_detection": 0.19, "downwind_of_recent_fire": 0.16, "seasonal_rate": 0.13, "relative_humidity": 0.09, "hour_of_day": 0.07, "elevation_gradient": 0.05} if spec["model"] == "lightgbm" else None,
        }
    return {
        "target": "Probability that MODIS/VIIRS detect burning activity in each ~3.3 km cell during the next 6, 12 and 24 h of satellite observation.",
        "issue_time": now.isoformat(),
        "cell_size_deg": CELL_DEG,
        "caveat": "This is not a fire-spread prediction. It estimates where new satellite-observed activity may be detected, and a cell outside the corridor can still burn.",
        "inputs_used": ["recent detections (MODIS, VIIRS SNPP, VIIRS NOAA-20)", "historical same-season detections", "wind, humidity and temperature (Open-Meteo; ERA5 for training)", "terrain elevation (Copernicus DEM)", "hour of day"],
        "inputs_not_used": ["land cover (no free global raster API integrated)", "fuel moisture", "suppression activity"],
        "horizons": horizons,
        "withheld_reasons_global": [],
    }


def _exposure(sc: dict[str, Any], spec: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
    ky, kx = 111.32, 111.32 * math.cos(math.radians(sc["lat"]))
    corridor = {(c["lat"], c["lon"]) for h in forecast["horizons"].values() for c in h["cells"] if c["p"] >= 0.1}
    area = len(corridor) * (CELL_DEG * kx) * (CELL_DEG * ky)
    assets: dict[str, Any] = {}
    for key, label in CATEGORY_LABELS.items():
        items = [
            {"name": name, "lat": round(sc["lat"] + dlat, 5), "lon": round(sc["lon"] + dlon, 5), "type": kind, "relation": relation, "population_tag": pop}
            for name, dlat, dlon, kind, relation, pop in spec["assets"].get(key, [])
        ]
        assets[key] = {"label": label, "status": "ok", "count": len(items), "items": items}
    assets["roads"] = {
        "label": "Major roads",
        "status": "ok",
        "length_km_inside_corridor": round(sum(km for _, km in spec["roads"]), 1),
        "items": [{"name": name, "km_inside": km} for name, km in spec["roads"]],
    }
    return {
        "status": "ok",
        "corridor_cells": len(corridor),
        "corridor_area_km2": round(area, 1),
        "population": {
            "status": "ok",
            "population": int(round(area * spec["population_per_km2"], -2)),
            "polygons": 1,
            "dataset": "WorldPop Global 2020 (100 m, unconstrained)",
            "note": "Modelled residential population estimate, not a census count.",
        },
        "assets": assets,
        "errors": [],
        "wording": "These people and assets lie within or near the possible future activity corridor. The platform does not claim they will be affected.",
        "sources": ["OpenStreetMap contributors via Overpass API (ODbL)", "WorldPop 2020 population estimates"],
    }


def scenario_outlook(sc: dict[str, Any], event: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    spec = OUTLOOKS[sc["key"]]
    burn = sc["burn_hours"]
    age = (now - ignition_time(sc, now)).total_seconds() / 3600
    age = min(age, burn) if burn is not None else age
    forecast = _forecast(sc, spec["forecast"], now)
    years = [now.year - k for k in range(1, 9)]
    rnd = random.Random(f"{sc['seed']}-history")
    per_year = {y: {"status": "ok", "detections": rnd.randint(40, 160) * (3 if sc["key"] == "bogura_straw" else 1), "failed_chunks": 0} for y in years}
    half = 60 / 111.32
    return {
        "event_id": event["event_id"],
        "demo_scenario": sc["key"],
        "history": {
            "bbox": [round(sc["lon"] - half, 3), round(sc["lat"] - half, 3), round(sc["lon"] + half, 3), round(sc["lat"] + half, 3)],
            "radius_km": 60.0,
            "years": years,
            "window_days": 91,
            "per_year": per_year,
            "failed_years": 0,
            "sensors": HISTORY_SENSORS,
            "detections": sum(v["detections"] for v in per_year.values()),
        },
        "analogues": _analogues(sc, spec["analogues"], age),
        "forecast": forecast,
        "exposure": _exposure(sc, spec["exposure"], forecast),
        "current_frp_mw": round(frp_at(sc, now, now), 1),
    }
