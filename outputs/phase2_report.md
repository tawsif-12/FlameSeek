# Phase 2 report: Step 6 sensor calibration

- Data version: `firms_nrt_2026-10-29_to_11-02_v2`; processing date 2026-11-02 (UTC)
- Commands: `python run_pipeline.py` then `python run_phase2.py`
- Procedure: `docs/harmonization_procedure.md` Step 6; deviations: `docs/decisions.md` (D22 onward)

Every number below was computed by this run. Items that could not be computed say why.

## A. Diagnostics

### A1. The 9,340 "both" events

| MODIS platforms | Events |
|---|---|
| Terra+VIIRS | 1,966 (21.0%) |
| Aqua+VIIRS | 5,779 (61.9%) |
| Terra+Aqua+VIIRS | 1,595 (17.1%) |

By VIIRS platform (an event can include several):

| VIIRS platform | Events |
|---|---|
| S-NPP | 7,165 |
| NOAA-20 | 7,364 |
| NOAA-21 | 7,104 |

### A2. Aqua–VIIRS time difference

For every Aqua overpass of an event that VIIRS also saw: the nearest overpass of each VIIRS platform in the same event. Figure: `outputs/figures/aqua_viirs_dt_hist.png`.

| VIIRS platform | Aqua overpasses | Median abs(Δt) | ≤ 30 min | ≤ 45 min | ≤ 60 min | Main peak (5-min bin) |
|---|---|---|---|---|---|---|
| S-NPP | 6,755 | 136.0 min | 0.6% | 1.2% | 4.8% | 150-155 min |
| NOAA-20 | 6,898 | 130.0 min | 0.2% | 0.8% | 1.3% | 125-130 min |
| NOAA-21 | 6,611 | 156.0 min | 0.1% | 0.3% | 1.7% | 155-160 min |

Median daytime local solar time of the computed overpasses (cells with |lat| < 30°, within 500 km of nadir): Terra 8:35, NOAA-21 13:23, NOAA-20 13:30, S-NPP 13:37, Aqua 15:46.
Aqua now passes about two hours after the VIIRS platforms. This is the orbit drift of Aqua, and it is why almost no Aqua–VIIRS pairs fall within 30 min.

### A3. The 6,849 MODIS_only events

| Platform | Day | Night | Day+night |
|---|---|---|---|
| Aqua | 5,028 | 36 | 3 |
| Terra | 1,152 | 570 | 2 |
| Terra+Aqua | 17 | 0 | 41 |

### A4. URT near-duplicates

Handled in Step 2 (`pipeline/quality.py`): a URT row is a duplicate when an NRT row of the same platform lies within ±2 min and 375 m. The count and its handling are in `outputs/phase1_report.md`, section 7. Detections still carrying a URT version in the clean table: 1,449.

### A5. Partial days

| UTC day | Clean detections | partial_day |
|---|---|---|
| 2026-10-29 | 144,545 | false |
| 2026-10-30 | 122,193 | false |
| 2026-10-31 | 130,397 | false |
| 2026-11-01 | 122,299 | false |
| 2026-11-02 | 26,103 | true |

Partial days stay in the event and calibration tables (each overpass is complete in itself) but are excluded from daily statistics; `grid_daily.csv` carries `partial_day`.

### A6. Candidate pilot boxes

| Box | Events | Seen by both | Share both | Events with Aqua | Calibration pairs | Detection-curve cases |
|---|---|---|---|---|---|---|
| Bangladesh | 25 | 0 | 0.0% | 0 | 0 | 1 |
| Punjab-Haryana | 2,253 | 97 | 4.3% | 476 | 0 | 62 |
| Indo-Gangetic Plain | 4,144 | 164 | 4.0% | 611 | 0 | 145 |
| Mainland SE Asia | 985 | 10 | 1.0% | 43 | 0 | 5 |
| Northern Australia | 1,165 | 203 | 17.4% | 164 | 3 | 80 |

## B. Matching window

Rule: keep 30 min unless the main peak lies beyond it; widen to the smallest window that covers the main peak, never above 60 min. Terra is never paired.

