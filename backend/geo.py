"""Geometry helpers: distances, satellite pixel footprints, AOI shapes, hulls.

Coordinates are (lon, lat) in degrees unless a name says otherwise. Planar
computations use a local equirectangular projection, which is accurate to well
under 1% at the scale of a fire event (tens of km).
"""

from __future__ import annotations

from math import asin, atan2, cos, degrees, floor, radians, sin, sqrt
from typing import Any, Iterable

from config import GEOLOCATION_ERROR_KM, NOMINAL_PIXEL_KM


EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = 111.32


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp = p2 - p1
    dl = radians(lon2 - lon1)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(h)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    x = sin(dl) * cos(p2)
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(x, y)) + 360) % 360


def km_per_deg_lon(lat: float) -> float:
    return KM_PER_DEG_LAT * max(cos(radians(lat)), 0.01)


def to_local_km(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    return ((lon - lon0) * km_per_deg_lon(lat0), (lat - lat0) * KM_PER_DEG_LAT)


# --- Satellite pixel footprints -------------------------------------------------


def pixel_size_km(row: dict[str, Any]) -> tuple[float, float]:
    """Along-scan and along-track pixel size in km from FIRMS scan/track fields."""
    sensor = str(row.get("sensor", "modis"))
    nominal = NOMINAL_PIXEL_KM.get(sensor, 1.0)
    scan = row.get("scan_km")
    track = row.get("track_km")
    # FIRMS GOES/Landsat scan/track are pixel indices, not sizes; ignore implausible values.
    if scan is None or not (0 < float(scan) <= 6):
        scan = nominal
    if track is None or not (0 < float(track) <= 6):
        track = nominal
    return float(scan), float(track)


def footprint_polygon(row: dict[str, Any]) -> list[list[float]]:
    """Approximate pixel footprint as an axis-aligned rectangle [[lon, lat], ...].

    Polar orbiters scan roughly east-west, so scan maps to longitude and track to
    latitude. This is an approximation of the true (rotated, bow-tie) footprint.
    """
    lat, lon = float(row["lat"]), float(row["lon"])
    scan, track = pixel_size_km(row)
    half_lon = (scan / 2) / km_per_deg_lon(lat)
    half_lat = (track / 2) / KM_PER_DEG_LAT
    return [
        [lon - half_lon, lat - half_lat],
        [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat],
        [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]


def location_uncertainty_km(row: dict[str, Any]) -> float:
    """Radius within which the fire inside a detected pixel most likely lies."""
    scan, track = pixel_size_km(row)
    half_diagonal = 0.5 * sqrt(scan * scan + track * track)
    return round(half_diagonal + GEOLOCATION_ERROR_KM.get(str(row.get("sensor")), 0.3), 3)


def footprint_cell_fractions(row: dict[str, Any], grid_res: float) -> list[tuple[float, float, float]]:
    """Distribute one detection across the grid cells its footprint overlaps.

    Returns (cell_lat, cell_lon, fraction) with fractions summing to 1. Cell keys are
    cell centres snapped like harmonize.snap_value, so a detection is attributed
    proportionally instead of treating a whole pixel as a single burned point.
    """
    ring = footprint_polygon(row)
    west, south = ring[0]
    east, north = ring[2]
    area = (east - west) * (north - south)
    if area <= 0:
        return [(round(round(float(row["lat"]) / grid_res) * grid_res, 6), round(round(float(row["lon"]) / grid_res) * grid_res, 6), 1.0)]
    parts = []
    i0, i1 = floor(south / grid_res + 0.5), floor(north / grid_res + 0.5)
    j0, j1 = floor(west / grid_res + 0.5), floor(east / grid_res + 0.5)
    for i in range(i0, i1 + 1):
        c_s, c_n = (i - 0.5) * grid_res, (i + 0.5) * grid_res
        overlap_lat = min(north, c_n) - max(south, c_s)
        if overlap_lat <= 0:
            continue
        for j in range(j0, j1 + 1):
            c_w, c_e = (j - 0.5) * grid_res, (j + 0.5) * grid_res
            overlap_lon = min(east, c_e) - max(west, c_w)
            if overlap_lon <= 0:
                continue
            parts.append((round(i * grid_res, 6), round(j * grid_res, 6), overlap_lat * overlap_lon / area))
    total = sum(p[2] for p in parts) or 1.0
    return [(a, b, f / total) for a, b, f in parts]


# --- Area of interest ------------------------------------------------------------


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def point_in_polygons(lon: float, lat: float, polygons: list[list[list[list[float]]]]) -> bool:
    """polygons: list of polygons, each a list of rings (outer first, then holes)."""
    for polygon in polygons:
        if polygon and point_in_ring(lon, lat, polygon[0]) and not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            return True
    return False


def geojson_to_polygons(geometry: dict[str, Any] | None) -> list[list[list[list[float]]]]:
    if not geometry:
        return []
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coords]
    if kind == "MultiPolygon":
        return list(coords)
    return []


def polygons_bbox(polygons: list[list[list[list[float]]]]) -> tuple[float, float, float, float]:
    xs = [pt[0] for poly in polygons for ring in poly[:1] for pt in ring]
    ys = [pt[1] for poly in polygons for ring in poly[:1] for pt in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def radius_bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = radius_km / km_per_deg_lon(lat)
    return (max(-180.0, lon - dlon), max(-90.0, lat - dlat), min(180.0, lon + dlon), min(90.0, lat + dlat))


class AOI:
    """Area of interest: a bbox, optionally refined by polygons or a radius."""

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        polygons: list[list[list[list[float]]]] | None = None,
        center: tuple[float, float] | None = None,
        radius_km: float | None = None,
        name: str | None = None,
        kind: str = "bbox",
    ):
        self.bbox = tuple(float(v) for v in bbox)
        self.polygons = polygons or []
        self.center = center
        self.radius_km = radius_km
        self.name = name
        self.kind = kind

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AOI":
        polygons = geojson_to_polygons(payload.get("geometry"))
        center = payload.get("center")
        radius = payload.get("radius_km")
        bbox = payload.get("bbox")
        kind = payload.get("kind") or ("radius" if center and radius else "polygon" if polygons else "bbox")
        if center and radius:
            bbox = radius_bbox(center[1], center[0], float(radius))
        elif polygons and not bbox:
            bbox = polygons_bbox(polygons)
        if not bbox:
            raise ValueError("AOI needs a bbox, a geometry, or a center with radius_km")
        return cls(tuple(bbox), polygons, tuple(center) if center else None, float(radius) if radius else None, payload.get("name"), kind)

    def contains(self, lat: float, lon: float) -> bool:
        west, south, east, north = self.bbox
        if not (west <= lon <= east and south <= lat <= north):
            return False
        if self.center and self.radius_km:
            return haversine_km(lat, lon, self.center[1], self.center[0]) <= self.radius_km
        if self.polygons:
            return point_in_polygons(lon, lat, self.polygons)
        return True

    def filter(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self.contains(float(row["lat"]), float(row["lon"]))]

    def area_km2(self) -> float:
        west, south, east, north = self.bbox
        mid = (south + north) / 2
        box = (east - west) * km_per_deg_lon(mid) * (north - south) * KM_PER_DEG_LAT
        if self.center and self.radius_km:
            return 3.14159 * self.radius_km**2
        if self.polygons:
            return sum(abs(ring_area_km2(poly[0])) - sum(abs(ring_area_km2(h)) for h in poly[1:]) for poly in self.polygons)
        return box

    def describe(self) -> dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "kind": self.kind,
            "name": self.name,
            "center": list(self.center) if self.center else None,
            "radius_km": self.radius_km,
            "has_polygon": bool(self.polygons),
            "area_km2": round(self.area_km2(), 1),
        }


