"""FlameSeek Phase 2: Step 6 (sensor calibration) on the Phase 1 outputs.

    python run_pipeline.py          # Phase 1 first (Steps 1-5)
    python run_phase2.py [--recompute-overpasses]

A diagnostics -> B matching window check -> C observation opportunities ->
D FRP calibration -> E detection curve -> F FRP distribution -> outputs/phase2_report.md
"""
from __future__ import annotations

import argparse
import time
import warnings

import numpy as np
import pandas as pd

from pipeline import calibration as cal
from pipeline import diagnostics as diag
from pipeline import frp_dist, overpasses
from pipeline.config import DEFAULT_SETTINGS, ROOT, ensure_dirs, load_settings
from pipeline.events import window_by_platform
from pipeline.grid import cell_id, cell_index

warnings.filterwarnings("ignore", category=FutureWarning)


def lowconf_near_misses(sample: pd.DataFrame, lowconf_path, radius_km=3.0, dt_s=600) -> dict:
    """How many MODIS 'misses' had a low-confidence Aqua detection within radius_km and dt_s."""
    from sklearn.neighbors import BallTree
    miss = sample[sample["detected"] == 0]
    low = pd.read_parquet(lowconf_path, columns=["platform", "acq_datetime_utc", "latitude", "longitude"])
    low = low[low["platform"] == "Aqua"]
    if miss.empty or low.empty:
        return {"misses": len(miss), "with_lowconf_aqua": 0, "n_lowconf_aqua": len(low)}
    lt = pd.to_datetime(low["acq_datetime_utc"], utc=True).astype("int64").to_numpy() // 10**9
    mt = pd.to_datetime(miss["overpass_time_utc"], utc=True).astype("int64").to_numpy() // 10**9
    tree = BallTree(np.radians(low[["latitude", "longitude"]].to_numpy()), metric="haversine")
    nb = tree.query_radius(np.radians(miss[["lat", "lon"]].to_numpy()), r=radius_km / 6371.0088)
    hit = sum(bool(len(n)) and bool((np.abs(lt[n] - t) <= dt_s).any()) for n, t in zip(nb, mt))
    return {"misses": len(miss), "with_lowconf_aqua": int(hit), "n_lowconf_aqua": len(low)}


