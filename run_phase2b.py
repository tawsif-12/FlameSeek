"""FlameSeek Phase 2b: overpass-time drift history (Terra, Aqua, S-NPP, NOAA-20, NOAA-21).

    python run_phase2b.py

Downloads one late-October FIRMS SP sample per year (cached in data/raw/firms_archive/),
computes median daytime local solar time per platform and year, the Aqua–S-NPP time
difference per year, the first drifted year per MODIS platform and the calibration years.
Writes data/processed/drift_by_year.csv, outputs/figures/overpass_lst_by_year.png,
outputs/phase2b_drift_report.md, and the first drifted years into config/settings.yaml
(drift.first_drift_year), which Step 1 uses for the `drifted_era` column.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from pipeline import drift
from pipeline.config import DEFAULT_SETTINGS, ROOT, ensure_dirs, load_settings

# 2026 values computed from the TLE overpasses in Phase 2 (outputs/phase2_report.md, A2).
PHASE2_OVERPASS_LST = {"Terra": 8 + 35 / 60, "NOAA-21": 13 + 23 / 60, "NOAA-20": 13 + 30 / 60,
                       "S-NPP": 13 + 37 / 60, "Aqua": 15 + 46 / 60}


def write_first_drift(path, first: dict) -> None:
    text = path.read_text(encoding="utf-8")
    val = "{" + ", ".join(f"{k}: {v if v is not None else 'null'}" for k, v in first.items()) + "}"
    text = re.sub(r"(  first_drift_year: )\{[^}]*\}", lambda m: m.group(1) + val, text)
    path.write_text(text, encoding="utf-8")


def main() -> dict:
    cfg = load_settings()
    ensure_dirs(cfg)
    d = cfg["drift"]
    res = drift.history(cfg)
    lst, pairs = res["lst"], res["pairs"]
    wide = lst.pivot(index="year", columns="platform", values="lst_median")
    table = wide.join(lst.pivot(index="year", columns="platform", values="n_day_detections")
                      .add_prefix("n_")).join(pairs.set_index("year"))
    table["calibration_year"] = table.index.isin(res["calibration_years"])
    table.to_csv(ROOT / "data" / "processed" / "drift_by_year.csv")
    drift.plot(res, PHASE2_OVERPASS_LST, ROOT / "outputs" / "figures" / "overpass_lst_by_year.png", cfg)
    write_first_drift(DEFAULT_SETTINGS, {k: res["first_drift"][k] for k in ("Terra", "Aqua")})

    H = drift.hhmm
    pre = pairs[pairs["year"] < min(v for v in res["first_drift"].values() if v)]
    plats = [p for p in ("Terra", "Aqua", "S-NPP", "NOAA-20", "NOAA-21") if p in wide.columns]
    L = ["# Phase 2b: overpass-time drift history", "",
         f"Sample: daytime FIRMS detections on {d['window_start']} (+{d['window_days'] - 1} day) each year, "
         f"|lat| ≤ {d['lat_band']}°. {d['first_year']}–{d['last_archive_year']} from the FIRMS standard-"
         f"processing archive (cached in `{d['archive_dir']}/`); {d['current_year']} from `data/raw/` (Phase 2 "
         f"data). {res['n_detections']:,} daytime detections in all. Figure: "
         "`outputs/figures/overpass_lst_by_year.png`; table: `data/processed/drift_by_year.csv`.", "",
         "## Median local solar time of daytime detections", "",
         "| Year | " + " | ".join(plats) + " | Aqua–S-NPP median abs(Δt) | Pairs | Calibration year |",
         "|---|" + "---|" * len(plats) + "---|---|---|"]
    for y, r in table.iterrows():
        cells = [H(r.get(p, np.nan)) for p in plats]
        L.append(f"| {y} | " + " | ".join(cells) +
                 f" | {('%.1f min' % r['aqua_snpp_dt_median_min']) if np.isfinite(r['aqua_snpp_dt_median_min']) else '–'}"
                 f" | {int(r['n_pairs']):,} | {'yes' if r['calibration_year'] else 'no'} |")
    L += ["", f"2026 overpass times computed from TLEs in Phase 2 (diamonds in the figure): "
          + ", ".join(f"{k} {H(v)}" for k, v in PHASE2_OVERPASS_LST.items()) + ".", "",
          "## Drift", "",
          f"Early-archive value = median of {', '.join(map(str, d['baseline_years']))}. A platform has drifted "
          f"in the first year its median LST is more than {d['drift_threshold_min']} min from that value.", "",
          "| Platform | Early-archive LST | First drifted year | LST that year | Latest LST |", "|---|---|---|---|---|"]
    for p in ("Terra", "Aqua", "S-NPP"):
        s = wide[p].dropna()
        fy = res["first_drift"][p]
        L.append(f"| {p} | {H(res['baseline'][p])} | {fy if fy else 'none (no drift > 30 min)'} | "
                 f"{H(s.loc[fy]) if fy else '–'} | {H(s.iloc[-1])} ({s.index[-1]}) |")
    cy = res["calibration_years"]
    L += ["", "## Definitions now used by the pipeline", "",
          f"- **Calibration years** (median Aqua–S-NPP abs(Δt) ≤ {d['calib_max_dt_min']} min, at least "
          f"{d['min_pairs_per_year']} pairs): {', '.join(map(str, cy)) if cy else 'none'}.",
          f"- **Drifted era**: a MODIS detection is `drifted_era = true` when its year is at or after its "
          f"platform's first drifted year (Terra {res['first_drift']['Terra']}, Aqua "
          f"{res['first_drift']['Aqua']}). The values are stored in `config/settings.yaml` "
          "(`drift.first_drift_year`), and Step 1 writes the column for every MODIS row. VIIRS rows are "
          "left empty (not applicable).",
          f"- All MODIS detections in the current data ({d['current_year']}) are in the drifted era, and "
          f"{d['current_year']} is {'a' if d['current_year'] in cy else 'not a'} calibration year. The "
          "Phase 2 FRP calibration therefore comes from drifted-era pairs; a calibration from "
          "calibration-year archive data is the next step.",
          "", "## Limits", "",
          f"- **The calibration-year list is fragile.** Before any drift ({d['first_year']}–"
          f"{min(v for v in res['first_drift'].values() if v) - 1}), the Aqua–S-NPP median abs(Δt) already ranges "
          f"{pre['aqua_snpp_dt_median_min'].min():.0f}–{pre['aqua_snpp_dt_median_min'].max():.0f} min from year to year. "
          "Both satellites cross at about 13:30, but on any two given days their ground tracks are "
          "offset by a varying part of an orbit, so a 2-day sample mostly measures that phase, not "
          "drift. A wider sample per year (e.g. all of October) is needed before the ≤ 20 min rule is "
          "used to pick calibration data.",
          "- One 2-day late-October sample per year. It shows the trend; it is not a full-year mean.",
          "- Median LST of detections also depends on where fires are within the swath. The "
          "|lat| ≤ 30° band and the same calendar window keep this similar from year to year.",
          "- The Aqua–S-NPP Δt uses detections, not events: the nearest S-NPP detection within "
          f"{d['pair_radius_km']} km on the same UTC day."]
    (ROOT / "outputs" / "phase2b_drift_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    print("\n".join(L))
    return res


if __name__ == "__main__":
    main()
