"""Satellite observation grouping and regional-source helpers.

Legacy scoring helpers are retained for compatibility, but are not used by
the source-backed case builder exported at the end of this module.
Streams (run after the first detection, recalculated whenever evidence is refreshed):
- A: later polar passes (predicted from orbits): seen stronger/weaker, spread, clear miss, cloud, not covered
- B: regional geostationary satellites: when the fire started, how long it burned, when it ended
- C: news and official reports (NLP-classified, matched by distance and time)
plus background facts: land use, nearby heat sources, the local burning season, repeat heat.

Every item lands in one time-ordered evidence block and votes for the categories it
supports, weighted by its reliability. The answer:
1. Is it real?   2. What kind?   3. What is it doing now?
A type is only named when the top category scores above 50% and leads the next by 20 points.
Percentages are evidence scores, not calibrated probabilities.
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from environment import hourly_weather, weather_at
from firms_client import FirmsAPIError, fetch_hotspots_with_report
from geo import haversine_km, radius_bbox
from harmonize import filter_low_confidence
from http_utils import ExternalServiceError
from overpass import predict_passes
from witness import (
    DEFAULT_DIURNAL,
    FALSE_ALARM_PER_LOOK,
    PRIOR_PROFILE,
    VIIRS_SENSITIVITY,
    WITNESS_FAMILY,
    WITNESS_LABEL,
    detection_probability,
    diurnal_value,
    witness_of,
)


CASE_WINDOW_HOURS = 24
PASS_MATCH_MINUTES = 15
CLOUDY_PCT = 70.0
MIN_TOP_SCORE = 50.0
MIN_LEAD = 20.0
BASE_VOTE = 0.25
SEASON_YEARS = 5
SEASON_HALF_WINDOW_DAYS = 15

CATEGORIES = ["agricultural_burn", "wildfire", "controlled_burn", "industrial_source", "building_fire", "volcanic", "not_a_fire"]
CATEGORY_LABEL = {
    "agricultural_burn": "Agricultural burn",
    "wildfire": "Forest or wildfire",
    "controlled_burn": "Controlled burn",
    "industrial_source": "Industrial heat source or gas flare",
    "building_fire": "Building or industrial fire",
    "volcanic": "Volcanic activity",
    "not_a_fire": "Not a fire (false detection)",
}
FIRE_CATEGORIES = ["agricultural_burn", "wildfire", "controlled_burn", "building_fire"]
NEWS_CATEGORY = {
    "WILDFIRE": "wildfire",
    "FOREST_FIRE": "wildfire",
    "AGRICULTURAL_BURN": "agricultural_burn",
    "LAND_CLEARING": "agricultural_burn",
    "DEFORESTATION_RELATED_BURNING": "wildfire",
    "CONTROLLED_BURN": "controlled_burn",
    "FACTORY_FIRE": "building_fire",
    "BUILDING_FIRE": "building_fire",
    "INDUSTRIAL_HEAT_SOURCE": "industrial_source",
    "GAS_FLARE": "industrial_source",
    "VOLCANIC_ACTIVITY": "volcanic",
}
CROPLAND = {"farmland", "meadow", "orchard", "plantation", "farmyard", "vineyard"}
WILDLAND = {"forest", "wood", "scrub", "grassland", "heath", "wetland"}
NON_FIRE_HEAT = {"industrial_source", "volcanic", "not_a_fire"}
OUTCOME_LABEL = {
    "first_detection": "First detection (case opened)",
    "seen": "Fire still seen",
    "seen_stronger": "Fire seen, stronger",
    "seen_weaker": "Fire seen, weaker",
    "spread": "Fire spread to neighbouring cells",
    "clear_no_fire": "Clear view, no fire",
    "cloud_or_smoke": "Clouds or smoke, no view",
    "not_covered": "Predicted outside instrument swath",
    "expected": "Predicted pass (not an observation)",
    "unverified": "No matching detection; observation coverage unverified",
}


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


class Ballot:
    """Collects evidence items and their category votes."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.totals: dict[str, float] = {c: BASE_VOTE for c in CATEGORIES}

    def add(self, stream: str, source: str, summary: str, reliability: float, votes: dict[str, float] | None = None, time: datetime | None = None, link: str | None = None, kind: str = "observation") -> None:
        weighted = {c: round(w * reliability, 3) for c, w in (votes or {}).items() if w * reliability > 0}
        for c, w in weighted.items():
            self.totals[c] += w
        self.items.append({"time": _iso(time), "stream": stream, "source": source, "kind": kind, "summary": summary, "reliability": round(reliability, 2), "votes": weighted, "link": link})

    def scores(self) -> list[dict[str, Any]]:
        total = sum(self.totals.values())
        raw = [(c, 100 * v / total) for c, v in self.totals.items()]
        rounded = [[c, math.floor(v)] for c, v in raw]
        # Largest-remainder rounding so the shown percentages sum to exactly 100.
        for i in sorted(range(len(raw)), key=lambda i: raw[i][1] - math.floor(raw[i][1]), reverse=True)[: 100 - sum(r[1] for r in rounded)]:
            rounded[i][1] += 1
        out = [{"category": c, "label": CATEGORY_LABEL[c], "score": s, "raw_score": round(v, 2)} for (c, s), (_, v) in zip(rounded, raw)]
        return sorted(out, key=lambda r: r["raw_score"], reverse=True)