| VIIRS platform | Window used | Rule outcome |
|---|---|---|
| S-NPP | 60 min | main peak extends to 155 min, beyond the 60 min maximum; capped at 60 (pairs are the peak's leading edge only) |
| NOAA-20 | 60 min | main peak extends to 130 min, beyond the 60 min maximum; capped at 60 (pairs are the peak's leading edge only) |
| NOAA-21 | 60 min | main peak extends to 160 min, beyond the 60 min maximum; capped at 60 (pairs are the peak's leading edge only) |

Pairs used for calibration: Aqua with S-NPP or NOAA-20 (the procedure's pairing). One pair per Aqua event-overpass: the nearest VIIRS overpass of the same event inside its window. Each pair keeps its signed time difference (`dt_min`) and window (`window_min`) in `data/interim/calibration_pairs.csv`.

## C. Observation opportunities

- `data/processed/overpasses.parquet`: 6,179,726 cell-overpasses over 109,054 cells (every 0.1° cell with a detection, plus all cells of the five pilot boxes), five platforms, the whole data period.
- Swath widths: MODIS 2,330 km, VIIRS 3,060 km.
- **Clear sky assumed (`cloud_adjusted = false`).** Cloud-covered overpasses still count as observation opportunities in this version.

| Platform | TLE source | TLE epoch (UTC) | Cell-overpasses |
|---|---|---|---|
| Aqua | https://tle.ivanstanojevic.me/api/tle/27424 | 2026-11-01 12:54:56.782074+00:00 | 1,049,637 |
| NOAA-20 | https://tle.ivanstanojevic.me/api/tle/43013 | 2026-11-01 10:46:07.211700+00:00 | 1,361,483 |
| NOAA-21 | https://tle.ivanstanojevic.me/api/tle/54234 | 2026-11-01 09:48:43.077881+00:00 | 1,357,826 |
| S-NPP | https://tle.ivanstanojevic.me/api/tle/37849 | 2026-11-01 12:07:33.491119+00:00 | 1,350,631 |
| Terra | https://tle.ivanstanojevic.me/api/tle/25994 | 2026-11-01 09:06:22.651764+00:00 | 1,060,149 |

Check: share of clean detections that fall inside a computed overpass of their own platform within ±10 min: **99.96%**.

| Platform | Detections | Inside an overpass | Median abs(Δt) |
|---|---|---|---|
| Aqua | 22,733 | 99.84% | 0.7 min |
| NOAA-20 | 175,603 | 100.00% | 0.7 min |
| NOAA-21 | 168,090 | 99.96% | 0.7 min |
| S-NPP | 167,712 | 99.92% | 0.8 min |
| Terra | 11,399 | 100.00% | 0.8 min |

Pixel-area model check: observed scan × track divided by the expected pixel area at the matched overpass.

| Platform | Median ratio | 10th–90th percentile |
|---|---|---|
| Aqua | 1.00 | 1.00–1.02 |
| NOAA-20 | 0.99 | 0.97–1.00 |
| NOAA-21 | 0.99 | 0.97–1.01 |
| S-NPP | 0.98 | 0.96–0.99 |
| Terra | 1.00 | 1.00–1.02 |

## D. FRP calibration (Aqua MODIS vs VIIRS)

Matched pairs: **396** in 392 events (S-NPP 309, NOAA-20 87; day 357, night 39; median abs(Δt) 50.5 min).

Model: log10(FRP_VIIRS) = a + b · log10(FRP_MODIS), orthogonal distance regression (scipy.odr), 1,000 bootstrap resamples, 90% intervals. FRP is the event's sum within one overpass.

| Subset | Pairs | a [90% CI] | b [90% CI] | Residual SD (log10) | Median VIIRS/MODIS |
|---|---|---|---|---|---|
| all | 396 | -0.824 [-1.143, -0.550] | 1.320 [1.162, 1.500] | 0.599 | 0.61 |
| day | 357 | -0.730 [-1.051, -0.464] | 1.273 [1.126, 1.458] | 0.578 | 0.61 |
| night | 39 | -1.993 [-11.155, -0.380] | 1.939 [1.034, 7.024] | 0.872 | 0.61 |

- **Biome-specific fits are pending**: no land-cover (MCD12Q1) layer is loaded yet.
- Caveat: with windows up to 60 min, part of the FRP difference is real change in the fire between the two overpasses, not sensor difference.

## E. MODIS detection probability

Sample: every VIIRS event-overpass (S-NPP, NOAA-20, NOAA-21) that lies inside a computed Aqua overpass within the platform's window, detected or not. **n = 7,787** (497 detected by Aqua, 7,290 missed). A_MODIS = expected Aqua pixel area at that overpass. Figure: `outputs/figures/modis_detection_curve.png`.

Model: logit P = b0 + b1·log10(FRP_VIIRS) − b2·log10(A_MODIS) (statsmodels Logit).

| Coefficient | Estimate | 90% CI |
|---|---|---|
| b0 | -3.789 | [-4.034, -3.543] |
| b1 | 2.397 | [2.239, 2.555] |
| b2 | 2.881 | [2.580, 3.182] |

- FRP at P = 0.5, nadir (A = 1 km²): **38.1 MW** (90% bootstrap 31.9–45.7)
- FRP at P = 0.5, swath edge (A = 9.6 km²): **577.4 MW** (90% bootstrap 463.7–730.2)
- McFadden pseudo-R²: 0.262; successful bootstrap fits: 1,000
- Caveat: VIIRS and Aqua look up to 60 min apart, so some misses are fires that changed or ended between the two looks.

**How reliable are the 50% FRP values?** The sample is not typical of MODIS viewing:
- Expected MODIS pixel area, 10th/50th/90th percentile: 1.87 / 5.63 / 9.29 km². Near-simultaneous Aqua–VIIRS looks only occur towards the swath edge or at high latitude (median abs(latitude) 41°), so **the nadir value (A = 1 km²) is an extrapolation** beyond most of the data. The swath-edge value is inside the data.
- VIIRS FRP in the sample, 10th/50th/90th percentile: 1.6 / 6.8 / 40.5 MW.
- Missed cases with a low-confidence Aqua detection within 3 km and 10 min (filtered out in Step 2): 0 of 7,290. The confidence filter does not explain the misses.

Refit on narrower time windows (point estimates):

| abs(Δt) ≤ | Cases | Detected share | 50% FRP nadir (MW) | 50% FRP edge (MW) |
|---|---|---|---|---|
| 15 min | 633 | 4.7% | 99.0 | 425.6 |
| 30 min | 1,315 | 3.5% | 178.1 | 401.2 |
| 45 min | 3,230 | 4.3% | 108.8 | 290.3 |
| 60 min | 7,787 | 6.4% | 38.1 | 577.4 |

The detected share barely changes with the window, so timing is not the main cause of misses. The nadir value moves a lot between windows; treat it as indicative only. The published reference (Li et al. 2020: 50% at about 4.3 MW at nadir, 31.7 MW at the edge) was derived from pixel-level matches with more near-nadir data, and is not directly comparable to these event-level values.

## F. VIIRS FRP distribution

VIIRS event FRP per overpass; F_min by the Clauset KS method; power law vs lognormal by normalised log-likelihood ratio R (R > 0 favours the power law). Figure: `outputs/figures/frp_distribution.png`.

| Subset | n | F_min (MW) | Share ≥ F_min | α ± SE | KS D | R | p | Better fit |
|---|---|---|---|---|---|---|---|---|
| day | 175,452 | 11.31 | 35.9% | 2.033 ± 0.004 | 0.0310 | -20.94 | 2.16e-97 | lognormal |
| night | 63,517 | 19.71 | 6.0% | 2.239 ± 0.020 | 0.0221 | -2.69 | 0.00709 | lognormal |

π_MODIS = ∫ P_det(F, A) f(F) dF, the share of VIIRS-detected fires Aqua MODIS would detect:

| Subset | Empirical, nadir | Empirical, edge | Power-law tail (F ≥ F_min), nadir | Power-law tail, edge |
|---|---|---|---|---|
| day | 22.9% | 2.8% | 42.9% | 6.9% |
| night | 9.3% | 0.9% | 52.3% | 8.6% |
| all | 19.3% | 2.3% | – | – |

"Empirical" averages P_det over every VIIRS event-overpass; "power-law tail" integrates over the fitted power law above F_min only. Both are relative to fires VIIRS itself detected, so fires too small for VIIRS are outside both.

## Recommended pilot region

No candidate box has enough matched pairs for its own FRP calibration: the most is 3 (Northern Australia), below the 15-pair minimum. The FRP calibration therefore stays global (section D).

**Recommended: Indo-Gangetic Plain.** Of the five boxes it has the most detection-curve cases (145) and 4,144 events (4.0% seen by both sensors, 611 with Aqua). It contains the Punjab–Haryana crop-burning belt and borders Bangladesh (the boxes overlap at 88–89°E), so its fire regime is the closest of the five to the Bangladesh pilot.
Northern Australia has the highest share seen by both sensors (17.4%) and is the best second region for checking MODIS–VIIRS agreement.
Bangladesh has 25 events, 0 seen by both, 0 pairs and 1 detection-curve cases in this 5-day window, so it cannot support a calibration on its own yet. It stays the demonstration region; the coefficients come from the global or the recommended box until a longer Bangladesh record (dry season, Feb–Apr) is added.

## Remaining limitations

- **Aqua drift.** Aqua passes about two hours after the VIIRS platforms, so near-simultaneous pairs are rare and come from the edge of the time-difference distribution, not its peak. Windows are capped at 60 min by rule.
- Clear sky assumed for observation opportunities (no cloud mask).
- TLEs are current elements from a CelesTrak mirror (CelesTrak itself timed out), back-propagated over the 5-day period; positional error is a few km at most.
- No land cover: biome-specific calibration and detection curves are pending.
- Five days of data: no hold-out year, no changepoint or burned-area test.
- NRT files: no `type` field, so static sources and volcanoes are not removed.
- The pixel-area model is geometric (Ichoku & Kaufman 2005, plus VIIRS aggregation zones); section C shows how well it matches the observed scan × track.
