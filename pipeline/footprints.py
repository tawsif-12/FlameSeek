"""Step 3: pixel footprints.

Each detection becomes a scan x track rectangle around its pixel centre:
scan_km wide (across-track) and track_km long (along-track).

The rectangle is built in a local azimuthal-equidistant (AEQD) projection
centred on the detection, then mapped back to WGS84. In AEQD, distance and
azimuth from the centre are exact. So the inverse of a corner at (x, y) is the
geodesic point at distance sqrt(x^2+y^2) and azimuth atan2(x, y) from the
centre. pyproj.Geod.fwd computes that for all rows at once, without building
one projection per detection. tests/test_footprints.py checks the result
against an explicit pyproj AEQD transform.

Areas are measured in EPSG:6933 (equal-area). Because 6933 is cylindrical,
area does not change when a shape is shifted in longitude. Each polygon is
therefore shifted to longitude 0 before projecting, which also avoids
problems at the antimeridian.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Geod, Transformer

GEOD = Geod(ellps="WGS84")
_TO_6933 = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)

# Afternoon-orbit platforms cross the equator northbound in daytime; Terra southbound.
ASCENDING_BY_DAY = {"Aqua": True, "S-NPP": True, "NOAA-20": True, "NOAA-21": True, "Terra": False}


def track_heading_deg(lat: np.ndarray, platform: pd.Series, daynight: pd.Series,
                      inclination_deg: float) -> np.ndarray:
    """Approximate ground-track azimuth (deg clockwise from north).

    Spherical orbit geometry: sin(deviation) = |cos i| / cos(lat). Ascending
    passes of these retrograde sun-synchronous orbits head north-northwest,
    descending passes south-southwest. Earth rotation (a few degrees) is ignored.
    """
    s = np.clip(abs(np.cos(np.radians(inclination_deg))) / np.cos(np.radians(lat)), 0, 1)
    dev = np.degrees(np.arcsin(s))
    asc_by_day = platform.map(ASCENDING_BY_DAY).fillna(True).to_numpy(bool)
    is_day = daynight.astype(str).str.upper().eq("D").to_numpy()
    ascending = np.where(is_day, asc_by_day, ~asc_by_day)
    return np.where(ascending, 360.0 - dev, 180.0 + dev)


def footprint_polygons(lat, lon, scan_km, track_km, heading_deg) -> np.ndarray:
    """Return shapely polygons (WGS84) for the scan x track rectangles."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    hs, ht = np.asarray(scan_km) * 500.0, np.asarray(track_km) * 500.0  # half sides in metres
    # Corner offsets in the AEQD plane, with y along-track and x across-track.
    corners = [(-hs, -ht), (hs, -ht), (hs, ht), (-hs, ht)]
    xs, ys = [], []
    for cx, cy in corners:
        dist = np.hypot(cx, cy)
        az = heading_deg + np.degrees(np.arctan2(cx, cy))  # rotate by the track heading
        clon, clat, _ = GEOD.fwd(lon, lat, az, dist)
        xs.append(clon)
        ys.append(clat)
    xs, ys = np.stack(xs, 1), np.stack(ys, 1)
    # Antimeridian: keep corners on the same side as the centre (lon may exceed +/-180).
    xs = np.where(xs - lon[:, None] > 180, xs - 360, xs)
    xs = np.where(xs - lon[:, None] < -180, xs + 360, xs)
    rings = np.stack([xs, ys], axis=2)
    return shapely.polygons(rings)


def area_km2_6933(geoms: np.ndarray, ref_lon: np.ndarray) -> np.ndarray:
    """Equal-area (EPSG:6933) area of WGS84 polygons, shifted by ref_lon to lon 0 first."""
    geoms = np.asarray(geoms, dtype=object)
    coords = shapely.get_coordinates(geoms)
    counts = shapely.get_num_coordinates(geoms)
    shift = np.repeat(np.asarray(ref_lon, float), counts)
    x, y = _TO_6933.transform(coords[:, 0] - shift, coords[:, 1])
    # set_coordinates writes in place, so work on a copy.
    projected = shapely.set_coordinates(shapely.transform(geoms, lambda c: c), np.c_[x, y])
    return shapely.area(projected) / 1e6


def run(clean: pd.DataFrame, cfg: dict) -> gpd.GeoDataFrame:
    fp_cfg = cfg["footprints"]
    if fp_cfg.get("orientation", "ground_track") == "ground_track":
        heading = track_heading_deg(clean["latitude"].to_numpy(), clean["platform"],
                                    clean["daynight"], fp_cfg["orbit_inclination_deg"])
    else:
        heading = np.zeros(len(clean))
    geoms = footprint_polygons(clean["latitude"], clean["longitude"],
                               clean["scan_km"], clean["track_km"], heading)
    gdf = gpd.GeoDataFrame(clean.copy(), geometry=geoms, crs="EPSG:4326")
    gdf["track_heading_deg"] = heading
    gdf["footprint_area_km2"] = area_km2_6933(geoms, clean["longitude"].to_numpy())
    gdf["nominal_area_km2"] = gdf["scan_km"] * gdf["track_km"]
    gdf["half_diag_km"] = 0.5 * np.hypot(gdf["scan_km"], gdf["track_km"])

    # Parsing check: area range per sensor against the procedure's expected ranges.
    ranges = {}
    for sensor, g in gdf.groupby("sensor"):
        lo, hi = fp_cfg["area_range_km2"][sensor]
        a = g["footprint_area_km2"]
        ranges[sensor] = {"n": len(g), "min_km2": float(a.min()), "max_km2": float(a.max()),
                          "median_km2": float(a.median()),
                          "scan_min": float(g["scan_km"].min()), "scan_max": float(g["scan_km"].max()),
                          "track_min": float(g["track_km"].min()), "track_max": float(g["track_km"].max()),
                          "expected": [lo, hi], "n_outside": int(((a < lo) | (a > hi)).sum())}
        print(f"[Step 3] {sensor}: footprint area {a.min():.4f}-{a.max():.4f} km2 "
              f"(expected {lo}-{hi}); outside range: {ranges[sensor]['n_outside']}")
    gdf.attrs["area_ranges"] = ranges
    return gdf
