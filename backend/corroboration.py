"""Independent corroboration: regional satellites and official incident feeds.

Automated checks (queried live):
- Other polar-orbiting platforms in FIRMS (MODIS Terra/Aqua, VIIRS SNPP/NOAA-20/NOAA-21)
- GOES geostationary fire product via FIRMS (Americas)
- Landsat 8/9 30 m active fire via FIRMS (US and Canada)
- Sentinel-2 L2A scenes via Earth Search STAC (imagery availability for visual review)
- CWFIS M3 fire perimeters (Canada's national satellite fire product)
- EFFIS burnt areas (Copernicus, Europe / Middle East / North Africa)
- Official incident feeds: GDACS (global), NIFC WFIGS (US), NSW RFS (Australia)

Geostationary imagery with no public fire API (Himawari, Meteosat) is offered as
a review link and reported as not automatically checked.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from firms_client import FirmsAPIError, fetch_hotspots_with_report
from geo import haversine_km
from http_utils import ExternalServiceError, request_json
from source_directory import EU_EFFIS_COUNTRIES, sources_for_country


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hours_between(a: datetime, b: datetime) -> float:
    return (_utc(a) - _utc(b)).total_seconds() / 3600


def _time_gap_to_window(t: datetime, start: datetime, end: datetime) -> float:
    """Hours outside [start, end]; 0 when inside."""
    if t < start:
        return _hours_between(start, t)
    if t > end:
        return _hours_between(t, end)
    return 0.0


def _match_rows(rows: list[dict[str, Any]], subject: dict[str, Any], max_km: float, max_hours: float) -> list[dict[str, Any]]:
    matches = []
    for row in rows:
        d = haversine_km(subject["lat"], subject["lon"], row["lat"], row["lon"]) - subject.get("radius_km", 0)
        gap = _time_gap_to_window(_utc(row["acq_datetime"]), subject["t_start"], subject["t_end"])
        if d <= max_km and gap <= max_hours:
            matches.append({**row, "distance_km": round(max(d, 0.0), 2), "time_gap_hours": round(gap, 2)})
    return sorted(matches, key=lambda r: (r["distance_km"], r["time_gap_hours"]))


def _subject_bbox(subject: dict[str, Any], pad_km: float) -> tuple[float, float, float, float]:
    from geo import radius_bbox

    return tuple(round(v, 4) for v in radius_bbox(subject["lat"], subject["lon"], subject.get("radius_km", 0) + pad_km))  # type: ignore[return-value]


def _in_goes_coverage(lat: float, lon: float) -> bool:
    return -65 <= lat <= 65 and -180 <= lon <= -15


def _in_himawari_coverage(lat: float, lon: float) -> bool:
    return -65 <= lat <= 65 and (lon >= 75 or lon <= -165)


def _in_meteosat_coverage(lat: float, lon: float) -> bool:
    return -65 <= lat <= 65 and -65 <= lon <= 110


async def _firms_platform_check(subject: dict[str, Any]) -> dict[str, Any]:
    """Detections from polar platforms the subject itself was not built from."""
    own = set(subject.get("sensors", []))
    others = [s for s in ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"] if s not in own]
    base = {"name": "Other polar-orbiting platforms (FIRMS)", "kind": "automated", "sensors_checked": others}
    if not others:
        return {**base, "status": "not_applicable", "detail": "All MODIS and VIIRS platforms already contribute to this event; cross-sensor agreement is reported under observation quality."}
    start = (subject["t_start"] - timedelta(hours=12)).date()
    end = (subject["t_end"] + timedelta(hours=12)).date()
    try:
        rows, _ = await fetch_hotspots_with_report(_subject_bbox(subject, 10), start, end, others)
    except FirmsAPIError as exc:
        return {**base, "status": "unavailable", "detail": f"FIRMS error: {exc.message[:120]}"}
    matches = _match_rows(rows, subject, 5.0, 12.0)
    if matches:
        platforms = sorted({m["sensor"] for m in matches})
        return {**base, "status": "corroborating", "independent": True, "matches": matches[:10], "detail": f"{len(matches)} detection(s) from {', '.join(platforms)} within 5 km and 12 h."}
    return {**base, "status": "no_match", "detail": "No detections from the other platforms within 5 km and 12 h (small, short or cloud-obscured fires are often missed)."}


async def _firms_source_check(subject: dict[str, Any], sensor: str, name: str, max_km: float, max_hours: float) -> dict[str, Any]:
    base = {"name": name, "kind": "automated"}
    today = datetime.now(timezone.utc).date()
    if subject["t_end"].date() < today - timedelta(days=60):
        return {**base, "status": "not_covered", "detail": "Only near-real-time data is available from FIRMS for this source."}
    start = (subject["t_start"] - timedelta(hours=max_hours)).date()
    end = min(today, (subject["t_end"] + timedelta(hours=max_hours)).date())
    try:
        rows, _ = await fetch_hotspots_with_report(_subject_bbox(subject, max_km + 5), start, end, [sensor])
    except FirmsAPIError as exc:
        return {**base, "status": "unavailable", "detail": f"FIRMS error: {exc.message[:120]}"}
    matches = _match_rows(rows, subject, max_km, max_hours)
    if matches:
        return {**base, "status": "corroborating", "independent": True, "matches": matches[:10], "detail": f"{len(matches)} detection(s) within {max_km:g} km and {max_hours:g} h."}
    return {**base, "status": "no_match", "detail": f"No {name} detection within {max_km:g} km and {max_hours:g} h."}


async def _sentinel2_check(subject: dict[str, Any]) -> dict[str, Any]:
    base = {"name": "Sentinel-2 L2A (Copernicus, via Earth Search STAC)", "kind": "imagery"}
    west, south, east, north = _subject_bbox(subject, 1)
    start = subject["t_start"] - timedelta(days=5)
    end = subject["t_end"] + timedelta(days=5)
    try:
        data = await request_json(
            "https://earth-search.aws.element84.com/v1/search",
            service="Earth Search",
            params={
                "collections": "sentinel-2-l2a",
                "bbox": f"{west},{south},{east},{north}",
                "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                "limit": 20,
            },
            ttl_seconds=6 * 3600,
        )
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    scenes = []
    for feat in (data or {}).get("features", []):
        props = feat.get("properties", {})
        when = datetime.fromisoformat(props["datetime"].replace("Z", "+00:00"))
        scenes.append(
            {
                "id": feat.get("id"),
                "datetime": when.isoformat(),
                "cloud_cover_pct": props.get("eo:cloud_cover"),
                "hours_from_detection": round(_hours_between(when, subject["t_end"]), 1),
                "thumbnail": ((feat.get("assets") or {}).get("thumbnail") or {}).get("href"),
            }
        )
    scenes.sort(key=lambda s: ((s["cloud_cover_pct"] or 100) > 60, abs(s["hours_from_detection"])))
    browser = (
        "https://browser.dataspace.copernicus.eu/?zoom=13"
        f"&lat={subject['lat']:.5f}&lng={subject['lon']:.5f}"
        f"&fromTime={start.date().isoformat()}T00:00:00.000Z&toTime={end.date().isoformat()}T23:59:59.999Z"
        "&datasetId=S2_L2A_CDAS&layerId=3_SWIR"
    )
    if not scenes:
        return {**base, "status": "no_scene", "detail": "No Sentinel-2 scene within +/-5 days.", "review_url": browser}
    clear = [s for s in scenes if (s["cloud_cover_pct"] or 100) <= 60]
    return {
        **base,
        "status": "review_available" if clear else "cloudy_only",
        "scenes": scenes[:4],
        "review_url": browser,
        "detail": (
            f"{len(clear)} scene(s) with <=60% cloud within +/-5 days. SWIR composites show active fire and burn scars for visual confirmation; this is not an automatic detection."
            if clear
            else "Only cloudy Sentinel-2 scenes in the window."
        ),
    }


async def _cwfis_m3_check(subject: dict[str, Any]) -> dict[str, Any]:
    base = {"name": "CWFIS M3 fire perimeters (Natural Resources Canada)", "kind": "automated"}
    west, south, east, north = _subject_bbox(subject, 10)
    try:
        data = await request_json(
            "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows",
            service="CWFIS",
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "public:m3_polygons_current",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{south},{west},{north},{east},urn:ogc:def:crs:EPSG::4326",
                "count": 50,
            },
            ttl_seconds=3600,
        )
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    matches = []
    for feat in (data or {}).get("features", []):
        p = feat.get("properties", {})
        try:
            first = datetime.fromisoformat(p["firstdate"].replace("Z", "+00:00"))
            last = datetime.fromisoformat(p["lastdate"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError):
            continue
        if last >= subject["t_start"] - timedelta(days=2) and first <= subject["t_end"] + timedelta(days=1):
            matches.append({"first_detection": first.isoformat(), "last_detection": last.isoformat(), "area_ha": p.get("area"), "hotspot_count": p.get("hcount")})
    if matches:
        return {**base, "status": "corroborating", "independent": True, "matches": matches, "detail": f"{len(matches)} current M3 fire perimeter(s) overlap this location and time."}
    return {**base, "status": "no_match", "detail": "No current M3 perimeter at this location."}


async def _effis_check(subject: dict[str, Any], country_code: str) -> dict[str, Any]:
    base = {"name": "EFFIS burnt areas (Copernicus Emergency Management Service)", "kind": "automated"}
    code = {"GR": "EL", "GB": "UK"}.get(country_code, country_code)
    try:
        data = await request_json(
            "https://api.effis.emergency.copernicus.eu/rest/2/burntareas/current/",
            service="EFFIS",
            params={"format": "json", "country": code, "ordering": "-firedate", "limit": 100},
            ttl_seconds=3600,
            timeout=60,
        )
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    matches = []
    for r in (data or {}).get("results", []):
        try:
            when = datetime.fromisoformat(r["firedate"])
            lon, lat = r["centroid"]["coordinates"]
        except (KeyError, ValueError, TypeError):
            continue
        d = haversine_km(subject["lat"], subject["lon"], lat, lon) - subject.get("radius_km", 0)
        if d <= 8 and subject["t_start"] - timedelta(days=3) <= when <= subject["t_end"] + timedelta(days=5):
            matches.append({"fire_date": when.isoformat(), "area_ha": r.get("area_ha"), "province": r.get("province"), "commune": r.get("commune"), "distance_km": round(max(d, 0), 2)})
    if matches:
        return {**base, "status": "corroborating", "independent": True, "matches": matches[:5], "detail": f"EFFIS mapped {len(matches)} burnt area(s) within 8 km of this event."}
    return {**base, "status": "no_match", "detail": "No EFFIS burnt area mapped nearby yet (mapping follows fires by days)."}


def _review_links(subject: dict[str, Any]) -> list[dict[str, Any]]:
    lat, lon = subject["lat"], subject["lon"]
    when = subject["t_end"]
    links = []
    if _in_himawari_coverage(lat, lon):
        links.append(
            {
                "name": "Himawari-9 (JMA) via RAMMB/CIRA SLIDER",
                "kind": "manual_review",
                "status": "review_link",
                "detail": "Asia-Pacific geostationary imagery (10-minute). No public fire-detection API, so it is not checked automatically.",
                "review_url": f"https://rammb-slider.cira.colostate.edu/?sat=himawari&sec=full_disk&x=0&y=0&z=0&im=12&ts=1&st={when.strftime('%Y%m%d%H%M%S')}&et=0&p%5B0%5D=band_07",
            }
        )
    if _in_meteosat_coverage(lat, lon):
        links.append(
            {
                "name": "Meteosat (EUMETSAT) via EUMETView",
                "kind": "manual_review",
                "status": "review_link",
                "detail": "Europe/Africa geostationary imagery. The LSA SAF FRP-PIXEL product requires registration, so it is not checked automatically.",
                "review_url": "https://view.eumetsat.int/productviewer?v=default",
            }
        )
    links.append(
        {
            "name": "NASA Worldview",
            "kind": "manual_review",
            "status": "review_link",
            "detail": "True-colour MODIS/VIIRS imagery for smoke plumes and burn scars on the detection date.",
            "review_url": (
                "https://worldview.earthdata.nasa.gov/"
                f"?v={lon - 0.35:.4f},{lat - 0.35:.4f},{lon + 0.35:.4f},{lat + 0.35:.4f}"
                f"&l=VIIRS_NOAA20_CorrectedReflectance_TrueColor,VIIRS_NOAA20_Thermal_Anomalies_375m_All,MODIS_Combined_Thermal_Anomalies_All,Reference_Labels_15m"
                f"&t={when.date().isoformat()}"
            ),
        }
    )
    return links


async def regional_satellite_evidence(subject: dict[str, Any], place: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    lat, lon = subject["lat"], subject["lon"]
    cc = (place.get("country_code") or "").upper()
    tasks = [_firms_platform_check(subject), _sentinel2_check(subject)]
    if _in_goes_coverage(lat, lon):
        tasks.append(_firms_source_check(subject, "goes", "GOES-East/West geostationary fire product (FIRMS)", 6.0, 3.0))
    if cc in {"US", "CA"}:
        tasks.append(_firms_source_check(subject, "landsat", "Landsat 8/9 active fire (FIRMS, 30 m)", 2.0, 24.0))
    if cc == "CA":
        tasks.append(_cwfis_m3_check(subject))
    if cc in EU_EFFIS_COUNTRIES:
        tasks.append(_effis_check(subject, cc))
    checks = list(await asyncio.gather(*tasks))
    for nat in sources_for_country(cc).get("national_satellite", []):
        if not nat.get("automated"):
            checks.append({"name": nat["name"], "kind": "manual_review", "status": "review_link", "detail": "National fire-monitoring product; no public API connected.", "review_url": nat["url"]})
    checks += _review_links(subject)
    corroborating = [c for c in checks if c.get("status") == "corroborating"]
    return {
        "checks": checks,
        "corroborating_sources": [c["name"] for c in corroborating],
        "geostationary_or_highres_match": any(("GOES" in c["name"] or "Landsat" in c["name"] or "EFFIS" in c["name"] or "M3" in c["name"]) for c in corroborating),
        "other_platform_match": any("polar" in c["name"] for c in corroborating),
    }


# --- Official incident feeds -------------------------------------------------------------


async def _gdacs(subject: dict[str, Any]) -> dict[str, Any]:
    base = {"name": "GDACS (UN / European Commission Global Disaster Alert and Coordination System)", "kind": "automated", "authority": "international"}
    start = (subject["t_start"] - timedelta(days=10)).date().isoformat()
    end = (subject["t_end"] + timedelta(days=3)).date().isoformat()
    try:
        data = await request_json(
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
            service="GDACS",
            params={"eventlist": "WF", "fromDate": start, "toDate": end},
            ttl_seconds=3 * 3600,
        )
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    matches = []
    for feat in (data or {}).get("features", []) or []:
        p = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        if coords[0] is None:
            continue
        d = haversine_km(subject["lat"], subject["lon"], coords[1], coords[0])
        if d <= 60:
            matches.append(
                {
                    "title": p.get("name"),
                    "from": p.get("fromdate"),
                    "to": p.get("todate"),
                    "alert_level": p.get("alertlevel"),
                    "severity": (p.get("severitydata") or {}).get("severitytext"),
                    "distance_km": round(d, 1),
                    "url": (p.get("url") or {}).get("report"),
                    "incident_type": "WILDFIRE",
                }
            )
    if matches:
        return {**base, "status": "match", "matches": matches, "detail": f"GDACS lists {len(matches)} wildfire event(s) within 60 km (GDACS reports large fires by centroid)."}
    return {**base, "status": "no_match", "detail": "No GDACS wildfire event nearby (GDACS covers only large fires)."}


async def _nifc(subject: dict[str, Any]) -> dict[str, Any]:
    base = {"name": "NIFC WFIGS current incidents (US)", "kind": "automated", "authority": "national"}
    try:
        data = await request_json(
            "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query",
            service="NIFC",
            params={
                "where": "1=1",
                "geometry": f"{subject['lon']},{subject['lat']}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "distance": 15 + subject.get("radius_km", 0),
                "units": "esriSRUnit_Kilometer",
                "outFields": "IncidentName,FireDiscoveryDateTime,IncidentSize,PercentContained,IncidentTypeCategory,POOState,FireCause",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "json",
            },
            ttl_seconds=1800,
        )
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    matches = []
    for feat in (data or {}).get("features", []):
        a = feat.get("attributes", {})
        g = feat.get("geometry") or {}
        discovered = datetime.fromtimestamp(a["FireDiscoveryDateTime"] / 1000, tz=timezone.utc) if a.get("FireDiscoveryDateTime") else None
        if discovered and discovered > subject["t_end"] + timedelta(days=2):
            continue
        category = a.get("IncidentTypeCategory")
        matches.append(
            {
                "title": a.get("IncidentName"),
                "discovered": discovered.isoformat() if discovered else None,
                "size_acres": a.get("IncidentSize"),
                "percent_contained": a.get("PercentContained"),
                "cause": a.get("FireCause"),
                "incident_type": {"WF": "WILDFIRE", "RX": "CONTROLLED_BURN", "CX": "OTHER"}.get(category, category),
                "distance_km": round(haversine_km(subject["lat"], subject["lon"], g.get("y", subject["lat"]), g.get("x", subject["lon"])), 2),
                "url": "https://inciweb.wildfire.gov/",
            }
        )
    matches.sort(key=lambda m: m["distance_km"])
    if matches:
        return {**base, "status": "match", "matches": matches[:5], "detail": f"{len(matches)} reported incident(s) within {15 + subject.get('radius_km', 0):.0f} km."}
    return {**base, "status": "no_match", "detail": "No NIFC-reported incident within 15 km."}


async def _nsw_rfs(subject: dict[str, Any]) -> dict[str, Any]:
    base = {"name": "NSW Rural Fire Service major incidents", "kind": "automated", "authority": "state"}
    try:
        data = await request_json("https://www.rfs.nsw.gov.au/feeds/majorIncidents.json", service="NSW RFS", ttl_seconds=900)
    except ExternalServiceError as exc:
        return {**base, "status": "unavailable", "detail": str(exc)}
    matches = []
    for feat in (data or {}).get("features", []):
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") != "Point" or not coords:
            continue
        d = haversine_km(subject["lat"], subject["lon"], coords[1], coords[0])
        if d > 15 + subject.get("radius_km", 0):
            continue
        p = feat.get("properties", {})
        desc = p.get("description", "")
        kind = re.search(r"TYPE:\s*([^<]+)", desc)
        kind_text = kind.group(1).strip() if kind else ""
        matches.append(
            {
                "title": p.get("title"),
                "published": p.get("pubDate"),
                "incident_type": "CONTROLLED_BURN" if "hazard reduction" in kind_text.lower() else "WILDFIRE" if "fire" in kind_text.lower() else kind_text.upper() or "UNKNOWN",
                "status_text": (re.search(r"STATUS:\s*([^<]+)", desc) or [None, None])[1],
                "distance_km": round(d, 2),
                "url": p.get("link"),
            }
        )
    if matches:
        return {**base, "status": "match", "matches": matches, "detail": f"{len(matches)} NSW RFS incident(s) nearby."}
    return {**base, "status": "no_match", "detail": "No NSW RFS major incident nearby."}


async def official_evidence(subject: dict[str, Any], place: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    cc = (place.get("country_code") or "").upper()
    recent = subject["t_end"] >= datetime.now(timezone.utc) - timedelta(days=14)
    tasks = [_gdacs(subject)]
    if cc == "US" and recent:
        tasks.append(_nifc(subject))
    if cc == "AU" and recent and (place.get("state") or "").lower().startswith("new south wales"):
        tasks.append(_nsw_rfs(subject))
    checks = list(await asyncio.gather(*tasks))
    automated_names = {c["name"] for c in checks}
    for agency in sources_for_country(cc).get("government", []):
        if agency.get("automated") and any(agency["name"].split()[0] in n for n in automated_names):
            continue
        checks.append(
            {
                "name": agency["name"],
                "kind": "manual_review",
                "status": "not_connected",
                "detail": "No machine-readable incident feed connected; check the agency directly." if agency.get("url") else "Agency type to consult; no specific feed configured for this country.",
                "review_url": agency.get("url"),
            }
        )
    matched = [m for c in checks if c.get("status") == "match" for m in c.get("matches", [])]
    return {
        "checks": checks,
        "matches": matched,
        "has_official_match": bool(matched),
        "controlled_burn_reported": any(m.get("incident_type") == "CONTROLLED_BURN" for m in matched),
        "note": "Official sources are only reported as checked when an automated connector queried them.",
    }
