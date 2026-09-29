"""Reverse geocoding, place search and land context from OpenStreetMap.

Nominatim (1 request/second policy, enforced in http_utils) supplies
administrative context; Overpass supplies the forest / protected area that
contains a point. Falls back to coarse country boxes when OSM is unreachable.
"""

from __future__ import annotations

import time
from typing import Any

from geo import geojson_to_polygons, haversine_km, polygons_bbox
from http_utils import ExternalServiceError, request_json
from verification import _country_context


NOMINATIM = "https://nominatim.openstreetmap.org"
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [OVERPASS, "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
_overpass_down_until: dict[str, float] = {}


async def reverse_geocode(lat: float, lon: float) -> dict[str, Any]:
    lat_r, lon_r = round(lat, 3), round(lon, 3)
    place: dict[str, Any] = {"coordinates": {"lat": lat, "lon": lon}}
    try:
        data = await request_json(
            f"{NOMINATIM}/reverse",
            service="Nominatim",
            params={"lat": lat_r, "lon": lon_r, "format": "jsonv2", "zoom": 14, "addressdetails": 1, "accept-language": "en"},
            ttl_seconds=30 * 86400,
            disk_namespace="nominatim",
        )
    except ExternalServiceError as exc:
        data = None
        place["geocoder_error"] = str(exc)
    address = (data or {}).get("address") or {}
    if address:
        place.update(
            {
                "country": address.get("country"),
                "country_code": (address.get("country_code") or "").upper() or None,
                "state": address.get("state") or address.get("province") or address.get("region"),
                "district": address.get("state_district") or address.get("county") or address.get("district") or address.get("municipality"),
                "city": address.get("city") or address.get("town"),
                "village": address.get("village") or address.get("hamlet") or address.get("suburb"),
                "local_name": (data or {}).get("name") or address.get("road") or address.get("neighbourhood"),
                "display_name": (data or {}).get("display_name"),
                "precision": "osm_address",
                "source": "OpenStreetMap Nominatim",
            }
        )
    else:
        fallback = _country_context({"lat": lat, "lon": lon})
        place.update(
            {
                "country": fallback["country_name"] if fallback["country_code"] else None,
                "country_code": fallback["country_code"],
                "state": None,
                "district": None,
                "city": None,
                "village": None,
                "local_name": None,
                "display_name": None,
                "precision": "country_bbox_fallback" if fallback["country_code"] else "none",
                "source": "built-in country boxes (Nominatim returned no address: open ocean, remote area, or service unavailable)",
            }
        )
    place["nearest_settlement"] = await nearest_settlement(lat, lon)
    place["land_context"] = await land_context(lat, lon)
    place["land_context"]["nearby_heat_sources"] = await nearby_heat_sources(lat, lon)
    # Kept for older clients that read these keys.
    place["admin_level_1"] = place.get("state")
    place["admin_level_2"] = place.get("district")
    place["locality"] = place.get("village") or place.get("city") or place.get("district")
    return place


async def overpass_query(query: str, ttl: float = 7 * 86400) -> list[dict[str, Any]]:
    """Run an Overpass query, falling back to public mirrors when the main server is busy."""
    last: ExternalServiceError | None = None
    for url in OVERPASS_MIRRORS:
        if _overpass_down_until.get(url, 0) > time.monotonic():
            continue
        try:
            data = await request_json(url, service="Overpass", method="POST", data={"data": query}, ttl_seconds=ttl, disk_namespace="overpass", timeout=50, retries=0)
            return (data or {}).get("elements") or []
        except ExternalServiceError as exc:
            last = exc
            # Circuit breaker: an overloaded or unreachable mirror is skipped for 5 minutes.
            if exc.status_code is None or exc.status_code >= 500 or exc.status_code == 429:
                _overpass_down_until[url] = time.monotonic() + 300
    raise last or ExternalServiceError("Overpass", "all Overpass servers are temporarily unavailable")


async def _overpass(query: str, ttl: float = 7 * 86400) -> list[dict[str, Any]]:
    try:
        return await overpass_query(query, ttl)
    except ExternalServiceError:
        return []


async def land_context(lat: float, lon: float) -> dict[str, Any]:
    """Forests, protected areas and land use polygons that contain the point."""
    query = f"""[out:json][timeout:25];
is_in({lat:.4f},{lon:.4f})->.a;
(
  area.a["boundary"~"protected_area|national_park"];
  area.a["leisure"="nature_reserve"];
  area.a["landuse"~"forest|farmland|meadow|orchard|plantation|industrial|residential"];
  area.a["natural"~"wood|scrub|grassland|heath|wetland"];
);
out tags;"""
    elements = await _overpass(query)
    protected, forest, landuse = [], [], []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name:en") or tags.get("name")
        if tags.get("boundary") in {"protected_area", "national_park"} or tags.get("leisure") == "nature_reserve":
            protected.append({"name": name or "Unnamed protected area", "protect_class": tags.get("protect_class"), "designation": tags.get("protection_title") or tags.get("designation")})
        elif tags.get("landuse") == "forest" or tags.get("natural") == "wood":
            forest.append({"name": name or "Unnamed forest/woodland"})
        elif tags.get("landuse") or tags.get("natural"):
            landuse.append(tags.get("landuse") or tags.get("natural"))
    return {
        "protected_areas": protected[:5],
        "forests": forest[:5],
        "land_use": sorted(set(landuse)),
        "source": "OpenStreetMap via Overpass (mapped polygons only; unmapped land shows as empty)",
    }


async def nearby_heat_sources(lat: float, lon: float) -> list[dict[str, Any]]:
    """Mapped features that commonly produce non-fire thermal anomalies."""
    query = f"""[out:json][timeout:25];
(
  node(around:15000,{lat:.4f},{lon:.4f})["natural"="volcano"];
  nwr(around:2000,{lat:.4f},{lon:.4f})["man_made"~"flare|kiln|works|chimney"];
  nwr(around:2000,{lat:.4f},{lon:.4f})["industrial"~"oil|gas|refinery|steel|cement|mine"];
  nwr(around:1500,{lat:.4f},{lon:.4f})["power"="plant"];
  nwr(around:1500,{lat:.4f},{lon:.4f})["landuse"="industrial"];
);
out tags center 20;"""
    found = []
    for el in await _overpass(query):
        tags = el.get("tags") or {}
        kind = (
            "volcano" if tags.get("natural") == "volcano"
            else "gas_flare" if tags.get("man_made") == "flare"
            else "power_plant" if tags.get("power") == "plant"
            else "industrial"
        )
        plat = el.get("lat") or (el.get("center") or {}).get("lat")
        plon = el.get("lon") or (el.get("center") or {}).get("lon")
        found.append(
            {
                "type": kind,
                "name": tags.get("name:en") or tags.get("name") or kind.replace("_", " "),
                "distance_km": round(haversine_km(lat, lon, plat, plon), 2) if plat is not None else None,
            }
        )
    return sorted(found, key=lambda f: f["distance_km"] if f["distance_km"] is not None else 99)[:6]


async def nearest_settlement(lat: float, lon: float, radius_m: int = 25000) -> dict[str, Any] | None:
    query = f"""[out:json][timeout:25];
node(around:{radius_m},{lat:.4f},{lon:.4f})["place"~"city|town|village|hamlet"];
out tags center 50;"""
    best = None
    for el in await _overpass(query):
        tags = el.get("tags") or {}
        if "lat" not in el:
            continue
        d = haversine_km(lat, lon, el["lat"], el["lon"])
        if best is None or d < best["distance_km"]:
            best = {"name": tags.get("name:en") or tags.get("name"), "type": tags.get("place"), "distance_km": round(d, 2), "lat": el["lat"], "lon": el["lon"]}
    return best


async def search_places(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Forward search for AOI selection (country, state, district, forest, protected area...)."""
    data = await request_json(
        f"{NOMINATIM}/search",
        service="Nominatim",
        params={"q": query, "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": 0.005, "limit": limit, "accept-language": "en"},
        ttl_seconds=30 * 86400,
        disk_namespace="nominatim",
    )
    results = []
    for item in data or []:
        bbox = item.get("boundingbox")
        polygons = geojson_to_polygons(item.get("geojson"))
        if polygons:
            west, south, east, north = polygons_bbox(polygons)
        elif bbox:
            south, north, west, east = (float(v) for v in bbox)
        else:
            continue
        results.append(
            {
                "name": item.get("display_name"),
                "category": item.get("category"),
                "type": item.get("type"),
                "addresstype": item.get("addresstype"),
                "bbox": [west, south, east, north],
                "center": [float(item["lon"]), float(item["lat"])],
                "geometry": item.get("geojson") if polygons else None,
            }
        )
    return results


async def geocode_place_name(name: str, country_code: str | None = None) -> dict[str, Any] | None:
    """Best-effort forward geocode of a place mentioned in a news article."""
    params: dict[str, Any] = {"q": name, "format": "jsonv2", "limit": 1, "accept-language": "en"}
    if country_code:
        params["countrycodes"] = country_code.lower()
    try:
        data = await request_json(f"{NOMINATIM}/search", service="Nominatim", params=params, ttl_seconds=30 * 86400, disk_namespace="nominatim")
    except ExternalServiceError:
        return None
    if not data:
        return None
    return {"name": data[0].get("display_name"), "lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "type": data[0].get("addresstype")}
