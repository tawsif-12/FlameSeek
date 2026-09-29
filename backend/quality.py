"""Observation quality: was the surface actually observable when we say "no fire"?

An absence of hotspots only means "no fire detected" when a sensor was
operating, its data were retrieved, and the sky was reasonably clear. Each day
gets one of six observation classes and a 0-100 Observation Sufficiency Score.
"""

from __future__ import annotations

from typing import Any


OBSERVATION_CLASSES = {
    "reliable_multi_sensor": {"label": "Reliable multi-sensor observation", "display": "RELIABLE"},
    "valid_no_fire": {"label": "Valid observation with no detected fire", "display": "NO FIRE DETECTED"},
    "limited_evidence": {"label": "Limited evidence", "display": "LIMITED EVIDENCE"},
    "sensor_disagreement": {"label": "Sensor disagreement", "display": "AMBIGUOUS"},
    "cloud_obscured": {"label": "Cloud-covered or low-quality observation", "display": "UNKNOWN"},
    "missing_observation": {"label": "Missing satellite observation opportunity", "display": "INSUFFICIENT OBSERVATION"},
}

CLOUD_OBSCURED_PCT = 70.0
# A family "sees substantial activity" when it has at least this many detections or this much FRP.
SUBSTANTIAL_DETECTIONS = 3
SUBSTANTIAL_FRP_MW = 50.0


def sensor_family(sensor: str) -> str:
    if sensor == "modis":
        return "MODIS"
    if sensor.startswith("viirs"):
        return "VIIRS"
    return sensor.upper()


def sufficiency_score(platforms_available: int, cloud_cover_pct: float | None) -> int:
    """100 * coverage * clarity.

    coverage: available platforms / 3 (e.g. MODIS + two VIIRS satellites = full), capped at 1.
    clarity: 1 - 0.8 * cloud fraction (ERA5 proxy); 0.7 when cloud cover is unknown.
    """
    coverage = min(1.0, platforms_available / 3)
    clarity = 0.7 if cloud_cover_pct is None else 1 - 0.8 * max(0.0, min(100.0, cloud_cover_pct)) / 100
    return round(100 * coverage * clarity)


def classify_observation(
    available_sensors: list[str],
    detections: list[dict[str, Any]],
    cloud_cover_pct: float | None,
) -> dict[str, Any]:
    families_available = {sensor_family(s) for s in available_sensors if sensor_family(s) in {"MODIS", "VIIRS"}}
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in detections:
        by_family.setdefault(sensor_family(str(row["sensor"])), []).append(row)

    def substantial(rows: list[dict[str, Any]]) -> bool:
        return len(rows) >= SUBSTANTIAL_DETECTIONS or sum(float(r.get("frp") or 0) for r in rows) >= SUBSTANTIAL_FRP_MW

    detecting = {fam for fam, rows in by_family.items() if rows and fam in {"MODIS", "VIIRS"}}
    if not available_sensors:
        status = "missing_observation"
    elif detections:
        if len(detecting) >= 2:
            status = "reliable_multi_sensor"
        elif len(families_available) >= 2 and any(substantial(by_family[f]) for f in detecting):
            status = "sensor_disagreement"
        else:
            status = "limited_evidence"
    elif cloud_cover_pct is not None and cloud_cover_pct >= CLOUD_OBSCURED_PCT:
        status = "cloud_obscured"
    else:
        status = "valid_no_fire"

    score = sufficiency_score(len(available_sensors), cloud_cover_pct)
    if status == "missing_observation":
        score = 0
    return {
        "status": status,
        "label": OBSERVATION_CLASSES[status]["label"],
        "display": OBSERVATION_CLASSES[status]["display"],
        "sufficiency_score": score,
        "sensors_available": sorted(available_sensors),
        "families_detecting": sorted(detecting),
        "cloud_cover_pct": cloud_cover_pct,
    }


def summarize_observations(daily: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {key: 0 for key in OBSERVATION_CLASSES}
    for row in daily:
        counts[row["observation"]["status"]] += 1
    n = len(daily) or 1
    scores = [row["observation"]["sufficiency_score"] for row in daily]
    return {
        "counts": counts,
        "labels": {key: value["label"] for key, value in OBSERVATION_CLASSES.items()},
        "mean_sufficiency_score": round(sum(scores) / n, 1) if scores else 0,
        "pct_days_unobservable": round(100 * (counts["cloud_obscured"] + counts["missing_observation"]) / n, 1),
        "method": "Sensor availability from FIRMS archive date ranges and fetch results; cloud cover from ERA5 reanalysis daily mean at the AOI centroid (proxy, not a satellite cloud mask).",
    }
