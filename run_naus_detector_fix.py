"""D73: daytime-detector improvement round for Northern Australia (in memory; no params written).

    E:\\anaconda\\envs\\flameseek\\python.exe run_naus_detector_fix.py

1. Prepare B04 on the cached grid (alignment-checked).
2. Tune on Oct 29-30 over the pre-registered grid; choose by M1 + M3.
3. Score baseline vs chosen on Oct 31 - Nov 1 once; apply the pre-registered checks.
Results: outputs/naus_detector_fix.json.
"""
import json

import numpy as np
import pandas as pd

from pipeline import calibration, diurnal, transfer
from pipeline import himawari as hw, naus_detector as nx, naus_diagnostics as nd
from pipeline.config import ROOT, load_settings

LABEL = "provisional – detector fix D73, not active"


def key(fix):
    return f"r{fix['reflectance_max']:.2f}_cap{fix['delta_cap_k']}"


def refit(cfg, chosen):
    """Step 3 (only when all checks pass): all scans, FRP per clear area, 30% clear gate on the
    new mask, day bootstrap. Writes NEW provisional files; nothing existing is replaced."""
    r = nd.regional_cfg(cfg)
    settings = r["himawari"]
    res = nx.run(cfg, {"fixed": chosen})["fixed"]
    s = res["stats"].copy()
    clear_km2 = s.clear_sky_fraction * s.valid_land_area_km2
    s["frp_mw"] = np.where(clear_km2 > 0, s.frp_mw / clear_km2, np.nan)  # MW per clear km2; scale cancels
    model, points = diurnal.fit_region(s, settings)
    model.update(region="Northern_Australia", status=LABEL, role="method demonstration region",
                 transfer_to_south_asia=False, detector="D73 day fix", day_fix=chosen,
                 fit_quantity="FRP per clear valid land area")
    hw.json_write(ROOT / "params/diurnal_v3_naus_dayfix.json",
                  dict(kind="diurnal", version=3, source_window=cfg["window"]["name"], status=LABEL,
                       regions={"Northern_Australia": model}))
    out = {"diurnal": nd.summarize(model)}
    if not model.get("fitted"):
        return out
    models = {"Northern_Australia": model}
    folder = ROOT / "outputs/phase3c_naus_dayfix"
    folder.mkdir(parents=True, exist_ok=True)
    refs = pd.read_parquet(cfg["paths"]["window_processed"] / "detections_clean.parquet")
    refs["acq_datetime_utc"] = pd.to_datetime(refs.acq_datetime_utc, utc=True)
    ov = pd.read_csv(cfg["paths"]["window_interim"] / "event_overpasses.csv")
    ov = calibration.enrich_overpasses(ov, refs, cfg["grid"]["cell_deg"])
    w, s_, e, n = nd.BOX
    ov = ov[ov.lon.between(w, e) & ov.lat.between(s_, n)].copy()
    pairs = transfer.adjusted_pairs(ov, models, r)
    pairs["event_specific_ahi_ratio"] = transfer.event_specific_ratios(pairs, res["fires"], settings)
    pairs.to_csv(folder / "transfer_pairs.csv", index=False)
    fit = transfer.fit_adjusted(pairs, r)
    hw.json_write(ROOT / "params/calibration_v3_transfer_naus_dayfix.json",
                  dict(kind="calibration", version=3, region="Northern_Australia", status=LABEL,
                       role="method demonstration region", transfer_to_south_asia=False,
                       source_window=cfg["window"]["name"], sample_size=fit["n"], fit=fit))
    perpass, daily, totals = transfer.energy_table(ov, models, r)
    perpass.to_csv(folder / "fre_overpasses.csv", index=False)
    daily.to_csv(folder / "fre_daily.csv", index=False)
    events = pd.read_csv(cfg["paths"]["window_processed"] / "fire_events.csv", low_memory=False)
    events = events[events.fire_id.isin(ov.fire_id)].copy()
    events["FRE_estimate"] = events.fire_id.map(totals)
    events["FRE_status"] = np.where(events.FRE_estimate.notna(), LABEL, "not_available")
    events.to_csv(folder / "fire_events_fre.csv", index=False)
    out.update(calibration={k: fit.get(k) for k in ("n", "fitted", "a", "b", "a_ci", "b_ci", "b_bounds_ols", "reason")},
               n_fre_events=int(events.FRE_estimate.notna().sum()),
               fre_total_mj=float(events.FRE_estimate.sum()))
    return out


def main():
    cfg = load_settings()
    prep = nx.prepare_b04(cfg)
    print("B04 prepared:", prep, flush=True)
    refs = nd.references(cfg)

    grid = {key(f): f for f in ({"reflectance_max": r, "sza_max_deg": nx.SZA_MAX, "delta_cap_k": c}
                                for r in nx.GRID_REFLECTANCE for c in nx.GRID_CAP)}
    train = nx.run(cfg, {"baseline": None, **grid}, dates=nx.TRAIN)
    scores = []
    for name, res in train.items():
        m = nx.metrics(res, refs, nx.TRAIN)
        scores.append({"variant": name, "objective": nx.objective(m), **{k: m[k] for k in
                       ("M1_cloud_share_viirs_12_14h", "M3_never_confirmed_share_09_13h", "M1_n", "M3_n")},
                       "M2": m["M2_day_detection_by_frp"], "no_b04_day_scans": res["no_b04_day_scans"]})
        print(name, round(scores[-1]["objective"], 4), flush=True)
    def strictness(name):  # ties: lower reflectance threshold, then larger cap (no cap = largest)
        f = grid[name]
        return (f["reflectance_max"], -(f["delta_cap_k"] if f["delta_cap_k"] is not None else 1e9))
    cand = [s for s in scores if s["variant"] != "baseline"]
    best = min(cand, key=lambda s: (round(s["objective"], 6), strictness(s["variant"])))
    chosen = grid[best["variant"]]

    test = nx.run(cfg, {"baseline": None, "fixed": chosen}, dates=nx.TEST)
    before, after = nx.metrics(test["baseline"], refs, nx.TEST), nx.metrics(test["fixed"], refs, nx.TEST)
    verdict = nx.success(before, after)
    out = {"b04_preparation": prep, "train_dates": nx.TRAIN, "test_dates": nx.TEST,
           "training_scores": scores, "chosen": chosen, "chosen_variant": best["variant"],
           "test_before": before, "test_after": after, "checks": verdict,
           "test_no_b04_day_scans": test["fixed"]["no_b04_day_scans"]}
    if verdict["all_clear"]:
        out["refit"] = refit(cfg, chosen)
    else:
        out["refit"] = "not run: pre-registered checks did not all pass (D73)"
    hw.json_write(ROOT / "outputs/naus_detector_fix.json", out)
    print(json.dumps({k: out[k] for k in ("chosen_variant", "test_before", "test_after", "checks", "refit")}, indent=1, default=str))


if __name__ == "__main__":
    main()