# --- Background: local burning season and repeat heat -------------------------------------------


async def burning_season(lat: float, lon: float, when: datetime) -> dict[str, Any]:
    """Same +/-15 days in the previous 5 years (MODIS, consistent record): recurring fire nearby and repeat heat on the spot."""
    bbox = tuple(round(v, 3) for v in radius_bbox(lat, lon, 10))

    async def year(back: int) -> tuple[int, list[dict[str, Any]] | None]:
        try:
            center = when.date().replace(year=when.year - back)
        except ValueError:
            center = when.date().replace(year=when.year - back, day=28)
        try:
            rows, _ = await fetch_hotspots_with_report(bbox, center - timedelta(days=SEASON_HALF_WINDOW_DAYS), center + timedelta(days=SEASON_HALF_WINDOW_DAYS), ["modis"])  # type: ignore[arg-type]
        except FirmsAPIError:
            return center.year, None
        return center.year, filter_low_confidence(rows)

    results = await asyncio.gather(*(year(b) for b in range(1, SEASON_YEARS + 1)))
    ok = [(y, rows) for y, rows in results if rows is not None]
    if not ok:
        return {"status": "unavailable", "note": "FIRMS archive could not be reached for the burning-season check."}
    within5 = [y for y, rows in ok if any(haversine_km(lat, lon, r["lat"], r["lon"]) <= 5 for r in rows)]
    within1 = [y for y, rows in ok if any(haversine_km(lat, lon, r["lat"], r["lon"]) <= 1.0 for r in rows)]
    return {
        "status": "ok",
        "years_checked": len(ok),
        "years_with_fire_within_5km": len(within5),
        "years_with_heat_within_1km": len(within1),
        "detections_by_year": {str(y): sum(1 for r in rows if haversine_km(lat, lon, r["lat"], r["lon"]) <= 5) for y, rows in ok},
        "window": f"same date +/-{SEASON_HALF_WINDOW_DAYS} days in {', '.join(str(y) for y, _ in ok)}",
        "note": "MODIS detections from the FIRMS archive (consistent-record sensitivity).",
    }


# --- Stream A: later polar passes ------------------------------------------------------------------


