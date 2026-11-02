# Phase 1 report: harmonization Steps 1-5

- Data version: `firms_nrt_2026-10-29_to_11-02_v2`; processing date: 2026-11-02 (UTC)
- Procedure: `docs/harmonization_procedure.md`; deviations: `docs/decisions.md`
- Command: `python run_pipeline.py`

All numbers below were computed by this run; nothing is estimated or filled in by hand.

## 1. Detections and fire events

| Stage | Count |
|---|---|
| Raw rows read (all files in `data/raw/`) | 24,928 |
| Removed by sanity checks (incl. duplicates) | 56 |
| Low-confidence rows stored separately | 847 |
| Clean detections (nominal + high) | 24,025 |
| **Fire events** | **12,289** |

Raw rows per fire event: 2.03; clean detections per fire event: 1.96.

Reason codes (one row can carry several):

- `low_confidence`: 850
- `modis_type_2_static_land`: 56

Quality filters that could not run on this data:

- persistent_hotspot_mask: needs multi-year history (>30% of years rule)
- nightfire_flare_mask: disabled in config; no VIIRS Nightfire flare list available
- transient_filter: needs Himawari detections within +/-30 min; no Himawari data
- modis_type_filter: NRT files have no `type` column

Clean detections per UTC day (partial days are excluded from daily statistics):

| UTC day | Clean detections | Partial |
|---|---|---|
| 2016-10-29 | 3,139 | no |
| 2016-10-30 | 1,998 | no |
| 2016-10-31 | 7,394 | no |
| 2016-11-01 | 6,086 | no |
| 2016-11-02 | 5,408 | no |

Mean clean detections per full day: 4,805 (5 full days).

## 2. Sensor share of fire events

| sensor_flag | Events |
|---|---|
| MODIS_only | 690 (5.6%) |
| VIIRS_only | 9,989 (81.3%) |
| both | 1,610 (13.1%) |

Events by platforms seen:

- S-NPP: 9,989
- Aqua;S-NPP: 1,547
- Aqua: 625
- Terra: 60
- S-NPP;Terra: 32
- Aqua;S-NPP;Terra: 31
- Aqua;Terra: 5

## 3. Footprint area ranges per sensor (Step 3 check)

| Sensor | n | scan km | track km | area km² min | median | max | expected | outside |
|---|---|---|---|---|---|---|---|---|
| MODIS | 3,431 | 1.00–3.10 | 1.00–1.70 | 1.0000 | 1.4300 | 5.2700 | 0.9–10.6 | 0 |
| VIIRS | 20,594 | 0.32–0.79 | 0.36–0.78 | 0.1368 | 0.2024 | 0.6162 | 0.127–0.704 | 0 |

Largest difference between the EPSG:6933 footprint area and scan × track: 0.000%.

## 4. Energy conservation (Step 5)

- Total FRP of clean detections before gridding: **202,062.900000 MW**
- Total FRP over all cell-overpass rows after gridding: **202,062.900000 MW**
- Relative difference: 0.00e+00 (tolerance 1e-09) -> **PASS**
- Largest raw deviation of Σ_c w_ic from 1 before normalisation: nan
- Grid: 0.1° cells with true area stored; 3,878 cell-days, 5,443 cell-overpass rows.
- These totals are a bookkeeping check. grid_daily.csv never adds FRP across overpasses; it reports the maximum and mean per overpass.

## 5. Anti-chaining caps (Step 4C)

- Caps: 25 km extent, 14 days
- Connected components before caps: 12,289
- Components split: **0** (by extent: 0, by duration: 0), giving 0 events
- Largest event extent after splitting: 9.33 km; longest event: 6 day(s)
- Daily links: 13,428 (7,300 footprint overlaps, 6,128 by half-diagonal distance only); multi-day links: 5,354
- Day used for clustering: `local_solar_date`

## 6. Near-simultaneous Aqua–VIIRS pairs (input to Step 6)

- Window per VIIRS platform (min): {'S-NPP': 60, 'NOAA-20': 60, 'NOAA-21': 60}; Aqua with S-NPP or NOAA-20; Terra never paired.
- Pairs found: **1368** in 1291 events.

## 7. Data problems

- URT near-duplicates of NRT rows dropped (NRT kept): 0.
- Study bbox detected from the data: [72.9, 20.4, 92.7, 32.6].
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
| Study bbox [lon_min, lat_min, lon_max, lat_max] | [72.9, 20.4, 92.7, 32.6] |
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

- `data/interim/windows/sync_2016/detections_lowconf.parquet`
- `data/interim/windows/sync_2016/detections_removed.parquet`
- `data/interim/windows/sync_2016/eras.csv`
- `data/interim/windows/sync_2016/event_overpasses.csv`
- `data/interim/windows/sync_2016/footprints.geoparquet`
- `data/interim/windows/sync_2016/grid_overpass.csv`
- `data/interim/windows/sync_2016/manifest.json`
- `data/interim/windows/sync_2016/matched_pairs_aqua_viirs.csv`
- `data/processed/windows/sync_2016/detections_clean.parquet`
- `data/processed/windows/sync_2016/eras.csv`
- `data/processed/windows/sync_2016/fire_events.csv`
- `data/processed/windows/sync_2016/grid_daily.csv`
- `data/processed/windows/sync_2016/partitions`
- `outputs/windows/sync_2016/figures/detections_per_platform_day.png`
- `outputs/windows/sync_2016/figures/map_raw_vs_events.png`
