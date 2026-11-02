"""Run FlameSeek Steps 1-5 day by day for one window.

    python run_pipeline.py [--window current_2026] [--force] [--workers 4] [--skip-inspect]

Stages (each reads/writes one partition per day under data/processed/<stage>/year=/month=/day=):
  raw_split -> detect (parallel) -> link (sequential, uses only the previous day) ->
  grid (parallel) -> finalize (DuckDB + pandas, month chunks) -> report
Days whose partitions exist are skipped unless --force. The window tables go to
data/processed/windows/<window>/ and data/interim/windows/<window>/.
"""
from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

from pipeline import eras as eras_mod
from pipeline import figures, inspect_raw, report, stages
from pipeline.config import DEFAULT_SETTINGS, ROOT, ensure_dirs, load_settings


# ------------------------------------------------------- stage monitor -------
class StageMonitor:
    """Wall time and peak resident memory (this process + worker processes) per stage."""

    def __init__(self):
        import psutil
        self.proc = psutil.Process()
        self.rows = []

    def _rss(self):
        tot = self.proc.memory_info().rss
        for c in self.proc.children(recursive=True):
            try:
                tot += c.memory_info().rss
            except Exception:
                pass
        return tot

    def run(self, name, fn, *a, **k):
        peak = [self._rss()]
        stop = threading.Event()

        def sample():
            while not stop.is_set():
                peak[0] = max(peak[0], self._rss())
                stop.wait(0.05)
        th = threading.Thread(target=sample, daemon=True)
        th.start()
        t0 = time.perf_counter()
        try:
            out = fn(*a, **k)
        finally:
            stop.set()
            th.join()
        self.rows.append({"stage": name, "seconds": time.perf_counter() - t0, "peak_mb": peak[0] / 2**20})
        print(f"[{name}] {self.rows[-1]['seconds']:.1f}s, peak {self.rows[-1]['peak_mb']:.0f} MB")
        return out


def _map_days(fn, cfg, days, force, workers):
    if workers <= 1 or len(days) <= 1:
        return [fn(cfg, d, force) for d in days]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fn, cfg, d, force) for d in days]
        return [f.result() for f in futs]


def configure(window=None, partition_root=None, start=None, end=None, tag=None) -> dict:
    """Settings for a window; optional start/end override (sub-window) and output tag."""
    cfg = load_settings(DEFAULT_SETTINGS, window=window, partition_root=partition_root)
    if start or end:
        cfg["window"]["start"] = date.fromisoformat(start) if isinstance(start, str) else (start or cfg["window"]["start"])
        cfg["window"]["end"] = date.fromisoformat(end) if isinstance(end, str) else (end or cfg["window"]["end"])
    if tag:
        cfg["window"]["name"] = tag
        for k, sub in (("window_processed", "processed"), ("window_interim", "interim")):
            cfg["paths"][k] = ROOT / "data" / "bench" / tag / sub
        cfg["paths"]["processed_dir"] = cfg["paths"]["window_processed"]
        cfg["paths"]["interim_dir"] = cfg["paths"]["window_interim"]
        cfg["paths"]["window_outputs"] = ROOT / "data" / "bench" / tag / "outputs"
        cfg["paths"]["figures_dir"] = cfg["paths"]["window_outputs"] / "figures"
        cfg["paths"]["report"] = cfg["paths"]["window_outputs"] / "phase1_report.md"
        cfg["paths"]["inspection_report"] = cfg["paths"]["window_outputs"] / "raw_inspection_report.md"
    return cfg


def main(window=None, force=False, workers=None, skip_inspect=False, make_report=True,
         partition_root=None, start=None, end=None, tag=None) -> dict:
    t_all = time.perf_counter()
    cfg = configure(window, partition_root, start, end, tag)
    ensure_dirs(cfg)
    workers = workers or cfg["partitions"]["workers"]
    mon = StageMonitor()
    w = cfg["window"]
    print(f"Window {w['name']}: {w['start']} .. {w['end']} (UTC), raw {w['raw_dir']}, workers {workers}, "
          f"partitions {cfg['paths']['partition_root']}")

    facts = {"problems": [], "sensors_present": []}
    if not skip_inspect:
        text, facts = mon.run("inspect", inspect_raw.build_report, cfg)
        cfg["paths"]["inspection_report"].parent.mkdir(parents=True, exist_ok=True)
        cfg["paths"]["inspection_report"].write_text(text, encoding="utf-8")
    man = mon.run("raw_split", stages.raw_split, cfg, force)
    days = stages.local_days(cfg)
    det_res = mon.run("detect", _map_days, stages.detect_day, cfg, days, force, workers)
    link_res = mon.run("link", lambda: [stages.link_day(cfg, d, force) for d in days])
    grid_res = mon.run("grid", _map_days, stages.grid_day, cfg, days, force, workers)
    fin = mon.run("finalize", stages.finalize, cfg)
    summary = {}
    if make_report:
        summary = mon.run("report", write_report, cfg, man, fin, facts)
    total = time.perf_counter() - t_all
    print(f"\nDone in {total:.1f}s. Window tables: {cfg['paths']['window_processed'].relative_to(ROOT).as_posix()}")
    return {"cfg": cfg, "stages": mon.rows, "total_seconds": total, "finalize": fin, "manifest": man,
            "detect": det_res, "link": link_res, "grid": grid_res, "summary": summary}