# --- Shapes of point sets -----------------------------------------------------------


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def ring_area_km2(ring: list[list[float]]) -> float:
    if len(ring) < 3:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    return polygon_area([to_local_km(p[1], p[0], lat0, lon0) for p in ring])


def detections_extent_km2(rows: list[dict[str, Any]]) -> float:
    """Area of the convex hull of detections, with each point buffered by its pixel.

    The buffer keeps a single detection from reporting zero area and avoids
    claiming the whole hull burned: it is a spatial extent, not burned area.
    """
    if not rows:
        return 0.0
    lat0 = sum(float(r["lat"]) for r in rows) / len(rows)
    lon0 = sum(float(r["lon"]) for r in rows) / len(rows)
    corners: list[tuple[float, float]] = []
    for row in rows:
        x, y = to_local_km(float(row["lat"]), float(row["lon"]), lat0, lon0)
        scan, track = pixel_size_km(row)
        corners += [(x - scan / 2, y - track / 2), (x + scan / 2, y - track / 2), (x + scan / 2, y + track / 2), (x - scan / 2, y + track / 2)]
    return round(polygon_area(convex_hull(corners)), 3)


class IncrementalExtent:
    """Running detection extent: hull(previous hull + new pixels) equals hull of all pixels,
    so each update costs only the new points plus the current hull vertices."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.hull: list[tuple[float, float]] = []

    def add(self, rows: list[dict[str, Any]]) -> float:
        corners = list(self.hull)
        for row in rows:
            x, y = to_local_km(float(row["lat"]), float(row["lon"]), self.lat0, self.lon0)
            scan, track = pixel_size_km(row)
            corners += [(x - scan / 2, y - track / 2), (x + scan / 2, y - track / 2), (x + scan / 2, y + track / 2), (x - scan / 2, y + track / 2)]
        self.hull = convex_hull(corners)
        return round(polygon_area(self.hull), 3)


def hull_lonlat(rows: list[dict[str, Any]]) -> list[list[float]]:
    pts = convex_hull([(round(float(r["lon"]), 5), round(float(r["lat"]), 5)) for r in rows])
    return [[x, y] for x, y in pts]
