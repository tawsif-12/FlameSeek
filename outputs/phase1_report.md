# Phase 1 report: harmonization Steps 1-5

- Data version: `firms_nrt_2026-10-29_to_11-02_v2`; processing date: 2026-11-02 (UTC)
- Procedure: `docs/harmonization_procedure.md`; deviations: `docs/decisions.md`
- Command: `python run_pipeline.py`

All numbers below were computed by this run; nothing is estimated or filled in by hand.

## 1. Detections and fire events

| Stage | Count |
|---|---|
| Raw rows read (all files in `data/raw/`) | 618,185 |
| Removed by sanity checks (incl. duplicates) | 0 |
| Low-confidence rows stored separately | 72,648 |
| Clean detections (nominal + high) | 545,537 |
| **Fire events** | **138,576** |

Raw rows per fire event: 4.46; clean detections per fire event: 3.94.

Reason codes (one row can carry several):

- `low_confidence`: 72,648

Quality filters that could not run on this data:

- persistent_hotspot_mask: needs multi-year history (>30% of years rule)
- nightfire_flare_mask: disabled in config; no VIIRS Nightfire flare list available
- transient_filter: needs Himawari detections within +/-30 min; no Himawari data
- modis_type_filter: NRT files have no `type` column

Clean detections per UTC day (partial days are excluded from daily statistics):

| UTC day | Clean detections | Partial |
|---|---|---|
| 2026-10-29 | 144,545 | no |
| 2026-10-30 | 122,193 | no |
| 2026-10-31 | 130,397 | no |
| 2026-11-01 | 122,299 | no |
| 2026-11-02 | 26,103 | yes |

Mean clean detections per full day: 129,858 (4 full days).

## 2. Sensor share of fire events

| sensor_flag | Events |
|---|---|
| MODIS_only | 6,849 (4.9%) |
| VIIRS_only | 122,387 (88.3%) |
| both | 9,340 (6.7%) |

Events by platforms seen:

- NOAA-21: 31,411
- NOAA-20: 30,096
- S-NPP: 23,292
- NOAA-20;NOAA-21;S-NPP: 13,134
- NOAA-20;S-NPP: 10,192
- NOAA-21;S-NPP: 7,601
- NOAA-20;NOAA-21: 6,661
- Aqua: 5,067
- Aqua;NOAA-20;NOAA-21;S-NPP: 2,662
- Terra: 1,724
- Aqua;NOAA-20;NOAA-21;S-NPP;Terra: 1,389
- NOAA-20;NOAA-21;S-NPP;Terra: 1,031
- Aqua;NOAA-20;S-NPP: 656
- Aqua;NOAA-20: 595
- Aqua;NOAA-21: 554
- Aqua;S-NPP: 448
- Aqua;NOAA-21;S-NPP: 440
- Aqua;NOAA-20;NOAA-21: 424
- NOAA-21;Terra: 178
- NOAA-20;Terra: 175
- NOAA-21;S-NPP;Terra: 172
- NOAA-20;NOAA-21;Terra: 156
- NOAA-20;S-NPP;Terra: 144
- S-NPP;Terra: 110
- Aqua;NOAA-20;S-NPP;Terra: 62
- Aqua;Terra: 58
- Aqua;NOAA-20;NOAA-21;Terra: 41
- Aqua;NOAA-21;S-NPP;Terra: 34
- Aqua;NOAA-20;Terra: 29
- Aqua;NOAA-21;Terra: 23
- Aqua;S-NPP;Terra: 17

## 3. Footprint area ranges per sensor (Step 3 check)

| Sensor | n | scan km | track km | area km² min | median | max | expected | outside |
|---|---|---|---|---|---|---|---|---|
| MODIS | 34,132 | 1.00–4.82 | 1.00–2.00 | 1.0000 | 1.2744 | 9.6400 | 0.9–10.6 | 0 |
| VIIRS | 511,405 | 0.30–0.80 | 0.36–0.80 | 0.1368 | 0.1995 | 0.6400 | 0.127–0.704 | 0 |

Largest difference between the EPSG:6933 footprint area and scan × track: 0.000%.

## 4. Energy conservation (Step 5)

- Total FRP of clean detections before gridding: **5,259,083.280000 MW**
- Total FRP over all cell-overpass rows after gridding: **5,259,083.280000 MW**
- Relative difference: 1.77e-16 (tolerance 1e-09) -> **PASS**
- Largest raw deviation of Σ_c w_ic from 1 before normalisation: nan
- Grid: 0.1° cells with true area stored; 114,903 cell-days, 230,820 cell-overpass rows.
- These totals are a bookkeeping check. grid_daily.csv never adds FRP across overpasses; it reports the maximum and mean per overpass.

