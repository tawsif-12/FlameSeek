"""Write outputs/phase1_report.md from the numbers the run actually produced."""
from __future__ import annotations

import pandas as pd


def _pct(n, d):
    return f"{n:,} ({100 * n / d:.1f}%)" if d else f"{n:,}"


def write(cfg: dict, s: dict) -> str:
    ev, st, en = s["events"], s["event_stats"], s["energy"]
    n_ev = len(ev)
    flags = ev["sensor_flag"].value_counts()
    L = ["# Phase 1 report: harmonization Steps 1-5", "",
         f"- Data version: `{cfg['data_version']}`; processing date: {cfg['processing_date']} (UTC)",
         f"- Procedure: `docs/harmonization_procedure.md`; deviations: `docs/decisions.md`",
         f"- Command: `python run_pipeline.py`", "",
         "All numbers below were computed by this run; nothing is estimated or filled in by hand.", "",
         "## 1. Detections and fire events", "",
         "| Stage | Count |", "|---|---|",
         f"| Raw rows read (all files in `data/raw/`) | {s['n_raw_rows']:,} |",
         f"| Removed by sanity checks (incl. duplicates) | {len(s['removed']):,} |",
         f"| Low-confidence rows stored separately | {len(s['lowconf']):,} |",
         f"| Clean detections (nominal + high) | {len(s['clean']):,} |",
         f"| **Fire events** | **{n_ev:,}** |", "",
         f"Raw rows per fire event: {s['n_raw_rows'] / n_ev:.2f}; "
         f"clean detections per fire event: {len(s['clean']) / n_ev:.2f}.", "",
         "Reason codes (one row can carry several):", ""]
    L += [f"- `{k}`: {v:,}" for k, v in sorted(s["reason_counts"].items())]
    L += ["", "Quality filters that could not run on this data:", ""]
    L += [f"- {k}: {v}" for k, v in s["not_applied"].items()]

    L += ["", "Clean detections per UTC day (partial days are excluded from daily statistics):", "",
          "| UTC day | Clean detections | Partial |", "|---|---|---|"]
    full = []
    for d, n in sorted(s["day_counts_clean"].items()):
        part = d in s["partial_days"]
        full += [] if part else [n]
        L.append(f"| {d} | {n:,} | {'yes' if part else 'no'} |")
    if full:
        L += ["", f"Mean clean detections per full day: {sum(full) / len(full):,.0f} ({len(full)} full days)."]
    L += ["", "## 2. Sensor share of fire events", "", "| sensor_flag | Events |", "|---|---|"]
    L += [f"| {f} | {_pct(int(flags.get(f, 0)), n_ev)} |" for f in ("MODIS_only", "VIIRS_only", "both")]
    L += ["", "Events by platforms seen:", ""]
    L += [f"- {k}: {v:,}" for k, v in ev["platforms_seen"].value_counts().items()]
    if "MODIS" not in s["sensors_present"]:
        L += ["", "**No MODIS rows exist in the input**, so every event is VIIRS_only by construction. "
              "This is a data gap, not a finding about MODIS."]

    L += ["", "## 3. Footprint area ranges per sensor (Step 3 check)", "",
          "| Sensor | n | scan km | track km | area km² min | median | max | expected | outside |",
          "|---|---|---|---|---|---|---|---|---|"]
    for sensor in ("MODIS", "VIIRS"):
        r = s["area_ranges"].get(sensor)
        if r is None:
            L.append(f"| {sensor} | 0 | – | – | – | – | – | "
                     f"{cfg['footprints']['area_range_km2'][sensor]} | no data |")
            continue
        L.append(f"| {sensor} | {r['n']:,} | {r['scan_min']:.2f}–{r['scan_max']:.2f} | "
                 f"{r['track_min']:.2f}–{r['track_max']:.2f} | {r['min_km2']:.4f} | {r['median_km2']:.4f} | "
                 f"{r['max_km2']:.4f} | {r['expected'][0]}–{r['expected'][1]} | {r['n_outside']} |")
    L += ["", f"Largest difference between the EPSG:6933 footprint area and scan × track: "
          f"{s['area_rel_dev'] * 100:.3f}%."]

    L += ["", "## 4. Energy conservation (Step 5)", "",
          f"- Total FRP of clean detections before gridding: **{en['frp_before_mw']:,.6f} MW**",
          f"- Total FRP over all cell-overpass rows after gridding: **{en['frp_after_mw']:,.6f} MW**",
          f"- Relative difference: {en['rel_diff']:.2e} (tolerance {cfg['grid']['energy_rel_tol']:.0e}) "
          f"-> **{'PASS' if en['pass'] else 'FAIL'}**",
          f"- Largest raw deviation of Σ_c w_ic from 1 before normalisation: "
          f"{en['max_weight_sum_deviation']:.2e}",
          f"- Grid: {cfg['grid']['cell_deg']}° cells with true area stored; "
          f"{len(s['grid_daily']):,} cell-days, {len(s['grid_overpass']):,} cell-overpass rows.",
          "- These totals are a bookkeeping check. grid_daily.csv never adds FRP across overpasses; "
          "it reports the maximum and mean per overpass."]

    L += ["", "## 5. Anti-chaining caps (Step 4C)", "",
          f"- Caps: {cfg['events']['cap_extent_km']} km extent, {cfg['events']['cap_duration_days']} days",
          f"- Connected components before caps: {st['n_raw_components']:,}",
          f"- Components split: **{st['n_events_split']}** "
          f"(by extent: {st['n_split_by_extent']}, by duration: {st['n_split_by_duration']}), "
          f"giving {st['n_pieces_from_splits']} events",
          f"- Largest event extent after splitting: {ev['extent_km'].max():.2f} km; "
          f"longest event: {int(ev['n_days'].max())} day(s)",
          f"- Daily links: {st['n_daily_links']:,} ({st['n_links_overlap']:,} footprint overlaps, "
          f"{st['n_links_halfdiag_only']:,} by half-diagonal distance only); "
          f"multi-day links: {st['n_multiday_links']:,}",
          f"- Day used for clustering: `{st['day_basis']}`"]

    from pipeline.events import window_by_platform
    L += ["", "## 6. Near-simultaneous Aqua–VIIRS pairs (input to Step 6)", "",
          f"- Window per VIIRS platform (min): {window_by_platform(cfg)}; Aqua with "
          f"{' or '.join(cfg['events']['matched_pair_viirs'])}; Terra never paired.",
          f"- Pairs found: **{st['n_matched_pairs']}** in {st['n_events_with_matched_pair']} events."]
    if st["n_matched_pairs"] == 0 and "MODIS" not in s["sensors_present"]:
        L.append("- Zero because there is no Aqua (MODIS) data in the input. The detection-curve "
                 "test therefore stays **pending**.")

    L += ["", "## 7. Data problems", ""]
    L += [f"- {p}" for p in s["problems"]]

    L += ["", "## 8. Validation tests (procedure table)", "", "| Test | Status |", "|---|---|",
          f"| Energy conservation | {'pass' if en['pass'] else 'FAIL'} (see section 4; also `pytest`) |",
          f"| Footprint ranges | {'pass' if all(r['n_outside'] == 0 for r in s['area_ranges'].values()) else 'FAIL'}"
          f" for sensors present; MODIS pending (no data) |",
          "| Detection curve fit | pending: needs matched Aqua–VIIRS pairs |",
          "| Distribution fit | pending: Step 6 not in this phase |",
          "| Calibration hold-out, synthetic degradation, changepoint | pending: needs multi-year data |",
          "| Burned-area check | pending: needs MCD64A1 |",
          "| Himawari agreement | pending: no Himawari data |"]

    L += ["", "## 9. Parameters used", "", "| Parameter | Value |", "|---|---|",
          f"| Confidence kept | p_conf {cfg['quality']['keep_p_conf']} |",
          f"| Study bbox [lon_min, lat_min, lon_max, lat_max] | {s['bbox']} |",
          f"| Event caps | {cfg['events']['cap_extent_km']} km, {cfg['events']['cap_duration_days']} days |",
          f"| Matched-pair window | {cfg['events']['matched_pair_window_min']} min |",
          f"| Grid | {cfg['grid']['cell_deg']}°, true cell area stored |",
          f"| Footprint orientation | {cfg['footprints']['orientation']} |",
          f"| Distance / area CRS | UTM auto zone / {cfg['events']['area_crs']} |",
          f"| Persistent hotspot threshold | {cfg['quality']['persistent_hotspot_year_share']:.0%} of years (not applied) |",
          f"| Transient filter window | ±{cfg['quality']['transient_window_min']} min (not applied) |",
          "", "## 10. Not produced in this phase", "",
          "- fire_events: `FRE_estimate` (Step 7) and `cause_label` are not computed; "
          "`biome` is empty because MCD12Q1 is not available.",
          "- grid_daily: `lambda_hat`, `lambda_lo90/hi90`, `fre_harm`, `n_obs_opportunities`, "
          "`reference_sensor`, `era`, `diurnal_source` belong to Steps 6-8.",
          "", "## Outputs", ""]
    L += [f"- `{p}`" for p in s["written"]]
    text = "\n".join(L) + "\n"
    cfg["paths"]["report"].write_text(text, encoding="utf-8")
    return text
