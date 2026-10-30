"""Fire Case: every detection opens a case that gathers evidence and ends in one three-part answer.

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
    "not_covered": "Not covered by this pass",
    "expected": "Expected pass",
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
            w = weather_at(hourly, p["time"]) if hourly else None
            cloud = (w or {}).get("cloud_cover")
            item["cloud_cover_pct"] = cloud
            item["outcome"] = "cloud_or_smoke" if cloud is not None and cloud >= CLOUDY_PCT else "clear_no_fire"
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


async def build_fire_case(
    subject: dict[str, Any],
    place: dict[str, Any],
    regional: dict[str, Any],
    official: dict[str, Any],
    news: dict[str, Any],
    fusion: dict[str, Any],
    now: datetime | None = None,
    pending_streams: list[str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pending_streams = pending_streams or []
    now = now or datetime.now(timezone.utc)
    dets = sorted(subject["detections"], key=lambda d: _utc(d["acq_datetime"]))
    first, last = _utc(dets[0]["acq_datetime"]), _utc(dets[-1]["acq_datetime"])
    closes = first + timedelta(hours=CASE_WINDOW_HOURS)
    lat, lon = subject["lat"], subject["lon"]

    async def cloud() -> list[dict[str, Any]]:
        try:
            return await hourly_weather(lat, lon, (first - timedelta(days=1)).date(), max(now, closes).date())
        except ExternalServiceError:
            return []

    if overrides:
        overpasses, hourly, season = overrides["overpasses"], overrides["hourly"], overrides["season"]
    else:
        overpasses, hourly, season = await asyncio.gather(
            predict_passes(lat, lon, first - timedelta(minutes=30), max(closes, now + timedelta(hours=12)), first.date()),
            cloud(),
            burning_season(lat, lon, first),
        )
    window_start, window_end = first - timedelta(minutes=30), max(closes, now + timedelta(hours=12))
    overpasses = {**overpasses, "passes": [p for p in overpasses["passes"] if window_start <= p["time"] <= window_end]}
    passes = classify_passes(overpasses["passes"], dets, hourly, (lat, lon), subject.get("radius_km", 1.0), now)
    max_frp = max((float(d.get("frp") or 0) for d in dets), default=0.0)
    best_conf = max((float(d.get("confidence_pct") or 0) for d in dets), default=0.0)
    for p in passes:
        # How likely this pass was to see a fire like this one: time of day, view position and sensor eyesight.
        if p.get("local_solar_hour") is not None:
            p["detection_chance"] = round(pass_detection_chance(p["witness"], p["local_solar_hour"], max_frp, p.get("swath_position", "unknown")), 2)
    sat = case_fire_probability(passes, season, first, max_frp, best_conf)
    ballot = Ballot()

    # Trigger.
    w0 = witness_of(dets[0])
    ballot.add("trigger", WITNESS_LABEL.get(str(w0), dets[0]["sensor"]), f"First detection: {best_conf:.0f}% confidence, {float(dets[0].get('frp') or 0):.1f} MW. Case opened.", 1.0,
               {"not_a_fire": 1.0} if best_conf < 50 else {"not_a_fire": 0.3}, first)

    # Background facts.
    land = place.get("land_context") or {}
    land_use = set(land.get("land_use") or [])
    forests = land.get("forests") or []
    protected = land.get("protected_areas") or []
    if land_use & CROPLAND:
        ballot.add("background", "OpenStreetMap land use", f"Mapped as {', '.join(sorted(land_use & CROPLAND))}.", 0.6, {"agricultural_burn": 1.5}, kind="background")
    if forests or (land_use & WILDLAND):
        names = ", ".join(f["name"] for f in forests[:2]) or ", ".join(sorted(land_use & WILDLAND))
        ballot.add("background", "OpenStreetMap land cover", f"Inside forest or wildland ({names}).", 0.6, {"wildfire": 1.5, "controlled_burn": 0.3}, kind="background")
    if protected:
        ballot.add("background", "OpenStreetMap protected areas", f"Inside {protected[0]['name']}.", 0.6, {"wildfire": 0.8, "controlled_burn": 0.4}, kind="background")
    if land_use & {"industrial"}:
        ballot.add("background", "OpenStreetMap land use", "Mapped as industrial land.", 0.6, {"industrial_source": 1.2, "building_fire": 0.6}, kind="background")
    if land_use & {"residential"}:
        ballot.add("background", "OpenStreetMap land use", "Mapped as residential land.", 0.6, {"building_fire": 1.0}, kind="background")
    for h in (land.get("nearby_heat_sources") or [])[:3]:
        d = h.get("distance_km")
        if d is None:
            continue
        if h["type"] == "volcano" and d <= 10:
            ballot.add("background", "OpenStreetMap", f"Volcano '{h['name']}' {d} km away.", 0.7, {"volcanic": 3.0}, kind="background")
        elif h["type"] != "volcano" and d <= 2:
            ballot.add("background", "OpenStreetMap", f"{h['type'].replace('_', ' ').title()} '{h['name']}' {d} km away.", 0.7, {"industrial_source": 2.5}, kind="background")
    if season.get("status") == "ok":
        yrs, n = season["years_with_fire_within_5km"], season["years_checked"]
        spot = season["years_with_heat_within_1km"]
        if spot >= max(3, n - 1):
            ballot.add("background", "Burning calendar (MODIS archive)", f"Heat on this exact spot (within 1 km) in {spot} of {n} previous years at this time of year: typical of a fixed heat source.", 0.8, {"industrial_source": 2.0}, kind="background")
        if yrs >= max(2, math.ceil(n / 2)):
            votes = {"agricultural_burn": 1.5, "controlled_burn": 0.3} if (land_use & CROPLAND or not forests) else {"wildfire": 0.8, "agricultural_burn": 0.7, "controlled_burn": 0.5}
            ballot.add("background", "Burning calendar (MODIS archive)", f"Fires within 5 km in {yrs} of {n} previous years at this time of year: inside the local burning season.", 0.8, votes, kind="background")
        else:
            ballot.add("background", "Burning calendar (MODIS archive)", f"Fires within 5 km in only {yrs} of {n} previous years at this time of year: outside the usual burning season.", 0.8, {"wildfire": 0.4, "not_a_fire": 0.3}, kind="background")

    # Stream A.
    nights = {(_utc(d["acq_datetime"]) + timedelta(hours=lon / 15 - 12)).date() for d in dets if str(d.get("daynight", "")).upper() == "N"}
    span_km = max((haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a in dets[:100] for b in dets[:100]), default=0.0)
    behaviour = subject.get("behaviour") or {}
    for p in passes:
        if p["outcome"] in {"first_detection", "expected"} or p["time"] < first:
            continue
        rel = 0.9 if WITNESS_FAMILY[p["witness"]] == "VIIRS" else 0.7
        hours_after = (p["time"] - first).total_seconds() / 3600
        votes: dict[str, float] = {}
        if p["outcome"] in {"seen", "seen_stronger", "seen_weaker"}:
            votes = {c: 0.05 for c in FIRE_CATEGORIES + ["industrial_source"]}
        elif p["outcome"] == "spread":
            votes = {"wildfire": 1.5, "agricultural_burn": 0.3}
        elif p["outcome"] == "clear_no_fire":
            # A miss only counts as much as this pass could have seen the fire.
            sharp = min(1.0, p.get("detection_chance", 0.5) / 0.6)
            if hours_after <= 14 and len(dets) == 1:
                votes = {"not_a_fire": 1.5 * sharp, "agricultural_burn": 0.5, "controlled_burn": 0.3}
            else:
                votes = {"agricultural_burn": 0.3, "controlled_burn": 0.2}
        summary = (
            f"{p['label']}: {p['outcome_label'].lower()}"
            + (f" ({p.get('frp_mw')} MW)" if p.get("frp_mw") is not None else "")
            + (f", {p['swath_position']}" if p.get("swath_position") not in (None, "unknown") else "")
            + (f", cloud {p['cloud_cover_pct']:.0f}%" if p.get("cloud_cover_pct") is not None else "")
            + (f", {p['detection_chance']:.0%} chance to see this fire" if p.get("detection_chance") is not None else "")
            + "."
        )
        ballot.add("A", p["label"], summary, rel if p["outcome"] not in {"cloud_or_smoke", "not_covered"} else 0.0, votes, p["time"])
    if len(nights) >= 2 and span_km <= 1.5:
        ballot.add("A", "Polar passes", f"Heat at the same spot on {len(nights)} different nights with no movement.", 0.9, {"industrial_source": 2.0}, last)
    if behaviour.get("state") in {"Expanding", "Intensifying"}:
        votes = {"wildfire": 2.0 + (1.0 if forests or land_use & WILDLAND else 0.0)}
        ballot.add("A", "Fire event reconstruction", f"{behaviour['state']}: {' '.join(behaviour.get('reasons', [])[:1])}", 0.8, votes, last)
    duration_h = (last - first).total_seconds() / 3600
    if duration_h < 6 and any(p["outcome"] == "clear_no_fire" and p["time"] > last for p in passes):
        ballot.add("A", "Polar passes", f"Short burn: all detections within {duration_h:.1f} h, then no fire on a clear pass. Short fires often end before the next pass, so this is not proof of a false alarm.", 0.7, {"agricultural_burn": 1.0, "controlled_burn": 0.5}, last)

    # Stream B.
    geo = geostationary_stream(regional) if "B" not in pending_streams else {"status": "pending", "detail": "Waiting for the regional satellite check.", "review_links": []}
    if geo["status"] == "pending":
        pass
    elif geo["status"] == "seen":
        votes = {c: 0.5 for c in FIRE_CATEGORIES}
        if geo["duration_hours"] < 4:
            votes.update({"agricultural_burn": 1.5, "controlled_burn": 0.8})
        elif geo["duration_hours"] > 12 and (forests or land_use & WILDLAND):
            votes.update({"wildfire": 1.5})
        ballot.add("B", f"{geo['satellite']} geostationary", f"Seen {geo['observations']} times from {geo['started'][11:16]} to {geo['last_seen'][11:16]} UTC ({geo['duration_hours']} h).", 0.85, votes, _utc(geo["started"]))
    elif geo["status"] == "not_seen":
        ballot.add("B", f"{geo['satellite']} geostationary", "No geostationary heat at this spot (small fires are often below GOES sensitivity).", 0.6, {"not_a_fire": 0.8 if len(dets) == 1 else 0.2}, first)
    else:
        ballot.add("B", geo.get("satellite") or "Geostationary", geo["detail"], 0.0, None, first, kind="note")

    # Other independent platforms and Sentinel-2 review.
    for c in regional["checks"]:
        if c.get("status") == "corroborating" and "GOES" not in c["name"] and not c.get("geostationary"):
            ballot.add("B" if "Landsat" in c["name"] or "M3" in c["name"] or "EFFIS" in c["name"] else "A", c["name"], c.get("detail") or "Corroborating detection.", 0.85, {cat: 0.5 for cat in FIRE_CATEGORIES}, first)

    # Stream C.
    for m in official["matches"][:3]:
        cat = NEWS_CATEGORY.get(str(m.get("incident_type")))
        when = _utc(m["discovered"]) if m.get("discovered") else None
        ballot.add("C", m.get("source") or "Official source", f"'{m.get('title') or 'Incident'}' ({str(m.get('incident_type') or '').replace('_', ' ').lower()}), {m.get('distance_km')} km away.", 0.95, {cat: 3.0} if cat else {c: 0.6 for c in FIRE_CATEGORIES}, when, m.get("url"), kind="external")
    for a in [a for a in news["articles"] if a["relevance_score"] >= 55][:4]:
        cat = NEWS_CATEGORY.get(a["event_type"])
        rel = 0.5 + 0.5 * a["source_reliability_score"] / 100
        weight = 2.5 * a["relevance_score"] / 100
        when = _utc(a["published_at"]) if a.get("published_at") else None
        ballot.add("C", a["publication"] or a["domain"], f"News ({a['match_label'].lower()}): {a['headline']}", rel, {cat: weight} if cat else {c: weight / 4 for c in FIRE_CATEGORIES}, when, a.get("url"), kind="external")
    if "C" not in pending_streams and not news["articles"] and not official["matches"]:
        ballot.add("C", "News and official reports", "No matching report found. Small rural fires are rarely reported, so this is weak evidence.", 0.3, {"not_a_fire": 0.3, "agricultural_burn": 0.3}, now, kind="note")

    scores = ballot.scores()
    top, second = scores[0], scores[1]
    lead = top["raw_score"] - second["raw_score"]
    decided = top["raw_score"] > MIN_TOP_SCORE and lead >= MIN_LEAD
    reality, reality_basis = _reality(fusion, top["category"], decided, sat["probability"])
    now_label, now_basis = _now_state(passes, behaviour, last, now)

    if decided:
        kind_label, kind_note = top["label"], f"{top['label']} scores {top['score']}% and leads {second['label'].lower()} by {lead:.0f} points."
    elif reality in {"Confirmed fire", "Highly likely fire"}:
        kind_label, kind_note = "Unknown (fire confirmed, type uncertain)", f"Top category {top['label'].lower()} at {top['score']}% does not pass both rules (> {MIN_TOP_SCORE:.0f}% and a {MIN_LEAD:.0f}-point lead)."
    else:
        kind_label, kind_note = "Unknown (needs verification)", f"Top category {top['label'].lower()} at {top['score']}% does not pass both rules (> {MIN_TOP_SCORE:.0f}% and a {MIN_LEAD:.0f}-point lead)."

    future = [p for p in passes if p["outcome"] == "expected" and p["in_swath"]]
    looked_since = {p["witness"] for p in passes if p["time"] > first + timedelta(minutes=PASS_MATCH_MINUTES) and p["outcome"] not in {"expected", "not_covered"}}
    pending = sorted(set(overpasses["witnesses"]) - looked_since)
    closed = now >= closes or not pending
    lack_of_views = sum(1 for p in passes if p["outcome"] == "cloud_or_smoke")
    explanation = (
        f"{WITNESS_LABEL.get(str(w0), 'A satellite')} opened this case at {first.strftime('%H:%M')} UTC on {first.date().isoformat()}. "
        f"Is it real? {reality}: {reality_basis} "
        f"What kind? {kind_label}. {kind_note} "
        f"Now: {now_label}. {now_basis}"
        + (f" {lack_of_views} pass(es) were blocked by cloud or smoke, so the satellites saw less than usual." if lack_of_views else "")
        + ("" if closed else f" The answer is provisional until {closes.strftime('%H:%M')} UTC on {closes.date().isoformat()} or until every satellite has passed.")
    )
    items = sorted(ballot.items, key=lambda i: (i["kind"] != "background", i["time"] or ""))
    return {
        "case_id": subject.get("event_id") or f"HS-{lat:.3f}-{lon:.3f}-{first.strftime('%Y%m%d%H%M')}",
        "opened_at": _iso(first),
        "closes_at": _iso(closes),
        "status": "closed" if closed else "open",
        "provisional": not closed,
        "pending_witnesses": [WITNESS_LABEL[w] for w in pending],
        "answer": {
            "is_real": {"label": reality, "basis": reality_basis},
            "kind": {"category": top["category"] if decided else "unknown", "label": kind_label, "decided": decided, "basis": kind_note},
            "now": {"label": now_label, "basis": now_basis},
        },
        "category_scores": scores,
        "decision_rules": {"min_top_score": MIN_TOP_SCORE, "min_lead": MIN_LEAD, "top": top["category"], "top_score": top["score"], "lead": round(lead, 1), "passed": decided},
        "satellite_fire_probability": sat,
        "passes": [{**p, "time": _iso(p["time"])} for p in passes],
        "next_passes": [{"label": p["label"], "time": _iso(p["time"]), "swath_position": p["swath_position"]} for p in future[:4]],
        "overpass_method": overpasses["method"],
        "overpass_errors": overpasses["errors"],
        "geostationary": geo,
        "burning_season": season,
        "evidence_block": items,
        "explanation": explanation,
        "marker": {"kind": top["category"] if decided else "unknown", "reality": reality, "state": now_label, "provisional": not closed},
        "situations": {
            "spreading_fires": "Later passes are checked across the whole event area, not just the first point.",
            "short_fires": "A clear miss after a short burn is weighted as weak evidence, not proof of a false alarm.",
            "merged_alerts": f"{len(dets)} detection(s) linked into this one case.",
        },
        "streams": {
            "pending": pending_streams,
            "A": {"status": "done", "passes_observed": sum(1 for p in passes if p["outcome"] not in {"expected", "not_covered"}), "passes_expected": len(future)},
            "B": {"status": "pending" if "B" in pending_streams else geo["status"]},
            "C": {"status": "pending" if "C" in pending_streams else "done", "reports": len(official["matches"]) + sum(1 for a in news["articles"] if a["relevance_score"] >= 55)},
        },
        "score_note": "Category percentages are evidence scores that sum to 100. They are not calibrated probabilities until the system is tested on labelled fires.",
    }
