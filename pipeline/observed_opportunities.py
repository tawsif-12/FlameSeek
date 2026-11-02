"""Fallback observation opportunities without orbital elements (decisions.md D69).

Label: "detection-conditioned opportunities – lower bound on O_s".

When no TLE close to a window exists, each platform's passes are rebuilt from
the window's own detections:
1. Detections of one platform separated by less than `pass_gap_min` form one pass,
   cut into segments of at most `max_pass_min`.
2. Each detection's pixel size gives its cross-track ground distance from nadir
   (MODIS: along-scan size; VIIRS: along-track size, which grows monotonically with
   scan angle, whereas the aggregated along-scan size does not). The FIRMS
   rounding of that size is kept as an interval.
3. The nadir track is a line with the local ground-track slope of a circular
   sun-synchronous orbit (inclination, period). Its offset is every value that
   keeps the largest number of detections consistent with their intervals.
   When several offsets fit (left/right ambiguity, coarse rounding), a cell
   counts only if it lies inside the swath under ALL of them.
4. Along-track, a pass covers only the latitude span of its own detections.
5. Time over each cell follows from the orbital latitude rate, anchored on the
   detection times. Scan angle and pixel size use the same geometry as Step 6A.

Every step can only drop real opportunities, never add them: passes with no
detection are missed, and the along-track and cross-track extents are cut to what
the detections prove. The result is a lower bound on O_s. Used as a λ denominator,
it biases λ upward. In the MODIS detection-curve sample, Aqua passes with no
detections at all are missing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.overpasses import (R_KM, SENSOR_OF, pixel_size_km, scan_angle_deg,
                                 solar_zenith_deg)

LABEL = "detection-conditioned opportunities – lower bound on O_s"
SIDEREAL_DAY_MIN = 1436.068
KM_PER_DEG = np.pi * R_KM / 180


# ------------------------------------------------------------- geometry ------
def ground_distance_km(eta_deg, alt_km):
    """Inverse of the scan-angle relation: nadir-to-pixel ground distance."""
    eta = np.radians(eta_deg)
    r = R_KM + alt_km
    return (np.arcsin(np.clip(r / R_KM * np.sin(eta), -1, 1)) - eta) * R_KM


def size_curve(sensor, alt_km, nadir_km, max_eta=56.5):
    """Monotonic pixel-size curve used to invert size -> scan angle."""
    eta = np.linspace(0, max_eta, 2000)
    scan, track = pixel_size_km(eta, alt_km, nadir_km, sensor)
    size = scan if sensor == "MODIS" else track
    return eta, np.maximum.accumulate(size)


def distance_interval(size, quantum, sensor, alt_km, nadir_km):
    """Cross-track ground distance interval (km) for a FIRMS pixel size rounded to `quantum`."""
    eta, s = size_curve(sensor, alt_km, nadir_km)
    lo = np.interp(np.asarray(size) - quantum / 2, s, eta, left=0, right=eta[-1])
    hi = np.interp(np.asarray(size) + quantum / 2, s, eta, left=0, right=eta[-1])
    return ground_distance_km(lo, alt_km), ground_distance_km(hi, alt_km)


def track_terms(lat_deg, incl_deg, period_min):
    """Ascending-node ground-track slope dlon/dlat and |cos beta| at latitude."""
    phi = np.radians(lat_deg)
    sinb = np.clip(np.cos(np.radians(incl_deg)) / np.cos(phi), -1, 1)
    cosb = np.sqrt(1 - sinb ** 2)
    k_asc = (sinb / cosb) / np.cos(phi) - (period_min / SIDEREAL_DAY_MIN) / cosb
    return k_asc, cosb


def nadir_lon(c, lat, lat0, sign, incl, period):
    """Nadir longitude at `lat` for a track through (lat0, c); midpoint slope."""
    k, _ = track_terms((lat + lat0) / 2, incl, period)
    return c + sign * k * (lat - lat0)


def cross_km(lon, lat, nlon, incl, period):
    _, cosb = track_terms(lat, incl, period)
    dlon = (lon - nlon + 180) % 360 - 180
    return np.abs(dlon) * KM_PER_DEG * np.cos(np.radians(lat)) * cosb


# ---------------------------------------------------------------- passes -----
def split_passes(d: pd.DataFrame, gap_min: float, max_min: float = np.inf) -> pd.Series:
    """Pass id: a new pass starts after a gap > gap_min, or once a pass reaches max_min
    (keeps each segment short enough for a straight local ground track)."""
    t = d["acq_datetime_utc"].sort_values()
    mins = (t - t.iloc[0]).dt.total_seconds().to_numpy() / 60
    ids, start, cur = np.empty(len(t), dtype=np.int64), mins[0] if len(mins) else 0, 0
    for i, m in enumerate(mins):
        if i and (m - mins[i - 1] > gap_min or m - start > max_min):
            cur += 1
            start = m
        ids[i] = cur
    return pd.Series(ids, index=t.index).reindex(d.index)


def fit_pass(p: pd.DataFrame, plat: str, o: dict, rng) -> dict | None:
    sensor = SENSOR_OF[plat]
    alt, incl, period = o["altitude_km"][plat], o["inclination_deg"][plat], o["period_min"][plat]
    if len(p) > o["max_fit_detections"]:
        p = p.iloc[rng.choice(len(p), o["max_fit_detections"], replace=False)]
    size = p["scan_km"] if sensor == "MODIS" else p["track_km"]
    dlo, dhi = distance_interval(size.to_numpy(), o["size_quantum_km"][sensor], sensor, alt,
                                 o["nadir_pixel_km"][sensor])
    dlo, dhi = dlo - o["distance_slack_km"], dhi + o["distance_slack_km"]
    day = (p["daynight"] == "D").mean() >= 0.5
    node = o["day_node"][plat] if day else ("D" if o["day_node"][plat] == "A" else "A")
    sign = 1.0 if node == "A" else -1.0
    lat, lon = p["latitude"].to_numpy(), p["longitude"].to_numpy()
    lat0 = float(np.median(lat))
    half = o["swath_km"][sensor] / 2
    span = half / (KM_PER_DEG * max(np.cos(np.radians(lat0)), 0.2)) + 1
    cs = np.arange(lon.min() - span, lon.max() + span, o["offset_step_deg"])
    nl = nadir_lon(cs[None, :], lat[:, None], lat0, sign, incl, period)
    dist = cross_km(lon[:, None], lat[:, None], nl, incl, period)
    ok = (dist >= dlo[:, None]) & (dist <= dhi[:, None])
    count = ok.sum(axis=0)
    best = count.max()
    if best < o["min_consistent_share"] * len(p):
        return None
    good = cs[count == best]
    # Anchor time: detections' along-track position ~ their latitude.
    _, cosb = track_terms(lat0, incl, period)
    rate = 360.0 / (period * 60) * cosb * sign  # deg latitude per second
    t = (p["acq_datetime_utc"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy()
    t0 = float(np.mean(t - (lat - lat0) / rate))
    return dict(platform=plat, sensor=sensor, node=node, c_min=float(good.min()), c_max=float(good.max()),
                lat0=lat0, sign=sign, lat_min=float(lat.min()), lat_max=float(lat.max()), t0=t0,
                rate=float(rate), n_det=int(len(p)), n_consistent=int(best))


def pass_cells(fit: dict, cells: pd.DataFrame, o: dict) -> pd.DataFrame:
    plat = fit["platform"]
    alt, incl, period = o["altitude_km"][plat], o["inclination_deg"][plat], o["period_min"][plat]
    half = o["swath_km"][fit["sensor"]] / 2
    c = cells[cells["lat"].between(fit["lat_min"], fit["lat_max"])]
    if c.empty:
        return pd.DataFrame()
    lat, lon = c["lat"].to_numpy(), c["lon"].to_numpy()
    d_all = [cross_km(lon, lat, nadir_lon(cc, lat, fit["lat0"], fit["sign"], incl, period), incl, period)
             for cc in (fit["c_min"], fit["c_max"])]
    inside = (d_all[0] <= half) & (d_all[1] <= half)
    if not inside.any():
        return pd.DataFrame()
    c, lat, lon = c[inside], lat[inside], lon[inside]
    mid = (fit["c_min"] + fit["c_max"]) / 2
    d = cross_km(lon, lat, nadir_lon(mid, lat, fit["lat0"], fit["sign"], incl, period), incl, period)
    eta = scan_angle_deg(d / R_KM, alt)
    ps, pt = pixel_size_km(eta, alt, o["nadir_pixel_km"][fit["sensor"]], fit["sensor"])
    times = pd.to_datetime(fit["t0"] + (lat - fit["lat0"]) / fit["rate"], unit="s", utc=True)
    sza = solar_zenith_deg(pd.DatetimeIndex(times), lat, lon)
    return pd.DataFrame({
        "cell_id": c["cell_id"].to_numpy(), "cell_lat": lat, "cell_lon": lon, "platform": plat,
        "sensor": fit["sensor"], "overpass_time_utc": times, "node": fit["node"],
        "daynight": np.where(sza < 85, "D", "N"), "solar_zenith_deg": sza.astype("float32"),
        "cross_track_km": d.astype("float32"), "scan_angle_deg": eta.astype("float32"),
        "sat_alt_km": np.float32(alt), "pixel_scan_km": ps.astype("float32"),
        "pixel_track_km": pt.astype("float32"), "pixel_area_km2": (ps * pt).astype("float32"),
        "offset_ambiguity_km": np.float32(abs(fit["c_max"] - fit["c_min"]) * KM_PER_DEG
                                          * np.cos(np.radians(fit["lat0"])))})


def run(det: pd.DataFrame, cells: pd.DataFrame, cfg: dict, platforms=None) -> dict:
    o = {**cfg["overpasses"], **cfg["observed_opportunities"]}
    rng = np.random.default_rng(o["seed"])
    d = det.copy()
    d["acq_datetime_utc"] = pd.to_datetime(d["acq_datetime_utc"], utc=True)
    platforms = platforms or list(o["altitude_km"])
    frames, fits, dropped = [], [], 0
    for plat in platforms:
        dp = d[d["platform"].astype(str).eq(plat)]
        if dp.empty:
            continue
        dp = dp.assign(pass_id=split_passes(dp, o["pass_gap_min"], o["max_pass_min"]))
        for _, p in dp.groupby("pass_id"):
            fit = fit_pass(p, plat, o, rng)
            if fit is None:
                dropped += 1
                continue
            fits.append(fit)
            frames.append(pass_cells(fit, cells, o))
    ov = pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()
    if len(ov):
        ov["tle_epoch_utc"] = pd.NaT
        ov["tle_source"] = "none: " + LABEL
        ov["opportunity_basis"] = LABEL
        ov["cloud_adjusted"] = bool(cfg["overpasses"]["cloud_adjusted"])
    return {"overpasses": ov, "passes": pd.DataFrame(fits), "n_passes_dropped_inconsistent": dropped}


def compare(fallback: pd.DataFrame, reference: pd.DataFrame, cell_ids, t0, t1, tol_min: float) -> dict:
    """Fallback vs TLE-based cell-overpasses for the same cells and period.

    precision: share of fallback cell-overpasses with a TLE pass of the same platform over
    the same cell within tol_min. coverage_ratio: matched fallback rows / TLE rows, i.e.
    how much of the true O_s the lower bound recovers.
    """
    ids = set(map(str, cell_ids))
    frames = []
    for frame in (fallback, reference):
        x = frame[["cell_id", "platform", "overpass_time_utc", "scan_angle_deg"]].copy()
        x["cell_id"] = x["cell_id"].astype(str)
        x["platform"] = x["platform"].astype(str)
        x["overpass_time_utc"] = pd.to_datetime(x["overpass_time_utc"], utc=True).astype("datetime64[ns, UTC]")
        frames.append(x[x["cell_id"].isin(ids) & x["overpass_time_utc"].between(t0, t1)])
    f, r = frames
    out = {}
    for plat, fp in f.groupby("platform"):
        rp = r[r["platform"].eq(plat)].sort_values("overpass_time_utc")
        if rp.empty:
            continue
        m = pd.merge_asof(fp.sort_values("overpass_time_utc"),
                          rp.rename(columns={"overpass_time_utc": "t_ref", "scan_angle_deg": "eta_ref"})[["cell_id", "t_ref", "eta_ref"]],
                          left_on="overpass_time_utc", right_on="t_ref", by="cell_id", direction="nearest")
        dt = (m["overpass_time_utc"] - m["t_ref"]).dt.total_seconds().abs() / 60
        hit = dt <= tol_min
        out[plat] = {"n_fallback": int(len(fp)), "n_reference": int(len(rp)),
                     "precision": float(hit.mean()),
                     "coverage_ratio": float(hit.sum() / len(rp)),
                     "median_abs_dt_min": float(dt[hit].median()) if hit.any() else None,
                     "median_abs_dscan_deg": float((m.loc[hit, "scan_angle_deg"].abs()
                                                    - m.loc[hit, "eta_ref"].abs()).abs().median()) if hit.any() else None}
    return out
