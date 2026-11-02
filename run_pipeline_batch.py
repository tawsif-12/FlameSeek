"""LEGACY whole-window batch run of Steps 1-5 (kept as the reference for the day-partitioned
pipeline; see run_pipeline.py). Run FlameSeek harmonization Steps 1-5 from config/settings.yaml.

    python run_pipeline.py [--config config/settings.yaml]

Order: inspect raw data -> Step 1 ingest -> Step 2 quality -> Step 3 footprints
-> Step 4 events -> Step 5 grid -> figures -> outputs/phase1_report.md
"""
from __future__ import annotations

import argparse
import time
import warnings

import pandas as pd

from pipeline import events, figures, footprints, grid, ingest, inspect_raw, quality, report
from pipeline.config import DEFAULT_SETTINGS, ROOT, ensure_dirs, load_settings

warnings.filterwarnings("ignore", category=FutureWarning)


def main(config_path=DEFAULT_SETTINGS) -> dict:
    t0 = time.time()
    cfg = load_settings(config_path)
    ensure_dirs(cfg)
    P = cfg["paths"]
    written = []

    def rel(p):
        written.append(p.relative_to(ROOT).as_posix())
        return p

    # Task 3: inspection report first, so problems are visible before processing.
    text, facts = inspect_raw.build_report(cfg)
    P["inspection_report"].write_text(text, encoding="utf-8")
    print(text)
    rel(P["inspection_report"])

    det = ingest.run(cfg)                                   # Step 1
    qc = quality.run(det, cfg)                              # Step 2
    cfg["_coverage"] = qc["coverage"]                       # used to flag partial grid days
    fp = footprints.run(qc["clean"], cfg)                   # Step 3
    ev = events.run(fp, cfg)                                # Step 4
    gr = grid.run(ev["detections"], cfg)                    # Step 5

    # ---- write tables ----
    stamp = {"data_version": cfg["data_version"], "processing_date": cfg["processing_date"]}
    d = ev["detections"]
    clean_cols = [c for c in d.columns if c != "geometry"]
    d[clean_cols].assign(**stamp).to_parquet(rel(P["processed_dir"] / "detections_clean.parquet"), index=False)
    qc["lowconf"].assign(**stamp).to_parquet(rel(P["interim_dir"] / "detections_lowconf.parquet"), index=False)
    qc["removed"].assign(**stamp).to_parquet(rel(P["interim_dir"] / "detections_removed.parquet"), index=False)
    d[["det_id", "fire_id", "sensor", "platform", "acq_datetime_utc", "scan_km", "track_km",
       "track_heading_deg", "footprint_area_km2", "frp_mw", "p_conf", "geometry"]] \
        .assign(**stamp).to_parquet(rel(P["interim_dir"] / "footprints.geoparquet"), index=False)
    ev["events"].to_csv(rel(P["processed_dir"] / "fire_events.csv"), index=False)
    ev["overpasses"].assign(**stamp).to_csv(rel(P["interim_dir"] / "event_overpasses.csv"), index=False)
    ev["pairs"].to_csv(rel(P["interim_dir"] / "matched_pairs_aqua_viirs.csv"), index=False)
    gr["overpass"].to_csv(rel(P["interim_dir"] / "grid_overpass.csv"), index=False)
    gr["daily"].to_csv(rel(P["processed_dir"] / "grid_daily.csv"), index=False)

    # ---- figures ----
    figures.map_raw_vs_events(det, ev["events"], rel(P["figures_dir"] / "map_raw_vs_events.png"), qc["bbox"])
    figures.bar_platform_day(det, qc["clean"], rel(P["figures_dir"] / "detections_per_platform_day.png"),
                             qc["partial_days"])

    # ---- report ----
    area_rel_dev = float(((fp["footprint_area_km2"] - fp["nominal_area_km2"]).abs()
                          / fp["nominal_area_km2"]).max())
    problems = list(facts["problems"])
    n_dup = qc["reason_counts"].get("duplicate_detection", 0)
    if n_dup:
        problems.append(f"{n_dup:,} rows were exact duplicates of rows in another file and were removed "
                        "(reason `duplicate_detection`).")
    days = det["utc_date"].dropna().unique()
    if len(days) < 3:
        problems.append(f"The input covers {len(days)} UTC day(s) ({', '.join(sorted(days))}), not the "
                        "expected ~5 days, so multi-day linking and the 14-day cap are barely exercised.")
    problems.append("The FIRMS files are a global extract, not Bangladesh only; the detected study bbox is "
                    "near-global. Set `study_bbox` in config/settings.yaml to restrict to the pilot area.")
    ev_ = ev["events"]
    in_bd = ev_["centroid_lat"].between(20.5, 26.7) & ev_["centroid_lon"].between(88.0, 92.7)
    problems.append(f"The Bangladesh pilot box (88.0-92.7 E, 20.5-26.7 N) contains {int(in_bd.sum())} fire events "
                    + ("in this data, so no Bangladesh-specific result can be drawn from this run." if not in_bd.any()
                       else "in this data: too few for Bangladesh-specific statistics (e.g. Step 6 calibration)."))
    n_low_dup = int(det.loc[qc["removed"].index, "p_conf"].eq(0.3).sum()) if len(qc["removed"]) else 0
    if n_low_dup:
        problems.append(f"{n_low_dup:,} of the low-confidence flags sit on duplicate rows, so only "
                        f"{len(qc['lowconf']):,} low-confidence rows are stored in detections_lowconf.parquet.")
    problems.append("NRT files have no `type` column, so volcano/static-source/offshore rows cannot be dropped "
                    "(known limitation in the procedure).")
    rel(P["report"])
    for d_ in qc["partial_days"]:
        problems.append(f"UTC day {d_} has {qc['day_counts'].get(d_, 0):,} detections, far below the other days: "
                        "flagged partial_day=true and excluded from daily statistics (download cut-off).")
    problems.append(f"URT rows: {qc['n_urt_rows']:,}; near-duplicates of NRT rows (same platform, within "
                    f"{cfg['quality']['urt_dup_max_dt_min']} min and {cfg['quality']['urt_dup_max_dist_m']} m): "
                    f"{qc['n_urt_duplicates']:,}" + (" (dropped, NRT kept, reason `urt_duplicate_of_nrt`)."
                                                     if qc['n_urt_duplicates'] else "."))
    summary = {"n_raw_rows": len(det), "clean": qc["clean"], "lowconf": qc["lowconf"], "removed": qc["removed"],
               "reason_counts": qc["reason_counts"], "not_applied": qc["not_applied"], "bbox": qc["bbox"],
               "area_ranges": fp.attrs["area_ranges"], "area_rel_dev": area_rel_dev,
               "events": ev["events"], "event_stats": ev["stats"], "energy": gr["energy"],
               "grid_daily": gr["daily"], "grid_overpass": gr["overpass"],
               "sensors_present": facts["sensors_present"], "partial_days": qc["partial_days"],
               "day_counts_clean": qc["clean"].groupby("utc_date").size().to_dict(), "problems": problems, "written": written}
    report.write(cfg, summary)
    print(f"\nDone in {time.time() - t0:.1f}s. Report: {P['report'].relative_to(ROOT).as_posix()}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_SETTINGS)
    main(ap.parse_args().config)
