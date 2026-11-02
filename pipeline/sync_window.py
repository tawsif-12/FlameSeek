"""Synchronized-window analysis under the D68 gate.

For one window: gate -> (if it passes) FRP calibration v2 -> observation
opportunities (archived TLEs, else the D69 detection-conditioned lower bound) ->
MODIS detection curve -> empirical pi_MODIS -> latent lambda and degradation test.
Windows that fail the gate get only the gate record.
"""
from __future__ import annotations

import pandas as pd

from pipeline import calibration, diagnostics, observed_opportunities, overpasses, sync_gate, tle_archive
from pipeline import himawari as hw
from pipeline.config import ROOT, load_settings

NEAR_NADIR_AREA_KM2 = 1.5   # MODIS pixel area below this = within ~20 deg of nadir (reporting only)


def tag(window: str) -> str:
    return window.replace("_", "")


def has_raw(cfg) -> bool:
    raw = cfg["paths"]["raw_dir"]
    return raw.exists() and any(raw.rglob("*.csv"))


def ensure_phases(window: str, cfg) -> bool:
    """Run Phases 1-2 (unchanged) when raw files exist but window products do not."""
    if (cfg["paths"]["window_processed"] / "detections_clean.parquet").exists():
        return True
    if not has_raw(cfg):
        return False
    import run_pipeline
    run_pipeline.main(window=window, workers=1, partition_root=cfg["paths"]["window_processed"] / "partitions")
    return True


def load(cfg):
    det = pd.read_parquet(cfg["paths"]["window_processed"] / "detections_clean.parquet")
    det["acq_datetime_utc"] = pd.to_datetime(det["acq_datetime_utc"], utc=True)
    ov = pd.read_csv(cfg["paths"]["window_interim"] / "event_overpasses.csv")
    return det, ov, calibration.enrich_overpasses(ov, det, cfg["grid"]["cell_deg"])


def old_rule(ov) -> dict:
    return sync_gate.old_rule(diagnostics.aqua_viirs_dt(ov))


def gate(window: str) -> dict:
    cfg = load_settings(window=window)
    if not ensure_phases(window, cfg):
        return {"window": window, "status": "awaiting data", "raw_dir": str(cfg["paths"]["raw_dir"])}
    det, ov, enriched = load(cfg)
    return {**sync_gate.evaluate(det, enriched, cfg), "old_rule": old_rule(ov), "status": "evaluated"}


def target_cells(cfg) -> pd.DataFrame:
    from pipeline import latent
    gd = pd.read_csv(cfg["paths"]["window_processed"] / "grid_daily.csv", usecols=["cell_id"])
    a = overpasses.target_cells(gd, cfg)
    b = latent.grid_cells(cfg).rename(columns={"cell_lon": "lon", "cell_lat": "lat"})[["cell_id", "lat", "lon"]]
    return pd.concat([a, b]).drop_duplicates("cell_id").reset_index(drop=True)


def opportunities(cfg, det) -> tuple[pd.DataFrame, dict]:
    sel = tle_archive.select(cfg)
    cells = target_cells(cfg)
    if sel["complete"]:
        t0 = det["acq_datetime_utc"].min().floor("D") - pd.Timedelta(hours=1)
        t1 = det["acq_datetime_utc"].max().ceil("D") + pd.Timedelta(hours=1)
        opp = tle_archive.compute(cfg, cells, t0, t1, sel["tles"])
        opp.to_parquet(cfg["paths"]["window_processed"] / "overpasses.parquet", index=False)
        info = {"basis": "TLE-propagated (archived epoch)", "tle_files": sel["files"],
                "tle_epochs": {p: str(t["epoch"]) for p, t in sel["tles"].items()}}
    else:
        r = observed_opportunities.run(det, cells, cfg, platforms=cfg["tle_archive"]["platforms"])
        opp = r["overpasses"]
        opp.to_parquet(cfg["paths"]["window_processed"] / "observed_overpasses.parquet", index=False)
        r["passes"].to_csv(cfg["paths"]["window_interim"] / "observed_passes.csv", index=False)
        info = {"basis": observed_opportunities.LABEL, "tle_missing": sel["missing"],
                "n_passes": int(len(r["passes"])), "n_passes_dropped_inconsistent": r["n_passes_dropped_inconsistent"],
                "bias_direction": ("O_s undercounted: passes without detections and swath parts not proven by "
                                   "detections are missing. lambda (count / opportunities) is biased HIGH. In the "
                                   "detection-curve sample, Aqua passes with no detection at all are missing.")}
    info["n_cell_overpasses"] = {str(k): int(v) for k, v in opp["platform"].astype(str).value_counts().items()}
    return opp, info


