"""Step 6A: observation opportunities O_s(c, t).

For every 0.1° cell of interest and every platform, list each overpass in the
data period with its time, cross-track distance, scan angle and expected pixel
size. Version 1 assumes clear sky (cloud_adjusted = false).

Method
1. TLEs for Terra, Aqua, S-NPP, NOAA-20 and NOAA-21: CelesTrak first, then a
   public CelesTrak mirror (CelesTrak is not reachable from every network).
   Each TLE is cached with its source and epoch in data/interim/tle/.
2. skyfield (SGP4) propagates each orbit once at `step_s` steps and gives the
   sub-satellite point and altitude.
3. A KD-tree on the track points finds, for each cell, every track point
   within the half swath (plus a margin). Consecutive track indices form one
   pass. The closest point of each pass is refined by projecting the cell onto
   the neighbouring track segments, which gives the overpass time and the
   cross-track (ground) distance.
4. A pass counts when the cross-track distance is within half the swath
   (MODIS 2,330 km, VIIRS 3,060 km).
5. Scan angle from spherical geometry: tan(eta) = R sin(theta) / (r - R cos(theta)).
   Pixel size from Ichoku & Kaufman (2005):
     along-scan  S = R s (cos(eta) / sqrt((R/r)^2 - sin^2(eta)) - 1)
     along-track T = r s (cos(eta) - sqrt((R/r)^2 - sin^2(eta)))
   with s = nadir_pixel / altitude. VIIRS I-band also aggregates 3, 2 or 1
   native samples along-scan (|eta| < 31.59°, < 44.68°, beyond). The native
   sample is a third of the nadir pixel.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from pipeline.config import ROOT

R_KM = 6371.0088
SENSOR_OF = {"Terra": "MODIS", "Aqua": "MODIS", "S-NPP": "VIIRS", "NOAA-20": "VIIRS", "NOAA-21": "VIIRS"}


# ------------------------------------------------------------------ TLEs -----
def fetch_tle(platform: str, cfg: dict) -> dict:
    """Return {'line1','line2','epoch','source'}; tries each source, falls back to the cache."""
    o = cfg["overpasses"]
    nid = o["norad_ids"][platform]
    cache = ROOT / o["tle_cache_dir"]
    cache.mkdir(parents=True, exist_ok=True)
    cfile = cache / f"{platform}.json"
    errors = []
    for url_t in o["tle_sources"]:
        url = url_t.format(id=nid)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FlameSeek/1.0 (research pipeline)"})
            body = urllib.request.urlopen(req, timeout=20).read().decode()
            if body.lstrip().startswith("{"):
                j = json.loads(body)
                l1, l2 = j["line1"], j["line2"]
            else:
                lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
                l1 = next(ln for ln in lines if ln.startswith("1 "))
                l2 = next(ln for ln in lines if ln.startswith("2 "))
            rec = {"platform": platform, "norad_id": nid, "line1": l1, "line2": l2,
                   "source": url, "fetched_utc": pd.Timestamp.now(tz="UTC").isoformat()}
            cfile.write_text(json.dumps(rec, indent=2))
            return rec
        except Exception as exc:  # unreachable, blocked, or malformed
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    if cfile.exists():
        rec = json.loads(cfile.read_text())
        rec["source"] += " (cached)"
        return rec
    raise RuntimeError(f"No TLE for {platform}: " + " | ".join(errors))


# ------------------------------------------------------------- geometry ------
def unit_vectors(lat_deg, lon_deg) -> np.ndarray:
    la, lo = np.radians(lat_deg), np.radians(lon_deg)
    return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]


def scan_angle_deg(theta_rad, alt_km):
    r = R_KM + alt_km
    return np.degrees(np.arctan2(R_KM * np.sin(theta_rad), r - R_KM * np.cos(theta_rad)))


def pixel_size_km(eta_deg, alt_km, nadir_km, sensor: str):
    """Expected (along-scan, along-track) pixel size in km at scan angle eta."""
    eta = np.radians(np.abs(eta_deg))
    r = R_KM + alt_km
    root = np.sqrt(np.clip((R_KM / r) ** 2 - np.sin(eta) ** 2, 1e-9, None))
    if sensor == "VIIRS":
        native = nadir_km / 3.0
        n_agg = np.where(np.abs(eta_deg) < 31.59, 3, np.where(np.abs(eta_deg) < 44.68, 2, 1))
        scan = R_KM * (native / alt_km) * (np.cos(eta) / root - 1) * n_agg
    else:
        scan = R_KM * (nadir_km / alt_km) * (np.cos(eta) / root - 1)
    track = r * (nadir_km / alt_km) * (np.cos(eta) - root)
    return scan, track


def solar_zenith_deg(times: pd.DatetimeIndex, lat, lon):
    """NOAA approximation (accurate to ~0.5°), enough for a day/night label."""
    doy = times.dayofyear.to_numpy()
    hour = (times.hour + times.minute / 60 + times.second / 3600).to_numpy()
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    ha = np.radians((hour * 60 + eqt + 4 * np.asarray(lon)) / 4 - 180)
    la = np.radians(lat)
    cz = np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)
    return np.degrees(np.arccos(np.clip(cz, -1, 1)))


# ------------------------------------------------------------ propagation ----
def propagate(tle: dict, t0: pd.Timestamp, t1: pd.Timestamp, step_s: int):
    from skyfield.api import EarthSatellite, load, wgs84
    ts = load.timescale(builtin=True)
    sat = EarthSatellite(tle["line1"], tle["line2"], tle["platform"], ts)
    secs = np.arange(0, (t1 - t0).total_seconds() + step_s, step_s)
    when = t0 + pd.to_timedelta(secs, unit="s")
    a = lambda idx: np.asarray(idx, dtype=float)  # noqa: E731  (skyfield wants plain arrays)
    t = ts.utc(a(when.year), a(when.month), a(when.day), a(when.hour), a(when.minute),
               a(when.second) + a(when.microsecond) / 1e6)
    geo = sat.at(t)
    sub = wgs84.subpoint_of(geo)
    alt = wgs84.height_of(geo).km
    epoch = sat.epoch.utc_datetime()
    return when, sub.latitude.degrees, sub.longitude.degrees, alt, pd.Timestamp(epoch)


def passes_for_platform(platform, tle, cells: pd.DataFrame, t0, t1, cfg, chunk=8000) -> pd.DataFrame:
    o = cfg["overpasses"]
    sensor = SENSOR_OF[platform]
    step = o["step_s"]
    when, tlat, tlon, alt, epoch = propagate(tle, t0, t1, step)
    P = unit_vectors(tlat, tlon)
    half = o["swath_km"][sensor] / 2.0
    margin = 7.5 * step  # ground speed ~6.7 km/s: half a step plus slack
    r_chord = 2 * np.sin((half + margin) / R_KM / 2)
    tree = cKDTree(P)
    C = unit_vectors(cells["lat"].to_numpy(), cells["lon"].to_numpy())
    t_sec = (when - when[0]).total_seconds().to_numpy()
    out = []
    for s0 in range(0, len(C), chunk):
        Cc = C[s0:s0 + chunk]
        lists = tree.query_ball_point(Cc, r_chord)
        ci = np.repeat(np.arange(len(Cc)), [len(x) for x in lists])
        if len(ci) == 0:
            continue
        ti = np.concatenate([np.sort(np.asarray(x, dtype=np.int64)) for x in lists])
        # Runs of consecutive track indices for the same cell = one pass.
        new = np.r_[True, (np.diff(ci) != 0) | (np.diff(ti) != 1)]
        run = np.cumsum(new) - 1
        ang = np.arccos(np.clip(np.einsum("ij,ij->i", Cc[ci], P[ti]), -1, 1))
        order = np.lexsort((ang, run))
        first = np.r_[True, np.diff(run[order]) != 0]
        best = order[first]  # row of the closest track point in each run
        bc, bk = ci[best], ti[best]
        # Refine on the two neighbouring segments.
        best_ang = ang[best].copy()
        best_t = t_sec[bk].astype(float)
        for nb in (bk - 1, bk + 1):
            ok = (nb >= 0) & (nb < len(P))
            nbc = np.clip(nb, 0, len(P) - 1)
            A, B, c = P[bk], P[nbc], Cc[bc]
            AB = B - A
            u = np.clip(np.einsum("ij,ij->i", c - A, AB) / np.maximum(np.einsum("ij,ij->i", AB, AB), 1e-18), 0, 1)
            Q = A + u[:, None] * AB
            Q /= np.linalg.norm(Q, axis=1)[:, None]
            a2 = np.arccos(np.clip(np.einsum("ij,ij->i", c, Q), -1, 1))
            better = ok & (a2 < best_ang)
            best_ang = np.where(better, a2, best_ang)
            best_t = np.where(better, t_sec[bk] + u * (t_sec[nbc] - t_sec[bk]), best_t)
        d_km = best_ang * R_KM
        keep = d_km <= half
        if not keep.any():
            continue
        bc, bk, best_ang, best_t, d_km = bc[keep], bk[keep], best_ang[keep], best_t[keep], d_km[keep]
        h = alt[bk]
        eta = scan_angle_deg(best_ang, h)
        ps, pt = pixel_size_km(eta, h, o["nadir_pixel_km"][sensor], sensor)
        times = when[0] + pd.to_timedelta(best_t, unit="s")
        sub = cells.iloc[s0:s0 + chunk].iloc[bc]
        nxt = np.clip(bk + 1, 0, len(P) - 1)
        prv = np.clip(bk - 1, 0, len(P) - 1)
        node = np.where(tlat[nxt] >= tlat[prv], "A", "D")
        sza = solar_zenith_deg(pd.DatetimeIndex(times), sub["lat"].to_numpy(), sub["lon"].to_numpy())
        out.append(pd.DataFrame({
            "cell_id": sub["cell_id"].to_numpy(), "cell_lat": sub["lat"].to_numpy(),
            "cell_lon": sub["lon"].to_numpy(), "platform": platform, "sensor": sensor,
            "overpass_time_utc": times, "node": node,
            "daynight": np.where(sza < 85, "D", "N"), "solar_zenith_deg": sza.astype("float32"),
            "cross_track_km": d_km.astype("float32"), "scan_angle_deg": eta.astype("float32"),
            "sat_alt_km": h.astype("float32"), "pixel_scan_km": ps.astype("float32"),
            "pixel_track_km": pt.astype("float32"), "pixel_area_km2": (ps * pt).astype("float32")}))
    df = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    df["tle_epoch_utc"] = epoch
    df["tle_source"] = tle["source"]
    return df


def target_cells(grid_daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Every cell with a detection, plus every cell inside the candidate pilot boxes."""
    from pipeline.grid import cell_id as make_id, cell_index
    deg = cfg["grid"]["cell_deg"]
    ids = set(grid_daily["cell_id"].unique())
    for x0, y0, x1, y1 in cfg["overpasses"]["pilot_boxes"].values():
        lons = np.arange(x0 + deg / 2, x1, deg)
        lats = np.arange(y0 + deg / 2, y1, deg)
        LO, LA = np.meshgrid(lons, lats)
        ix, iy = cell_index(LO.ravel(), LA.ravel(), deg)
        ids.update(make_id(ix, iy))
    ids = np.array(sorted(ids))
    iy = np.array([int(s[1:5]) for s in ids])
    ix = np.array([int(s[6:10]) for s in ids])
    return pd.DataFrame({"cell_id": ids, "lat": -90 + (iy + 0.5) * deg, "lon": -180 + (ix + 0.5) * deg})


