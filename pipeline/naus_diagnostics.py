"""Northern Australia diurnal-fit diagnostics (decisions.md D71). Diagnose only.

Nothing here writes params/ or changes detector thresholds. Counterfactual
threshold runs and refits are computed in memory and reported.

Terms used:
- reference-observed hour: a local-solar hour in which some polar-orbiter
  (VIIRS / MODIS) detection exists in the box. "Unmatched" is only interpretable
  as possible commission in those hours; elsewhere no reference could match.
- location-confirmed: a Himawari pixel with any reference detection within
  `match_radius_km` at ANY time in the window (the place burns, the time may differ).
- persistent unmatched location: a native Himawari pixel with >= `PERSIST_MIN_DET`
  detections on >= `PERSIST_MIN_DAYS` UTC days, never time-matched, and never
  location-confirmed.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import diurnal
from pipeline import himawari as hw
from pipeline.config import ROOT

PERSIST_MIN_DET = 3
PERSIST_MIN_DAYS = 2
GLINT_DEG = 12.0
BOX = [125.0, -20.0, 138.0, -11.0]


def regional_cfg(cfg):
    r = deepcopy(cfg)
    r["himawari"]["regions"] = {"Northern_Australia": BOX}
    r["himawari"]["segments"] = cfg["phase3c"]["northern_australia"]["segments"]
    return r


def cache_dir(cfg) -> Path:
    return cfg["paths"]["window_interim"] / "phase3c_naus" / "himawari"


def scan_files(cfg):
    return sorted(cache_dir(cfg).glob("[0-9][0-9][0-9][0-9]/*/*/*.npz"))


# --------------------------------------------------------------- geometry ----
def satellite_angles(lon, lat, sat_lon=140.7, sat_alt_km=35785.863):
    """Satellite zenith and azimuth (deg, azimuth clockwise from north) seen from the ground."""
    R = 6378.137
    la, lo = np.radians(lat), np.radians(lon)
    ground = R * np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    s = np.radians(sat_lon)
    sat = (R + sat_alt_km) * np.array([np.cos(s), np.sin(s), 0.0]).reshape(3, *([1] * np.ndim(lat)))
    v = sat - ground
    east = np.stack([-np.sin(lo), np.cos(lo), np.zeros_like(lo)])
    north = np.stack([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
    up = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    e, n, u = (v * east).sum(0), (v * north).sum(0), (v * up).sum(0)
    zen = np.degrees(np.arccos(np.clip(u / np.sqrt(e ** 2 + n ** 2 + u ** 2), -1, 1)))
    return zen, np.degrees(np.arctan2(e, n)) % 360


def glint_angle_deg(sun_zen, sun_az, sat_zen, sat_az):
    """Angle between the view direction and the specular reflection of the sun."""
    ts, tv = np.radians(sun_zen), np.radians(sat_zen)
    dphi = np.radians(sat_az - sun_az)
    return np.degrees(np.arccos(np.clip(np.cos(ts) * np.cos(tv) - np.sin(ts) * np.sin(tv) * np.cos(dphi), -1, 1)))


def sun_azimuth(times, lon, lat):
    from pyorbital.astronomy import get_alt_az
    _, az = get_alt_az(pd.DatetimeIndex(times).tz_convert(None).to_pydatetime(), np.asarray(lon), np.asarray(lat))
    return np.degrees(az) % 360


# ---------------------------------------------------------------- per scan ---
def scan_rows(frame, geom, result, cand, t, settings):
    """Per pixel-local-solar-hour aggregates for one scan (box, valid view, land)."""
    box = geom["box_Northern_Australia"] & (geom["vza_deg"] <= settings["max_vza_deg"]) & geom["land"]
    hour = np.floor(hw.lst(t, geom["longitude"])).astype(int)
    clear = box & result["clear"]
    bg = clear & ~cand
    b7 = frame["b07"]
    rows = []
    for h in np.unique(hour[box]):
        m = hour == h
        c, g = clear & m, bg & m
        day = result["day"] & m & box
        rows.append(dict(acq_datetime_utc=t, lst_hour=int(h), n_valid_land=int((box & m).sum()),
                         n_clear=int(c.sum()), day_share=float(day.sum() / max((box & m).sum(), 1)),
                         n_bg=int(g.sum()), b07_bg_mean=float(b7[g].mean()) if g.any() else np.nan,
                         b07_bg_std=float(b7[g].std()) if g.sum() > 1 else np.nan,
                         n_candidates=int((cand & box & m).sum())))
    return rows


def candidates(frame, geom, settings, day):
    dc = settings["detection"]
    d = frame["b07"] - frame["b14"]
    return (frame["b07"] > np.where(day, dc["candidate_day_k"], dc["candidate_night_k"])) & (d > dc["candidate_delta_k"])


def run_scans(cfg):
    """Baseline (stored thresholds) plus two counterfactual threshold runs, in memory."""
    r = regional_cfg(cfg)
    settings = r["himawari"]
    geom = dict(np.load(cache_dir(cfg) / "geometry.npz"))
    constant = hw.derive_mir_constant(r)
    variants = {"baseline": settings}
    for name, change in [("day_at_300K", {"candidate_day_k": settings["detection"]["candidate_night_k"]}),
                         ("night_at_310K", {"candidate_night_k": settings["detection"]["candidate_day_k"]})]:
        s = deepcopy(settings)
        s["detection"].update(change)
        variants[name] = s
    hourly, fires, stats = [], [], {k: [] for k in variants}
    for path in scan_files(cfg):
        frame = dict(np.load(path))
        t = pd.Timestamp(str(frame.pop("nominal_utc")))
        frame.pop("observation_start_utc", None)
        geom["vza_deg"] = frame.pop("vza_deg", geom["vza_deg"])
        for name, s in variants.items():
            res = hw.contextual(frame, geom, s, constant)
            stats[name].extend(hw.scan_stats(res, geom, t, r))
            box = res["fire"] & geom["box_Northern_Australia"]
            row, col = np.where(box)
            fires.append(pd.DataFrame(dict(variant=name, acq_datetime_utc=t, pixel_id=row * box.shape[1] + col,
                                           longitude=geom["longitude"][row, col], latitude=geom["latitude"][row, col],
                                           frp_mw=res["frp_mw"][row, col], daynight=np.where(res["day"][row, col], "D", "N"),
                                           sza_deg=frame["sza_deg"][row, col], b07=frame["b07"][row, col],
                                           bg_window=res["bg_window"][row, col])))
            if name == "baseline":
                cand = candidates(frame, geom, s, res["day"]) & res["clear"] & geom["land"]
                hourly.extend(scan_rows(frame, geom, res, cand, t, s))
    fires = pd.concat(fires, ignore_index=True)
    fires["lst_h"] = [hw.lst(t, lon) for t, lon in zip(fires.acq_datetime_utc, fires.longitude)]
    return pd.DataFrame(hourly), fires, {k: pd.DataFrame(v) for k, v in stats.items()}, geom


# ------------------------------------------------------------ references -----
def references(cfg):
    r = pd.read_parquet(cfg["paths"]["window_processed"] / "detections_clean.parquet",
                        columns=["platform", "sensor", "longitude", "latitude", "lst_h", "acq_datetime_utc", "frp_mw"])
    w, s, e, n = BOX
    r = r[r.longitude.between(w - .1, e + .1) & r.latitude.between(s - .1, n + .1)].copy()
    r["acq_datetime_utc"] = pd.to_datetime(r.acq_datetime_utc, utc=True)
    return r


def location_confirmed(fires, refs, radius_km):
    from sklearn.neighbors import BallTree
    if refs.empty:
        return np.zeros(len(fires), bool)
    tree = BallTree(np.radians(refs[["latitude", "longitude"]].to_numpy()), metric="haversine")
    return tree.query_radius(np.radians(fires[["latitude", "longitude"]].to_numpy()), r=radius_km / 6371.0088,
                             count_only=True) > 0


def persistent_locations(f: pd.DataFrame) -> pd.DataFrame:
    """Native pixels with repeated unmatched, never-confirmed detections."""
    d = f.assign(utc_day=pd.to_datetime(f.acq_datetime_utc, utc=True).dt.strftime("%Y-%m-%d"))
    g = d.groupby("pixel_id").agg(n_det=("frp_mw", "size"), n_days=("utc_day", "nunique"),
                                  n_time_matched=("reference_match", "sum"), confirmed=("location_confirmed", "max"),
                                  longitude=("longitude", "mean"), latitude=("latitude", "mean"),
                                  day_share=("daynight", lambda x: float((x == "D").mean())),
                                  median_frp_mw=("frp_mw", "median"), lst_min=("lst_h", "min"), lst_max=("lst_h", "max"),
                                  median_glint_deg=("glint_deg", "median"))
    keep = (g.n_det >= PERSIST_MIN_DET) & (g.n_days >= PERSIST_MIN_DAYS) & (g.n_time_matched == 0) & ~g.confirmed
    return g[keep].sort_values(["n_det", "n_days"], ascending=False)


# ---------------------------------------------------------------- refits -----
def refit(stats: pd.DataFrame, fires: pd.DataFrame, keep: pd.Series, settings) -> dict:
    """Diurnal refit with scan FRP recomputed from a subset of the baseline fire pixels."""
    sub = fires[keep.to_numpy()].groupby("acq_datetime_utc").frp_mw.sum()
    s = stats.copy()
    s["acq_datetime_utc"] = pd.to_datetime(s.acq_datetime_utc, utc=True)
    s["frp_mw"] = np.where(s.frp_mw.notna(), s.acq_datetime_utc.map(sub).fillna(0).to_numpy(), np.nan)
    model, _ = diurnal.fit_region(s, settings)
    return summarize(model)


def summarize(model: dict) -> dict:
    if not model.get("fitted"):
        return {"fitted": False, "reason": model.get("reason"), "n_points": model.get("sample_size")}
    p, i = model["parameters"], model["intervals"]
    at_bound = bool(p["sigma"] >= 11.99 or p["sigma"] <= .26 or p["h"] <= .01 or p["h"] >= 23.99)
    return {"fitted": True, "peak_h": p["h"], "peak_90": i["h"], "sigma_h": p["sigma"], "sigma_90": i["sigma"],
            "base_over_peak": p["base"] / p["peak"] if p["peak"] > 0 else None, "n_points": model["sample_size"],
            "n_days": model["n_days"], "parameter_at_bound": at_bound}


def hourly_table(hourly, fires_base, cases, refs):
    h = hourly.groupby("lst_hour").agg(n_scan_slices=("acq_datetime_utc", "nunique"), n_clear=("n_clear", "sum"),
                                       n_valid_land=("n_valid_land", "sum"), day_share=("day_share", "mean"),
                                       n_candidates=("n_candidates", "sum"), n_bg=("n_bg", "sum"))
    w = hourly.dropna(subset=["b07_bg_mean"])
    wt = w.n_bg
    h["b07_bg_mean_k"] = (w.b07_bg_mean * wt).groupby(w.lst_hour).sum() / wt.groupby(w.lst_hour).sum()
    h["b07_bg_std_k"] = (w.b07_bg_std * wt).groupby(w.lst_hour).sum() / wt.groupby(w.lst_hour).sum()
    fb = fires_base.assign(lst_hour=np.floor(fires_base.lst_h).astype(int))
    agg = fb.groupby("lst_hour").agg(fire_pixels=("frp_mw", "size"), frp_sum_mw=("frp_mw", "sum"),
                                     unmatched=("reference_match", lambda x: int((~x).sum())),
                                     unconfirmed=("location_confirmed", lambda x: int((~x).sum())),
                                     location_confirmed=("location_confirmed", "sum"))
    h = h.join(agg).fillna({"fire_pixels": 0, "frp_sum_mw": 0, "unmatched": 0, "unconfirmed": 0, "location_confirmed": 0})
    h["fires_per_million_clear"] = h.fire_pixels / h.n_clear * 1e6
    h["frp_mw_per_million_clear"] = h.frp_sum_mw / h.n_clear * 1e6
    ref_hours = np.floor(refs.lst_h).astype(int).value_counts()
    h["reference_detections"] = ref_hours.reindex(h.index).fillna(0).astype(int)
    h["reference_observed_hour"] = h.reference_detections > 0
    h["unmatched_share"] = h.unmatched / h.fire_pixels.where(h.fire_pixels > 0)
    h["unconfirmed_share"] = h.unconfirmed / h.fire_pixels.where(h.fire_pixels > 0)
    c = cases[cases.status.isin([0, 1])].assign(lst_hour=lambda x: np.floor(x.lst_h).astype(int))
    vr = c.groupby("lst_hour").agg(viirs_observed=("detected", "size"), viirs_detected=("detected", "sum"))
    h = h.join(vr)
    h["viirs_detection_rate"] = h.viirs_detected / h.viirs_observed
    return h.reset_index()


def threshold_effect(fires):
    f = fires.assign(lst_hour=np.floor(fires.lst_h).astype(int))
    t = f.pivot_table(index="lst_hour", columns="variant", values="frp_mw", aggfunc=["size", "sum"], fill_value=0)
    t.columns = [f"{'n' if a == 'size' else 'frp'}_{b}" for a, b in t.columns]
    return t.reset_index()


def plot(h, fits, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 7.5), sharex=True)
    x = h.lst_hour + .5
    night = h.day_share < .5
    for a in ax.flat:
        for hh in h.lst_hour[night]:
            a.axvspan(hh, hh + 1, color="0.92", zorder=0)
        for hh in h.lst_hour[~h.reference_observed_hour]:
            a.axvspan(hh, hh + 1, ymin=0, ymax=.04, color="#d9534f", zorder=1)
    ax[0, 0].bar(x, h.fire_pixels, width=.8, color="#2a78d6")
    ax[0, 0].set(ylabel="Himawari fire pixels", title="Fire pixels (grey = night; red tick = no polar reference)")
    a = ax[0, 1]
    a.bar(x, h.frp_mw_per_million_clear, width=.8, color="#eb6834", label="FRP per 1e6 clear pixels")
    a2 = a.twinx()
    a2.plot(x, h.frp_sum_mw, "k.-", label="summed FRP (MW)")
    a.set(ylabel="MW per 1e6 clear pixels", title="FRP: area-normalized (bars) and summed (line)")
    a2.set_ylabel("Summed FRP (MW)")
    for name, f in fits.items():
        if f.get("fitted"):
            a.axvline(f["peak_h"], ls="--", lw=1, label=f"peak: {name} {f['peak_h']:.1f} h")
    a.legend(fontsize=7, loc="upper left")
    ax[1, 0].bar(x, h.n_clear / 1e3, width=.8, color="0.5")
    ax[1, 0].set(ylabel="Clear valid land pixels (thousands)", xlabel="Local solar hour", title="Clear observed pixels")
    a = ax[1, 1]
    a.plot(x, h.viirs_detection_rate, "o-", color="#2a78d6", label="Himawari detects VIIRS fire")
    a.set(ylim=(0, 1), ylabel="Detection rate", xlabel="Local solar hour", title="VIIRS detection rate / background B07")
    a3 = a.twinx()
    a3.plot(x, h.b07_bg_std_k, "s--", color="#eb6834", ms=3, label="background B07 std (K)")
    a3.set_ylabel("Background B07 std (K)")
    a.legend(fontsize=7, loc="upper left")
    a3.legend(fontsize=7, loc="upper right")
    ax[1, 1].set_xlim(0, 24)
    for a in ax.flat:
        a.set_xticks(range(0, 25, 3))
    fig.suptitle("Northern Australia — diurnal diagnostics, 29 Oct–2 Nov 2026 (method demonstration region)")
    fig.tight_layout()
    out = ROOT / "outputs/figures/naus_diurnal_diagnostics.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def refit_area_normalized(stats: pd.DataFrame, fires: pd.DataFrame, keep, settings) -> dict:
    """Diagnostic refit on FRP per clear valid land area, using every scan with any clear land
    (removes the 0.3 clear-fraction filter that drops all 08-15 h scans)."""
    sub = fires[np.asarray(keep)].groupby("acq_datetime_utc").frp_mw.sum()
    s = stats.copy()
    s["acq_datetime_utc"] = pd.to_datetime(s.acq_datetime_utc, utc=True)
    clear_km2 = s.clear_sky_fraction * s.valid_land_area_km2
    s["frp_mw"] = np.where(clear_km2 > 0, s.acq_datetime_utc.map(sub).fillna(0).to_numpy() / clear_km2, np.nan)
    s["clear_sky_fraction"] = np.where(clear_km2 > 0, 1.0, 0.0)
    model, _ = diurnal.fit_region(s, settings)
    return summarize(model)


def top_unmatched_locations(f: pd.DataFrame, n=10, cell_deg=0.05) -> pd.DataFrame:
    """Locations (cell_deg grid) with the most detections that are neither time-matched nor
    ever confirmed at that location (candidates for static hot sources / glint)."""
    d = f[~f.reference_match & ~f.location_confirmed].assign(utc_day=pd.to_datetime(f.acq_datetime_utc, utc=True).dt.strftime("%Y-%m-%d"),
                                     cx=np.floor(f.longitude / cell_deg).astype(int), cy=np.floor(f.latitude / cell_deg).astype(int))
    g = d.groupby(["cx", "cy"]).agg(n_unmatched=("frp_mw", "size"), n_days=("utc_day", "nunique"),
                                    n_scans=("acq_datetime_utc", "nunique"), longitude=("longitude", "mean"),
                                    latitude=("latitude", "mean"), location_confirmed_share=("location_confirmed", "mean"),
                                    day_share=("daynight", lambda x: float((x == "D").mean())),
                                    lst_min=("lst_h", "min"), lst_max=("lst_h", "max"),
                                    median_frp_mw=("frp_mw", "median"), median_glint_deg=("glint_deg", "median"))
    return g.sort_values(["n_unmatched", "n_days"], ascending=False).head(n).reset_index(drop=True)


def time_match(query: pd.DataFrame, refs: pd.DataFrame, minutes: float, radius_km: float) -> np.ndarray:
    """Space-time match; hw.nearby is unit-safe since D72 (was 1,000x too wide under pandas 3)."""
    return hw.nearby(query, refs, minutes, radius_km)
