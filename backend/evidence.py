"""Fire Evidence: multi-source corroboration, evidence fusion and explanation.

Keeps four things separate throughout:
- observation: what MODIS/VIIRS actually recorded
- external evidence: what independent satellites, agencies and news report
- inference: the system's evidence status and score
- (forecast lives in forecast.py)

The System Evidence Score says how strongly available evidence supports the
fire interpretation. It is not a calibrated probability.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

from config import NEWS_API_KEY
from corroboration import official_evidence, regional_satellite_evidence
from geo import haversine_km, location_uncertainty_km
from geocode import geocode_place_name, reverse_geocode
from http_utils import ExternalServiceError, request_json
from nlp import extract, system_summary
from quality import sensor_family
from source_directory import source_reliability, sources_for_country


CACHE_TTL_SECONDS = 60 * 30
_EVIDENCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
FIRE_TYPES = {"WILDFIRE", "FOREST_FIRE", "UNKNOWN_THERMAL_EVENT", "DEFORESTATION_RELATED_BURNING", "LAND_CLEARING", "AGRICULTURAL_BURN", "CONTROLLED_BURN"}
NON_WILDFIRE_TYPES = {"FACTORY_FIRE", "BUILDING_FIRE", "INDUSTRIAL_HEAT_SOURCE", "GAS_FLARE", "VOLCANIC_ACTIVITY"}


# --- Subject -------------------------------------------------------------------------------


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def subject_from_hotspot(hotspot: dict[str, Any]) -> dict[str, Any]:
    t = _utc(hotspot["acq_datetime"])
    return {
        "kind": "hotspot",
        "lat": float(hotspot["lat"]),
        "lon": float(hotspot["lon"]),
        "t_start": t,
        "t_end": t,
        "radius_km": location_uncertainty_km(hotspot),
        "sensors": [hotspot["sensor"]],
        "detections": [hotspot],
    }


def subject_from_event(event: dict[str, Any]) -> dict[str, Any]:
    c = event["centroid"]
    radius = max((haversine_km(c["lat"], c["lon"], d["lat"], d["lon"]) + location_uncertainty_km(d) for d in event["detections"]), default=1.0)
    return {
        "kind": "event",
        "event_id": event["event_id"],
        "lat": c["lat"],
        "lon": c["lon"],
        "t_start": _utc(event["first_detection"]),
        "t_end": _utc(event["latest_detection"]),
        "radius_km": round(radius, 2),
        "sensors": event["sensors"],
        "detections": event["detections"],
        "behaviour": event.get("behaviour"),
    }


# --- Matching --------------------------------------------------------------------------------


def geographic_score(distance_km: float | None, admin_level: str | None) -> tuple[int, str]:
    if distance_km is not None:
        for limit, score in [(5, 100), (10, 90), (25, 75), (50, 55), (100, 35), (300, 15)]:
            if distance_km <= limit:
                return score, f"{distance_km:.0f} km from the satellite event"
        return 5, f"{distance_km:.0f} km away (likely a different event)"
    return {"village": (80, "same village/town named"), "district": (65, "same district named"), "state": (45, "same state/province named"), "country": (20, "only the country matches")}.get(
        admin_level or "", (10, "no location match")
    )


def temporal_score(published: datetime | None, t_start: datetime, t_end: datetime, event_dates: list[str]) -> tuple[int, str, float | None]:
    """Reports shortly after detection score highest; reports long before cannot describe it."""
    date_match = any(t_start.date() - timedelta(days=1) <= datetime.fromisoformat(d).date() <= t_end.date() + timedelta(days=1) for d in event_dates)
    if published is None:
        return (60 if date_match else 30), ("event date in text matches" if date_match else "publication time unknown"), None
    after = (published - t_end).total_seconds() / 3600
    before_start = (t_start - published).total_seconds() / 3600
    if published < t_start:
        score = 60 if before_start <= 6 else 30 if before_start <= 24 else 5
        label = f"published {before_start:.1f} h before first detection"
    elif published <= t_end:
        score, label = 100, "published while the event was being detected"
    else:
        score = next((s for lim, s in [(1, 100), (3, 92), (6, 85), (24, 70), (48, 50), (96, 30)] if after <= lim), 10)
        label = f"published {after:.1f} h after the latest detection"
    if date_match:
        score = min(100, score + 10)
        label += "; event date in text matches"
    return score, label, round((published - t_start).total_seconds() / 3600, 2)


def _parse_published(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        if len(text) >= 15 and text[:8].isdigit() and "T" in text:
            return datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return _utc(text)
    except ValueError:
        return None


# --- News -------------------------------------------------------------------------------------


def _gdelt_query(place: dict[str, Any]) -> str:
    names = [place.get(k) for k in ("village", "city", "district", "state")]
    names = [n for n in names if n and n.isascii()]
    country = place.get("country")
    terms = " OR ".join(f'"{n}"' for n in names[:3]) or (f'"{country}"' if country else "")
    return f"(wildfire OR \"forest fire\" OR fire OR blaze OR burning OR smoke) ({terms}) sourcelang:english" if terms else ""


async def _gdelt_articles(place: dict[str, Any], t_start: datetime, t_end: datetime) -> tuple[list[dict[str, Any]], str | None, str | None]:
    query = _gdelt_query(place)
    if not query:
        return [], None, "No named place to search for (open ocean or unmapped area)."
    start = (t_start - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    end = min(datetime.now(timezone.utc), t_end + timedelta(days=4)).strftime("%Y%m%d%H%M%S")
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={quote_plus(query)}&mode=artlist&format=json&maxrecords=50&startdatetime={start}&enddatetime={end}"
    try:
        data = await request_json(url, service="GDELT", ttl_seconds=1800, timeout=25, retries=2)
    except ExternalServiceError as exc:
        return [], url, str(exc)
    arts = []
    for a in (data or {}).get("articles", []):
        arts.append({"title": a.get("title", ""), "description": "", "url": a.get("url"), "domain": a.get("domain", ""), "publication": a.get("domain", ""), "published": a.get("seendate"), "provider": "GDELT"})
    return arts, url, None


async def _newsapi_articles(place: dict[str, Any], t_start: datetime, t_end: datetime, domains: list[str]) -> list[dict[str, Any]]:
    if not NEWS_API_KEY:
        return []
    location = place.get("village") or place.get("city") or place.get("district") or place.get("state") or place.get("country")
    if not location:
        return []
    try:
        data = await request_json(
            "https://newsapi.org/v2/everything",
            service="NewsAPI",
            params={
                "q": f'"{location}" AND (fire OR wildfire OR blaze OR smoke OR burning)',
                "searchIn": "title,description",
                "language": "en",
                "sortBy": "relevancy",
                "from": (t_start - timedelta(days=1)).date().isoformat(),
                "to": (t_end + timedelta(days=4)).date().isoformat(),
                "pageSize": 30,
                "apiKey": NEWS_API_KEY,
            },
            ttl_seconds=1800,
            retries=1,
        )
    except ExternalServiceError:
        return []
    out = []
    for a in (data or {}).get("articles", []):
        url = a.get("url") or ""
        out.append(
            {
                "title": a.get("title") or "",
                "description": a.get("description") or "",
                "url": url,
                "domain": url.split("/")[2] if url.count("/") >= 2 else "",
                "publication": (a.get("source") or {}).get("name", ""),
                "published": a.get("publishedAt"),
                "provider": "NewsAPI",
            }
        )
    return out


def _gazetteer(place: dict[str, Any]) -> list[tuple[str, str]]:
    names = []
    for key, level in [("village", "village"), ("city", "village"), ("local_name", "village"), ("district", "district"), ("state", "state"), ("country", "country")]:
        if place.get(key):
            names.append((place[key], level))
    for item in (place.get("land_context") or {}).get("protected_areas", []) + (place.get("land_context") or {}).get("forests", []):
        if item.get("name") and not item["name"].startswith("Unnamed"):
            names.append((item["name"], "village"))
    ns = place.get("nearest_settlement")
    if ns and ns.get("name"):
        names.append((ns["name"], "village"))
    return names


async def news_evidence(subject: dict[str, Any], place: dict[str, Any]) -> dict[str, Any]:
    country_code = place.get("country_code")
    domains = sources_for_country(country_code).get("news", [])
    (gdelt, gdelt_url, gdelt_error), newsapi = await asyncio.gather(_gdelt_articles(place, subject["t_start"], subject["t_end"]), _newsapi_articles(place, subject["t_start"], subject["t_end"], domains))
    gazetteer = _gazetteer(place)
    names = [n for n, _ in gazetteer]
    seen: set[str] = set()
    cards = []
    geocode_budget = 6
    for art in newsapi + gdelt:
        key = " ".join((art["title"] or "").lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        published = _parse_published(art["published"])
        facts = extract(f"{art['title']}. {art.get('description') or ''}", published, names)
        if not facts["is_fire_related"]:
            continue
        # Geographic match: geocode the most specific place the article names.
        admin_level = None
        for name, level in gazetteer:
            if name in facts["locations"]["gazetteer_matches"]:
                admin_level = level
                break
        distance = None
        located = None
        if admin_level == "village":
            ns = next(((n, lvl) for n, lvl in gazetteer if n in facts["locations"]["gazetteer_matches"]), None)
            if ns and place.get("nearest_settlement") and ns[0] == place["nearest_settlement"].get("name"):
                distance = place["nearest_settlement"]["distance_km"]
        candidates = facts["locations"]["other_place_mentions"]
        if distance is None and candidates and geocode_budget > 0:
            geocode_budget -= 1
            located = await geocode_place_name(candidates[0], country_code)
            if located:
                distance = round(haversine_km(subject["lat"], subject["lon"], located["lat"], located["lon"]), 1)
        geo_score, geo_label = geographic_score(distance, admin_level)
        t_score, t_label, hours_after = temporal_score(published, subject["t_start"], subject["t_end"], facts["dates_mentioned"])
        rel_score, rel_label = source_reliability(art["domain"], country_code)
        fire_score = 95 if facts["event_type"] in {"WILDFIRE", "FOREST_FIRE"} else 75 if facts["event_type"] in FIRE_TYPES else 35
        relevance = round(0.35 * geo_score + 0.25 * t_score + 0.25 * fire_score + 0.15 * rel_score)
        match = {"distance_km": distance, "hours_after_detection": hours_after}
        cards.append(
            {
                "headline": art["title"],
                "publication": art["publication"] or art["domain"],
                "domain": art["domain"],
                "provider": art["provider"],
                "published_at": published.isoformat() if published else None,
                "url": art["url"],
                "country": place.get("country"),
                "location_mentioned": (facts["locations"]["gazetteer_matches"] or facts["locations"]["other_place_mentions"] or [None])[0],
                "geocoded_location": located,
                "distance_km": distance,
                "event_type": facts["event_type"],
                "nlp": facts,
                "geographic_score": geo_score,
                "geographic_match": geo_label,
                "location_confidence": "high" if (distance is not None and distance <= 25) else "medium" if admin_level in {"village", "district"} else "low",
                "temporal_score": t_score,
                "temporal_match": t_label,
                "hours_after_detection": hours_after,
                "fire_event_score": fire_score,
                "source_reliability_score": rel_score,
                "source_reliability": rel_label,
                "relevance_score": relevance,
                "match_label": "Strong match" if relevance >= 75 else "Possible match" if relevance >= 55 else "Weak match",
                "system_summary": system_summary(facts, match),
                # Legacy field names used by older UI code.
                "location_score": geo_score,
                "time_score": t_score,
                "summary": system_summary(facts, match),
            }
        )
    cards.sort(key=lambda c: c["relevance_score"], reverse=True)
    return {
        "articles": cards[:12],
        "searched": {"gdelt_url": gdelt_url, "gdelt_error": gdelt_error, "newsapi_enabled": bool(NEWS_API_KEY), "preferred_outlets": domains},
        "note": "Only articles whose text describes a fire-type event are kept. Summaries are system-generated from extracted facts, not article text.",
    }


# --- Fusion -------------------------------------------------------------------------------------


def _satellite_component(subject: dict[str, Any], observation: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    dets = subject["detections"]
    best_conf = max(float(d.get("confidence_pct") or 0) for d in dets)
    max_frp = max((float(d.get("frp") or 0) for d in dets), default=0)
    night = any(str(d.get("daynight", "")).upper() == "N" for d in dets)
    hot = any((d.get("brightness_k") or 0) >= (330 if d["sensor"] == "modis" else 340) for d in dets)
    points = 0
    notes = []
    if best_conf >= 80:
        points += 7
        notes.append(f"high-confidence ({best_conf:.0f}%) detection")
    elif best_conf >= 50:
        points += 4
        notes.append(f"nominal-confidence ({best_conf:.0f}%) detection")
    if max_frp >= 30:
        points += 6
        notes.append(f"strong FRP ({max_frp:.0f} MW)")
    elif max_frp >= 10:
        points += 4
        notes.append(f"moderate FRP ({max_frp:.0f} MW)")
    if hot:
        points += 3
        notes.append("high brightness temperature")
    if night:
        points += 4
        notes.append("night-time detection (no sun-glint or solar-heated ground)")
    return min(points, 20), notes, {"best_confidence": best_conf, "max_frp": max_frp, "night": night, "high_brightness": hot}


def fuse(subject: dict[str, Any], place: dict[str, Any], regional: dict[str, Any], official: dict[str, Any], news: dict[str, Any]) -> dict[str, Any]:
    observation = {"sufficiency_score": None}
    sat_points, sat_notes, sat_facts = _satellite_component(subject, observation)
    families = {sensor_family(s) for s in subject["sensors"]}
    days = len({_utc(d["acq_datetime"]).date() for d in subject["detections"]})
    repeat_points = 0
    repeat_notes = []
    if len(subject["detections"]) >= 3:
        repeat_points += 4
        repeat_notes.append(f"{len(subject['detections'])} linked detections")
    if days >= 2:
        repeat_points += 2
        repeat_notes.append(f"detected on {days} days")
    if {"MODIS", "VIIRS"} <= families:
        repeat_points += 4
        repeat_notes.append("MODIS and VIIRS both detected it")

    regional_points = 20 if regional["geostationary_or_highres_match"] else 12 if regional["other_platform_match"] else 0
    official_match = official["has_official_match"]
    best_official = min((m.get("distance_km") or 99 for m in official["matches"]), default=None)
    official_points = 0
    if official_match:
        official_points = 25 if best_official is not None and best_official <= 15 else 15
    articles = news["articles"]
    best = articles[0] if articles else None
    news_points = 0
    if best:
        news_points = 10 if best["relevance_score"] >= 75 else 6 if best["relevance_score"] >= 55 else 2
    geo_best = max([a["geographic_score"] for a in articles[:3]] + ([100 if (best_official or 99) <= 15 else 60] if official_match else []), default=0)
    time_best = max([a["temporal_score"] for a in articles[:3]] + ([80] if official_match else []), default=0)
    geo_points = round(8 * geo_best / 100) if (articles or official_match) else 0
    time_points = round(7 * time_best / 100) if (articles or official_match) else 0
    components = [
        {"signal": "Satellite detection (confidence, FRP, brightness, day/night)", "points": sat_points, "max": 20, "notes": sat_notes},
        {"signal": "Repeat detections and MODIS/VIIRS sensor agreement", "points": min(repeat_points, 10), "max": 10, "notes": repeat_notes},
        {"signal": "Regional / independent satellite confirmation", "points": regional_points, "max": 20, "notes": regional["corroborating_sources"]},
        {"signal": "Government / official report", "points": official_points, "max": 25, "notes": [m.get("title") or "" for m in official["matches"][:3]]},
        {"signal": "Local news (NLP-classified, source reliability weighted)", "points": news_points, "max": 10, "notes": [best["headline"]] if best else []},
        {"signal": "Geographic match of external evidence", "points": geo_points, "max": 8, "notes": [best["geographic_match"]] if best else []},
        {"signal": "Temporal match of external evidence", "points": time_points, "max": 7, "notes": [best["temporal_match"]] if best else []},
    ]
    score = min(100, sum(c["points"] for c in components))

    heat_sources = (place.get("land_context") or {}).get("nearby_heat_sources") or []
    close_heat = [h for h in heat_sources if h.get("distance_km") is not None and (h["distance_km"] <= 2 or (h["type"] == "volcano" and h["distance_km"] <= 10))]
    non_wildfire_reports = [a for a in articles[:5] if a["event_type"] in NON_WILDFIRE_TYPES and a["relevance_score"] >= 55]
    managed_burn = official["controlled_burn_reported"] or any(a["event_type"] in {"CONTROLLED_BURN", "AGRICULTURAL_BURN"} and a["relevance_score"] >= 55 for a in articles[:5])
    strong_sat = sat_points >= 11
    external = official_match or regional_points >= 12 or news_points >= 6

    if official_match and best_official is not None and best_official <= 15 and official_points == 25 and not official["controlled_burn_reported"] and strong_sat:
        status = "Confirmed Fire" if (regional_points or news_points >= 6) else "Externally Corroborated Fire Event"
    elif official_match and (regional_points or news_points >= 6):
        status = "Strong Multi-Source Fire Evidence"
    elif official_match or (regional_points >= 12 and news_points >= 6):
        status = "Externally Corroborated Fire Event"
    elif (close_heat or non_wildfire_reports) and not official_match:
        status = "Likely Non-Fire Thermal Source"
    elif score >= 45 and strong_sat and (regional_points or repeat_points >= 6):
        status = "Highly Likely Fire"
    elif sat_points < 8 and repeat_points < 4 and not external:
        status = "Insufficient Evidence"
    elif strong_sat and not external:
        status = "No External Corroboration Yet"
    else:
        status = "Possible Fire / Needs More Evidence"

    if managed_burn and status not in {"Likely Non-Fire Thermal Source"}:
        fire_type_note = "Evidence points to a managed burn (prescribed/controlled or agricultural), which is still real combustion."
    else:
        fire_type_note = None

    uncertainty = []
    if not official_match:
        uncertainty.append("No official government confirmation found by the connected feeds.")
    if not articles:
        uncertainty.append("No matching news report found yet (local coverage often lags or is absent for small fires).")
    quality = subject.get("observation_quality") or {}
    sufficiency = quality.get("observation_sufficiency_score")
    if sufficiency is not None and sufficiency < 50:
        uncertainty.append(
            f"Observation sufficiency is only {sufficiency}/100 (cloud cover {quality.get('recent_cloud_cover_pct')}%), so missing corroboration or fewer detections may reflect obscured views rather than absence of fire."
        )
    unavailable = [c["name"] for c in regional["checks"] + official["checks"] if c.get("status") == "unavailable"]
    if unavailable:
        uncertainty.append("Could not be checked right now (source unavailable or rate-limited): " + "; ".join(unavailable) + ". Refresh later.")
    if not regional["corroborating_sources"] and any(c.get("status") == "no_match" for c in regional["checks"]):
        uncertainty.append("No independent satellite detection matched; small or cloud-covered fires are often missed.")
    if close_heat:
        uncertainty.append("Known non-fire heat source nearby: " + ", ".join(f"{h['name']} ({h['type'].replace('_', ' ')}, {h['distance_km']} km)" for h in close_heat[:3]) + ".")
    for a in non_wildfire_reports[:2]:
        uncertainty.append(f"A matched report describes a {a['event_type'].replace('_', ' ').lower()} rather than a vegetation fire.")

    if status == "Insufficient Evidence" and sufficiency is not None and sufficiency < 50:
        status_note = "Low observation sufficiency: re-check after the next clear overpass."
    else:
        status_note = None
    return {
        "final_status": status,
        "status_note": status_note,
        "observation_sufficiency": sufficiency,
        "system_evidence_score": score,
        "score_note": "Evidence strength on a 0-100 scale. It is not a probability of fire, because the weights are expert-set and have not been calibrated against labelled outcomes.",
        "components": components,
        "fire_type_note": fire_type_note,
        "uncertainty": uncertainty,
        "explanation": explain(subject, sat_facts, families, regional, official, news, status, close_heat),
        "confirmed_label_policy": "'Confirmed Fire' is used only when an authoritative incident report matches within 15 km and in time, with no report of a controlled burn.",
        # Legacy fields.
        "why": [n for c in components for n in c["notes"] if n][:8],
        "ai_analysis": "System interpretation computed from the listed components. It is rule-based, transparent and uncalibrated.",
    }


def explain(subject, sat_facts, families, regional, official, news, status, close_heat) -> str:
    dets = subject["detections"]
    first = dets[0]
    sentences = []
    conf = "high-confidence" if sat_facts["best_confidence"] >= 80 else "nominal-confidence" if sat_facts["best_confidence"] >= 50 else "low-confidence"
    timing = "nighttime" if sat_facts["night"] else "daytime"
    lead = sensor_family(first["sensor"])
    sentences.append(f"{lead} detected a {conf} {timing} thermal anomaly (peak FRP {sat_facts['max_frp']:.0f} MW).")
    if subject["kind"] == "event" and len(dets) > 1:
        other = families - {lead}
        extra = f" {', '.join(sorted(other))} also detected activity in the same event." if other else ""
        sentences.append(f"It is linked to {len(dets)} detections over {max(1, len({_utc(d['acq_datetime']).date() for d in dets}))} day(s).{extra}")
    for check in regional["checks"]:
        if check.get("status") == "corroborating":
            sentences.append(f"{check['name']}: {check['detail']}")
    arts = [a for a in news["articles"] if a["relevance_score"] >= 55]
    if arts:
        a = arts[0]
        dist = f" within {a['distance_km']:.0f} km of the satellite event" if a.get("distance_km") is not None else ""
        when = f" The first matching report appeared {abs(a['hours_after_detection']) * 60:.0f} minutes {'after' if a['hours_after_detection'] >= 0 else 'before'} the detection." if a.get("hours_after_detection") is not None and abs(a["hours_after_detection"]) < 3 else f" The best match was {a['temporal_match']}."
        sentences.append(f"{len(arts)} news report(s) describe a {a['event_type'].replace('_', ' ').lower()}{dist}.{when}")
    else:
        sentences.append("No matching local news report has been found.")
    if official["has_official_match"]:
        m = official["matches"][0]
        sentences.append(f"An official source lists '{m.get('title')}' {m.get('distance_km')} km away ({(m.get('incident_type') or '').replace('_', ' ').lower()}).")
    else:
        sentences.append("No official government confirmation is currently available from the connected feeds.")
    if close_heat:
        sentences.append(f"A mapped {close_heat[0]['type'].replace('_', ' ')} lies {close_heat[0]['distance_km']} km away, which can produce non-fire heat signals.")
    sentences.append(f"Overall status: {status}.")
    return " ".join(sentences)


# --- Orchestration --------------------------------------------------------------------------------


def _observation_block(subject: dict[str, Any]) -> dict[str, Any]:
    dets = subject["detections"]
    families = sorted({sensor_family(d["sensor"]) for d in dets})
    return {
        "detections": dets[:50],
        "sensor_families": families,
        "sensor_agreement": "MODIS and VIIRS both detected" if {"MODIS", "VIIRS"} <= set(families) else f"{families[0]} only" if families else "none",
        "location_uncertainty_km": subject["radius_km"],
        "provenance": {
            "data_source": "NASA FIRMS active fire (MODIS C6.1 MCD14, VIIRS 375 m VNP14IMG/VJ114IMG/VJ214IMG)",
            "sources": sorted({d.get("source") or d["sensor"] for d in dets}),
            "processing": "Confidence-filtered (>=30%), footprint from FIRMS scan/track, spatio-temporal event linking.",
        },
    }


async def build_evidence(subject: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    key = f"{subject['kind']}:{subject.get('event_id') or ''}:{subject['lat']:.4f}:{subject['lon']:.4f}:{subject['t_start'].isoformat()}:{subject['t_end'].isoformat()}:{len(subject['detections'])}"
    cached = _EVIDENCE_CACHE.get(key)
    if cached and not refresh and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        return {**cached[1], "cache": {"hit": True, "ttl_seconds": CACHE_TTL_SECONDS}}

    place = await reverse_geocode(subject["lat"], subject["lon"])
    regional, official, news = await asyncio.gather(regional_satellite_evidence(subject, place), official_evidence(subject, place), news_evidence(subject, place))
    fusion = fuse(subject, place, regional, official, news)
    stages = [
        {"name": "Satellite observation", "status": "completed", "detail": f"{len(subject['detections'])} detection(s)"},
        {"name": "Reverse geocoding", "status": "completed" if place.get("precision") == "osm_address" else "partial", "detail": place.get("display_name") or place.get("country") or "no named place"},
        {"name": "Regional satellite verification", "status": "completed", "detail": f"{len(regional['corroborating_sources'])} corroborating of {sum(1 for c in regional['checks'] if c['kind'] != 'manual_review')} automated checks"},
        {"name": "Government source verification", "status": "completed", "detail": f"{len(official['matches'])} matching official report(s)"},
        {"name": "News collection + NLP", "status": "completed", "detail": f"{len(news['articles'])} fire-related report(s)"},
        {"name": "Geographic and temporal matching", "status": "completed"},
        {"name": "Evidence fusion", "status": "completed", "detail": f"{fusion['system_evidence_score']}/100"},
    ]
    result = {
        "subject": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in subject.items() if k not in {"detections", "behaviour"}},
        "observation": _observation_block(subject),
        "place": place,
        "stages": stages,
        "external_evidence": {"regional_satellite": regional, "official": official, "news": news},
        "inference": fusion,
        "source_transparency": {
            "original_sources": "Headline, outlet, link and publication time come from the source.",
            "system_generated": "Summaries, event classifications, distances and match scores are generated by this system.",
            "system_interpretation": "Evidence status and score are the system's interpretation; they are not agency confirmations.",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache": {"hit": False, "ttl_seconds": CACHE_TTL_SECONDS},
    }
    _EVIDENCE_CACHE[key] = (time.time(), result)
    return result


async def build_hotspot_evidence(hotspot: Any, refresh: bool = False) -> dict[str, Any]:
    row = hotspot.model_dump() if hasattr(hotspot, "model_dump") else dict(hotspot)
    return await build_evidence(subject_from_hotspot(row), refresh)