def run(grid_daily: pd.DataFrame, det: pd.DataFrame, cfg: dict) -> dict:
    t0 = det["acq_datetime_utc"].min().floor("D") - pd.Timedelta(hours=1)
    t1 = det["acq_datetime_utc"].max().ceil("D") + pd.Timedelta(hours=1)
    cells = target_cells(grid_daily, cfg)
    frames, tles = [], {}
    for plat in cfg["overpasses"]["norad_ids"]:
        tle = fetch_tle(plat, cfg)
        df = passes_for_platform(plat, tle, cells, t0, t1, cfg)
        tles[plat] = {"source": tle["source"], "epoch": str(df["tle_epoch_utc"].iloc[0]) if len(df) else None,
                      "n_overpasses": len(df)}
        frames.append(df)
        print(f"[Step 6A] {plat}: {len(df):,} cell-overpasses (TLE epoch {tles[plat]['epoch']}, {tle['source']})")
    ov = pd.concat(frames, ignore_index=True)
    ov["cloud_adjusted"] = bool(cfg["overpasses"]["cloud_adjusted"])
    for c in ("cell_id", "platform", "sensor", "node", "daynight", "tle_source"):
        ov[c] = ov[c].astype("category")
    return {"overpasses": ov, "cells": cells, "tles": tles, "period": (t0, t1)}


