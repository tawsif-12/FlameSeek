"""Scripted demo fires for walkthroughs and videos: three complete Fire Cases in Bangladesh.

Each scenario is one coherent story. A fire-power curve and a cloud curve are sampled at
realistic overpass times of Terra, Aqua, Suomi NPP, NOAA-20 and NOAA-21, which yields the
detections shown on the globe. The same schedule, plus a scripted geostationary timeline,
official report, news items, place and land-use facts, feeds the Fire Case, so every field
of the case is filled and consistent, with no calls to external services.

Scenarios are anchored to the current local day (fires start "yesterday"), so times stay
stable while a demo is being recorded. Everything here is synthetic: the outlets, reports
and incident numbers are invented and results carry `demo_scenario`.

Injection points:
- `firms_client.fetch_recent_hotspots` appends `dhaka_demo_hotspots()` when the area covers Bangladesh.
- `evidence.build_evidence` uses `scenario_for()` / `scenario_evidence()` for demo events.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from geo import haversine_km
from witness import SWATH_KM, WITNESS_FAMILY, WITNESS_LABEL, WITNESSES, nominal_hours


BANGLADESH_BBOX = (88.0, 20.5, 92.7, 26.7)
SCENARIO_MATCH_KM = 8.0
SATELLITE_CODE = {"terra": "Terra", "aqua": "Aqua", "snpp": "N", "noaa20": "N20", "noaa21": "N21"}
SENSOR = {"terra": "modis", "aqua": "modis", "snpp": "viirs_snpp", "noaa20": "viirs_noaa20", "noaa21": "viirs_noaa21"}
SOURCE = {"modis": "MODIS_NRT", "viirs_snpp": "VIIRS_SNPP_NRT", "viirs_noaa20": "VIIRS_NOAA20_NRT", "viirs_noaa21": "VIIRS_NOAA21_NRT"}
# NOAA-21 flies about a quarter orbit from Suomi NPP.
WITNESS_OFFSET_H = {"noaa21": 0.42}
MIN_FRP_SEEN = {"MODIS": 12.0, "VIIRS": 2.0}

# Fire-power curve: (hours since ignition, MW); linear in between, 0 before and after `burn_hours`.
SCENARIOS: list[dict[str, Any]] = [
    {
        "key": "ashulia_factory",
        "label": "Ashulia DEPZ garment factory fire (Dhaka)",
        "lat": 23.8835,
        "lon": 90.3345,
        "seed": 11,
        "ignition": (-1, 11.4),
        "burn_hours": None,
        "frp_curve": [(0, 14), (3, 85), (9.5, 188), (15, 126), (22, 64), (30, 28), (48, 9)],
        "radius_km": [(0, 0.15), (10, 0.45), (48, 0.45)],
        "cloud": [(0, 28), (9, 35), (11, 84), (13, 40), (26, 22), (48, 30)],
        "place": {
            "country": "Bangladesh", "country_code": "BD", "state": "Dhaka Division", "district": "Dhaka District", "city": "Savar", "village": "Ashulia",
            "local_name": "Dhaka Export Processing Zone", "display_name": "Dhaka Export Processing Zone, Ashulia, Savar, Dhaka District, Dhaka Division, Bangladesh",
            "nearest_settlement": {"name": "Ashulia", "type": "town", "distance_km": 1.1},
            "land_context": {"protected_areas": [], "forests": [], "land_use": ["industrial"], "nearby_heat_sources": []},
        },
        "season": {"years_with_fire_within_5km": 1, "years_with_heat_within_1km": 0, "detections": [0, 0, 2, 0, 0]},
        "geostationary": {"start_h": 0.4, "end_h": None, "every_min": 10},
        "official": {
            "after_h": 1.1, "distance_km": 0.6, "incident_type": "BUILDING_FIRE", "agency": "Fire Service and Civil Defence control room (demo)",
            "title": "Fire at knit garment factory, DEPZ Ashulia: 12 units deployed",
        },
        "news": [
            {"after_h": 2.3, "distance_km": 0.8, "publication": "Dhaka Metro Post (demo)", "domain": "dhakametropost.example",
             "title": "Massive fire at garment factory in Ashulia export zone",
             "description": "A fire broke out at a knit garment factory in the Dhaka Export Processing Zone at Ashulia on the outskirts of Dhaka. Twelve firefighting units were working to control the blaze and no casualties were reported. Officials suspect an electrical short circuit in the fabric warehouse."},
            {"after_h": 7.5, "distance_km": 1.2, "publication": "Savar Courier (demo)", "domain": "savarcourier.example",
             "title": "Ashulia factory fire still burning after seven hours, warehouse gutted",
             "description": "The factory fire in Ashulia continued into the night as stored yarn and fabric kept burning. The fire service said the blaze was confined to one warehouse building near the Dhaka-Ashulia highway."},
        ],
    },
    {
        "key": "bogura_straw",
        "label": "Bogura paddy-straw burning (Shibganj)",
        "lat": 24.9620,
        "lon": 89.3320,
        "seed": 23,
        "ignition": (-1, 12.1),
        "burn_hours": 3.2,
        "frp_curve": [(0, 5), (0.8, 13), (1.6, 15), (2.4, 9), (3.2, 2)],
        "radius_km": [(0, 0.3), (3.2, 0.7)],
        "cloud": [(0, 18), (6, 25), (14, 30), (30, 20), (48, 26)],
        "place": {
            "country": "Bangladesh", "country_code": "BD", "state": "Rajshahi Division", "district": "Bogura District", "city": "Shibganj", "village": "Mokamtala",
            "local_name": "Mokamtala", "display_name": "Mokamtala, Shibganj, Bogura District, Rajshahi Division, Bangladesh",
            "nearest_settlement": {"name": "Mokamtala", "type": "village", "distance_km": 1.8},
            "land_context": {"protected_areas": [], "forests": [], "land_use": ["farmland"], "nearby_heat_sources": []},
        },
        "season": {"years_with_fire_within_5km": 5, "years_with_heat_within_1km": 1, "detections": [4, 7, 3, 6, 5]},
        "geostationary": {"start_h": 0.15, "end_h": 3.25, "every_min": 10},
        "official": None,
        "news": [
            {"after_h": 5.6, "distance_km": 3.0, "publication": "Uttarbanga Barta (demo)", "domain": "uttarbangabarta.example",
             "title": "Farmers burn paddy straw in Shibganj fields, smoke covers highway",
             "description": "Farmers in Mokamtala of Shibganj in Bogura were burning paddy straw and crop residue after the harvest on Thursday afternoon. Smoke from the stubble burning drifted over the Bogura-Rangpur highway for about three hours, agriculture officials said."},
        ],
    },
    {
        "key": "sundarbans_forest",
        "label": "Sundarbans forest fire (Chandpai range, Bagerhat)",
        "lat": 22.3180,
        "lon": 89.7460,
        "seed": 37,
        "ignition": (-1, 9.6),
        "burn_hours": None,
        "frp_curve": [(0, 18), (4, 46), (10, 72), (16, 118), (24, 205), (30, 262), (48, 310)],
        "radius_km": [(0, 0.3), (10, 0.9), (24, 1.9), (48, 3.2)],
        "cloud": [(0, 35), (7, 48), (12, 88), (15, 52), (22, 30), (27, 76), (29, 34), (48, 40)],
        "place": {
            "country": "Bangladesh", "country_code": "BD", "state": "Khulna Division", "district": "Bagerhat District", "city": "Morrelganj", "village": "Amurbunia",
            "local_name": "Chandpai Range", "display_name": "Chandpai Range, Sundarbans East, Morrelganj, Bagerhat District, Khulna Division, Bangladesh",
            "nearest_settlement": {"name": "Amurbunia", "type": "village", "distance_km": 3.4},
            "land_context": {
                "protected_areas": [{"name": "Sundarbans East Wildlife Sanctuary", "protect_class": "4", "designation": "Wildlife Sanctuary"}],
                "forests": [{"name": "Sundarbans Reserved Forest"}],
                "land_use": ["forest", "wetland"],
                "nearby_heat_sources": [],
            },
        },
        "season": {"years_with_fire_within_5km": 2, "years_with_heat_within_1km": 0, "detections": [0, 3, 0, 0, 5]},
        "geostationary": {"start_h": 1.2, "end_h": None, "every_min": 10},
        "official": {
            "after_h": 3.4, "distance_km": 1.5, "incident_type": "WILDFIRE", "agency": "Forest Department, Sundarbans East Division (demo)",
            "title": "Forest fire in Chandpai range near Amurbunia patrol post",
        },
        "news": [
            {"after_h": 5.2, "distance_km": 2.1, "publication": "Khulna Coast Journal (demo)", "domain": "khulnacoastjournal.example",
             "title": "Forest fire breaks out in Sundarbans' Chandpai range",
             "description": "A forest fire broke out in the Chandpai range of the Sundarbans in Bagerhat. Forest Department staff and villagers of Amurbunia were cutting a fire line because the nearest water source is about two kilometres away. The cause is not yet known."},
            {"after_h": 21.0, "distance_km": 2.6, "publication": "Bagerhat Dispatch (demo)", "domain": "bagerhatdispatch.example",
             "title": "Sundarbans fire spreads over more forest on second day",
             "description": "The forest fire in the Sundarbans spread to a wider area of the Chandpai range on Friday. Fire service units from Morrelganj and Mongla joined the Forest Department as the wildfire moved through dry undergrowth."},
        ],
    },
]


def _interp(curve: list[tuple[float, float]], x: float) -> float:
    if x <= curve[0][0]:
        return curve[0][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return curve[-1][1]


def _local_midnight(now: datetime, lon: float) -> datetime:
    """UTC time of today's local-solar midnight at this longitude."""
    local = now + timedelta(hours=lon / 15)
    return datetime(local.year, local.month, local.day, tzinfo=timezone.utc) - timedelta(hours=lon / 15)