# ------------------------------------------------------------------ report ---
def write_report(cfg, man, fin, facts) -> dict:
    import duckdb
    root = cfg["paths"]["partition_root"]
    d0, d1 = stages.local_days(cfg)[0], stages.local_days(cfg)[-1]
    det, ev, gov = fin["detections"], fin["events"], fin["grid_overpass"]
    ds = fin["day_stats"]
    from pipeline import partitions as P
    ls = P.duck(root, "link_stats", d0, d1)
    rem = fin["removed"]
    reason_counts = (rem["flags"].dropna().str.split(";").explode().value_counts().to_dict() if len(rem) else {})
    n_low = fin["n_lowconf"]
    reason_counts["low_confidence"] = reason_counts.get("low_confidence", 0) + n_low
    n_out = int(ds["n_outside_bbox"].sum()) if "n_outside_bbox" in ds else 0
    if n_out:
        reason_counts["outside_study_area (dropped at ingest, region first)"] = n_out

    ranges = {}
    for sensor, g in det.groupby("sensor"):
        lo, hi = cfg["footprints"]["area_range_km2"][sensor]
        a = g["footprint_area_km2"]
        ranges[sensor] = {"n": len(g), "min_km2": float(a.min()), "max_km2": float(a.max()),
                          "median_km2": float(a.median()), "scan_min": float(g["scan_km"].min()),
                          "scan_max": float(g["scan_km"].max()), "track_min": float(g["track_km"].min()),
                          "track_max": float(g["track_km"].max()), "expected": [lo, hi],
                          "n_outside": int(((a < lo) | (a > hi)).sum())}
    before, after = float(det["frp_mw"].sum()), float(gov["frp_mw"].sum()) if len(gov) else 0.0
    rel = abs(after - before) / before if before else 0.0
    energy = {"frp_before_mw": before, "frp_after_mw": after, "rel_diff": rel,
              "pass": rel <= cfg["grid"]["energy_rel_tol"], "max_weight_sum_deviation": np.nan}
    print(f"Energy conservation: before {before:.6f} MW, after {after:.6f} MW, rel. diff {rel:.2e} -> "
          f"{'PASS' if energy['pass'] else 'FAIL'}")
    n_split_day = int(ds.get("n_day_split_components", pd.Series(dtype=int)).fillna(0).sum())
    n_split_link = int(ls.get("n_link_split_components", pd.Series(dtype=int)).fillna(0).sum()) if len(ls) else 0
    split_ext = int(ds.get("n_day_split_extent", pd.Series(dtype=int)).fillna(0).sum()) + \
        (int(ls.get("n_link_split_extent", pd.Series(dtype=int)).fillna(0).sum()) if len(ls) else 0)
    split_dur = int(ds.get("n_day_split_duration", pd.Series(dtype=int)).fillna(0).sum()) + \
        (int(ls.get("n_link_split_duration", pd.Series(dtype=int)).fillna(0).sum()) if len(ls) else 0)
    n_pieces = int((ev["split_reason"].fillna("") != "").sum())
    stats = {"n_raw_components": len(ev) - n_pieces + n_split_day + n_split_link, "n_events": len(ev),
             "n_events_split": n_split_day + n_split_link, "n_split_by_extent": split_ext,
             "n_split_by_duration": split_dur, "n_pieces_from_splits": n_pieces,
             "n_daily_links": int(ds["n_daily_links"].fillna(0).sum()),
             "n_links_overlap": int(ds["n_links_overlap"].fillna(0).sum()),
             "n_links_halfdiag_only": int(ds["n_links_halfdiag_only"].fillna(0).sum()),
             "n_multiday_links": int(ls["n_multiday_links"].fillna(0).sum()) if len(ls) else 0,
             "n_matched_pairs": len(fin["pairs"]),
             "n_events_with_matched_pair": int(fin["pairs"]["fire_id"].nunique()) if len(fin["pairs"]) else 0,
             "day_basis": stages.DAY_COL}

    # Raw counts per UTC day and platform for the bar chart (DuckDB over raw_daily parts).
    files = [str(f) for d in pd.date_range(cfg["window"]["start"], cfg["window"]["end"]).date
             for f in sorted(P.part_dir(root, "raw_daily", d).glob("part-*.parquet"))]
    con = P.connect()
    raw_counts = con.execute(f"SELECT acq_date, trim(CAST(satellite AS VARCHAR)) AS sat, count(*) AS n, "
                             f"min(latitude) AS la0 FROM read_parquet({files!r}, union_by_name=true) "
                             f"GROUP BY 1, 2").df()
    raw_pts = con.execute(f"SELECT latitude, longitude FROM read_parquet({files!r}, union_by_name=true) "
                          f"USING SAMPLE 2000000 ROWS").df()
    con.close()
    from pipeline.inspect_raw import PLATFORM_CODES, parse_acq_date
    raw_counts["utc_date"] = parse_acq_date(raw_counts["acq_date"]).dt.strftime("%Y-%m-%d")
    raw_counts["platform"] = raw_counts["sat"].map(PLATFORM_CODES)
    raw_t = raw_counts.groupby(["utc_date", "platform"])["n"].sum()
    clean_t = det.groupby(["utc_date", "platform"]).size()
    figs = cfg["paths"]["figures_dir"]
    figs.mkdir(parents=True, exist_ok=True)
    figures.map_raw_vs_events(raw_pts, ev, figs / "map_raw_vs_events.png", man["bbox"])
    figures.bar_platform_day_counts(raw_t, clean_t, figs / "detections_per_platform_day.png", man["partial_days"])

    problems = list(facts.get("problems", []))
    for d_ in man["partial_days"]:
        problems.append(f"UTC day {d_} has {man['utc_day_counts'].get(d_, 0):,} raw rows, far below the other days: "
                        "flagged partial_day=true and excluded from daily statistics (download cut-off).")
    n_urt_dup = int(ds["n_urt_duplicates"].fillna(0).sum()) if "n_urt_duplicates" in ds else 0
    problems.append(f"URT near-duplicates of NRT rows dropped (NRT kept): {n_urt_dup:,}.")
    if man["bbox_source"] == "detected":
        problems.append(f"Study bbox detected from the data: {man['bbox']}.")
    else:
        problems.append(f"Study bbox from config (region first, applied at ingest): {man['bbox']}; "
                        f"{n_out:,} detections outside it were dropped before footprints.")
    era = eras_mod.summary(man["eras"])
    for _, r in era[era["drifted"] == True].iterrows():  # noqa: E712
        problems.append(f"{r['platform']} {r['month']}: median daytime LST {r['lst_median_h']:.2f} h is "
                        f"{r['deviation_min']:+.0f} min from its reference ({r['reference_source']}): drifted era.")
    problems.append("NRT files have no `type` column, so volcano/static-source/offshore rows cannot be dropped.")
    era.to_csv(cfg["paths"]["window_processed"] / "eras.csv", index=False)

    n_raw = int(sum(man["utc_day_counts"].values()) + man.get("n_undated", 0))
    written = sorted(p.relative_to(ROOT).as_posix() for p in list(cfg["paths"]["window_processed"].glob("*")) +
                     list(cfg["paths"]["window_interim"].glob("*")) + list(figs.glob("*.png")))
    s = {"n_raw_rows": n_raw, "clean": stages.Count(len(det)), "lowconf": stages.Count(n_low),
         "removed": stages.Count(len(rem)), "reason_counts": reason_counts,
         "not_applied": {"persistent_hotspot_mask": "needs multi-year history (>30% of years rule)",
                         "nightfire_flare_mask": "disabled in config; no VIIRS Nightfire flare list available",
                         "transient_filter": "needs Himawari detections within +/-30 min; no Himawari data",
                         "modis_type_filter": "NRT files have no `type` column"},
         "bbox": man["bbox"], "area_ranges": ranges,
         "area_rel_dev": float(((det["footprint_area_km2"] - det["nominal_area_km2"]).abs() /
                                det["nominal_area_km2"]).max()),
         "events": ev, "event_stats": stats, "energy": energy, "grid_daily": fin["grid_daily"],
         "grid_overpass": gov, "sensors_present": facts.get("sensors_present") or sorted(det["sensor"].unique()),
         "partial_days": man["partial_days"], "day_counts_clean": det.groupby("utc_date").size().to_dict(),
         "problems": problems, "written": written}
    report.write(cfg, s)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default=None)
    ap.add_argument("--force", action="store_true", help="reprocess days whose outputs exist")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--skip-inspect", action="store_true")
    a = ap.parse_args()
    main(a.window, a.force, a.workers, a.skip_inspect)
