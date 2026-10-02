"""Four-Witness harmonization: Terra, Aqua, Suomi NPP and NOAA-20 as witnesses with known blind spots.

Implements the eight-stage pipeline of the Four-Witness Fire Intelligence report:

1. collect detections (FIRMS) and observation opportunities (sensor availability + cloud)
2. clean and tag: vegetation fires only, confidence filter, local solar time, pixel area, 0.1 deg cell
3. remove MODIS duplicates from the same overpass (within ~1 km, keep the higher FRP)
4. learn the sensor detection profile P(MODIS detects | VIIRS FRP, pixel area) from Aqua/S-NPP matchups
5. correct for time of day: convert each observation to its Aqua 13:30 local-solar-time equivalent
6. two tiers: a consistent record at MODIS sensitivity and a detailed layer at full VIIRS sensitivity
7. normalize by observation effort: expected clear-sky looks per witness and day
8. fuse every look into one fire probability per 0.1 deg cell and local day (occupancy-style update)

Daily FIRMS observation masks (MOD14A1, MYD14A1, VNP14A1, VJ114A1) need an Earthdata login,
so stage 7 uses expected looks from orbit geometry (swath width vs ground-track spacing at
the cell's latitude) times the clear-sky fraction. That is an approximation of the masks.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np

from config import CONFIDENCE_THRESHOLD, SENSOR_START_DATES
from geo import haversine_km, pixel_size_km


CELL_DEG = 0.1
REFERENCE_HOUR = 13.5
VIIRS_NADIR_AREA_KM2 = 0.375 * 0.375
ORBIT_SPACING_KM = 40075.0 / 14.5
WITNESSES = ["terra", "aqua", "snpp", "noaa20", "noaa21"]
WITNESS_LABEL = {"terra": "Terra MODIS", "aqua": "Aqua MODIS", "snpp": "Suomi NPP VIIRS", "noaa20": "NOAA-20 VIIRS", "noaa21": "NOAA-21 VIIRS"}
WITNESS_FAMILY = {"terra": "MODIS", "aqua": "MODIS", "snpp": "VIIRS", "noaa20": "VIIRS", "noaa21": "VIIRS"}
WITNESS_SENSOR = {"terra": "modis", "aqua": "modis", "snpp": "viirs_snpp", "noaa20": "viirs_noaa20", "noaa21": "viirs_noaa21"}
WITNESS_START = {
    "terra": SENSOR_START_DATES["modis"],
    "aqua": date(2002, 7, 4),
    "snpp": SENSOR_START_DATES["viirs_snpp"],
    "noaa20": SENSOR_START_DATES["viirs_noaa20"],
    "noaa21": SENSOR_START_DATES["viirs_noaa21"],
}
SWATH_KM = {"terra": 2330.0, "aqua": 2330.0, "snpp": 3040.0, "noaa20": 3040.0, "noaa21": 3040.0}
# Nominal daytime equator-crossing local solar time; the night pass is 12 h later.
NOMINAL_DAY_HOUR = {"terra": 10.5, "aqua": 13.5, "snpp": 13.5, "noaa20": 12.67, "noaa21": 13.5}

# Li et al. (2020): MODIS misses fires below ~4.3 MW at nadir and ~31.7 MW at the scan edge.
PRIOR_FRP50_NADIR_MW = 4.3
PRIOR_EDGE_EXPONENT = 1.35
PRIOR_SLOPE = 1.6
PRIOR_PROFILE = {
    "intercept": -PRIOR_SLOPE * math.log(PRIOR_FRP50_NADIR_MW),
    "coef_log_frp": PRIOR_SLOPE,
    "coef_log_area": -PRIOR_SLOPE * PRIOR_EDGE_EXPONENT,
}
DEFAULT_DIURNAL = {"peak_hour": 14.0, "width_h": 2.5, "base": 0.08}
MAX_TIME_FACTOR = 4.0
DAY_HOURS = (7.0, 19.0)

MATCHUP_MINUTES = 20
MATCHUP_LOOKED_KM = 50.0
MATCHUP_HIT_KM = 1.5
PRE_DRIFT_END = date(2021, 6, 30)
MIN_MATCHUPS = 60
MIN_CLASS = 15

VIIRS_SENSITIVITY = 0.9
FALSE_ALARM_PER_LOOK = 0.005
PRIOR_STRENGTH_DAYS = 10.0
MIN_DIURNAL_DETECTIONS = 100


# --- Stage 2: clean and tag ---------------------------------------------------------------


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def local_solar_time(t: datetime, lon: float) -> datetime:
    return t + timedelta(hours=lon / 15.0)


def witness_of(row: dict[str, Any]) -> str | None:
    sensor = str(row.get("sensor", ""))
    if sensor == "modis":
        sat = str(row.get("satellite") or "").strip().lower()
        if sat.startswith("t"):
            return "terra"
        if sat.startswith("a"):
            return "aqua"
        solar = local_solar_time(_utc(row["acq_datetime"]), float(row["lon"]))
        h = solar.hour + solar.minute / 60
        # Terra passes ~10:30/22:30, Aqua ~13:30/01:30.
        return "terra" if (7 <= h < 12 or h >= 18) else "aqua"
    return {"viirs_snpp": "snpp", "viirs_noaa20": "noaa20", "viirs_noaa21": "noaa21"}.get(sensor)


def cell_of(lat: float, lon: float) -> tuple[int, int]:
    return math.floor(lat / CELL_DEG), math.floor(lon / CELL_DEG)


def cell_center(cell: tuple[int, int]) -> tuple[float, float]:
    return round((cell[0] + 0.5) * CELL_DEG, 4), round((cell[1] + 0.5) * CELL_DEG, 4)


def clean_and_tag(rows: list[dict[str, Any]], threshold: float = CONFIDENCE_THRESHOLD) -> tuple[list[dict[str, Any]], dict[str, int]]:
    dropped = {"low_confidence": 0, "non_vegetation_type": 0, "not_a_witness": 0}
    out = []
    for row in rows:
        w = witness_of(row)
        if w is None:
            dropped["not_a_witness"] += 1
            continue
        if float(row.get("confidence_pct") or 0) < threshold:
            dropped["low_confidence"] += 1
            continue
        if row.get("fire_type") not in (None, 0):
            dropped["non_vegetation_type"] += 1
            continue
        t = _utc(row["acq_datetime"])
        lat, lon = float(row["lat"]), float(row["lon"])
        solar = local_solar_time(t, lon)
        scan, track = pixel_size_km(row)
        out.append(
            {
                "lat": lat,
                "lon": lon,
                "utc": t,
                "frp": float(row["frp"]) if row.get("frp") is not None else 0.0,
                "witness": w,
                "family": WITNESS_FAMILY[w],
                "local_solar_hour": solar.hour + solar.minute / 60,
                "local_day": solar.date(),
                "pixel_area_km2": scan * track,
                "cell": cell_of(lat, lon),
            }
        )
    return out, dropped


# --- Stage 3: same-overpass merging --------------------------------------------------------


def merge_overpass(rows: list[dict[str, Any]], radius_km: float = 1.0, frp_mode: str = "max") -> list[dict[str, Any]]:
    """Merge one witness's detections from one overpass (<= 10 min) lying within radius_km.

    frp_mode="max" removes MODIS duplicates (keeps the higher FRP); "sum" groups adjacent
    375 m VIIRS pixels into one fire cluster comparable to a ~1 km MODIS pixel.
    """
    ordered = sorted(rows, key=lambda r: (r["witness"], r["utc"]))
    passes: list[list[dict[str, Any]]] = []
    for r in ordered:
        if passes and passes[-1][0]["witness"] == r["witness"] and (r["utc"] - passes[-1][0]["utc"]).total_seconds() <= 600:
            passes[-1].append(r)
        else:
            passes.append([r])
    merged = []
    hash_deg = 0.02
    for group in passes:
        group.sort(key=lambda r: r["frp"], reverse=True)
        grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        kept: list[dict[str, Any]] = []
        for r in group:
            gi, gj = int(r["lat"] // hash_deg), int(r["lon"] // hash_deg)
            target = None
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for k in grid.get((gi + di, gj + dj), []):
                        if haversine_km(r["lat"], r["lon"], k["lat"], k["lon"]) <= radius_km:
                            target = k
                            break
                    if target:
                        break
                if target:
                    break
            if target is None:
                item = {**r, "n_merged": 1}
                kept.append(item)
                grid[(gi, gj)].append(item)
            else:
                target["n_merged"] += 1
                if frp_mode == "sum":
                    target["frp"] += r["frp"]
        merged.extend(kept)
    return merged


# --- Stage 4: sensor detection profile -----------------------------------------------------


def detection_probability(profile: dict[str, float], frp: float, pixel_area_km2: float) -> float:
    area_ratio = max(1.0, pixel_area_km2 / VIIRS_NADIR_AREA_KM2)
    z = profile["intercept"] + profile["coef_log_frp"] * math.log(max(frp, 0.1)) + profile["coef_log_area"] * math.log(area_ratio)
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def frp50(profile: dict[str, float], area_ratio: float) -> float | None:
    if profile["coef_log_frp"] <= 0:
        return None
    return round(math.exp(-(profile["intercept"] + profile["coef_log_area"] * math.log(area_ratio)) / profile["coef_log_frp"]), 2)


def matchup_samples(modis: list[dict[str, Any]], viirs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """S-NPP fire clusters seen while Aqua was demonstrably looking at the same area (<= 20 min).

    Aqua "looked" when it recorded any detection within 50 km in that window. Each S-NPP
    cluster is labelled detected when an Aqua detection lies within 1.5 km.
    """
    aqua_index: dict[tuple[date, int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in modis:
        if r["witness"] == "aqua":
            aqua_index[(r["local_day"], int(r["lat"] // 0.5), int(r["lon"] // 0.5))].append(r)
    samples = []
    for c in viirs:
        if c["witness"] != "snpp":
            continue
        bi, bj = int(c["lat"] // 0.5), int(c["lon"] // 0.5)
        looked = False
        hit = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for a in aqua_index.get((c["local_day"], bi + di, bj + dj), []):
                    if abs((a["utc"] - c["utc"]).total_seconds()) > MATCHUP_MINUTES * 60:
                        continue
                    d = haversine_km(c["lat"], c["lon"], a["lat"], a["lon"])
                    if d <= MATCHUP_LOOKED_KM:
                        looked = True
                    if d <= MATCHUP_HIT_KM and (hit is None or a["frp"] > hit["frp"]):
                        hit = a
        if looked:
            samples.append(
                {
                    "local_day": c["local_day"],
                    "viirs_frp": c["frp"],
                    "viirs_area": c["pixel_area_km2"],
                    "detected": hit is not None,
                    "modis_frp": hit["frp"] if hit else None,
                }
            )
    return samples


def learn_detection_profile(modis: list[dict[str, Any]], viirs: list[dict[str, Any]]) -> dict[str, Any]:
    samples = matchup_samples(modis, viirs)
    pre_drift = [s for s in samples if s["local_day"] <= PRE_DRIFT_END]
    used = pre_drift if len(pre_drift) >= MIN_MATCHUPS else samples
    window = "2012 to mid-2021 (before Aqua's orbit drift)" if used is pre_drift else "all available years (too few pre-drift matchups)"
    positives = sum(1 for s in used if s["detected"])
    negatives = len(used) - positives
    profile = dict(PRIOR_PROFILE)
    source = "prior"
    note = f"Prior from Li et al. (2020): 50% MODIS detection at ~{PRIOR_FRP50_NADIR_MW} MW at nadir, ~31.7 MW at the scan edge. Too few Aqua/S-NPP matchups in this area to learn a regional profile."
    if len(used) >= MIN_MATCHUPS and positives >= MIN_CLASS and negatives >= MIN_CLASS:
        from sklearn.linear_model import LogisticRegression

        X = np.array([[math.log(max(s["viirs_frp"], 0.1)), math.log(max(1.0, s["viirs_area"] / VIIRS_NADIR_AREA_KM2))] for s in used])
        y = np.array([1 if s["detected"] else 0 for s in used])
        model = LogisticRegression(C=1.0, max_iter=500).fit(X, y)
        fitted = {"intercept": float(model.intercept_[0]), "coef_log_frp": float(model.coef_[0][0]), "coef_log_area": float(model.coef_[0][1])}
        if fitted["coef_log_frp"] > 0:
            profile, source = fitted, "learned"
            note = f"Logistic regression on {len(used)} Aqua/S-NPP matchups within {MATCHUP_MINUTES} min ({window}). Pixel area stands in for viewing angle; land cover is not used because FIRMS carries no per-pixel land cover."
        else:
            note = "Matchup fit gave a non-physical FRP slope (detection should rise with FRP); the published prior is used instead."
    ratios = sorted(s["modis_frp"] / s["viirs_frp"] for s in used if s["detected"] and s["viirs_frp"] > 0 and s["modis_frp"])
    frp_ratio = float(np.median(ratios)) if len(ratios) >= MIN_CLASS else 1.0
    return {
        "source": source,
        "profile": {k: round(v, 4) for k, v in profile.items()},
        "frp50_nadir_mw": frp50(profile, 1.0),
        "frp50_scan_edge_mw": frp50(profile, 4.4),
        "matchups": len(used),
        "matchups_detected_by_modis": positives,
        "matchup_window": window if used else None,
        "modis_frp_per_viirs_frp": round(frp_ratio, 3),
        "modis_frp_per_viirs_frp_iqr": [round(float(np.percentile(ratios, 25)), 3), round(float(np.percentile(ratios, 75)), 3)] if len(ratios) >= MIN_CLASS else None,
        "frp_relation_source": "learned (median of matched pairs)" if len(ratios) >= MIN_CLASS else "assumed 1.0 (too few matched pairs)",
        "note": note,
        "viirs_noaa_treatment": "NOAA-20 and NOAA-21 share the S-NPP VIIRS profile after time-of-day correction.",
    }


# --- Stage 5: time of day --------------------------------------------------------------------


def _hour_gap(a: float, b: float) -> float:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def diurnal_value(curve: dict[str, float], hour: float) -> float:
    d = _hour_gap(hour, curve["peak_hour"])
    return curve["base"] + (1 - curve["base"]) * math.exp(-(d * d) / (2 * curve["width_h"] ** 2))


def time_factor(curve: dict[str, float], hour: float) -> float:
    return min(MAX_TIME_FACTOR, diurnal_value(curve, REFERENCE_HOUR) / diurnal_value(curve, hour))


def _fit_curve(constraints: list[tuple[float, float, float]]) -> dict[str, float]:
    """Grid search for (peak, width, base) matching observed rate ratios f(h1)/f(h2), shrunk to the default."""
    best, best_loss = DEFAULT_DIURNAL, float("inf")
    for peak in np.arange(12.0, 16.51, 0.25):
        for width in np.arange(1.5, 5.01, 0.25):
            for base in np.arange(0.02, 0.41, 0.02):
                c = {"peak_hour": float(peak), "width_h": float(width), "base": float(base)}
                loss = sum((math.log(r) - math.log(diurnal_value(c, h1) / diurnal_value(c, h2))) ** 2 for h1, h2, r in constraints)
                loss += 0.3 * ((peak - 14.0) ** 2 / 4 + (width - 2.5) ** 2 / 1 + (base - 0.08) ** 2 / 0.0025)
                if loss < best_loss:
                    best, best_loss = c, loss
    return {k: round(v, 3) for k, v in best.items()}


def _ratio_constraints(clusters: list[dict[str, Any]], both_days: dict[tuple[str, str], set[date]]) -> list[tuple[float, float, float]]:
    out = []

    def mean_hour(rows: list[dict[str, Any]]) -> float:
        angles = [2 * math.pi * r["local_solar_hour"] / 24 for r in rows]
        return (math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles)) * 24 / (2 * math.pi)) % 24

    terra_aqua = both_days.get(("terra", "aqua"), set())
    terra = [c for c in clusters if c["witness"] == "terra" and c["local_day"] in terra_aqua and DAY_HOURS[0] <= c["local_solar_hour"] <= DAY_HOURS[1]]
    aqua = [c for c in clusters if c["witness"] == "aqua" and c["local_day"] in terra_aqua and DAY_HOURS[0] <= c["local_solar_hour"] <= DAY_HOURS[1]]
    if len(terra) >= MIN_DIURNAL_DETECTIONS and len(aqua) >= MIN_DIURNAL_DETECTIONS:
        out.append((mean_hour(terra), mean_hour(aqua), len(terra) / len(aqua)))
    viirs = [c for c in clusters if c["family"] == "VIIRS"]
    day = [c for c in viirs if DAY_HOURS[0] <= c["local_solar_hour"] <= DAY_HOURS[1]]
    night = [c for c in viirs if not (DAY_HOURS[0] <= c["local_solar_hour"] <= DAY_HOURS[1])]
    if len(day) >= MIN_DIURNAL_DETECTIONS and len(night) >= MIN_DIURNAL_DETECTIONS // 4:
        out.append((mean_hour(night), mean_hour(day), len(night) / len(day)))
    return out


def fit_diurnal_curves(clusters: list[dict[str, Any]], both_days: dict[tuple[str, str], set[date]]) -> dict[str, Any]:
    """One curve for the whole area, plus per-month curves where the month has enough detections."""
    overall_constraints = _ratio_constraints(clusters, both_days)
    overall = _fit_curve(overall_constraints) if overall_constraints else dict(DEFAULT_DIURNAL)
    by_month: dict[int, dict[str, float]] = {}
    for m in range(1, 13):
        cons = _ratio_constraints([c for c in clusters if c["local_day"].month == m], both_days)
        if len(cons) >= 2:
            by_month[m] = _fit_curve(cons)
    return {
        "overall": overall,
        "by_month": by_month,
        "source": "fitted from Terra/Aqua and VIIRS day/night detection ratios" if overall_constraints else "default afternoon-peaking curve (too few detections to fit)",
        "reference": "Aqua 13:30 local solar time",
        "note": "Each observation is scaled by f(13:30)/f(its real local time), capped at 4x, which also removes the overpass-drift artifacts of Terra and Aqua. Himawari diurnal cycles are not connected (no public fire API).",
    }


# --- Stage 7: observation effort ---------------------------------------------------------------


def looks_per_pass(witness: str, lat: float) -> float:
    """Expected looks per pass direction per day: swath / ground-track spacing at this latitude.

    Below 1 near the equator (MODIS swath gaps), well above 1 near the poles (overlapping swaths).
    """
    return SWATH_KM[witness] / (ORBIT_SPACING_KM * max(0.05, math.cos(math.radians(lat))))


def clear_fraction(cloud_pct: float | None) -> float:
    if cloud_pct is None:
        return 0.7
    return max(0.1, 1 - max(0.0, min(100.0, cloud_pct)) / 100)


def nominal_hours(witness: str, day: date) -> tuple[float, float]:
    """Approximate day/night local overpass hours, including Terra/Aqua drift after 2020-21."""
    h = NOMINAL_DAY_HOUR[witness]
    years = (day - date(2021, 1, 1)).days / 365.25
    if witness == "aqua" and years > 0:
        h += 0.35 * years
    elif witness == "terra" and years > 0:
        h -= 0.3 * years
    return h, (h + 12) % 24


def witnesses_available(day: date, sensors_available: list[str]) -> list[str]:
    return [w for w in WITNESSES if day >= WITNESS_START[w] and WITNESS_SENSOR[w] in sensors_available]


# --- Pipeline ----------------------------------------------------------------------------------


def _sigmoid(z: np.ndarray | float) -> Any:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


class WitnessModel:
    def __init__(
        self,
        hotspots: list[dict[str, Any]],
        start: date,
        end: date,
        sensors: list[str],
        availability: dict[date, list[str]] | None,
        cloud_cover: dict[date, float | None] | None,
        area_km2: float | None,
        lat_center: float | None = None,
    ):
        self.start, self.end = start, end
        self.days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        tagged, self.dropped = clean_and_tag(hotspots)
        self.tagged = tagged
        modis = merge_overpass([r for r in tagged if r["family"] == "MODIS"], 1.0, "max")
        self.modis_duplicates_removed = sum(1 for r in tagged if r["family"] == "MODIS") - len(modis)
        viirs = merge_overpass([r for r in tagged if r["family"] == "VIIRS"], 1.0, "sum")
        self.clusters = modis + viirs
        self.lat = lat_center if lat_center is not None else (float(np.mean([r["lat"] for r in tagged])) if tagged else 0.0)
        self.available = {d: witnesses_available(d, (availability or {}).get(d, sensors)) for d in self.days}
        self.clear = {d: clear_fraction((cloud_cover or {}).get(d)) for d in self.days}
        self.cloud_known = bool(cloud_cover)

        self.profile_info = learn_detection_profile(modis, viirs)
        self.profile = self.profile_info["profile"]
        for c in self.clusters:
            c["p_modis"] = 1.0 if c["family"] == "MODIS" else detection_probability(self.profile, c["frp"], c["pixel_area_km2"])

        both: dict[tuple[str, str], set[date]] = {("terra", "aqua"): {d for d, ws in self.available.items() if "terra" in ws and "aqua" in ws}}
        self.diurnal = fit_diurnal_curves(self.clusters, both)
        viirs_p = [c["p_modis"] for c in self.clusters if c["family"] == "VIIRS"]
        self.modis_fraction_of_viirs = float(np.mean(viirs_p)) if viirs_p else 0.4
        self.sensitivity = {w: (VIIRS_SENSITIVITY if WITNESS_FAMILY[w] == "VIIRS" else VIIRS_SENSITIVITY * self.modis_fraction_of_viirs) for w in WITNESSES}

        cell_area = (CELL_DEG * 111.32) ** 2 * max(0.05, math.cos(math.radians(self.lat)))
        self.n_cells_aoi = max(1, round((area_km2 or cell_area) / cell_area))

    def curve(self, day: date) -> dict[str, float]:
        return self.diurnal["by_month"].get(day.month, self.diurnal["overall"])

    def pass_detection_chance(self, witness: str, hour: float, day: date) -> float:
        return self.sensitivity[witness] * diurnal_value(self.curve(day), hour)

    # Stages 6 and 7: daily tiers, normalized by effort.
    def daily_tiers(self) -> dict[date, dict[str, Any]]:
        by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for c in self.clusters:
            by_day[c["local_day"]].append(c)
        raw_viirs: dict[date, int] = defaultdict(int)
        for r in self.tagged:
            if r["family"] == "VIIRS":
                raw_viirs[r["local_day"]] += 1
        frp_ratio = self.profile_info["modis_frp_per_viirs_frp"]
        out = {}
        for d in self.days:
            ws = self.available[d]
            curve = self.curve(d)
            clear = self.clear[d]
            day_looks = {w: looks_per_pass(w, self.lat) * clear for w in ws}
            viirs_looks = sum(2 * day_looks[w] for w in ws if WITNESS_FAMILY[w] == "VIIRS")
            x = var = frp = 0.0
            by_w: dict[str, int] = defaultdict(int)
            for c in by_day.get(d, []):
                if c["witness"] not in day_looks:
                    continue
                by_w[c["witness"]] += 1
                if not (DAY_HOURS[0] <= c["local_solar_hour"] <= DAY_HOURS[1]):
                    continue
                f = time_factor(curve, c["local_solar_hour"])
                p = c["p_modis"]
                x += p * f
                var += p * f * f
                frp += c["frp"] * (1.0 if c["family"] == "MODIS" else frp_ratio * p) * f
            effort = sum(day_looks.values())
            if effort < 0.05:
                out[d] = {"consistent": 0.0, "low": 0.0, "high": 0.0, "detailed": 0.0, "frp_aqua_equiv": 0.0, "effort_looks": round(effort, 3), "effort_ok": False, "detections_by_witness": dict(by_w), "witnesses": ws}
                continue
            value = x / effort
            sigma = math.sqrt(var) / effort
            out[d] = {
                "consistent": round(value, 4),
                "low": round(max(0.0, value - 1.96 * sigma), 4),
                "high": round(value + 1.96 * sigma, 4),
                "detailed": round(raw_viirs.get(d, 0) / viirs_looks, 4) if viirs_looks >= 0.05 else None,
                "frp_aqua_equiv": round(frp / effort, 3),
                "effort_looks": round(effort, 3),
                "effort_ok": True,
                "detections_by_witness": dict(by_w),
                "witnesses": ws,
            }
        return out

    # Stage 8: fused probability.
    def hits(self, exclude: str | None = None) -> dict[tuple[tuple[int, int], date], dict[str, dict[str, float]]]:
        """(cell, local day) -> witness -> {hour of the strongest detection, detections, frp}."""
        out: dict[tuple[tuple[int, int], date], dict[str, dict[str, float]]] = defaultdict(dict)
        for c in self.clusters:
            if c["witness"] == exclude or c["witness"] not in self.available.get(c["local_day"], []):
                continue
            slot = out[(c["cell"], c["local_day"])].setdefault(c["witness"], {"hour": c["local_solar_hour"], "detections": 0, "frp": 0.0, "best": -1.0})
            slot["detections"] += 1
            slot["frp"] += c["frp"]
            if c["frp"] > slot["best"]:
                slot["best"], slot["hour"] = c["frp"], c["local_solar_hour"]
        return out

    def priors(self, hits: dict) -> tuple[dict[tuple[tuple[int, int], int], int], dict[int, int], dict[int, float]]:
        k: dict[tuple[tuple[int, int], int], int] = defaultdict(int)
        for (cell, d) in hits:
            k[(cell, d.month)] += 1
        n_m: dict[int, int] = defaultdict(int)
        for d in self.days:
            n_m[d.month] += 1
        rate = {m: sum(v for (c, mm), v in k.items() if mm == m) / (n_m[m] * self.n_cells_aoi) for m in n_m}
        return k, n_m, rate

    def prior(self, k: int, month: int, n_m: dict[int, int], rate: dict[int, float]) -> float:
        return (k + PRIOR_STRENGTH_DAYS * rate[month]) / (n_m[month] + PRIOR_STRENGTH_DAYS)

    def miss_terms(self, d: date, exclude: str | None = None) -> dict[str, float]:
        """Log-likelihood ratio contributed by each witness when it looked and saw nothing."""
        out = {}
        for w in self.available[d]:
            if w == exclude:
                continue
            looks = looks_per_pass(w, self.lat) * self.clear[d]
            term = 0.0
            for hour in nominal_hours(w, d):
                pd = self.pass_detection_chance(w, hour, d)
                term += looks * (math.log(1 - pd) - math.log(1 - FALSE_ALARM_PER_LOOK))
            out[w] = term
        return out

    def cell_logit(self, prior: float, seen: dict[str, dict[str, float]], miss: dict[str, float], d: date) -> float:
        z = _logit(prior)
        for w, term in miss.items():
            if w in seen:
                pd = max(0.02, self.pass_detection_chance(w, seen[w]["hour"], d))
                z += math.log(pd / FALSE_ALARM_PER_LOOK)
            else:
                z += term
        return z

    def fuse(self, exclude: str | None = None) -> tuple[dict[date, dict[str, Any]], list[dict[str, Any]]]:
        hits = self.hits(exclude)
        k, n_m, rate = self.priors(hits)
        ever_by_month: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for (cell, m), v in k.items():
            ever_by_month[m][v] += 1
        hits_by_day: dict[date, list[tuple[tuple[int, int], dict]]] = defaultdict(list)
        for (cell, d), seen in hits.items():
            hits_by_day[d].append((cell, seen))
        daily: dict[date, dict[str, Any]] = {}
        rows: list[dict[str, Any]] = []
        for d in self.days:
            miss = self.miss_terms(d, exclude)
            m = d.month
            groups = dict(ever_by_month[m])
            groups[0] = groups.get(0, 0) + max(0, self.n_cells_aoi - sum(ever_by_month[m].values()))
            det_sum = 0.0
            for cell, seen in hits_by_day.get(d, []):
                kc = k[(cell, m)]
                groups[kc] -= 1
                p = float(_sigmoid(self.cell_logit(self.prior(kc - 1, m, n_m, rate), seen, miss, d)))
                det_sum += p
                lat, lon = cell_center(cell)
                rows.append(
                    {
                        "cell_lat": lat,
                        "cell_lon": lon,
                        "local_day": d.isoformat(),
                        "clear_looks": {w: round(looks_per_pass(w, self.lat) * self.clear[d] * 2, 2) for w in miss},
                        "detections": {w: int(s["detections"]) for w, s in seen.items()},
                        "sensors_seen": sorted(seen),
                        "fire_probability": round(p, 4),
                        "frp_aqua_equiv": round(sum(s["frp"] * time_factor(self.curve(d), s["hour"]) * (1.0 if WITNESS_FAMILY[w] == "MODIS" else self.profile_info["modis_frp_per_viirs_frp"]) for w, s in seen.items()) / max(1, len(seen)), 2),
                    }
                )
            m_total = sum(miss.values())
            quiet = sum(n * float(_sigmoid(_logit(self.prior(kv, m, n_m, rate)) + m_total)) for kv, n in groups.items() if n > 0)
            daily[d] = {"fused_fire_cells": round(det_sum + quiet, 4), "detected_cells": len(hits_by_day.get(d, []))}
        return daily, rows

    # Validation 2: hide one witness.
    def hide_one_witness(self, hidden: str, negatives: int = 4000, seed: int = 7) -> dict[str, Any]:
        days_h = [d for d in self.days if hidden in self.available[d]]
        truth = {key for key, seen in self.hits().items() if hidden in seen}
        if not days_h or not truth:
            return {"status": "not_run", "hidden": WITNESS_LABEL[hidden], "note": f"{WITNESS_LABEL[hidden]} has no detections in this area and period."}
        hits = self.hits(exclude=hidden)
        k, n_m, rate = self.priors(hits)
        day_set = set(days_h)
        candidates = {key for key in hits if key[1] in day_set} | {key for key in truth if key[1] in day_set}
        cells = sorted({cell for cell, _ in candidates})
        rng = random.Random(seed)
        for _ in range(negatives):
            candidates.add((rng.choice(cells), rng.choice(days_h)))
        scores, priors_only, labels, hard = [], [], [], []
        miss_cache: dict[date, dict[str, float]] = {}
        sees_cache: dict[date, float] = {}
        for cell, d in candidates:
            miss = miss_cache.setdefault(d, self.miss_terms(d, hidden))
            # Chance the hidden witness records a fire that is there, given its clear looks that day.
            sees = sees_cache.setdefault(d, 1 - math.exp(self.miss_terms(d).get(hidden, 0.0)))
            kc = k.get((cell, d.month), 0)
            seen = hits.get((cell, d), {})
            prior = self.prior(kc - 1 if seen else kc, d.month, n_m, rate)
            scores.append(float(_sigmoid(self.cell_logit(prior, seen, miss, d))) * sees)
            priors_only.append(prior * sees)
            labels.append(1 if (cell, d) in truth else 0)
            hard.append(bool(seen))
        s, p, y, h = np.array(scores), np.array(priors_only), np.array(labels), np.array(hard)
        result = {
            "status": "ok",
            "hidden": WITNESS_LABEL[hidden],
            "cell_days_evaluated": int(len(y)),
            "hidden_detections": int(y.sum()),
            "auc_fused": _auc(s, y),
            "auc_prior_only": _auc(p, y),
            "auc_fused_where_other_witnesses_detected": _auc(s[h], y[h]) if h.any() else None,
            "brier_fused": round(float(np.mean((s - y) ** 2)), 4),
            "brier_prior_only": round(float(np.mean((p - y) ** 2)), 4),
        }
        result["note"] = (
            f"{WITNESS_LABEL[hidden]} was removed and the fused probability rebuilt from the other witnesses, then multiplied by the chance the hidden witness would see a fire on that day's clear looks. AUC is how well this ranks the cell-days the hidden "
            f"witness actually detected (0.5 = chance). Negatives are {negatives} random cell-days from cells that burned at least once, so the first AUC is optimistic; "
            "the 'where other witnesses detected' AUC is the harder test."
        )
        return result


def _auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    pos, neg = int(labels.sum()), int(len(labels) - labels.sum())
    if pos == 0 or neg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores))
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return round(float((ranks[labels == 1].sum() - pos * (pos + 1) / 2) / (pos * neg)), 3)


# Validation 1: continuity across sensor changes.
SENSOR_STEPS = [("VIIRS Suomi NPP start", SENSOR_START_DATES["viirs_snpp"]), ("VIIRS NOAA-20 start", SENSOR_START_DATES["viirs_noaa20"])]


def continuity_test(daily: list[dict[str, Any]], months: int = 24) -> list[dict[str, Any]]:
    """Ratio of mean activity in the N months after vs before each sensor change, raw vs consistent.

    A good harmonization keeps the consistent ratio near 1 while the raw count jumps. Real
    year-to-year variability also moves both ratios, so compare them with each other.
    """
    results = []
    for label, step in SENSOR_STEPS:
        before = [r for r in daily if step - timedelta(days=30.44 * months) <= r["date"] < step]
        after = [r for r in daily if step <= r["date"] < step + timedelta(days=30.44 * months)]
        if len(before) < 300 or len(after) < 300:
            continue

        def ratio(field: str) -> float | None:
            b = sum(r[field] for r in before) / len(before)
            a = sum(r[field] for r in after) / len(after)
            return round(a / b, 3) if b > 0 else None

        raw, consistent = ratio("hotspot_count"), ratio("harmonized_activity")
        verdict = None
        if raw and consistent:
            reduced = abs(math.log(consistent)) < abs(math.log(raw))
            verdict = "step removed" if reduced and abs(math.log(consistent)) < math.log(1.35) else "step reduced" if reduced else "no improvement"
        results.append({"change": label, "date": step.isoformat(), "window_months": months, "raw_count_ratio": raw, "consistent_record_ratio": consistent, "verdict": verdict})
    return results


def run_witness_pipeline(
    hotspots: list[dict[str, Any]],
    start: date,
    end: date,
    sensors: list[str],
    availability: dict[date, list[str]] | None = None,
    cloud_cover: dict[date, float | None] | None = None,
    area_km2: float | None = None,
    lat_center: float | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    model = WitnessModel(hotspots, start, end, sensors, availability, cloud_cover, area_km2, lat_center)
    tiers = model.daily_tiers()
    fused, cell_days = model.fuse()
    validation: dict[str, Any] = {}
    if validate:
        hidden = "noaa20" if any(c["witness"] == "noaa20" for c in model.clusters) else "snpp"
        validation["hide_one_witness"] = model.hide_one_witness(hidden)
    witness_counts = defaultdict(int)
    for r in model.tagged:
        witness_counts[r["witness"]] += 1
    summary = {
        "witnesses": {w: {"label": WITNESS_LABEL[w], "detections": witness_counts.get(w, 0), "sensitivity_per_look": round(model.sensitivity[w], 3), "swath_km": SWATH_KM[w], "looks_per_pass_at_aoi": round(looks_per_pass(w, model.lat), 2)} for w in WITNESSES},
        "cleaning": {**model.dropped, "kept": len(model.tagged), "modis_duplicates_removed": model.modis_duplicates_removed, "viirs_pixels_grouped_into_clusters": sum(1 for r in model.tagged if r["family"] == "VIIRS") - sum(1 for c in model.clusters if c["family"] == "VIIRS")},
        "detection_profile": model.profile_info,
        "modis_fraction_of_viirs_fires": round(model.modis_fraction_of_viirs, 3),
        "diurnal": {**model.diurnal, "by_month": {str(k): v for k, v in model.diurnal["by_month"].items()}},
        "effort": {
            "method": "Expected looks = swath width / ground-track spacing at the AOI latitude, for the day and night pass, times the clear-sky fraction. Daily observation masks (MOD14A1/MYD14A1/VNP14A1/VJ114A1) need an Earthdata login and are not connected.",
            "cloud_source": "ERA5 daily mean cloud cover at the AOI centre" if model.cloud_known else "unknown (70% clear assumed)",
        },
        "tiers": {
            "consistent_record": "MODIS-level sensitivity in Aqua 13:30 equivalent detections per clear look: MODIS daytime detections (duplicates removed) plus VIIRS daytime clusters weighted by the chance MODIS would have seen them.",
            "detailed_layer": "Every VIIRS 375 m detection (day and night) per clear VIIRS look; drives the globe and live hotspots.",
        },
        "fusion": {
            "method": "Occupancy-style update per 0.1 deg cell and local day: start from the cell's historical burning rate for that month (shrunk to the area rate), add log(p_detect / false-alarm) for each witness that detected and log((1 - p_detect)^looks) for each clear miss; cloudy looks are not counted.",
            "false_alarm_per_look": FALSE_ALARM_PER_LOOK,
            "cells_in_aoi": model.n_cells_aoi,
        },
        "cell_grid_deg": CELL_DEG,
        "local_day": "Days are local solar days (UTC + longitude / 15).",
    }
    return {"model": model, "tiers": tiers, "fused": fused, "cell_days": cell_days, "summary": summary, "validation": validation}
