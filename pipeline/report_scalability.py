"""Write outputs/scalability_report.md from measured files only.

    python -m pipeline.report_scalability [--window current_2026]

Reads outputs/benchmark.csv, the window tables, the batch snapshot, params/*.json,
the window's eras.csv and history_status.json, and reruns the (fast) simulated tests'
measurements. Projections are linear extrapolations of measured per-day costs and say so.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from pipeline import params as params_mod
from pipeline.config import ROOT, load_settings


def bench_section(cfg) -> list[str]:
    f = ROOT / "outputs" / "benchmark.csv"
    if not f.exists():
        return ["Benchmark not run yet (`python run_benchmark.py`)."]
    from run_benchmark import extrapolate
    b = pd.read_csv(f)
    L = ["Measured with `python run_benchmark.py` (1 worker, `--force`, separate partition folders; late-October "
         "2026 data). Figure: `outputs/figures/scaling.png`; raw numbers: `outputs/benchmark.csv`.", "",
         "| Region | Days | Detections | Events | raw_split s | detect s | link s | grid s | finalize s | Total s | Peak MB | Partitions MB |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (region, days), g in b.groupby(["region", "days"]):
        s = g.set_index("stage")
        L.append(f"| {region} | {days} | {int(s['n_detections'].iloc[0]):,} | {int(s['n_events'].iloc[0]):,} | "
                 + " | ".join(f"{s.loc[st, 'seconds']:.1f}" if st in s.index else "–"
                              for st in ("raw_split", "detect", "link", "grid", "finalize", "total"))
                 + f" | {s['peak_mb'].max():.0f} | {s['partition_mb'].iloc[0]:.0f} |")
    x = extrapolate(b)
    L += ["", "### Is growth linear?", "",
          "Fit seconds = fixed + per_day × days for each stage (R² of the linear fit; log–log exponent "
          "1.0 = linear).", "",
          "| Region | Stage | s per day | Fixed s | R² | Exponent | Peak MB (1 → 5 days) |", "|---|---|---|---|---|---|---|"]
    for _, r in x.iterrows():
        L.append(f"| {r['region']} | {r['stage']} | {r['sec_per_day']:.1f} | {r['fixed_sec']:.1f} | "
                 f"{r['r2_linear']:.3f} | {r['loglog_exponent']:.2f} | {r['peak_mb_min']:.0f} → {r['peak_mb_max']:.0f} |")
    tot = x[x["stage"] == "total"].set_index("region")
    per_day_store = b[b["stage"] == "total"].groupby("region").apply(
        lambda g: np.polyfit(g["days"], g["partition_mb"], 1)[0], include_groups=False)
    det_per_day = b[b["stage"] == "total"].groupby("region").apply(
        lambda g: np.polyfit(g["days"], g["n_detections"], 1)[0], include_groups=False)
    workers = cfg["partitions"]["workers"]
    L += ["", "### Extrapolation", "",
          "Linear in days at the measured late-October rate. Fire activity varies through the year (the "
          "global peak is around Aug–Sep), so treat these as order-of-magnitude figures. Detect and grid "
          f"run in parallel; the column \"{workers} workers\" divides those two stages by {workers} "
          "(link and finalize are serial).", "",
          "| Region | Clean detections per day | 1 year, 1 worker | 1 year, %d workers | 15 years, 1 worker | 15 years, %d workers | Partition storage, 15 years |" % (workers, workers),
          "|---|---|---|---|---|---|---|"]
    for region in tot.index:
        st = x[x["region"] == region].set_index("stage")
        par = sum(st.loc[s_, "sec_per_day"] for s_ in ("detect", "grid") if s_ in st.index)
        ser = sum(st.loc[s_, "sec_per_day"] for s_ in ("raw_split", "link", "finalize") if s_ in st.index)
        one = (par + ser) * 365 / 3600
        onep = (par / workers + ser) * 365 / 3600
        L.append(f"| {region} | {det_per_day[region]:,.0f} | {one:,.1f} h | {onep:,.1f} h | {one * 15 / 24:,.1f} days | "
                 f"{onep * 15 / 24:,.1f} days | {per_day_store[region] * 365 * 15 / 1024:,.0f} GB |")
    return L


def equivalence_section(cfg) -> list[str]:
    W, I = cfg["paths"]["window_processed"], cfg["paths"]["window_interim"]
    leg = ROOT / "data" / "interim" / "legacy_batch"
    if not (leg / "fire_events.csv").exists() or not (W / "fire_events.csv").exists():
        return ["Batch snapshot or window outputs missing."]
    cols = ["source_file", "source_row", "frp_mw", "fire_id"]
    n, o = pd.read_parquet(W / "detections_clean.parquet", columns=cols), pd.read_parquet(leg / "detections_clean.parquet", columns=cols)
    en, eo = pd.read_csv(W / "fire_events.csv", low_memory=False), pd.read_csv(leg / "fire_events.csv", low_memory=False)
    gn = {frozenset(zip(g.source_file, g.source_row)) for _, g in n.groupby("fire_id")}
    go = {frozenset(zip(g.source_file, g.source_row)) for _, g in o.groupby("fire_id")}
    pairs = len(pd.read_csv(I / "matched_pairs_aqua_viirs.csv"))
    return ["| Check | Batch (before) | Day-by-day (now) |", "|---|---|---|",
            f"| Clean detections | {len(o):,} | {len(n):,} (same rows: "
            f"{set(zip(n.source_file, n.source_row)) == set(zip(o.source_file, o.source_row))}) |",
            f"| Total FRP (MW) | {o.frp_mw.sum():,.2f} | {n.frp_mw.sum():,.2f} |",
            f"| Fire events | {len(eo):,} | {len(en):,} ({(len(en) - len(eo)) / len(eo):+.2%}) |",
            f"| Identical event groupings | | {len(gn & go):,} of {len(go):,} ({len(gn & go) / len(go):.2%}) |",
            f"| Largest event extent | {eo.extent_km.max():.2f} km | {en.extent_km.max():.2f} km |",
            f"| Aqua–VIIRS pairs (≤ 60 min) | 416 | {pairs:,} |", "",
            "Differences come only from where the 25 km cap splits a multi-day component: batch split the "
            "whole component after the fact, day-by-day decides each day from the previous day (decisions D38)."]


def params_section(cfg) -> list[str]:
    L = ["| File | Status | Source window | Sample size | Fit method |", "|---|---|---|---|---|"]
    for kind in params_mod.KINDS:
        for v in params_mod.versions(kind, cfg):
            d = params_mod.load(kind, v, cfg=cfg)
            L.append(f"| `{kind}_v{v}.json` | **{d['status']}** | {d['source_window'].get('window')} "
                     f"({d['source_window'].get('start')}–{d['source_window'].get('end')}) | "
                     f"{d['sample_size']} | {d['fit_method']} |")
    return L


def simulated_section(cfg) -> list[str]:
    sys.path.insert(0, str(ROOT / "tests" / "simulated"))
    from generate import circ_dist, simulate

    from forecast import climatology, evaluate
    from pipeline import anomalies, calendar
    df, truth = simulate()
    cal = calendar.build_calendar(df, cfg)
    found = cal["peak"].set_index("cell_id")["peak_week"]
    err = np.array([circ_dist(found[c], truth["peak_week"][c]) for c in found.index])
    an = anomalies.detect(df, cfg)
    t = an["table"].set_index(["cell_id", "year", "week"])
    flags = set(t[t["anomaly_flag"]].index)
    planted = set(truth["anomalies"])
    false = flags - planted
    false_post = sum(1 for k in false if k[1] >= truth["step_year"])
    annual = df.groupby("year")["value"].sum()
    pt = anomalies.pettitt(annual.to_numpy(), annual.index, cfg)
    ctrl, _ = simulate(step_factor=1.0, seed=11)
    pc = anomalies.pettitt(ctrl.groupby("year")["value"].sum().to_numpy(), None, cfg)
    yrs = sorted(df["year"].unique())
    tr, te = df[df["year"] <= yrs[-4]], df[df["year"] > yrs[-4]]
    m = climatology.fit(tr, cfg)
    p = climatology.predict(m, te)
    base = (tr["value"] > 0).mean()
    rel = evaluate.reliability(p["p"], p["y"])
    figs = ROOT / "outputs" / "figures"
    evaluate.plot_reliability(rel, figs / "reliability_simulated.png",
                              "Climatology forecast on simulated data (train 2011–2022, test 2023–2025)")
    big = rel[rel["n"] >= 200]
    return [f"Synthetic data (`tests/simulated/generate.py`): {df['cell_id'].nunique()} cells × "
            f"{df['year'].nunique()} years × 52 weeks, a known seasonal peak per cell, negative-binomial noise, "
            f"a step change ×{truth['step_factor']} from {truth['step_year']}, and {len(planted)} planted anomalies.",
            "", "| Component | Test | Result |", "|---|---|---|",
            f"| Calendar | seasonal peak week recovered | {(err == 0).sum()} cells exact, {(err == 1).sum()} within ±1 week, "
            f"{(err > 1).sum()} off by more (of {len(err)}) |",
            f"| Anomalies (negative binomial) | planted anomalies found | {len(planted & flags)} of {len(planted)} |",
            f"| Anomalies | false alarms | {len(false):,} of {len(t):,} cell-weeks ({len(false) / len(t):.2%}); "
            f"{false_post:,} of them after the step change |",
            f"| Pettitt | step change located | first changed year {pt['first_after_change']} (true "
            f"{truth['step_year']}), p = {pt['p_value']:.4f} (the floor for 15 years); no-step control p = {pc['p_value']:.2f} |",
            f"| Climatology forecast | skill on held-out years | Brier {evaluate.brier(p['p'], p['y']):.3f}, BSS "
            f"{evaluate.brier_skill(p['p'], p['y'], base):.3f} vs. constant base rate {base:.3f} |",
            f"| Climatology forecast | reliability | max abs(observed − forecast) in bins with ≥ 200 cases: "
            f"{(big['obs_freq'] - big['mean_p']).abs().max():.3f}; figure `outputs/figures/reliability_simulated.png` |",
            "| XGBoost | training | written; status \"requires multi-year data\" (xgboost is not installed in the env yet) |",
            "", "The false alarms cluster after the step change: the baseline pools all other years, so a "
            "lasting increase reads as many moderate anomalies until a trend-aware baseline (Step 9 refinement) is used."]


def write(window=None) -> str:
    cfg = load_settings(window=window)
    w = cfg["window"]
    eras = pd.read_csv(cfg["paths"]["window_processed"] / "eras.csv")
    hist = json.loads((cfg["paths"]["window_outputs"] / "history_status.json").read_text())
    L = ["# FlameSeek scalability report", "",
         f"Window used for measurements: `{w['name']}` ({w['start']} – {w['end']}). Every number below was "
         "measured in this project; projections are labelled as such.", "",
         "## 1. Architecture", "",
         "| Piece | What it does |", "|---|---|",
         "| Windows | `config/settings.yaml` → `windows:`. Every command takes `--window`. |",
         "| Day partitions | `data/processed/<stage>/year=YYYY/month=MM/day=DD/part.parquet`; one partition per local solar day per stage, atomic writes. |",
         "| raw_split | One pass over the raw CSVs: UTC-day parts, partial days, bbox, and per-month minute histograms of local solar time (for eras). |",
         "| detect (parallel) | Per local day: ingest → region filter (bbox first) → quality → footprints → daily clustering, with the 25 km cap inside the day. |",
         "| link (sequential) | Per day, reading only day D−1: footprint overlaps → fire ids; caps; `event_state` (hull, start day); `merges`. |",
         "| grid (parallel) | Per day: area-weighted 0.1° grid, FRP per overpass, energy check. |",
         "| finalize | DuckDB over the partitions; merges resolved (union-find); events built in month chunks (+14 days). |",
         "| Incremental | Existing day partitions are skipped unless `--force`; reruns are identical (tested). |",
         "| Parallel | `concurrent.futures.ProcessPoolExecutor`, `partitions.workers` in config or `--workers`. |",
         "| Params | `params/<kind>_vN.json`; only `refit_params.py --window` writes them. |",
         "| Eras | Measured per platform-month from the data (median daytime LST vs. the platform's own early-archive value). |",
         "| Multi-year modules | `pipeline/calendar.py`, `pipeline/anomalies.py`, `forecast/`; return `insufficient_history` on short records. |",
         "", "## 2. Same results as before the refactor", ""] + equivalence_section(cfg)
    L += ["", "## 3. Scaling benchmark", ""] + bench_section(cfg)
    L += ["", "## 4. Eras measured in this window", "",
          "| Platform | Month | Daytime detections | Median LST | Reference | Deviation | Drifted | Era |",
          "|---|---|---|---|---|---|---|---|"]
    for _, r in eras.iterrows():
        hh = lambda h: f"{int(h):02d}:{int(round(h % 1 * 60)):02d}"  # noqa: E731
        L.append(f"| {r['platform']} | {r['month']} | {int(r['n_day_lst']):,} | {hh(r['lst_median_h'])} | "
                 f"{hh(r['reference_h'])} | {r['deviation_min']:+.0f} min | {r['drifted']} | {r['era_sensor']} |")
    L += ["", "## 5. Parameters: provisional vs validated", ""] + params_section(cfg)
    sync_dir = ROOT / "data" / "raw" / "archive" / "2016"
    L += ["", f"- **No parameter is validated yet.** The sync window `sync_2016` was not run: "
          f"`{sync_dir.relative_to(ROOT).as_posix()}/` {'is empty' if sync_dir.exists() else 'does not exist'}. "
          "The v1 files stay provisional (Part 2.4).",
          "- The 2-day archive sample (Phase 2b) gives 29–30 Oct 2016 an Aqua–S-NPP median abs(Δt) of 32 min, "
          "above the 20-min sync rule; 2015, 2018 and 2021 met it in that sample (decisions D37, D45).",
          "- `diurnal_v1.json` is not_available: Step 7 needs Himawari data."]
    L += ["", "## 6. Multi-year components", "", "### On simulated data", ""] + simulated_section(cfg)
    L += ["", f"### On the real window ({', '.join(map(str, hist['years_in_window']))})", "",
          "| Component | Status | Years available / required |", "|---|---|---|"]
    for k in ("calendar", "anomalies", "changepoint", "forecast_climatology", "forecast_xgboost"):
        d = hist[k]
        L.append(f"| {k} | {d['status']} | {d.get('years_available')} / {d.get('years_required')} |")
    L += ["", "## 7. What must be added to run 10–15 years", "",
          "**Data**",
          "- FIRMS standard-processing (SP) archive, global or per region, for every year: MODIS C6.1 (Terra, "
          "Aqua), VIIRS S-NPP, NOAA-20 (from 2018), NOAA-21 (from 2023). The FIRMS API used here serves at most "
          "a few days per request, so a full archive needs the FIRMS archive download (yearly files, requested "
          "with an Earthdata login) placed in `data/raw/archive/<year>/`, plus one window per year in the config.",
          "- MCD12Q1 land cover (biome per cell per year) and MCD64A1 burned area (validation), from LAADS/LP DAAC.",
          "- Himawari-8/9 AHI L1b bands B07 and B14 (NOAA open data on AWS, no account), for Step 7.",
          "- Historical TLEs per date (Space-Track), so observation opportunities use the elements valid at the "
          "time instead of current elements back-propagated.",
          "- A cloud mask (e.g. MODIS/VIIRS cloud products) to make observation opportunities cloud-adjusted.",
          "", "**Accounts**",
          "- NASA Earthdata login (FIRMS archive, LAADS, LP DAAC). The FIRMS MAP_KEY already in `backend/.env` "
          "covers API samples only.",
          "- Space-Track.org account (historical TLEs).",
          "", "**Compute and storage**: see the extrapolation table in section 3. All stages keep memory per "
          "day, so memory does not grow with the number of days; runtime and storage grow linearly. The "
          "largest single cost is `detect`, because each local day re-standardises three UTC days (D40).",
          "", "**Code still to write**: Step 7 (Himawari diurnal), Step 8 (latent fire field and Monte Carlo), "
          "a trend-aware anomaly baseline, and the XGBoost forecast training run (`pip install xgboost`)."]
    text = "\n".join(L) + "\n"
    (ROOT / "outputs" / "scalability_report.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default=None)
    write(ap.parse_args().window)
    print("wrote outputs/scalability_report.md")
