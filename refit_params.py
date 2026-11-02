"""Refit Step 6 parameters from one window and write the next params/<kind>_vN.json.

    python refit_params.py --window current_2026 [--recompute-overpasses]

Needs `python run_pipeline.py --window <name>` first. Processing stages never refit; they
only read params (pipeline/params.py).

Status of the new files is decided from measured facts, not dates:
  - Aqua–S-NPP median abs(Δt) in the window <= drift.calib_max_dt_min (20 min):
    "validated-sync-window", calibration refitted with the sync method (pairs <= 15 min,
    truncation filter, Deming with stated error ratio, OLS bounds, bootstrap), and earlier
    files fitted in drifted windows are re-marked "drift-affected".
  - otherwise: "provisional" (the era measurement is recorded in the file).
The diurnal file is written as "not_available" until Step 7 (Himawari) exists.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import run_phase2
from pipeline import calibration as cal
from pipeline import params
from pipeline.config import DEFAULT_SETTINGS


def era_info(S: dict, cfg: dict) -> dict:
    eras_csv = cfg["paths"]["window_processed"] / "eras.csv"
    e = pd.read_csv(eras_csv) if eras_csv.exists() else pd.DataFrame()
    plat = {}
    for _, r in e.iterrows():
        plat.setdefault(r["platform"], []).append(
            {"month": r["month"], "lst_median_h": r["lst_median_h"], "deviation_min": r["deviation_min"],
             "drifted": None if pd.isna(r["drifted"]) else bool(r["drifted"])})
    dt = S["dt_stats"].get("S-NPP", {})
    return {"aqua_snpp_median_abs_dt_min": dt.get("median_abs_min"),
            "aqua_drifted": any(m["drifted"] for m in plat.get("Aqua", []) if m["drifted"] is not None),
            "terra_drifted": any(m["drifted"] for m in plat.get("Terra", []) if m["drifted"] is not None),
            "era_sensor": sorted(set(e["era_sensor"])) if len(e) else [], "per_platform_month": plat}


def main(window=None, recompute_overpasses=False) -> dict:
    S = run_phase2.main(DEFAULT_SETTINGS, recompute_overpasses, window)
    cfg = S["cfg"]
    w = cfg["window"]
    era = era_info(S, cfg)
    dt = era["aqua_snpp_median_abs_dt_min"]
    sync = dt is not None and np.isfinite(dt) and dt <= cfg["drift"]["calib_max_dt_min"]
    status = "validated-sync-window" if sync else "provisional"
    src = {"window": w["name"], "start": str(w["start"]), "end": str(w["end"]), "raw_dir": str(w["raw_dir"])}
    note_era = (f"Aqua–S-NPP median abs(Δt) {dt:.1f} min "
                f"({'<=' if sync else '>'} {cfg['drift']['calib_max_dt_min']} min); "
                f"Aqua drifted: {era['aqua_drifted']}.")
    written = []

    # ---- calibration ----
    allfit = next(r for r in S["calib"] if r["subset"] == "all")
    if sync:
        sf = cal.fit_sync(S["pairs"], cfg)
        payload = {"status": status if sf["fitted"] else "not_available", "source_window": src, "era": era,
                   "sample_size": sf["n"], "fit_method": "Deming (stated error ratio) on log10 FRP, pairs <= "
                   f"{sf['sync_max_dt_min']} min, both FRP >= {sf['trunc_frp_mw']} MW; OLS slope bounds; ODR",
                   "values": {k: sf.get(k) for k in ("a", "b", "odr")},
                   "intervals": {"a_90": sf.get("a_ci"), "b_90": sf.get("b_ci"), "b_bounds_ols": sf.get("b_bounds_ols")},
                   "notes": [note_era] + ([sf["reason"]] if not sf["fitted"] else [])}
    else:
        payload = {"status": status, "source_window": src, "era": era, "sample_size": allfit["n"],
                   "fit_method": "ODR (scipy.odr) on log10 FRP, one pair per Aqua overpass, windows "
                   f"{S['windows']} min; {cfg['calibration']['bootstrap']} bootstrap resamples",
                   "values": {"a": allfit.get("a"), "b": allfit.get("b"),
                              "by_daynight": {r["subset"]: {k: r.get(k) for k in ("n", "a", "b")}
                                              for r in S["calib"] if r["subset"] != "all"}},
                   "intervals": {"a_90": [allfit.get("a_lo"), allfit.get("a_hi")],
                                 "b_90": [allfit.get("b_lo"), allfit.get("b_hi")]},
                   "notes": [note_era, "Pairs come from the edge of the Aqua–VIIRS time distribution "
                             "(decisions D22); night fit unstable (D24)."]}
    written.append(params.write("calibration", payload, cfg))

    # ---- detection curve ----
    c = S["curve"]
    written.append(params.write("detection_curve", {
        "status": status if c.get("fitted") else "not_available", "source_window": src, "era": era,
        "sample_size": c["n"], "fit_method": "statsmodels Logit: logit P = b0 + b1 log10 F_VIIRS - b2 log10 A_MODIS",
        "values": {k: c.get(k) for k in ("b0", "b1", "b2", "f50_nadir_mw", "f50_edge_mw", "edge_area_km2")},
        "intervals": {k: c.get(k) for k in ("b0_ci", "b1_ci", "b2_ci", "f50_nadir_ci", "f50_edge_ci")},
        "notes": [note_era, f"Sample pixel area median {S['sample_q']['a_modis_km2'][0.5]:.2f} km²: the nadir "
                  "value is an extrapolation (decisions D29)."]}, cfg))

    # ---- pi_MODIS ----
    d = S["dist"]
    written.append(params.write("pi_modis", {
        "status": status if c.get("fitted") else "not_available", "source_window": src, "era": era,
        "sample_size": {k: v.get("n") for k, v in d["fits"].items()},
        "fit_method": "pi = ∫ P_det(F,A) f(F) dF; empirical (mean over VIIRS event-overpasses) and power-law tail",
        "values": d["pi"], "intervals": None,
        "distribution": {k: {kk: v.get(kk) for kk in ("xmin", "alpha", "alpha_se", "R", "p", "better")}
                         for k, v in d["fits"].items()},
        "notes": [note_era, "Intervals not yet propagated (needs Step 8 Monte Carlo)."]}, cfg))

    # ---- diurnal ----
    written.append(params.write("diurnal", {
        "status": "not_available", "source_window": src, "era": era, "sample_size": 0,
        "fit_method": "Gaussian diurnal shape from Himawari (Step 7)", "values": None, "intervals": None,
        "notes": ["Step 7 not implemented; no Himawari data in data/raw/himawari/."]}, cfg))

    if sync:  # supersede fits from drifted windows
        for kind in ("calibration", "detection_curve", "pi_modis"):
            for v in params.versions(kind, cfg):
                doc = params.load(kind, v, cfg=cfg)
                if doc and doc["status"] == "provisional" and doc.get("era", {}).get("aqua_drifted"):
                    params.set_status(kind, v, "drift-affected",
                                      f"superseded by sync-window fit from {w['name']}", cfg)
    for p in written:
        print("wrote", p.name)
    return {"S": S, "written": written, "status": status}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default=None)
    ap.add_argument("--recompute-overpasses", action="store_true")
    a = ap.parse_args()
    main(a.window, a.recompute_overpasses)