## 5. Anti-chaining caps (Step 4C)

- Caps: 25 km extent, 14 days
- Connected components before caps: 138,516
- Components split: **15** (by extent: 15, by duration: 0), giving 75 events
- Largest event extent after splitting: 24.87 km; longest event: 6 day(s)
- Daily links: 1,444,491 (957,470 footprint overlaps, 487,021 by half-diagonal distance only); multi-day links: 549,037
- Day used for clustering: `local_solar_date`

## 6. Near-simultaneous Aqua–VIIRS pairs (input to Step 6)

- Window per VIIRS platform (min): {'S-NPP': 60, 'NOAA-20': 60, 'NOAA-21': 60}; Aqua with S-NPP or NOAA-20; Terra never paired.
- Pairs found: **416** in 392 events.

## 7. Data problems

- UTC day 2026-11-02 has 27,487 raw rows, far below the other days: flagged partial_day=true and excluded from daily statistics (download cut-off).
- URT near-duplicates of NRT rows dropped (NRT kept): 0.
- Study bbox detected from the data: [-179.5, -73.5, 180.0, 71.6].
- Aqua 2026-10: median daytime LST 15.78 h is +131 min from its reference (measured early-archive median 2013-2015 (drift_by_year.csv)): drifted era.
- Aqua 2026-11: median daytime LST 15.82 h is +133 min from its reference (measured early-archive median 2013-2015 (drift_by_year.csv)): drifted era.
- Terra 2026-10: median daytime LST 8.57 h is -111 min from its reference (measured early-archive median 2013-2015 (drift_by_year.csv)): drifted era.
- Terra 2026-11: median daytime LST 8.58 h is -110 min from its reference (measured early-archive median 2013-2015 (drift_by_year.csv)): drifted era.
- NRT files have no `type` column, so volcano/static-source/offshore rows cannot be dropped.

## 8. Validation tests (procedure table)

| Test | Status |
|---|---|
| Energy conservation | pass (see section 4; also `pytest`) |
| Footprint ranges | pass for sensors present; MODIS pending (no data) |
| Detection curve fit | pending: needs matched Aqua–VIIRS pairs |
| Distribution fit | pending: Step 6 not in this phase |
| Calibration hold-out, synthetic degradation, changepoint | pending: needs multi-year data |
| Burned-area check | pending: needs MCD64A1 |
| Himawari agreement | pending: no Himawari data |

## 9. Parameters used

| Parameter | Value |
|---|---|
| Confidence kept | p_conf [0.6, 0.9] |
| Study bbox [lon_min, lat_min, lon_max, lat_max] | [-179.5, -73.5, 180.0, 71.6] |
| Event caps | 25 km, 14 days |
| Matched-pair window | 30 min |
| Grid | 0.1°, true cell area stored |
| Footprint orientation | ground_track |
| Distance / area CRS | UTM auto zone / EPSG:6933 |
| Persistent hotspot threshold | 30% of years (not applied) |
| Transient filter window | ±30 min (not applied) |

## 10. Not produced in this phase

- fire_events: `FRE_estimate` (Step 7) and `cause_label` are not computed; `biome` is empty because MCD12Q1 is not available.
- grid_daily: `lambda_hat`, `lambda_lo90/hi90`, `fre_harm`, `n_obs_opportunities`, `reference_sensor`, `era`, `diurnal_source` belong to Steps 6-8.

## Outputs

- `data/interim/windows/current_2026/calibration_pairs.csv`
- `data/interim/windows/current_2026/detection_curve_sample.csv`
- `data/interim/windows/current_2026/detections_lowconf.parquet`
- `data/interim/windows/current_2026/detections_removed.parquet`
- `data/interim/windows/current_2026/eras.csv`
- `data/interim/windows/current_2026/event_overpasses.csv`
- `data/interim/windows/current_2026/footprints.geoparquet`
- `data/interim/windows/current_2026/grid_overpass.csv`
- `data/interim/windows/current_2026/manifest.json`
- `data/interim/windows/current_2026/matched_pairs_aqua_viirs.csv`
- `data/processed/windows/current_2026/detections_clean.parquet`
- `data/processed/windows/current_2026/eras.csv`
- `data/processed/windows/current_2026/fire_events.csv`
- `data/processed/windows/current_2026/grid_daily.csv`
- `data/processed/windows/current_2026/overpasses.parquet`
- `outputs/figures/aqua_viirs_dt_hist.png`
- `outputs/figures/detections_per_platform_day.png`
- `outputs/figures/frp_distribution.png`
- `outputs/figures/map_raw_vs_events.png`
- `outputs/figures/modis_detection_curve.png`
- `outputs/figures/overpass_lst_by_year.png`
