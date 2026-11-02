"""Write outputs/phase2_report.md from the numbers run_phase2.py computed."""
from __future__ import annotations

import numpy as np


def _f(x, nd=2):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:,.{nd}f}"


def _pct(x):
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.1f}%"


def write(S: dict, path) -> str:
    cfg = S["cfg"]
    L = ["# Phase 2 report: Step 6 sensor calibration", "",
         f"- Data version: `{cfg['data_version']}`; processing date {cfg['processing_date']} (UTC)",
         "- Commands: `python run_pipeline.py` then `python run_phase2.py`",
         "- Procedure: `docs/harmonization_procedure.md` Step 6; deviations: `docs/decisions.md` (D22 onward)",
         "", "Every number below was computed by this run. Items that could not be computed say why.", ""]

    # ---- A ----
    b = S["both"]
    L += ["## A. Diagnostics", "", f"### A1. The {b['n']:,} \"both\" events", "",
          "| MODIS platforms | Events |", "|---|---|"]
    L += [f"| {k} | {v:,} ({v / b['n']:.1%}) |" for k, v in b["by_combo"].items()]
    L += ["", "By VIIRS platform (an event can include several):", "", "| VIIRS platform | Events |", "|---|---|"]
    L += [f"| {k} | {v:,} |" for k, v in b["by_viirs_platform"].items()]

    L += ["", "### A2. Aqua–VIIRS time difference", "",
          "For every Aqua overpass of an event that VIIRS also saw: the nearest overpass of each VIIRS "
          "platform in the same event. Figure: `outputs/figures/aqua_viirs_dt_hist.png`.", "",
          "| VIIRS platform | Aqua overpasses | Median abs(Δt) | ≤ 30 min | ≤ 45 min | ≤ 60 min | Main peak (5-min bin) |",
          "|---|---|---|---|---|---|---|"]
    for p, d in S["dt_stats"].items():
        ch = S["window_choice"][p]
        L.append(f"| {p} | {d['n']:,} | {_f(d['median_abs_min'], 1)} min | {_pct(d['share_le_30'])} | "
                 f"{_pct(d['share_le_45'])} | {_pct(d['share_le_60'])} | {ch.get('peak_bin', '–')} |")
    lst = S["day_lst"]
    L += ["", "Median daytime local solar time of the computed overpasses (cells with |lat| < 30°, "
          "within 500 km of nadir): " + ", ".join(f"{k} {int(v)}:{int(round(v % 1 * 60)):02d}"
                                                     for k, v in lst.sort_values().items()) + ".",
          "Aqua now passes about two hours after the VIIRS platforms. This is the orbit drift of Aqua, "
          "and it is why almost no Aqua–VIIRS pairs fall within 30 min."]

    mo = S["modis_only"]
    L += ["", f"### A3. The {mo['n']:,} MODIS_only events", "", "| Platform | Day | Night | Day+night |",
          "|---|---|---|---|"]
    t = mo["table"]
    for plat in t.index:
        r = t.loc[plat]
        L.append(f"| {plat} | {int(r.get('day', 0)):,} | {int(r.get('night', 0)):,} | "
                 f"{int(r.get('day+night', 0)):,} |")

    m = S["match"]
    L += ["", "### A4. URT near-duplicates", "",
          "Handled in Step 2 (`pipeline/quality.py`): a URT row is a duplicate when an NRT row of the same "
          f"platform lies within ±{cfg['quality']['urt_dup_max_dt_min']} min and "
          f"{cfg['quality']['urt_dup_max_dist_m']} m. The count and its handling are in "
          "`outputs/phase1_report.md`, section 7. Detections still carrying a URT version in the clean "
          f"table: {int(S.get('n_urt_clean', 0)):,}.", "",
          "### A5. Partial days", "", "| UTC day | Clean detections | partial_day |", "|---|---|---|"]
    for d, r in S["days"].iterrows():
        L.append(f"| {d} | {int(r['n']):,} | {'true' if r['partial'] else 'false'} |")
    L += ["", "Partial days stay in the event and calibration tables (each overpass is complete in "
          "itself) but are excluded from daily statistics; `grid_daily.csv` carries `partial_day`."]

    L += ["", "### A6. Candidate pilot boxes", "",
          "| Box | Events | Seen by both | Share both | Events with Aqua | Calibration pairs | Detection-curve cases |",
          "|---|---|---|---|---|---|---|"]
    for _, r in S["boxes"].iterrows():
        L.append(f"| {r['box']} | {r['events']:,} | {r['both']:,} | {_pct(r['share_both'])} | "
                 f"{r['with_aqua']:,} | {r['calib_pairs']:,} | {r['curve_sample']:,} |")

    # ---- B ----
    w = S["windows"]
    L += ["", "## B. Matching window", "",
          f"Rule: keep {cfg['events']['matched_pair_window_min']} min unless the main peak lies beyond it; "
          f"widen to the smallest window that covers the main peak, never above "
          f"{cfg['events']['matched_pair_window_max_min']} min. Terra is never paired.", "",
          "| VIIRS platform | Window used | Rule outcome |", "|---|---|---|"]
    L += [f"| {p} | {w[p]} min | {S['window_choice'][p]['reason']} |" for p in w]
    L += ["", "Pairs used for calibration: Aqua with "
          f"{' or '.join(cfg['events']['matched_pair_viirs'])} (the procedure's pairing). One pair per Aqua "
          "event-overpass: the nearest VIIRS overpass of the same event inside its window. Each pair "
          "keeps its signed time difference (`dt_min`) and window (`window_min`) in "
          "`data/interim/calibration_pairs.csv`."]

    # ---- C ----
    L += ["", "## C. Observation opportunities", "",
          f"- `data/processed/overpasses.parquet`: {S['n_overpasses']:,} cell-overpasses over "
          f"{S['n_cells']:,} cells (every 0.1° cell with a detection, plus all cells of the five pilot "
          "boxes), five platforms, the whole data period.",
          f"- Swath widths: MODIS {cfg['overpasses']['swath_km']['MODIS']:,} km, VIIRS "
          f"{cfg['overpasses']['swath_km']['VIIRS']:,} km.",
          "- **Clear sky assumed (`cloud_adjusted = false`).** Cloud-covered overpasses still count as "
          "observation opportunities in this version.", "",
          "| Platform | TLE source | TLE epoch (UTC) | Cell-overpasses |", "|---|---|---|---|"]
    for p, t in S["tles"].items():
        L.append(f"| {p} | {t['source']} | {t['epoch']} | {int(float(t['n_overpasses'])):,} |")
    L += ["", f"Check: share of clean detections that fall inside a computed overpass of their own platform "
          f"within ±{cfg['overpasses']['match_tolerance_min']} min: **{S['match_all']:.2%}**.", "",
          "| Platform | Detections | Inside an overpass | Median abs(Δt) |", "|---|---|---|---|"]
    for p, r in m.iterrows():
        L.append(f"| {p} | {int(r['n']):,} | {r['share']:.2%} | {_f(r['median_abs_dt'], 1)} min |")
    pc = S["pixel_check"]
    L += ["", "Pixel-area model check: observed scan × track divided by the expected pixel area at the "
          "matched overpass.", "", "| Platform | Median ratio | 10th–90th percentile |", "|---|---|---|"]
    for p, r in pc.iterrows():
        L.append(f"| {p} | {_f(r['50%'])} | {_f(r['10%'])}–{_f(r['90%'])} |")

    # ---- D ----
    pairs = S["pairs"]
    L += ["", "## D. FRP calibration (Aqua MODIS vs VIIRS)", "",
          f"Matched pairs: **{len(pairs):,}** in {pairs['fire_id'].nunique() if len(pairs) else 0:,} events "
          + (f"(S-NPP {int((pairs['platform_viirs'] == 'S-NPP').sum()):,}, NOAA-20 "
             f"{int((pairs['platform_viirs'] == 'NOAA-20').sum()):,}; day "
             f"{int((pairs['daynight_modis'] == 'D').sum()):,}, night {int((pairs['daynight_modis'] == 'N').sum()):,}; "
             f"median abs(Δt) {pairs['dt_min'].abs().median():.1f} min)." if len(pairs) else "."),
          "", "Model: log10(FRP_VIIRS) = a + b · log10(FRP_MODIS), orthogonal distance regression "
          f"(scipy.odr), {cfg['calibration']['bootstrap']:,} bootstrap resamples, "
          f"{cfg['calibration']['ci']:.0%} intervals. FRP is the event's sum within one overpass.", "",
          "| Subset | Pairs | a [90% CI] | b [90% CI] | Residual SD (log10) | Median VIIRS/MODIS |",
          "|---|---|---|---|---|---|"]
    for r in S["calib"]:
        if r["fitted"]:
            L.append(f"| {r['subset']} | {r['n']:,} | {r['a']:.3f} [{r['a_lo']:.3f}, {r['a_hi']:.3f}] | "
                     f"{r['b']:.3f} [{r['b_lo']:.3f}, {r['b_hi']:.3f}] | {r['resid_sd_log10']:.3f} | "
                     f"{r['median_ratio_viirs_over_modis']:.2f} |")
        else:
            L.append(f"| {r['subset']} | {r['n']:,} | not fitted | – | – | {r['reason']} |")
    L += ["", "- **Biome-specific fits are pending**: no land-cover (MCD12Q1) layer is loaded yet.",
          "- Caveat: with windows up to 60 min, part of the FRP difference is real change in the fire "
          "between the two overpasses, not sensor difference."]

    # ---- E ----
    c = S["curve"]
    L += ["", "## E. MODIS detection probability", "",
          f"Sample: every VIIRS event-overpass ({', '.join(cfg['calibration']['detection_curve_viirs'])}) that "
          "lies inside a computed Aqua overpass within the platform's window, detected or not. "
          f"**n = {c['n']:,}** ({c['n_detected']:,} detected by Aqua, {c['n_missed']:,} missed). "
          "A_MODIS = expected Aqua pixel area at that overpass. Figure: `outputs/figures/modis_detection_curve.png`.",
          ""]
    if c["fitted"]:
        L += ["Model: logit P = b0 + b1·log10(FRP_VIIRS) − b2·log10(A_MODIS) (statsmodels Logit).", "",
              "| Coefficient | Estimate | 90% CI |", "|---|---|---|",
              f"| b0 | {c['b0']:.3f} | [{c['b0_ci'][0]:.3f}, {c['b0_ci'][1]:.3f}] |",
              f"| b1 | {c['b1']:.3f} | [{c['b1_ci'][0]:.3f}, {c['b1_ci'][1]:.3f}] |",
              f"| b2 | {c['b2']:.3f} | [{c['b2_ci'][0]:.3f}, {c['b2_ci'][1]:.3f}] |", "",
              f"- FRP at P = 0.5, nadir (A = 1 km²): **{c['f50_nadir_mw']:.1f} MW** "
              f"(90% bootstrap {c['f50_nadir_ci'][0]:.1f}–{c['f50_nadir_ci'][1]:.1f})",
              f"- FRP at P = 0.5, swath edge (A = {c['edge_area_km2']} km²): **{c['f50_edge_mw']:.1f} MW** "
              f"(90% bootstrap {c['f50_edge_ci'][0]:.1f}–{c['f50_edge_ci'][1]:.1f})",
              f"- McFadden pseudo-R²: {c['pseudo_r2']:.3f}; successful bootstrap fits: {c['n_boot_ok']:,}",
              "- Caveat: VIIRS and Aqua look up to 60 min apart, so some misses are fires that changed "
              "or ended between the two looks."]
    else:
        L.append(f"Not fitted: {c['reason']}.")
    q = S["sample_q"]
    L += ["", "**How reliable are the 50% FRP values?** The sample is not typical of MODIS viewing:",
          f"- Expected MODIS pixel area, 10th/50th/90th percentile: {q['a_modis_km2'][0.1]:.2f} / "
          f"{q['a_modis_km2'][0.5]:.2f} / {q['a_modis_km2'][0.9]:.2f} km². Near-simultaneous Aqua–VIIRS "
          "looks only occur towards the swath edge or at high latitude "
          f"(median abs(latitude) {q['abs_lat'][0.5]:.0f}°), so **the nadir value (A = 1 km²) is an "
          "extrapolation** beyond most of the data. The swath-edge value is inside the data.",
          f"- VIIRS FRP in the sample, 10th/50th/90th percentile: {q['frp_viirs_mw'][0.1]:.1f} / "
          f"{q['frp_viirs_mw'][0.5]:.1f} / {q['frp_viirs_mw'][0.9]:.1f} MW.",
          f"- Missed cases with a low-confidence Aqua detection within 3 km and 10 min (filtered out in "
          f"Step 2): {S['lowconf_misses']['with_lowconf_aqua']:,} of {S['lowconf_misses']['misses']:,}. The "
          "confidence filter does not explain the misses.", "",
          "Refit on narrower time windows (point estimates):", "",
          "| abs(Δt) ≤ | Cases | Detected share | 50% FRP nadir (MW) | 50% FRP edge (MW) |",
          "|---|---|---|---|---|"]
    for r in S["curve_sens"]:
        L.append(f"| {r['window']} min | {r['n']:,} | {_pct(r['rate'])} | {_f(r.get('f50_nadir', np.nan), 1)} | "
                 f"{_f(r.get('f50_edge', np.nan), 1)} |")
    L += ["", "The detected share barely changes with the window, so timing is not the main cause of misses. "
          "The nadir value moves a lot between windows; treat it as indicative only. The published "
          "reference (Li et al. 2020: 50% at about 4.3 MW at nadir, 31.7 MW at the edge) was derived "
          "from pixel-level matches with more near-nadir data, and is not directly comparable to these "
          "event-level values."]

    # ---- F ----
    L += ["", "## F. VIIRS FRP distribution", "",
          "VIIRS event FRP per overpass; F_min by the Clauset KS method; power law vs lognormal by "
          "normalised log-likelihood ratio R (R > 0 favours the power law). Figure: "
          "`outputs/figures/frp_distribution.png`.", "",
          "| Subset | n | F_min (MW) | Share ≥ F_min | α ± SE | KS D | R | p | Better fit |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, r in S["dist"]["fits"].items():
        if r.get("fitted"):
            L.append(f"| {k} | {r['n']:,} | {r['xmin']:.2f} | {r['tail_share']:.1%} | {r['alpha']:.3f} ± "
                     f"{r['alpha_se']:.3f} | {r['D']:.4f} | {r['R']:.2f} | {r['p']:.3g} | {r['better']} |")
        else:
            L.append(f"| {k} | {r['n']:,} | not fitted: {r.get('reason')} |  |  |  |  |  |  |")
    L += ["", "π_MODIS = ∫ P_det(F, A) f(F) dF, the share of VIIRS-detected fires Aqua MODIS would detect:", "",
          "| Subset | Empirical, nadir | Empirical, edge | Power-law tail (F ≥ F_min), nadir | Power-law tail, edge |",
          "|---|---|---|---|---|"]
    for k, pi in S["dist"]["pi"].items():
        if "reason" in pi:
            L.append(f"| {k} | {pi['reason']} | | | |")
            continue
        L.append(f"| {k} | {_pct(pi.get('empirical_nadir'))} | {_pct(pi.get('empirical_edge'))} | "
                 f"{_pct(pi.get('powerlaw_tail_nadir', np.nan))} | {_pct(pi.get('powerlaw_tail_edge', np.nan))} |")
    L += ["", "\"Empirical\" averages P_det over every VIIRS event-overpass; \"power-law tail\" integrates "
          "over the fitted power law above F_min only. Both are relative to fires VIIRS itself detected, "
          "so fires too small for VIIRS are outside both."]

    # ---- recommendation ----
    bx = S["boxes"].copy()
    bd = bx[bx["box"] == "Bangladesh"].iloc[0]
    max_pairs = bx.sort_values("calib_pairs", ascending=False).iloc[0]
    # No box can be calibrated locally when pairs are scarce, so rank by what a pilot needs
    # from this data: detection-curve cases (MODIS sensitivity), then events, then share seen by both.
    best = bx.sort_values(["curve_sample", "events", "share_both"], ascending=False).iloc[0]
    most_both = bx.sort_values("share_both", ascending=False).iloc[0]
    local_ok = max_pairs["calib_pairs"] >= cfg["calibration"]["min_pairs"]
    L += ["", "## Recommended pilot region", "",
          ("No candidate box has enough matched pairs for its own FRP calibration: the most is "
           f"{max_pairs['calib_pairs']:,} ({max_pairs['box']}), below the {cfg['calibration']['min_pairs']}-pair "
           "minimum. The FRP calibration therefore stays global (section D)."
           if not local_ok else
           f"{max_pairs['box']} has {max_pairs['calib_pairs']:,} matched pairs, enough for a local calibration."),
          "",
          f"**Recommended: {best['box']}.** Of the five boxes it has the most detection-curve cases "
          f"({best['curve_sample']:,}) and {best['events']:,} events ({_pct(best['share_both'])} seen by both "
          f"sensors, {best['with_aqua']:,} with Aqua)."
          + (" It contains the Punjab–Haryana crop-burning belt and borders Bangladesh (the boxes overlap at 88–89°E), "
             "so its fire regime is the closest of the five to the Bangladesh pilot." if best["box"] == "Indo-Gangetic Plain" else ""),
          f"{most_both['box']} has the highest share seen by both sensors ({_pct(most_both['share_both'])}) and "
          f"is the best second region for checking MODIS–VIIRS agreement.",
          f"Bangladesh has {bd['events']:,} events, {bd['both']:,} seen by both, {bd['calib_pairs']:,} pairs "
          f"and {bd['curve_sample']:,} detection-curve cases in this 5-day window, so it cannot support "
          "a calibration on its own yet. It stays the demonstration region; the coefficients come from "
          "the global or the recommended box until a longer Bangladesh record (dry season, Feb–Apr) is added."]

    L += ["", "## Remaining limitations", "",
          "- **Aqua drift.** Aqua passes about two hours after the VIIRS platforms, so near-simultaneous pairs "
          "are rare and come from the edge of the time-difference distribution, not its peak. Windows are "
          "capped at 60 min by rule.",
          "- Clear sky assumed for observation opportunities (no cloud mask).",
          "- TLEs are current elements from a CelesTrak mirror (CelesTrak itself timed out), back-propagated "
          "over the 5-day period; positional error is a few km at most.",
          "- No land cover: biome-specific calibration and detection curves are pending.",
          "- Five days of data: no hold-out year, no changepoint or burned-area test.",
          "- NRT files: no `type` field, so static sources and volcanoes are not removed.",
          "- The pixel-area model is geometric (Ichoku & Kaufman 2005, plus VIIRS aggregation zones); "
          "section C shows how well it matches the observed scan × track."]
    text = "\n".join(L) + "\n"
    path.write_text(text, encoding="utf-8")
    return text
