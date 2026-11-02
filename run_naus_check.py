"""Northern Australia diurnal-fit check (D71). Diagnose only: writes outputs, never params.

    E:\\anaconda\\envs\\flameseek\\python.exe run_naus_check.py
"""
import json

import numpy as np
import pandas as pd

from pipeline import diurnal, himawari as hw
from pipeline import naus_diagnostics as nd
from pipeline.config import ROOT, load_settings

OUT = ROOT / "outputs/naus_diagnostics"


def main():
    cfg = load_settings()
    settings = nd.regional_cfg(cfg)["himawari"]
    OUT.mkdir(parents=True, exist_ok=True)
    hourly, fires, stats, _ = nd.run_scans(cfg)
    refs = nd.references(cfg)
    base = fires[fires.variant.eq("baseline")].reset_index(drop=True)
    tol = cfg["himawari"]["reference_tolerance_minutes"]
    base["reference_match"] = nd.time_match(base, refs, tol, settings["match_radius_km"])
    base["location_confirmed"] = nd.location_confirmed(base, refs, settings["match_radius_km"])
    sat_zen, sat_az = nd.satellite_angles(base.longitude.to_numpy(), base.latitude.to_numpy())
    sun_az = nd.sun_azimuth(base.acq_datetime_utc, base.longitude, base.latitude)
    base["glint_deg"] = np.where(base.daynight.eq("D"), nd.glint_angle_deg(base.sza_deg, sun_az, sat_zen, sat_az), np.nan)

    # Reproduction check against the stored Phase 3c fire pixels.
    stored = pd.read_parquet(ROOT / "data/processed/geo_fires/platform=Himawari/region=Northern_Australia")
    repro = {"stored_pixels": int(len(stored)), "recomputed_pixels": int(len(base)),
             "corrected_time_matched_share": float(base.reference_match.mean()),
             "stored_unmatched_share": float(1 - stored.reference_match.mean()),
             "note": "stored share predates the D72 nearby() fix (D71)"}

    cases = pd.read_csv(ROOT / "outputs/phase3c_naus/viirs_cases.csv", low_memory=False)
    cases = cases[cases.box_Northern_Australia.astype(str).eq("True")]
    h = nd.hourly_table(hourly, base, cases, refs)
    h.to_csv(OUT / "hourly.csv", index=False)
    thr = nd.threshold_effect(fires)
    thr.to_csv(OUT / "threshold_effect_by_hour.csv", index=False)

    # Commission only where a reference sensor observed.
    obs_hours = set(h.loc[h.reference_observed_hour, "lst_hour"])
    b = base.assign(lst_hour=np.floor(base.lst_h).astype(int))
    in_ref = b[b.lst_hour.isin(obs_hours)]
    b["cell"] = (np.floor(b.longitude).astype(int).astype(str) + "E_" + np.floor(-b.latitude).astype(int).astype(str) + "S")
    by_cell = b.groupby("cell").agg(fire_pixels=("frp_mw", "size"), unmatched=("reference_match", lambda x: int((~x).sum())),
                                    unmatched_in_reference_hours=("lst_hour", lambda x: int((~b.loc[x.index, "reference_match"] & x.isin(obs_hours)).sum())),
                                    location_confirmed_share=("location_confirmed", "mean")).sort_values("fire_pixels", ascending=False)
    by_cell.to_csv(OUT / "unmatched_by_1deg_cell.csv")
    persistent = nd.persistent_locations(base)
    persistent.to_csv(OUT / "persistent_unmatched_locations.csv")

    # Diurnal fits (in memory only).
    fits = {"as_published": nd.summarize(diurnal.fit_region(stats["baseline"], settings)[0]),
            "time_matched_only_corrected_60min": nd.refit(stats["baseline"], base, base.reference_match, settings),
            "location_confirmed_only": nd.refit(stats["baseline"], base, base.location_confirmed, settings),
            "excluding_persistent_unmatched": nd.refit(stats["baseline"], base, ~base.pixel_id.isin(persistent.index), settings),
            "counterfactual_day_threshold_300K": nd.summarize(diurnal.fit_region(stats["day_at_300K"], settings)[0]),
            "counterfactual_night_threshold_310K": nd.summarize(diurnal.fit_region(stats["night_at_310K"], settings)[0]),
            "area_normalized_all_scans_all_detections": nd.refit_area_normalized(stats["baseline"], base, np.ones(len(base), bool), settings),
            "area_normalized_all_scans_location_confirmed": nd.refit_area_normalized(stats["baseline"], base, base.location_confirmed, settings)}
    fires["location_confirmed"] = nd.location_confirmed(fires, refs, settings["match_radius_km"])
    by_variant = fires.groupby(["variant", "daynight"]).agg(pixels=("frp_mw", "size"), frp_mw=("frp_mw", "sum"),
                                                          location_confirmed_share=("location_confirmed", "mean")).reset_index()
    by_variant.to_csv(OUT / "threshold_effect_day_night.csv", index=False)
    top = nd.top_unmatched_locations(base)
    top.to_csv(OUT / "top10_unmatched_locations.csv", index=False)
    obs_cases = cases[cases.status.isin([0, 1])]
    viirs_dn = obs_cases.groupby("daynight").agg(n=("detected", "size"), rate=("detected", "mean"),
                                               median_frp_mw=("frp_mw", "median")).reset_index()
    viirs_dn.to_csv(OUT / "viirs_detection_day_night.csv", index=False)
    day, night = b[b.daynight.eq("D")], b[b.daynight.eq("N")]
    summary = {
        "reproduction": repro, "fits": fits,
        "reference_observed_hours": sorted(int(x) for x in obs_hours),
        "commission": {"overall_unmatched_share": float(1 - base.reference_match.mean()),
                       "unmatched_share_in_reference_hours": float(1 - in_ref.reference_match.mean()) if len(in_ref) else None,
                       "n_in_reference_hours": int(len(in_ref)),
                       "unmatched_share_outside_reference_hours": float(1 - b[~b.lst_hour.isin(obs_hours)].reference_match.mean()),
                       "location_confirmed_share_all": float(base.location_confirmed.mean()),
                       "n_persistent_locations": int(len(persistent)),
                       "n_pixels_at_persistent_locations": int(base.pixel_id.isin(persistent.index).sum()),
                       "daytime_glint_lt_12deg": int((base.glint_deg < nd.GLINT_DEG).sum())},
        "day_night": {"day_pixels": int(len(day)), "night_pixels": int(len(night)),
                      "day_frp_mw": float(day.frp_mw.sum()), "night_frp_mw": float(night.frp_mw.sum()),
                      "day_location_confirmed": float(day.location_confirmed.mean()),
                      "night_location_confirmed": float(night.location_confirmed.mean())},
        "threshold_totals": {v: {"pixels": int((fires.variant == v).sum()), "frp_mw": float(fires.loc[fires.variant == v, "frp_mw"].sum())}
                             for v in fires.variant.unique()},
    }
    hw.json_write(OUT / "summary.json", summary)
    nd.plot(h, {k: fits[k] for k in ("as_published", "location_confirmed_only", "counterfactual_night_threshold_310K")}, cfg)
    print(json.dumps(summary, indent=1, default=str))
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(h.round(3).to_string())
        print(thr.to_string())
        print(persistent.head(10).round(3).to_string())
        print(by_variant.round(3).to_string()); print(top.round(3).to_string()); print(viirs_dn.round(3).to_string())
        print(by_cell.head(12).to_string())


if __name__ == "__main__":
    main()