def main(config_path=DEFAULT_SETTINGS, recompute_overpasses=False, window=None) -> dict:
    t0 = time.time()
    cfg = load_settings(config_path, window=window)
    ensure_dirs(cfg)
    P = cfg["paths"]
    figs = P["figures_dir"]
    ev = pd.read_csv(P["processed_dir"] / "fire_events.csv", low_memory=False)
    ov_raw = pd.read_csv(P["interim_dir"] / "event_overpasses.csv")
    det = pd.read_parquet(P["processed_dir"] / "detections_clean.parquet",
                          columns=["det_id", "fire_id", "sensor", "platform", "acq_datetime_utc", "utc_date",
                                   "daynight", "latitude", "longitude", "scan_km", "track_km", "frp_mw",
                                   "partial_day", "version"])
    gd = pd.read_csv(P["processed_dir"] / "grid_daily.csv", usecols=["cell_id", "date", "partial_day"])
    deg = cfg["grid"]["cell_deg"]
    ov = cal.enrich_overpasses(ov_raw, det, deg)
    S = {"cfg": cfg, "n_urt_clean": int(det["version"].astype(str).str.contains("URT").sum())}

    # ---------------- A. diagnostics ----------------
    S["both"] = diag.both_breakdown(ev)
    near = diag.aqua_viirs_dt(ov_raw)
    S["dt_stats"] = diag.dt_stats(near)
    S["modis_only"] = diag.modis_only_breakdown(ev, det)
    S["boxes"] = diag.pilot_boxes(ev, cfg["overpasses"]["pilot_boxes"])
    day = det.groupby("utc_date").agg(n=("det_id", "size"), partial=("partial_day", "first"))
    S["days"] = day
    print("[A1] both:", S["both"]["by_combo"], S["both"]["by_viirs_platform"])
    print("[A2] Aqua-VIIRS |dt|:", {k: (round(v["median_abs_min"], 1), round(v["share_le_30"], 4),
                                       round(v["share_le_45"], 4), round(v["share_le_60"], 4))
                                   for k, v in S["dt_stats"].items()})
    print("[A3] MODIS_only:", S["modis_only"]["by_platform"], S["modis_only"]["by_daynight"])
    print("[A5] days:", day.to_dict("index"))
    print("[A6] pilot boxes:\n", S["boxes"].to_string(index=False))

    # ---------------- B. window check ----------------
    e = cfg["events"]
    S["window_choice"] = {p: diag.choose_window(near, p, e["matched_pair_window_min"],
                                                e["matched_pair_window_max_min"]) for p in diag.VIIRS}
    S["windows"] = window_by_platform(cfg)
    for p, ch in S["window_choice"].items():
        flag = "" if ch["window_min"] == S["windows"][p] else "  <-- differs from config/settings.yaml"
        print(f"[B] {p}: rule gives {ch['window_min']} min ({ch['reason']}); configured {S['windows'][p]}{flag}")
    diag.plot_dt_hist(near, figs / "aqua_viirs_dt_hist.png", S["windows"])

    # ---------------- C. observation opportunities ----------------
    ovp_path = P["processed_dir"] / "overpasses.parquet"
    if ovp_path.exists() and not recompute_overpasses:
        opp = pd.read_parquet(ovp_path)
        S["tles"] = (opp.groupby("platform", observed=True)
                        .agg(source=("tle_source", "first"), epoch=("tle_epoch_utc", "first"),
                             n_overpasses=("cell_id", "size")).astype(str).to_dict("index"))
        print(f"[C] loaded {len(opp):,} cell-overpasses from {ovp_path.name}")
    else:
        det_t = pd.to_datetime(det["acq_datetime_utc"], utc=True)
        r = overpasses.run(gd, det.assign(acq_datetime_utc=det_t), cfg)
        opp, S["tles"] = r["overpasses"], r["tles"]
        opp.to_parquet(ovp_path, index=False)
    S["n_cells"] = opp["cell_id"].nunique()
    S["n_overpasses"] = len(opp)
    dd = det.copy()
    dd["acq_datetime_utc"] = pd.to_datetime(dd["acq_datetime_utc"], utc=True)
    ix, iy = cell_index(dd["longitude"].to_numpy(), dd["latitude"].to_numpy(), deg)
    dd["cell_id"] = cell_id(ix, iy)
    match = overpasses.detection_match(dd, opp, cfg["overpasses"]["match_tolerance_min"])
    S["match"] = match.groupby("platform").agg(n=("det_id", "size"), share=("matched", "mean"),
                                               median_abs_dt=("dt_min", lambda s: s.abs().median()))
    S["match_all"] = float(match["matched"].mean())
    mm = match[match["matched"]]
    S["pixel_check"] = (mm.assign(ratio=(mm["scan_km"] * mm["track_km"]) / mm["pixel_area_km2"])
                          .groupby("platform")["ratio"].describe(percentiles=[0.1, 0.5, 0.9]))
    low = opp[(opp["cell_lat"].abs() < 30) & (opp["daynight"] == "D") & (opp["cross_track_km"] < 500)]
    lst = (low["overpass_time_utc"].dt.hour + low["overpass_time_utc"].dt.minute / 60 + low["cell_lon"] / 15) % 24
    S["day_lst"] = lst.groupby(low["platform"].astype(str)).median()
    print(f"[C] {S['n_overpasses']:,} cell-overpasses over {S['n_cells']:,} cells; detections inside an "
          f"overpass of their platform (±{cfg['overpasses']['match_tolerance_min']} min): {S['match_all']:.4%}")
    print("    median daytime LST per platform (|lat|<30):", S["day_lst"].round(2).to_dict())

    # ---------------- D. FRP calibration ----------------
    pairs = cal.build_pairs(ov, cfg)
    pairs.to_csv(P["interim_dir"] / "calibration_pairs.csv", index=False)
    S["pairs"] = pairs
    S["calib"] = cal.calibrate(pairs, cfg)
    for r in S["calib"]:
        print("[D]", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    # ---------------- E. detection curve ----------------
    sample = cal.detection_sample(ov, opp, cfg)
    sample.to_csv(P["interim_dir"] / "detection_curve_sample.csv", index=False)
    S["sample"] = sample
    S["curve"] = cal.fit_detection_curve(sample, cfg)
    cal.plot_detection_curve(sample, S["curve"], cfg, figs / "modis_detection_curve.png")
    # Sensitivity: refit on narrower windows (point estimates), sample make-up, and whether
    # missed cases had a low-confidence Aqua detection nearby (those are filtered in Step 2).
    sens = []
    for w_ in (15, 30, 45, 60):
        sub = sample[sample["dt_aqua_min"].abs() <= w_]
        row = {"window": w_, "n": len(sub), "rate": float(sub["detected"].mean()) if len(sub) else np.nan}
        if len(sub) >= cfg["calibration"]["min_pairs"] and 0 < sub["detected"].sum() < len(sub):
            b0_, b1_, bA_ = cal._logit(sub).params
            row.update(f50_nadir=float(cal.f50(b0_, b1_, -bA_, 1.0)),
                       f50_edge=float(cal.f50(b0_, b1_, -bA_, cfg["calibration"]["modis_edge_area_km2"])))
        sens.append(row)
    S["curve_sens"] = sens
    S["sample_q"] = {"a_modis_km2": sample["a_modis_km2"].quantile([0.1, 0.5, 0.9]).to_dict(),
                     "abs_lat": sample["lat"].abs().quantile([0.1, 0.5, 0.9]).to_dict(),
                     "frp_viirs_mw": sample["frp_viirs_mw"].quantile([0.1, 0.5, 0.9]).to_dict()}
    S["lowconf_misses"] = lowconf_near_misses(sample, P["interim_dir"] / "detections_lowconf.parquet")
    print("[E] sensitivity:", sens, "| misses with low-conf Aqua nearby:", S["lowconf_misses"])
    print("[E]", {k: v for k, v in S["curve"].items() if k != "boot"})

    # ---------------- F. FRP distribution ----------------
    S["dist"] = frp_dist.run(ov, S["curve"], cfg)
    frp_dist.plot(S["dist"]["fits"], figs / "frp_distribution.png")
    print("[F] pi_MODIS:", S["dist"]["pi"])

    # pilot boxes: calibration material per box
    bx = S["boxes"].copy()
    evc = ev.set_index("fire_id")[["centroid_lat", "centroid_lon"]]

    def in_box(df, b):
        c = evc.reindex(df["fire_id"])
        return (c["centroid_lon"].between(b[0], b[2]) & c["centroid_lat"].between(b[1], b[3])).to_numpy()
    bx["calib_pairs"] = [int(in_box(pairs, b).sum()) if len(pairs) else 0 for b in bx["bbox"]]
    bx["curve_sample"] = [int(in_box(sample, b).sum()) if len(sample) else 0 for b in bx["bbox"]]
    S["boxes"] = bx

    from pipeline import report_phase2
    report_phase2.write(S, ROOT / "outputs" / "phase2_report.md")
    print(f"\nDone in {time.time() - t0:.0f}s. Report: outputs/phase2_report.md")
    return S


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_SETTINGS)
    ap.add_argument("--recompute-overpasses", action="store_true")
    ap.add_argument("--window", default=None)
    a = ap.parse_args()
    main(a.config, a.recompute_overpasses, a.window)