def process(window: str) -> dict:
    cfg = load_settings(window=window)
    g = gate(window)
    if g["status"] != "evaluated" or not window.startswith("sync_"):
        return {"gate": g}
    det, ov, enriched = load(cfg)
    t = tag(window)
    pairs = calibration.build_pairs(enriched, cfg)
    if g["synchronized"]:
        fit = calibration.fit_sync(pairs, cfg)
    else:
        failed = [k for k in ("a_no_drift", "b_sample") if not g[k]["pass"]]
        fit = {"fitted": False, "n": 0, "reason": "window fails sync gate part(s): " + ", ".join(failed)}
    cal_status = "validated – synchronized window" if fit.get("fitted") else "not_available"
    hw.json_write(ROOT / f"params/calibration_v2_{t}.json",
                  dict(kind="calibration", version=2, status=cal_status, source_window=window,
                       sample_size=fit["n"], fit=fit, gate=g))
    out = {"gate": g, "calibration": {**fit, "status": cal_status}}
    if not g["synchronized"]:
        return out

    opp, info = opportunities(cfg, det)
    sample = calibration.detection_sample(enriched, opp, cfg)
    curve = calibration.fit_detection_curve(sample, cfg)
    tle_based = info["basis"].startswith("TLE")
    status = ("validated – synchronized window" if tle_based else
              "synchronized window; " + observed_opportunities.LABEL) if curve["fitted"] else "not_available"
    area = sample["a_modis_km2"] if len(sample) else pd.Series(dtype=float)
    coverage = {"area_min_km2": float(area.min()) if len(area) else None,
                "area_median_km2": float(area.median()) if len(area) else None,
                "area_max_km2": float(area.max()) if len(area) else None,
                f"n_near_nadir_area_le_{NEAR_NADIR_AREA_KM2}": int((area <= NEAR_NADIR_AREA_KM2).sum()),
                "n_detected_near_nadir": int(sample.loc[area <= NEAR_NADIR_AREA_KM2, "detected"].sum()) if len(area) else 0}
    clean = {k: v for k, v in curve.items() if k != "boot"}
    hw.json_write(ROOT / f"params/detection_curve_v3_{t}.json",
                  dict(kind="detection_curve", version=3, status=status, source_window=window,
                       opportunity_basis=info["basis"], sample_size=len(sample), fit=clean, coverage=coverage))
    if curve["fitted"]:
        fig = cfg["paths"]["figures_dir"] / f"detection_curve_v3_{t}.png"
        fig.parent.mkdir(parents=True, exist_ok=True)
        calibration.plot_detection_curve(sample, curve, cfg, fig)
    empirical = {}
    if curve["fitted"]:
        viirs = enriched[enriched.sensor.eq("VIIRS") & enriched.frp_sum_mw.gt(0)]
        w, s, e, n = cfg["himawari"]["regions"]["full_IGP"]
        for name, d in [("all", viirs), ("IGP", viirs[viirs.lon.between(w, e) & viirs.lat.between(s, n)])]:
            empirical[name] = dict(n=len(d), nadir=float(calibration.p_det(
                d.frp_sum_mw.values, 1, curve["b0"], curve["b1"], curve["b2"]).mean()) if len(d) else None)
    hw.json_write(cfg["paths"]["window_outputs"] / "pi_modis_empirical.json",
                  dict(source_window=window, opportunity_basis=info["basis"], values=empirical))
    from pipeline import latent
    lam = latent.run_window(window) if window in cfg["latent"]["detection_curve_by_window"] else \
        {"status": "awaiting data", "reason": f"no latent configuration for {window}"}
    return {**out, "opportunities": info, "detection_curve": {**clean, "status": status, "coverage": coverage},
            "pi_modis": empirical, "latent": lam}


def intervals_overlap(x, y) -> bool | None:
    if not x or not y:
        return None
    return bool(max(x[0], y[0]) <= min(x[1], y[1]))


def compare_calibrations(a: dict, b: dict) -> dict:
    if not (a.get("fitted") and b.get("fitted")):
        return {"status": "awaiting data"}
    return {"status": "compared", "a_overlap": intervals_overlap(a["a_ci"], b["a_ci"]),
            "b_overlap": intervals_overlap(a["b_ci"], b["b_ci"])}