def ignition_time(sc: dict[str, Any], now: datetime) -> datetime:
    day, hour = sc["ignition"]
    return _local_midnight(now, sc["lon"]) + timedelta(days=day, hours=hour)


def frp_at(sc: dict[str, Any], t: datetime, now: datetime) -> float:
    h = (t - ignition_time(sc, now)).total_seconds() / 3600
    if h < 0 or (sc["burn_hours"] is not None and h > sc["burn_hours"]):
        return 0.0
    return _interp(sc["frp_curve"], h)


def cloud_at(sc: dict[str, Any], t: datetime, now: datetime) -> float:
    h = (t - ignition_time(sc, now)).total_seconds() / 3600
    return round(_interp(sc["cloud"], max(0.0, h)), 0)


def scenario_passes(sc: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """Overpasses of every witness from two days ago to 14 h ahead, in predict_passes format."""
    lon = sc["lon"]
    midnight = _local_midnight(now, lon)
    out = []
    for day in range(-2, 2):
        date = (midnight + timedelta(days=day, hours=lon / 15)).date()
        for w in WITNESSES:
            for k, hour in enumerate(nominal_hours(w, date)):
                rnd = random.Random(f"{sc['seed']}-{w}-{date.isoformat()}-{k}")
                local_hour = (hour + WITNESS_OFFSET_H.get(w, 0.0) + rnd.uniform(-0.3, 0.3)) % 24
                when = (midnight + timedelta(days=day, hours=local_hour)).replace(second=0, microsecond=0)
                if not (midnight - timedelta(days=2) <= when <= now + timedelta(hours=14)):
                    continue
                half = SWATH_KM[w] / 2
                # MODIS swaths leave gaps at this latitude: about one pass in five misses the spot.
                off = rnd.uniform(0, half * (1.22 if WITNESS_FAMILY[w] == "MODIS" else 0.98))
                frac = off / half
                out.append(
                    {
                        "witness": w,
                        "label": WITNESS_LABEL[w],
                        "time": when,
                        "off_nadir_km": round(off, 1),
                        "in_swath": frac <= 1.0,
                        "coverage_probability": 1.0 if frac <= 1.0 else 0.0,
                        "swath_position": "near nadir" if frac < 0.35 else "mid swath" if frac < 0.75 else "swath edge",
                        "local_solar_hour": round(local_hour, 2),
                        "method": "nominal overpass schedule",
                    }
                )
    return sorted(out, key=lambda p: p["time"])


def _detections(sc: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    rows = []
    ignition = ignition_time(sc, now)
    for p in scenario_passes(sc, now):
        if p["time"] > now or not p["in_swath"] or cloud_at(sc, p["time"], now) >= 70:
            continue
        frp = frp_at(sc, p["time"], now)
        family = WITNESS_FAMILY[p["witness"]]
        edge = 2.0 if p["swath_position"] == "swath edge" else 1.0
        if frp < MIN_FRP_SEEN[family] * (edge if family == "MODIS" else 1.0):
            continue
        rnd = random.Random(f"{sc['seed']}-det-{p['witness']}-{p['time'].isoformat()}")
        hours = (p["time"] - ignition).total_seconds() / 3600
        radius = _interp(sc["radius_km"], hours)
        if family == "VIIRS":
            n = max(2, min(7, round(frp / 30) + 2))
            pixel = {"near nadir": (0.39, 0.36), "mid swath": (0.46, 0.41), "swath edge": (0.62, 0.58)}[p["swath_position"]]
            total = frp * rnd.uniform(0.9, 1.1)
        else:
            n = 1 if frp < 60 else 2
            pixel = {"near nadir": (1.0, 1.0), "mid swath": (1.5, 1.2), "swath edge": (3.1, 1.7)}[p["swath_position"]]
            total = frp * rnd.uniform(1.0, 1.25)
        shares = [rnd.uniform(0.6, 1.4) for _ in range(n)]
        solar_hour = p["local_solar_hour"]
        for share in shares:
            f = total * share / sum(shares)
            bearing, dist = rnd.uniform(0, 6.283), radius * rnd.uniform(0.1, 1.0)
            lat = sc["lat"] + dist * math.cos(bearing) / 111.32
            lon = sc["lon"] + dist * math.sin(bearing) / (111.32 * math.cos(math.radians(sc["lat"])))
            night = not (6 <= solar_hour < 18)
            rows.append(
                {
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "acq_datetime": p["time"],
                    "confidence_pct": (90.0 if f >= 8 else 60.0) if family == "VIIRS" else round(min(100.0, 62 + f * 0.35 + rnd.uniform(-6, 6)), 0),
                    "frp": round(f, 2),
                    "sensor": SENSOR[p["witness"]],
                    "satellite": SATELLITE_CODE[p["witness"]],
                    "daynight": "N" if night else "D",
                    "scan_km": pixel[0],
                    "track_km": pixel[1],
                    "brightness_k": round((305 if night else 322) + 9 * math.log1p(f) + rnd.uniform(-3, 6), 1),
                    "brightness_2_k": round((287 if night else 296) + rnd.uniform(-3, 5), 1),
                    "version": "2.0NRT" if family == "VIIRS" else "6.1NRT",
                    "fire_type": None,
                    "source": SOURCE[SENSOR[p["witness"]]],
                    "place_hint": sc["label"],
                }
            )
    return rows


def dhaka_demo_hotspots(now: datetime | None = None) -> list[dict[str, Any]]:
    """Detections of the three scripted Bangladesh fires, at realistic overpass times."""
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    return [row for sc in SCENARIOS for row in _detections(sc, now)]


def bbox_covers_dhaka(bbox: tuple[float, float, float, float] | None) -> bool:
    """Whether the requested area contains any demo scenario (the whole world does)."""
    if bbox is None:
        return True
    west, south, east, north = bbox
    return any(west <= sc["lon"] <= east and south <= sc["lat"] <= north for sc in SCENARIOS)


# --- Fire Case evidence for a demo event -----------------------------------------------------------


def scenario_for(subject: dict[str, Any]) -> dict[str, Any] | None:
    if not any(d.get("place_hint") for d in subject.get("detections", [])):
        return None
    best = min(SCENARIOS, key=lambda sc: haversine_km(subject["lat"], subject["lon"], sc["lat"], sc["lon"]))
    return best if haversine_km(subject["lat"], subject["lon"], best["lat"], best["lon"]) <= SCENARIO_MATCH_KM else None


def _iso(t: datetime) -> str:
    return t.isoformat()


def scenario_evidence(sc: dict[str, Any], subject: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Everything the Fire Case needs for this scenario, shaped like the live evidence streams."""
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    ignition = ignition_time(sc, now)
    first = subject["t_start"]
    lat, lon = sc["lat"], sc["lon"]

    place = {
        **sc["place"],
        "coordinates": {"lat": subject["lat"], "lon": subject["lon"]},
        "precision": "osm_address",
        "source": "OpenStreetMap Nominatim",
        "admin_level_1": sc["place"]["state"],
        "admin_level_2": sc["place"]["district"],
        "locality": sc["place"]["village"],
    }
    place["land_context"] = {**sc["place"]["land_context"], "source": "OpenStreetMap via Overpass (mapped polygons only; unmapped land shows as empty)"}

    passes = scenario_passes(sc, now)
    start_hour = (first - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    hourly = []
    t = start_hour
    while t <= now + timedelta(hours=15):
        hourly.append({"time": t.strftime("%Y-%m-%dT%H:00"), "cloud_cover": cloud_at(sc, t + timedelta(minutes=30), now)})
        t += timedelta(hours=1)

    years = [first.year - k for k in range(1, 6)]
    season = {
        "status": "ok",
        "years_checked": 5,
        "years_with_fire_within_5km": sc["season"]["years_with_fire_within_5km"],
        "years_with_heat_within_1km": sc["season"]["years_with_heat_within_1km"],
        "detections_by_year": {str(y): n for y, n in zip(years, sc["season"]["detections"])},
        "window": f"same date +/-15 days in {', '.join(str(y) for y in years)}",
        "note": "MODIS detections from the FIRMS archive (consistent-record sensitivity).",
    }

    # Stream B: Himawari-9 watches Bangladesh every 10 minutes.
    geo = sc["geostationary"]
    g_start = ignition + timedelta(hours=geo["start_h"])
    g_end = min(now, ignition + timedelta(hours=geo["end_h"])) if geo["end_h"] is not None else now - timedelta(minutes=25)
    matches = []
    t = g_start.replace(minute=g_start.minute // 10 * 10, second=0, microsecond=0)
    while t <= g_end:
        if cloud_at(sc, t, now) < 80:
            matches.append({"acq_datetime": t, "lat": lat, "lon": lon, "sensor": "himawari", "distance_km": 0.9, "time_gap_hours": 0.0})
        t += timedelta(minutes=geo["every_min"])
    own = set(subject.get("sensors", []))
    others = [s for s in ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"] if s not in own]
    checks = [
        {
            "name": "Other polar-orbiting platforms (FIRMS)", "kind": "automated", "sensors_checked": others,
            "status": "not_applicable" if not others else "no_match",
            "detail": "All MODIS and VIIRS platforms already contribute to this event; cross-sensor agreement is reported under observation quality." if not others else f"No detections from {', '.join(others)} within 5 km and 12 h (small, short or cloud-obscured fires are often missed).",
        },
        {
            "name": "Himawari-9 AHI fire product (JMA)", "kind": "automated", "geostationary": True, "satellite": "Himawari-9",
            "status": "corroborating" if matches else "no_match", "independent": True, "matches": matches,
            "detail": f"{len(matches)} ten-minute observations with heat within 2 km of this spot." if matches else "No geostationary heat at this spot.",
        },
        {
            "name": "Sentinel-2 L2A (Copernicus, via Earth Search STAC)", "kind": "imagery", "status": "review_available",
            "scenes": [{"id": f"S2B_45QZG_{(first + timedelta(days=1)).strftime('%Y%m%d')}_0_L2A", "datetime": _iso((first + timedelta(days=1)).replace(hour=4, minute=37)), "cloud_cover_pct": 21.4, "hours_from_detection": 21.0, "thumbnail": None}],
            "review_url": f"https://browser.dataspace.copernicus.eu/?zoom=13&lat={lat:.5f}&lng={lon:.5f}&datasetId=S2_L2A_CDAS&layerId=3_SWIR",
            "detail": "1 scene(s) with <=60% cloud within +/-5 days. SWIR composites show active fire and burn scars for visual confirmation; this is not an automatic detection.",
        },
        {
            "name": "NASA Worldview", "kind": "manual_review", "status": "review_link",
            "detail": "True-colour MODIS/VIIRS imagery for smoke plumes and burn scars on the detection date.",
            "review_url": f"https://worldview.earthdata.nasa.gov/?v={lon - 0.35:.4f},{lat - 0.35:.4f},{lon + 0.35:.4f},{lat + 0.35:.4f}&l=VIIRS_NOAA20_CorrectedReflectance_TrueColor,VIIRS_NOAA20_Thermal_Anomalies_375m_All,Reference_Labels_15m&t={first.date().isoformat()}",
        },
    ]
    regional = {
        "checks": checks,
        "corroborating_sources": [c["name"] for c in checks if c["status"] == "corroborating"],
        "geostationary_or_highres_match": bool(matches),
        "other_platform_match": False,
    }

    off = sc["official"]
    official_matches = []
    if off and ignition + timedelta(hours=off["after_h"]) <= now:
        official_matches.append(
            {
                "source": off["agency"], "title": off["title"], "incident_type": off["incident_type"], "distance_km": off["distance_km"],
                "discovered": _iso(ignition + timedelta(hours=off["after_h"])), "url": None,
            }
        )
    official = {
        "checks": [
            {"name": "GDACS (UN / European Commission)", "kind": "automated", "status": "no_match", "detail": "No GDACS wildfire alert within 50 km (GDACS lists only very large fires)."},
            {
                "name": (off or {}).get("agency", "Fire Service and Civil Defence, Bangladesh"), "kind": "automated",
                "status": "corroborating" if official_matches else "no_match",
                "detail": f"Incident logged {official_matches[0]['distance_km']} km from the satellite event." if official_matches else "No incident logged for this location.",
            },
        ],
        "matches": official_matches,
        "has_official_match": bool(official_matches),
        "controlled_burn_reported": False,
        "note": "Official matches require an incident within 25 km whose dates overlap the detections.",
    }

    articles = [
        {
            "title": n["title"], "description": n["description"], "url": None, "domain": n["domain"], "publication": n["publication"],
            "published": _iso(ignition + timedelta(hours=n["after_h"])), "provider": "demo", "distance_km": n["distance_km"],
        }
        for n in sc["news"]
        if ignition + timedelta(hours=n["after_h"]) <= now
    ]
    return {
        "place": place,
        "regional": regional,
        "official": official,
        "articles": articles,
        "case_overrides": {
            "overpasses": {"passes": passes, "witnesses": list(WITNESSES), "method": "nominal overpass schedule", "errors": []},
            "hourly": hourly,
            "season": season,
        },
    }