def detection_match(det: pd.DataFrame, ov: pd.DataFrame, tol_min: float) -> pd.DataFrame:
    """For each detection: nearest computed overpass of its platform over its cell, and |Δt|."""
    d = det[["det_id", "cell_id", "platform", "acq_datetime_utc", "scan_km", "track_km"]].copy()
    d["cell_id"] = d["cell_id"].astype(str)
    o = ov[["cell_id", "platform", "overpass_time_utc", "scan_angle_deg", "pixel_area_km2",
            "pixel_scan_km", "pixel_track_km"]].copy()
    o["cell_id"] = o["cell_id"].astype(str)
    o["platform"] = o["platform"].astype(str)
    d["acq_datetime_utc"] = d["acq_datetime_utc"].astype("datetime64[ns, UTC]")
    o["overpass_time_utc"] = o["overpass_time_utc"].astype("datetime64[ns, UTC]")
    d = d.sort_values("acq_datetime_utc")
    o = o.sort_values("overpass_time_utc")
    m = pd.merge_asof(d, o, left_on="acq_datetime_utc", right_on="overpass_time_utc",
                      by=["cell_id", "platform"], direction="nearest")
    m["dt_min"] = (m["acq_datetime_utc"] - m["overpass_time_utc"]).dt.total_seconds() / 60
    m["matched"] = m["dt_min"].abs() <= tol_min
    return m
