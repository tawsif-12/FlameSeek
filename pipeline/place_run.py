"""Run the FlameSeek pipeline (Steps 1-5) for one searched place and summarize it for the website.

    python -m pipeline.place_run --id <place_id> --raw-dir <dir with FIRMS CSVs> --start YYYY-MM-DD
        --end YYYY-MM-DD --bbox w,s,e,n [--geometry <geojson file>] [--workers 2]

The stages are the normal ones (raw_split -> detect -> link -> grid -> finalize), unchanged; only the
window is ad hoc: its raw files are the NASA FIRMS archive chunks downloaded for the place, and its
outputs go to data/places/<place_id>/. Writes data/places/<place_id>/place_summary.json.

Calibration status per year follows the measured Aqua drift (data/processed/drift_by_year.csv) and
the D68 no-drift test: |median daytime Aqua LST - 13:30| <= 30 min -> synchronized era (calibration v2,
validated on the 2016 window); otherwise drift-affected (v1, provisional); no measurement -> awaiting.
Latent lambda needs historical orbital elements and is reported as awaiting data.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import stages
from pipeline.config import ROOT, ensure_dirs, load_settings

SUMMARY_VERSION = 2
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def progress(stage: str, frac: float, note: str = "") -> None:
    print(f"PROGRESS {frac:.3f} {stage} {note}".rstrip(), flush=True)


def place_cfg(place_id: str, raw_dir: Path, start: date, end: date, bbox: list[float]) -> dict:
    cfg = load_settings(window="current_2026")
    base = ROOT / "data" / "places" / place_id
    w = cfg["window"]
    w.update(name=f"place_{place_id}", start=start, end=end, raw_dir=raw_dir.resolve(), bbox=bbox)
    cfg["study_bbox"] = list(bbox)
    cfg["data_version"] = f"firms_sp_place_{place_id}_{start}_{end}"
    cfg["paths"]["raw_dir"] = raw_dir.resolve()
    cfg["paths"]["partition_root"] = base / "partitions"
    for key, sub in (("window_processed", "processed"), ("window_interim", "interim")):
        cfg["paths"][key] = base / sub
    cfg["paths"]["processed_dir"] = cfg["paths"]["window_processed"]
    cfg["paths"]["interim_dir"] = cfg["paths"]["window_interim"]
    cfg["paths"]["window_outputs"] = base / "outputs"
    cfg["paths"]["figures_dir"] = base / "outputs" / "figures"
    cfg["paths"]["report"] = base / "outputs" / "phase1_report.md"
    cfg["paths"]["inspection_report"] = base / "outputs" / "raw_inspection_report.md"
    return cfg


def run_stages(cfg: dict, workers: int) -> dict:
    ensure_dirs(cfg)
    progress("raw_split", 0.05)
    stages.raw_split(cfg, True)
    days = stages.local_days(cfg)
    total = len(days)
    for i, d in enumerate(days, 1):
        stages.detect_day(cfg, d, True)
        if i % 30 == 0 or i == total:
            progress("detect", 0.05 + 0.40 * i / total, f"{i}/{total} days")
    for i, d in enumerate(days, 1):
        stages.link_day(cfg, d, True)
        if i % 30 == 0 or i == total:
            progress("link", 0.45 + 0.20 * i / total, f"{i}/{total} days")
    for i, d in enumerate(days, 1):
        stages.grid_day(cfg, d, True)
        if i % 30 == 0 or i == total:
            progress("grid", 0.65 + 0.20 * i / total, f"{i}/{total} days")
    progress("finalize", 0.88)
    return stages.finalize(cfg)


# ------------------------------------------------------------------- summary --
def calibration_by_year(years: list[int], cfg: dict) -> dict[int, dict]:
    drift_path = ROOT / "data" / "processed" / "drift_by_year.csv"
    drift = pd.read_csv(drift_path).set_index("year") if drift_path.exists() else pd.DataFrame()
    nominal = cfg["sync_gate"]["aqua_nominal_lst_h"]
    tol = cfg["sync_gate"]["aqua_lst_tolerance_min"]
    params = {}
    for v, f in (("v1", "calibration_v1.json"), ("v2", "calibration_v2_sync2016.json")):
        p = ROOT / "params" / f
        params[v] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    out = {}
    for y in years:
        lst = float(drift.loc[y, "Aqua"]) if y in drift.index and pd.notna(drift.loc[y, "Aqua"]) else None
        if lst is None:
            out[y] = {"aqua_lst_h": None, "status": "calibration awaiting data", "version": None,
                      "reason": "no measured Aqua overpass time for this year"}
            continue
        offset = (lst - nominal) * 60
        if abs(offset) <= tol and params["v2"] and (params["v2"].get("fit") or {}).get("fitted"):
            out[y] = {"aqua_lst_h": lst, "offset_min": offset, "status": "synchronized era — calibration v2 (validated on 2016)",
                      "version": "v2"}
        elif abs(offset) > tol:
            out[y] = {"aqua_lst_h": lst, "offset_min": offset, "status": "drift-affected — calibration v1 (provisional)",
                      "version": "v1"}
        else:
            out[y] = {"aqua_lst_h": lst, "offset_min": offset, "status": "calibration awaiting data", "version": None}
    return out


def _inside(geometry: dict | None, lon: np.ndarray, lat: np.ndarray, bbox: list[float]) -> np.ndarray:
    w, s, e, n = bbox
    keep = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    if geometry:
        import shapely
        from shapely.geometry import shape
        poly = shape(geometry)
        keep &= shapely.contains_xy(poly, lon, lat)
    return keep


def robust_z(x: float, hist: np.ndarray) -> tuple[float | None, float | None]:
    if len(hist) < 3:
        return None, None
    med = float(np.median(hist))
    mad = float(np.median(np.abs(hist - med))) * 1.4826
    z = (x - med) / mad if mad > 0 else (0.0 if x == med else float("inf"))
    pct = float(np.mean(hist < x) * 100)
    return z, pct


def category(z: float | None) -> str | None:
    if z is None:
        return None
    if z == float("inf"):
        return "Highly Unusual"
    return "Normal" if z < 2 else "Above Normal" if z < 3.5 else "Unusual" if z < 5 else "Highly Unusual"


def summarize(cfg: dict, fin: dict, place_id: str, bbox: list[float], geometry: dict | None, seconds: float) -> dict:
    start, end = cfg["window"]["start"], cfg["window"]["end"]
    det = fin["detections"].copy()
    ev = fin["events"].copy()
    gcd = fin["grid_daily"].copy()
    gov = fin["grid_overpass"]

    det = det[_inside(geometry, det["longitude"].to_numpy(), det["latitude"].to_numpy(), bbox)] if len(det) else det
    ev = ev[_inside(geometry, ev["centroid_lon"].to_numpy(), ev["centroid_lat"].to_numpy(), bbox)] if len(ev) else ev
    gcd = gcd[_inside(geometry, gcd["cell_lon"].to_numpy(), gcd["cell_lat"].to_numpy(), bbox)] if len(gcd) else gcd

    det["date"] = pd.to_datetime(det["utc_date"]) if len(det) else pd.Series(dtype="datetime64[ns]")
    ev["start"] = pd.to_datetime(ev["start_time"], utc=True) if len(ev) else pd.Series(dtype="datetime64[ns, UTC]")
    years = list(range(start.year, end.year + 1))
    calib = calibration_by_year(years, cfg)

    def months_in_record(y: int) -> int:
        a, b = max(start, date(y, 1, 1)), min(end, date(y, 12, 31))
        return 0 if b < a else (b.year - a.year) * 12 + b.month - a.month + 1

    yearly = []
    for y in years:
        d = det[det["date"].dt.year == y] if len(det) else det
        e = ev[ev["start"].dt.year == y] if len(ev) else ev
        sensors = sorted(d["platform"].astype(str).unique().tolist()) if len(d) else []
        yearly.append({"year": y, "months_in_record": months_in_record(y), "full_year": months_in_record(y) == 12,
                       "n_events": int(len(e)), "n_detections": int(len(d)),
                       "fire_days": int(d["date"].dt.normalize().nunique()) if len(d) else 0,
                       "frp_sum_mw": float(d["frp_mw"].sum()) if len(d) else 0.0,
                       "detections_by_platform": d["platform"].astype(str).value_counts().to_dict() if len(d) else {},
                       "platforms": sensors, "viirs_present": any(s in ("S-NPP", "NOAA-20", "NOAA-21") for s in sensors) or y >= 2012,
                       "calibration": calib[y]})

    # Month-by-month event counts and the seasonal profile (median over full years).
    monthly = []
    for y in years:
        for m in range(1, 13):
            if date(y, m, 1) < date(start.year, start.month, 1) or date(y, m, 1) > end:
                continue
            e = ev[(ev["start"].dt.year == y) & (ev["start"].dt.month == m)] if len(ev) else ev
            d = det[(det["date"].dt.year == y) & (det["date"].dt.month == m)] if len(det) else det
            monthly.append({"year": y, "month": m, "n_events": int(len(e)),
                            "fire_days": int(d["date"].dt.normalize().nunique()) if len(d) else 0})
    mdf = pd.DataFrame(monthly)
    full_years = [r["year"] for r in yearly if r["full_year"]]
    prof = []
    for m in range(1, 13):
        v = mdf[(mdf["month"] == m) & (mdf["year"].isin(full_years))]["n_events"] if len(mdf) else pd.Series(dtype=float)
        prof.append({"month": m, "name": MONTHS[m - 1], "median_events": float(v.median()) if len(v) else None,
                     "mean_events": float(v.mean()) if len(v) else None, "years": int(len(v))})
    med = [p["median_events"] or 0 for p in prof]
    top = max(med) if med else 0
    peak = [p["name"] for p in prof if top > 0 and (p["median_events"] or 0) >= 0.5 * top]
    quiet = [p["name"] for p in prof if (p["median_events"] or 0) == 0]

    # Where fires repeat: the place's own detections (same inside-the-outline rule as every other
    # answer) binned to the pipeline's 0.1-degree grid. Grid cells are not filtered by their centre,
    # which would count fires just outside the outline in edge cells.
    cells = []
    if len(det):
        step = float(cfg["grid"]["cell_deg"])
        day_col = "local_solar_date" if "local_solar_date" in det.columns else "utc_date"
        g = det.assign(clat=(np.floor(det["latitude"] / step) + 0.5) * step, clon=(np.floor(det["longitude"] / step) + 0.5) * step,
                       day=det[day_col].astype(str), year=det["date"].dt.year)
        g["cell_id"] = "r" + np.floor(g["latitude"] / step).astype(int).astype(str) + "c" + np.floor(g["longitude"] / step).astype(int).astype(str)
        agg = g.groupby("cell_id").agg(lat=("clat", "first"), lon=("clon", "first"), days=("day", "nunique"),
                                       years=("year", "nunique"), first=("day", "min"), last=("day", "max"),
                                       frp_max_mw=("frp_mw", "max"))
        agg[["lat", "lon"]] = agg[["lat", "lon"]].round(3)
        agg = agg.sort_values(["days", "years"], ascending=False)
        cells = [{"cell_id": i, **{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}} for i, r in agg.head(400).iterrows()]

    # Is the latest 30 days unusual? Events in the window vs the same dates in earlier years.
    win_end = end
    win_start = end - timedelta(days=29)
    def count_between(a: date, b: date) -> int:
        if not len(ev):
            return 0
        s = ev["start"].dt.date
        return int(((s >= a) & (s <= b)).sum())
    current = count_between(win_start, win_end)
    hist = []
    for y in range(start.year, end.year):
        try:
            a, b = win_start.replace(year=win_start.year - (end.year - y)), win_end.replace(year=y)
        except ValueError:
            continue
        if a >= start:
            hist.append(count_between(a, b))
    z, pct = robust_z(current, np.asarray(hist, float))
    unusual = {"window": {"start": win_start.isoformat(), "end": win_end.isoformat()}, "current_events": current,
               "history_events": hist, "robust_z": None if z is None or z == float("inf") else round(z, 2),
               "percentile_rank": None if pct is None else round(pct), "category": category(z),
               "status": "computed" if z is not None else "insufficient_history"}

    # Long-term change: Theil-Sen slope of yearly events over full years, with sensor-era caveat.
    change = {"status": "insufficient_history"}
    fy = [r for r in yearly if r["full_year"]]
    if len(fy) >= 4:
        from scipy.stats import theilslopes
        xs = np.array([r["year"] for r in fy], float)
        ys = np.array([r["n_events"] for r in fy], float)
        slope, intercept, lo, hi = theilslopes(ys, xs, 0.90)
        sig = lo > 0 or hi < 0
        mean = float(ys.mean()) or 1.0
        change = {"status": "computed", "slope_events_per_year": round(float(slope), 2), "slope_90": [round(float(lo), 2), round(float(hi), 2)],
                  "relative_per_year": round(float(slope) / mean, 3) if mean else None,
                  "direction": ("increasing" if slope > 0 else "decreasing") if sig else "no clear trend",
                  "method": "Theil-Sen slope of yearly pipeline event counts over full years, 90% interval",
                  "caveat": "Event counts depend on which satellites flew: VIIRS (2012+) sees smaller fires than MODIS."}

    # Area climatology on the pipeline's own daily fire presence.
    risk = {"status": "insufficient_history"}
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from area_intel import area_climatology
        fire_days = set(det["date"].dt.date) if len(det) else set()
        daily = [{"date": (start + timedelta(days=i)).isoformat(),
                  "harmonized_activity": 1.0 if (start + timedelta(days=i)) in fire_days else 0.0}
                 for i in range((end - start).days + 1)]
        risk = area_climatology(daily, end)
        if risk.get("status") == "computed":
            risk["event"] = risk["event"].replace("consistent record", "FlameSeek pipeline, clean detections")
    except Exception as exc:  # noqa: BLE001 - report, never invent
        risk = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}

    before = float(fin["detections"]["frp_mw"].sum()) if len(fin["detections"]) else 0.0
    after = float(gov["frp_mw"].sum()) if len(gov) else 0.0
    rel = abs(after - before) / before if before else 0.0
    ds = fin.get("day_stats")
    return {
        "version": SUMMARY_VERSION, "place_id": place_id, "method": "FlameSeek pipeline Steps 1-5 (footprints, events, energy-conserving grid)",
        "data_version": cfg["data_version"], "period": {"start": start.isoformat(), "end": end.isoformat(), "years": len(years)},
        "run_seconds": round(seconds, 1),
        "quality": {"clean_detections": int(len(det)), "low_confidence_set_aside": int(fin.get("n_lowconf", 0)),
                    "events": int(len(ev)), "energy_conservation": {"frp_before_mw": before, "frp_after_mw": after, "rel_diff": rel,
                                                                   "pass": rel <= cfg["grid"]["energy_rel_tol"]},
                    "lambda": "awaiting data: latent fire rate needs historical satellite orbits (TLEs) for these years",
                    "platform_detections": det["platform"].astype(str).value_counts().to_dict() if len(det) else {}},
        "yearly": yearly, "monthly": monthly,
        "seasonal_profile": {"months": prof, "peak_months": peak, "quiet_months": quiet, "full_years": full_years,
                             "basis": "median monthly pipeline fire events over full years"},
        "hotspot_map": {"cell_deg": cfg["grid"]["cell_deg"], "cells": cells, "n_cells_with_fire": len(cells),
                        "method": "Pipeline grid cells; days = distinct local days with a clean detection inside the place in the cell"},
        "unusual": unusual, "change": change, "area_risk": risk,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--bbox", required=True)
    ap.add_argument("--geometry")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    bbox = [float(v) for v in a.bbox.split(",")]
    geometry = json.loads(Path(a.geometry).read_text(encoding="utf-8")) if a.geometry else None
    cfg = place_cfg(a.id, Path(a.raw_dir), date.fromisoformat(a.start), date.fromisoformat(a.end), bbox)
    fin = run_stages(cfg, a.workers)
    progress("summary", 0.95)
    out = summarize(cfg, fin, a.id, bbox, geometry, time.time() - t0)
    path = ROOT / "data" / "places" / a.id / "place_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str, indent=1), encoding="utf-8")
    progress("done", 1.0)
    print(f"SUMMARY {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
