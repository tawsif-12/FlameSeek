"""Exposure: what lies inside or near the possible future activity corridor.

Assets come from OpenStreetMap (Overpass); population from WorldPop. Listing an
asset means it lies within or near the corridor, not that it will be affected.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from environment import worldpop_population
from geo import KM_PER_DEG_LAT, haversine_km, km_per_deg_lon, point_in_ring
from geocode import overpass_query
from http_utils import ExternalServiceError


NEAR_KM = 1.0
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
# Three small Overpass requests: facilities (cheap centres), land-use ways and
# protected areas (bounds only; centres of huge relations are slow to compute).
ASSET_QUERIES = {
    "facilities": (
        [
            'node["place"~"^(city|town|village|hamlet)$"]',
            'nwr["amenity"~"^(school|college|university|kindergarten|hospital|clinic|fire_station|police|townhall)$"]',
            'nwr["healthcare"="hospital"]',
            'nwr["power"~"^(plant|substation)$"]',
            'way["power"="line"]',
            'nwr["man_made"~"^(water_works|wastewater_plant)$"]',
            'nwr["aeroway"="aerodrome"]',
            'nwr["industrial"~"oil|gas|chemical"]',
        ],
        "out tags center 1500;",
    ),
}
# Areas (farmland, forest, protected areas) are found with is_in at corridor cell
# centres: Overpass answers from precomputed areas, whereas bbox queries against
# huge park or forest polygons time out.
AREA_FILTERS = [
    'area.a["landuse"~"^(farmland|orchard|vineyard|plantation|meadow|greenhouse_horticulture|forest)$"]',
    'area.a["natural"="wood"]',
    'area.a["boundary"~"^(protected_area|national_park)$"]',
    'area.a["leisure"="nature_reserve"]',
]
MAX_AREA_SAMPLES = 40


def classify_asset(tags: dict[str, str]) -> str | None:
    if tags.get("place") in {"city", "town", "village", "hamlet"}:
        return "settlements"
    amenity = tags.get("amenity")
    if amenity in {"school", "college", "university", "kindergarten"}:
        return "schools"
    if amenity in {"hospital", "clinic"} or tags.get("healthcare") == "hospital":
        return "hospitals"
    if amenity in {"fire_station", "police", "townhall"} or tags.get("man_made") in {"water_works", "wastewater_plant"} or tags.get("aeroway") == "aerodrome" or tags.get("industrial"):
        return "critical_facilities"
    if tags.get("power"):
        return "power"
    if tags.get("boundary") in {"protected_area", "national_park"} or tags.get("leisure") == "nature_reserve":
        return "protected_areas"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forests"
    if tags.get("landuse"):
        return "agriculture"
    return None


def corridor_polygons(cells: list[dict[str, Any]], size: float) -> list[list[list[list[float]]]]:
    """Outline the union of grid cells as polygons (outer ring + holes).

    Each cell contributes four counter-clockwise edges; edges shared by two cells
    cancel, and the remaining edges chain into rings. Counter-clockwise rings are
    outer boundaries, clockwise rings are holes.
    """
    h = size / 2
    q = lambda v: round(v / h)  # integer lattice of half-cell units  # noqa: E731
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for c in cells:
        x0, y0, x1, y1 = q(c["lon"] - h), q(c["lat"] - h), q(c["lon"] + h), q(c["lat"] + h)
        for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
            if (b, a) in edges:
                edges.remove((b, a))
            else:
                edges.add((a, b))
    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for a, b in edges:
        outgoing[a].append(b)
    rings = []
    while outgoing:
        start = next(iter(outgoing))
        ring = [start]
        cur = start
        while True:
            nxt = outgoing[cur].pop()
            if not outgoing[cur]:
                del outgoing[cur]
            if nxt == start:
                break
            ring.append(nxt)
            cur = nxt
        rings.append([[x * h, y * h] for x, y in ring + [start]])

    def signed_area(r: list[list[float]]) -> float:
        return sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1)) / 2

    outers = [r for r in rings if signed_area(r) > 0]
    holes = [r for r in rings if signed_area(r) <= 0]
    polygons = [[o] for o in outers]
    for hole in holes:
        for poly in polygons:
            if point_in_ring(hole[0][0], hole[0][1], poly[0]):
                poly.append(hole)
                break
    return polygons


class Corridor:
    def __init__(self, cells: list[dict[str, Any]], size: float):
        self.cells = cells
        self.size = size
        self.index = {(round(c["lat"] / size), round(c["lon"] / size)): c for c in cells}
        lats = [c["lat"] for c in cells]
        lons = [c["lon"] for c in cells]
        pad = size / 2 + NEAR_KM / KM_PER_DEG_LAT
        self.bbox = (min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad)

    def distance_km(self, lat: float, lon: float) -> float:
        """0 inside a corridor cell, else approximate km to the nearest cell edge."""
        if (round(lat / self.size), round(lon / self.size)) in self.index:
            return 0.0
        best = min(haversine_km(lat, lon, c["lat"], c["lon"]) for c in self.cells)
        return max(0.0, best - self.size / 2 * KM_PER_DEG_LAT)

    def max_p(self, lat: float, lon: float) -> float:
        near = [c["p"] for c in self.cells if abs(c["lat"] - lat) <= self.size and abs(c["lon"] - lon) <= self.size]
        return max(near) if near else 0.0

    def bounds_touch(self, b: dict[str, float]) -> bool:
        half = self.size / 2
        return any(b["minlat"] <= c["lat"] + half and b["maxlat"] >= c["lat"] - half and b["minlon"] <= c["lon"] + half and b["maxlon"] >= c["lon"] - half for c in self.cells)


async def _population(corridor: Corridor) -> dict[str, Any]:
    polygons = corridor_polygons(corridor.cells, corridor.size)
    total = 0
    notes = []
    for poly in polygons[:10]:
        result = await worldpop_population({"type": "Polygon", "coordinates": poly})
        if result["population"] is None:
            notes.append(result.get("note") or "no data")
            continue
        total += result["population"]
    if notes and total == 0:
        return {"status": "unavailable", "population": None, "note": "; ".join(sorted(set(notes)))}
    return {
        "status": "ok" if not notes else "partial",
        "population": total,
        "polygons": len(polygons),
        "dataset": "WorldPop Global 2020 (100 m, unconstrained)",
        "note": "Modelled residential population estimate, not a census count." + (f" {len(notes)} polygon(s) had no data." if notes else ""),
    }


async def analyze_exposure(forecast: dict[str, Any]) -> dict[str, Any]:
    cells: dict[tuple[float, float], dict[str, Any]] = {}
    for h in forecast.get("horizons", {}).values():
        for c in h.get("cells", []):
            if c["p"] >= 0.1:
                k = (c["lat"], c["lon"])
                if k not in cells or c["p"] > cells[k]["p"]:
                    cells[k] = c
    if not cells:
        return {"status": "no_corridor", "note": "No forecast corridor was issued, so exposure cannot be assessed."}
    size = forecast["cell_size_deg"]
    corridor = Corridor(list(cells.values()), size)
    s, w, n, e = corridor.bbox
    bbox = f"{s:.4f},{w:.4f},{n:.4f},{e:.4f}"
    errors = []
    results: dict[str, Any] = {key: {"label": label, "status": "ok", "items": []} for key, label in CATEGORY_LABELS.items()}
    elements: list[dict[str, Any]] = []
    query_categories = {"facilities": ["settlements", "schools", "hospitals", "power", "critical_facilities"]}
    for name, (selectors, out) in ASSET_QUERIES.items():
        try:
            elements += await overpass_query("[out:json][timeout:40];(" + "".join(f"{sel}({bbox});" for sel in selectors) + ");" + out)
        except ExternalServiceError as exc:
            errors.append(f"OpenStreetMap {name.replace('_', ' ')}: {exc}")
            for key in query_categories[name]:
                results[key]["status"] = "unavailable"

    samples = sorted(corridor.cells, key=lambda c: -c["p"])[:MAX_AREA_SAMPLES]
    area_query = "[out:json][timeout:40];(" + "".join(f"is_in({c['lat']:.4f},{c['lon']:.4f});" for c in samples) + ")->.a;(" + "".join(f"{f};" for f in AREA_FILTERS) + ");out tags;"
    try:
        for area in await overpass_query(area_query):
            tags = area.get("tags") or {}
            key = classify_asset(tags)
            if key in {"agriculture", "forests", "protected_areas"}:
                results[key]["items"].append(
                    {
                        "name": tags.get("name:en") or tags.get("name") or (tags.get("landuse") or tags.get("natural") or tags.get("boundary") or "area").replace("_", " "),
                        "type": tags.get("landuse") or tags.get("natural") or tags.get("protection_title") or tags.get("boundary") or tags.get("leisure"),
                        "relation": "contains part of the corridor",
                        "max_corridor_probability": 0.0,
                    }
                )
    except ExternalServiceError as exc:
        errors.append(f"OpenStreetMap land use / protected areas: {exc}")
        for key in ("agriculture", "forests", "protected_areas"):
            results[key]["status"] = "unavailable"
    for el in elements:
        tags = el.get("tags") or {}
        key = classify_asset(tags)
        b = el.get("bounds")
        lat = el.get("lat") or (el.get("center") or {}).get("lat") or (((b["minlat"] + b["maxlat"]) / 2) if b else None)
        lon = el.get("lon") or (el.get("center") or {}).get("lon") or (((b["minlon"] + b["maxlon"]) / 2) if b else None)
        if key is None or lat is None:
            continue
        d = corridor.distance_km(lat, lon)
        inside_bounds = "bounds" in el and corridor.bounds_touch(el["bounds"])
        if d > NEAR_KM and not inside_bounds:
            continue
        results[key]["items"].append(
            {
                "name": tags.get("name:en") or tags.get("name") or (tags.get("place") or tags.get("amenity") or tags.get("landuse") or tags.get("power") or key).replace("_", " "),
                "type": tags.get("place") or tags.get("amenity") or tags.get("landuse") or tags.get("natural") or tags.get("power") or tags.get("boundary") or tags.get("leisure") or tags.get("man_made") or tags.get("aeroway"),
                "relation": "inside corridor" if d == 0 or inside_bounds else f"within {NEAR_KM:g} km of corridor",
                "max_corridor_probability": round(corridor.max_p(lat, lon), 2),
                "population_tag": tags.get("population"),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
            }
        )
    for block in results.values():
        block["items"].sort(key=lambda i: -i["max_corridor_probability"])
        block["count"] = len(block["items"])
        block["items"] = block["items"][:25]

    try:
        roads = await overpass_query(f'[out:json][timeout:60];way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]({bbox});out tags geom 400;')
        road_km = 0.0
        named: dict[str, float] = {}
        for way in roads:
            geom = way.get("geometry") or []
            for a, b in zip(geom, geom[1:]):
                if corridor.distance_km((a["lat"] + b["lat"]) / 2, (a["lon"] + b["lon"]) / 2) == 0:
                    seg = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                    road_km += seg
                    t = way.get("tags") or {}
                    nm = t.get("ref") or t.get("name") or t.get("highway")
                    named[nm] = named.get(nm, 0) + seg
        results["roads"] = {
            "label": "Major roads",
            "status": "ok",
            "length_km_inside_corridor": round(road_km, 1),
            "items": [{"name": k, "km_inside": round(v, 2)} for k, v in sorted(named.items(), key=lambda kv: -kv[1])[:15]],
            "count": len(named),
        }
    except ExternalServiceError as exc:
        errors.append(f"Roads: {exc}")
        results["roads"] = {"label": "Major roads", "status": "unavailable", "items": []}

    population = await _population(corridor)
    area = len(corridor.cells) * (size * km_per_deg_lon(corridor.cells[0]["lat"])) * (size * KM_PER_DEG_LAT)
    return {
        "status": "ok",
        "corridor_cells": len(corridor.cells),
        "corridor_area_km2": round(area, 1),
        "population": population,
        "assets": results,
        "errors": errors,
        "wording": "These people and assets lie within or near the possible future activity corridor. The platform does not claim they will be affected.",
        "sources": ["OpenStreetMap contributors via Overpass API (ODbL)", "WorldPop 2020 population estimates"],
    }