def _detection_passes(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the case's detections into overpasses (same witness, <= 10 min)."""
    rows = sorted(({**d, "_t": _utc(d["acq_datetime"]), "_w": witness_of(d)} for d in detections), key=lambda r: (str(r["_w"]), r["_t"]))
    groups: list[list[dict[str, Any]]] = []
    for r in rows:
        if r["_w"] is None:
            continue
        if groups and groups[-1][0]["_w"] == r["_w"] and (r["_t"] - groups[-1][0]["_t"]).total_seconds() <= 600:
            groups[-1].append(r)
        else:
            groups.append([r])
    return [{"witness": g[0]["_w"], "time": g[0]["_t"], "rows": g} for g in groups]


def pass_detection_chance(witness: str, local_hour: float, frp: float, swath_position: str) -> float:
    """Chance this witness sees a fire like the case's: sensor sensitivity x fire activity at that hour."""
    activity = diurnal_value(DEFAULT_DIURNAL, local_hour)
    if WITNESS_FAMILY[witness] == "VIIRS":
        edge = 0.85 if swath_position == "swath edge" else 1.0
        return VIIRS_SENSITIVITY * activity * edge
    area = {"near nadir": 0.15, "mid swath": 0.3, "swath edge": 0.6}.get(swath_position, 0.3)
    return VIIRS_SENSITIVITY * activity * detection_probability(PRIOR_PROFILE, max(frp, 1.0), area)


def classify_passes(predicted: list[dict[str, Any]], detections: list[dict[str, Any]], hourly: list[dict[str, Any]], origin: tuple[float, float], radius_km: float, now: datetime) -> list[dict[str, Any]]:
    det_passes = _detection_passes(detections)
    used: set[int] = set()
    out = []
    prev_frp: float | None = None
    for p in predicted:
        match = next((i for i, g in enumerate(det_passes) if i not in used and g["witness"] == p["witness"] and abs((g["time"] - p["time"]).total_seconds()) <= PASS_MATCH_MINUTES * 60), None)
        if match is not None:
            used.add(match)
        out.append({**p, "_group": det_passes[match] if match is not None else None})
    for i, g in enumerate(det_passes):
        if i not in used:
            solar = g["time"] + timedelta(hours=origin[1] / 15)
            out.append({"witness": g["witness"], "label": WITNESS_LABEL[g["witness"]], "time": g["time"], "off_nadir_km": None, "in_swath": True, "coverage_probability": 1.0, "swath_position": "unknown", "local_solar_hour": round(solar.hour + solar.minute / 60, 2), "method": "from detection", "_group": g})
    out.sort(key=lambda p: p["time"])

    first_cells = None
    result = []
    for p in out:
        group = p.pop("_group")
        item = dict(p)
        if p["time"] > now:
            item["outcome"] = "expected"
        elif group:
            # Display the recorded acquisition time, never the nearby predicted
            # orbit time that was used to associate this observation.
            item['time'] = group['time']
            item['method'] = 'recorded FIRMS detection'
            frp = sum(float(r.get("frp") or 0) for r in group["rows"])
            pts = [(r["lat"], r["lon"]) for r in group["rows"]]
            if first_cells is None:
                first_cells = pts
                outcome = "first_detection"
            elif any(min(haversine_km(a, b, c, d) for c, d in first_cells) > max(1.5, radius_km * 0.25) + 1.0 for a, b in pts):
                outcome = "spread"
            elif prev_frp and frp >= 1.25 * prev_frp:
                outcome = "seen_stronger"
            elif prev_frp and frp <= 0.75 * prev_frp:
                outcome = "seen_weaker"
            else:
                outcome = "seen"
            prev_frp = frp
            item.update({"outcome": outcome, "detections": len(group["rows"]), "frp_mw": round(frp, 1), "max_confidence": max(float(r.get("confidence_pct") or 0) for r in group["rows"])})
        elif not p["in_swath"]:
            item["outcome"] = "not_covered"
        else:
            # Modelled cloud cover is not an instrument cloud mask or proof of coverage.
            item["outcome"] = "unverified"
        item["outcome_label"] = OUTCOME_LABEL[item["outcome"]]
        result.append(item)
    return result


# --- Stream B: geostationary -----------------------------------------------------------------------


def geostationary_stream(regional: dict[str, Any]) -> dict[str, Any]:
    goes = next((c for c in regional["checks"] if "GOES" in c["name"] or c.get("geostationary")), None)
    sat_name = (goes or {}).get("satellite", "GOES")
    links = [c for c in regional["checks"] if c.get("kind") == "manual_review" and any(k in c["name"] for k in ("Himawari", "Meteosat"))]
    if goes and goes.get("status") == "corroborating":
        times = sorted(_utc(m["acq_datetime"]) for m in goes.get("matches", []))
        start, end = times[0], times[-1]
        return {"status": "seen", "satellite": sat_name, "started": _iso(start), "last_seen": _iso(end), "duration_hours": round((end - start).total_seconds() / 3600, 2), "observations": len(times), "detail": goes["detail"], "review_links": links}
    if goes and goes.get("status") == "no_match":
        return {"status": "not_seen", "satellite": sat_name, "detail": goes["detail"], "review_links": links}
    if goes:
        return {"status": "unavailable", "satellite": sat_name, "detail": goes.get("detail"), "review_links": links}
    if links:
        return {"status": "manual_review", "satellite": " / ".join(c["name"].split(" ")[0] for c in links), "detail": "Himawari and Meteosat have no public fire-detection API, so the start, duration and end of this fire cannot be measured automatically here. Use the review links.", "review_links": links}
    return {"status": "no_coverage", "detail": "No geostationary fire product covers this location.", "review_links": []}


# --- Satellite fire probability (stage 8 applied to the case) ------------------------------------


def case_fire_probability(passes: list[dict[str, Any]], season: dict[str, Any], first: datetime, max_frp: float, best_conf: float) -> dict[str, Any]:
    if season.get("status") == "ok":
        prior = 0.02 + 0.2 * season["years_with_fire_within_5km"] / max(1, season["years_checked"])
    else:
        prior = 0.05
    q = FALSE_ALARM_PER_LOOK * (3 if best_conf < 50 else 1)
    z = math.log(prior / (1 - prior))
    used = 0
    for p in passes:
        if p["outcome"] in {"expected", "not_covered", "cloud_or_smoke"} or not (first <= p["time"] <= first + timedelta(hours=12)):
            continue
        pd = max(0.02, min(0.95, pass_detection_chance(p["witness"], p["local_solar_hour"], max_frp, p.get("swath_position", "unknown"))))
        if p["outcome"] == "clear_no_fire":
            z += math.log(1 - pd) - math.log(1 - q)
        else:
            z += math.log(pd / q)
        used += 1
    return {
        "probability": round(1 / (1 + math.exp(-max(-30, min(30, z)))), 3),
        "prior": round(prior, 3),
        "passes_used": used,
        "method": "Occupancy-style update over polar passes within 12 h of the first detection: each detection multiplies the odds by p_detect / false-alarm rate, each clear miss by (1 - p_detect); cloudy and uncovered passes are ignored. The prior is the local burning-season recurrence.",
    }


# --- Answer ---------------------------------------------------------------------------------------------


def _reality(fusion: dict[str, Any], top: str, decided: bool, sat_prob: float) -> tuple[str, str]:
    status = fusion["final_status"]
    if status == "Confirmed Fire":
        return "Confirmed fire", "An official report describes a fire at this place and time."
    if status == "Likely Non-Fire Thermal Source" or (decided and top in NON_FIRE_HEAT):
        return "Likely non-fire thermal anomaly", f"The evidence favours '{CATEGORY_LABEL[top]}' over a burning fire." if decided and top in NON_FIRE_HEAT else "A known non-fire heat source or a non-vegetation report matches."
    if status in {"Strong Multi-Source Fire Evidence", "Externally Corroborated Fire Event", "Highly Likely Fire"}:
        return "Highly likely fire", f"{status}: independent sources agree."
    if sat_prob >= 0.9 and status != "Insufficient Evidence":
        return "Highly likely fire", f"Repeated satellite looks give a fused fire probability of {sat_prob:.0%}, but no independent source confirms it yet."
    if status == "No External Corroboration Yet":
        return "No external confirmation yet", "Satellites saw strong heat, but no other source has confirmed it yet."
    return "Possible fire (needs verification)", "The satellite evidence on its own is weak or mixed."


def _now_state(passes: list[dict[str, Any]], behaviour: dict[str, Any] | None, last_det: datetime, now: datetime) -> tuple[str, str]:
    since = (now - last_det).total_seconds() / 3600
    after = [p for p in passes if p["time"] > last_det + timedelta(minutes=PASS_MATCH_MINUTES) and p["outcome"] not in {"expected", "not_covered"}]
    clear_after = [p for p in after if p["outcome"] == "clear_no_fire"]
    cloudy_after = [p for p in after if p["outcome"] == "cloud_or_smoke"]
    state = (behaviour or {}).get("state")
    if since > 48 or (clear_after and since >= 6):
        basis = f"Last detected {since:.0f} h ago" + (f"; {len(clear_after)} later clear pass(es) saw no fire." if clear_after else ".")
        return "Ended", basis
    if any(p["outcome"] == "spread" for p in passes) or state in {"Expanding", "Intensifying"}:
        return "Growing", "On later passes, satellites saw the fire in new places or burning more strongly."
    seen = [p for p in passes if p.get("frp_mw") is not None]
    if state == "Decaying" or (seen and seen[-1]["outcome"] == "seen_weaker"):
        return "Weakening", "The fire was burning less strongly on the latest satellite pass."
    if cloudy_after and not clear_after:
        return "Active", f"Last detected {since:.0f} h ago; {len(cloudy_after)} later pass(es) were blocked by cloud or smoke, so it may still be burning."
    return "Active", f"Last detected {since:.1f} h ago."


from source_case import build_fire_case
