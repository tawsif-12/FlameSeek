"""D73: one daytime-detector improvement round, Northern Australia box only.

- B04 (0.86 µm) is aggregated to the cached 2 km B07 grid and cropped exactly like
  `himawari.prepare_scan`. Alignment is checked by reproducing the cached B07.
- Variants run in memory with `himawari.contextual(..., day_fix=...)`; night is unchanged.
- Tuning uses Oct 29-30 only; Oct 31 - Nov 1 are scored once with the chosen settings.
- Success metrics (fixed before scoring the test days, see decisions D73):
  M1 share of VIIRS fire pixels at 12-14 h LST classed cloud (vs 00-02 h night level),
  M2 daytime detection rate of clear-observed VIIRS fire pixels by VIIRS FRP bin,
  M3 share of Himawari detections at 09-13 h LST never confirmed within 2 km.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import himawari as hw
from pipeline import naus_diagnostics as nd
from pipeline.config import ROOT

TRAIN = ["2026-10-29", "2026-10-30"]
TEST = ["2026-10-31", "2026-11-01"]
FRP_BINS = [0, 5, 20, np.inf]
GRID_REFLECTANCE = [0.25, 0.30, 0.35, 0.40, 0.45]
GRID_CAP = [6, 8, 10, 12, None]
SZA_MAX = 80.0


def b04_dir(cfg) -> Path:
    return nd.cache_dir(cfg) / "b04"


def raw_files(cfg, t: pd.Timestamp, band: str) -> list[Path]:
    res = "R10" if band == "B04" else "R20"
    folder = cfg["paths"]["raw_dir"] / "himawari" / cfg["window"]["name"] / t.strftime("%Y/%m/%d")
    return [folder / f"HS_H09_{t:%Y%m%d_%H%M}_{band}_FLDK_{res}_{s}.DAT.bz2" for s in ("S0610", "S0710")]


def prepare_b04(cfg) -> dict:
    """Cache B04 reflectance (0-1) on the cached 2 km grid; verifies alignment via B07."""
    from satpy import Scene
    r = nd.regional_cfg(cfg)
    boxes = list(r["himawari"]["regions"].values())
    bbox = (min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2,
            max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2)
    geom = np.load(nd.cache_dir(cfg) / "geometry.npz")
    shape = geom["longitude"].shape
    out = {"prepared": 0, "missing": [], "misaligned": []}
    for path in nd.scan_files(cfg):
        z = np.load(path)
        t = pd.Timestamp(str(z["nominal_utc"]))
        target = b04_dir(cfg) / t.strftime("%Y/%m/%d") / t.strftime("%H%M.npz")
        if target.exists():
            out["prepared"] += 1
            continue
        if not (np.nanmin(z["sza_deg"]) < 90):
            continue  # night scan: no reflectance needed
        files = raw_files(cfg, t, "B04") + raw_files(cfg, t, "B07")
        if not all(f.exists() for f in files):
            out["missing"].append(str(t))
            continue
        scn = Scene(reader="ahi_hsd", filenames=[str(f) for f in files])
        scn.load(["B04", "B07"])
        low = scn.resample(scn["B07"].attrs["area"], resampler="native")
        crop = low.crop(ll_bbox=bbox)
        b04 = np.asarray(crop["B04"].values, dtype=np.float32) / 100.0
        b07 = np.asarray(crop["B07"].values, dtype=np.float32)
        if b04.shape != shape or not np.allclose(b07, z["b07"], equal_nan=True, atol=1e-3):
            out["misaligned"].append(str(t))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(target, b04=b04, nominal_utc=str(t))
        out["prepared"] += 1
    return out


def load_b04(cfg, t: pd.Timestamp):
    p = b04_dir(cfg) / t.strftime("%Y/%m/%d") / t.strftime("%H%M.npz")
    return np.load(p)["b04"] if p.exists() else None


def run(cfg, variants: dict, dates=None):
    """variants: name -> day_fix params without 'reflectance' (None = baseline).
    Returns per-variant (cases with status/detected, fire pixels, scan stats)."""
    r = nd.regional_cfg(cfg)
    settings = r["himawari"]
    geom = dict(np.load(nd.cache_dir(cfg) / "geometry.npz"))
    constant = hw.derive_mir_constant(r)
    box = geom["box_Northern_Australia"]
    cases = pd.read_csv(ROOT / "outputs/phase3c_naus/viirs_cases.csv", low_memory=False,
                        usecols=["fire_id", "platform", "acq_datetime_utc", "scan_time", "pixel_id", "lst_h",
                                 "frp_mw", "daynight", "latitude", "longitude", "box_Northern_Australia"])
    cases = cases[cases.box_Northern_Australia.astype(str).eq("True")].copy()
    cases["scan_time"] = pd.to_datetime(cases.scan_time, utc=True)
    out = {k: {"cases": [], "fires": [], "stats": [], "no_b04_day_scans": 0} for k in variants}
    for path in nd.scan_files(cfg):
        frame = dict(np.load(path))
        t = pd.Timestamp(str(frame.pop("nominal_utc")))
        if dates is not None and str(t.date()) not in dates:
            continue
        frame.pop("observation_start_utc", None)
        geom["vza_deg"] = frame.pop("vza_deg", geom["vza_deg"])
        b04 = load_b04(cfg, t)
        is_day = np.nanmin(frame["sza_deg"][box]) < 90
        which = cases.scan_time.eq(t)
        pix = cases.loc[which, "pixel_id"].to_numpy(int)
        for name, fix in variants.items():
            day_fix = None
            if fix is not None:
                if b04 is None and is_day:
                    out[name]["no_b04_day_scans"] += 1
                refl = b04 if b04 is not None else np.full(frame["b07"].shape, np.nan, np.float32)
                day_fix = {**fix, "reflectance": refl}
            res = hw.contextual(frame, geom, settings, constant, day_fix=day_fix)
            out[name]["stats"].extend(hw.scan_stats(res, geom, t, r))
            sel = res["fire"] & box
            row, col = np.where(sel)
            d = pd.DataFrame(dict(acq_datetime_utc=t, pixel_id=row * sel.shape[1] + col,
                                  longitude=geom["longitude"][row, col], latitude=geom["latitude"][row, col],
                                  frp_mw=res["frp_mw"][row, col], daynight=np.where(res["day"][row, col], "D", "N")))
            out[name]["fires"].append(d)
            c = cases.loc[which].copy()
            c["status"] = res["status"].flat[pix]
            c["detected"] = hw.nearby(c, d, 30, settings["match_radius_km"]) if len(d) else False
            out[name]["cases"].append(c)
    result = {}
    for name, v in out.items():
        fires = pd.concat(v["fires"], ignore_index=True)
        fires["lst_h"] = [hw.lst(t, lon) for t, lon in zip(fires.acq_datetime_utc, fires.longitude)]
        result[name] = {"cases": pd.concat(v["cases"], ignore_index=True), "fires": fires,
                        "stats": pd.DataFrame(v["stats"]), "no_b04_day_scans": v["no_b04_day_scans"]}
    return result


def metrics(res: dict, refs: pd.DataFrame, dates) -> dict:
    c = res["cases"][res["cases"].scan_time.dt.strftime("%Y-%m-%d").isin(dates)].copy()
    c["h"] = np.floor(c.lst_h).astype(int)
    midday = c[c.h.isin([12, 13, 14])]
    night = c[c.h.isin([0, 1, 2])]
    obs = c[c.status.isin([0, 1]) & c.daynight.eq("D")]
    rates = []
    for lo, hi in zip(FRP_BINS[:-1], FRP_BINS[1:]):
        s = obs[(obs.frp_mw >= lo) & (obs.frp_mw < hi)]
        rates.append({"frp_bin_mw": [lo, None if np.isinf(hi) else hi], "n": int(len(s)),
                      "rate": float(s.detected.mean()) if len(s) else None})
    f = res["fires"][res["fires"].acq_datetime_utc.dt.strftime("%Y-%m-%d").isin(dates)].copy()
    f["h"] = np.floor(f.lst_h).astype(int)
    mid = f[f.h.isin([9, 10, 11, 12, 13])]
    conf = nd.location_confirmed(mid, refs, 2) if len(mid) else np.zeros(0, bool)
    return {"M1_cloud_share_viirs_12_14h": float((midday.status == 2).mean()) if len(midday) else None,
            "M1_n": int(len(midday)),
            "M1_night_level_00_02h": float((night.status == 2).mean()) if len(night) else None,
            "M2_day_detection_by_frp": rates,
            "M3_never_confirmed_share_09_13h": float(1 - conf.mean()) if len(mid) else None,
            "M3_n": int(len(mid))}


def objective(m: dict) -> float:
    """Training objective: lower is better. Equal weights of M1 and M3."""
    a, b = m["M1_cloud_share_viirs_12_14h"], m["M3_never_confirmed_share_09_13h"]
    return (a if a is not None else 1.0) + (b if b is not None else 1.0)


def success(before: dict, after: dict) -> dict:
    """Pre-registered checks (D73)."""
    m1b, m1a, night = before["M1_cloud_share_viirs_12_14h"], after["M1_cloud_share_viirs_12_14h"], before["M1_night_level_00_02h"]
    c1 = None if None in (m1b, m1a, night) else bool(m1a <= m1b - 0.5 * (m1b - night))
    ra = after["M2_day_detection_by_frp"]
    rb = before["M2_day_detection_by_frp"]
    top_a, top_b, low_a = ra[-1]["rate"], rb[-1]["rate"], ra[0]["rate"]
    evaluable = ra[-1]["n"] >= 20 and ra[0]["n"] >= 20
    c2 = None if not evaluable or None in (top_a, top_b, low_a) else bool(top_a > low_a and top_a > top_b)
    m3b, m3a = before["M3_never_confirmed_share_09_13h"], after["M3_never_confirmed_share_09_13h"]
    c3 = None if None in (m3b, m3a) else bool(m3a <= m3b - 0.20 and m3a <= 0.5)
    return {"C1_cloud_gap_halved": c1, "C2_rate_rises_with_frp_and_top_bin_up": c2,
            "C3_never_confirmed_down_20pts_and_le_50pct": c3,
            "all_clear": bool(c1 and c2 and c3)}
