# FlameSeek scalability report

Window used for measurements: `current_2026` (2026-10-29 – 2026-11-02). Every number below was measured in this project; projections are labelled as such.

## 1. Architecture

| Piece | What it does |
|---|---|
| Windows | `config/settings.yaml` → `windows:`. Every command takes `--window`. |
| Day partitions | `data/processed/<stage>/year=YYYY/month=MM/day=DD/part.parquet`; one partition per local solar day per stage, atomic writes. |
| raw_split | One pass over the raw CSVs: UTC-day parts, partial days, bbox, and per-month minute histograms of local solar time (for eras). |
| detect (parallel) | Per local day: ingest → region filter (bbox first) → quality → footprints → daily clustering, with the 25 km cap inside the day. |
| link (sequential) | Per day, reading only day D−1: footprint overlaps → fire ids; caps; `event_state` (hull, start day); `merges`. |
| grid (parallel) | Per day: area-weighted 0.1° grid, FRP per overpass, energy check. |
| finalize | DuckDB over the partitions; merges resolved (union-find); events built in month chunks (+14 days). |
| Incremental | Existing day partitions are skipped unless `--force`; reruns are identical (tested). |
| Parallel | `concurrent.futures.ProcessPoolExecutor`, `partitions.workers` in config or `--workers`. |
| Params | `params/<kind>_vN.json`; only `refit_params.py --window` writes them. |
| Eras | Measured per platform-month from the data (median daytime LST vs. the platform's own early-archive value). |
| Multi-year modules | `pipeline/calendar.py`, `pipeline/anomalies.py`, `forecast/`; return `insufficient_history` on short records. |

## 2. Same results as before the refactor

| Check | Batch (before) | Day-by-day (now) |
|---|---|---|
| Clean detections | 545,537 | 545,537 (same rows: True) |
| Total FRP (MW) | 5,259,083.28 | 5,259,083.28 |
| Fire events | 138,518 | 138,576 (+0.04%) |
| Identical event groupings | | 138,484 of 138,518 (99.98%) |
| Largest event extent | 24.87 km | 24.87 km |
| Aqua–VIIRS pairs (≤ 60 min) | 416 | 416 |

Differences come only from where the 25 km cap splits a multi-day component: batch split the whole component after the fact, day-by-day decides each day from the previous day (decisions D38).

## 3. Scaling benchmark

Benchmark not run yet (`python run_benchmark.py`).

## 4. Eras measured in this window

| Platform | Month | Daytime detections | Median LST | Reference | Deviation | Drifted | Era |
|---|---|---|---|---|---|---|---|
| Aqua | 2026-10 | 13,466 | 15:47 | 13:36 | +131 min | True | multi_sensor |
| Aqua | 2026-11 | 5,375 | 15:49 | 13:36 | +133 min | True | multi_sensor |
| NOAA-20 | 2026-10 | 92,769 | 13:34 | 13:32 | +2 min | False | multi_sensor |
| NOAA-20 | 2026-11 | 33,325 | 13:37 | 13:32 | +5 min | False | multi_sensor |
| NOAA-21 | 2026-10 | 84,529 | 13:28 | 13:29 | -1 min | False | multi_sensor |
| NOAA-21 | 2026-11 | 34,404 | 13:28 | 13:29 | -1 min | False | multi_sensor |
| S-NPP | 2026-10 | 87,225 | 13:40 | 13:34 | +6 min | False | multi_sensor |
| S-NPP | 2026-11 | 34,618 | 13:45 | 13:34 | +11 min | False | multi_sensor |
| Terra | 2026-10 | 2,836 | 08:34 | 10:25 | -111 min | True | multi_sensor |
| Terra | 2026-11 | 1,402 | 08:35 | 10:25 | -110 min | True | multi_sensor |

## 5. Parameters: provisional vs validated

| File | Status | Source window | Sample size | Fit method |
|---|---|---|---|---|
| `calibration_v1.json` | **provisional** | current_2026 (2026-10-29–2026-11-02) | 396 | ODR (scipy.odr) on log10 FRP, one pair per Aqua overpass, windows {'S-NPP': 60, 'NOAA-20': 60, 'NOAA-21': 60} min; 1000 bootstrap resamples |
| `detection_curve_v1.json` | **provisional** | current_2026 (2026-10-29–2026-11-02) | 7787 | statsmodels Logit: logit P = b0 + b1 log10 F_VIIRS - b2 log10 A_MODIS |
| `pi_modis_v1.json` | **provisional** | current_2026 (2026-10-29–2026-11-02) | {'day': 175452, 'night': 63517} | pi = ∫ P_det(F,A) f(F) dF; empirical (mean over VIIRS event-overpasses) and power-law tail |
| `diurnal_v1.json` | **not_available** | current_2026 (2026-10-29–2026-11-02) | 0 | Gaussian diurnal shape from Himawari (Step 7) |

- **No parameter is validated yet.** The sync window `sync_2016` was not run: `data/raw/archive/2016/` does not exist. The v1 files stay provisional (Part 2.4).
- The 2-day archive sample (Phase 2b) gives 29–30 Oct 2016 an Aqua–S-NPP median abs(Δt) of 32 min, above the 20-min sync rule; 2015, 2018 and 2021 met it in that sample (decisions D37, D45).
- `diurnal_v1.json` is not_available: Step 7 needs Himawari data.

## 6. Multi-year components

### On simulated data

Synthetic data (`tests/simulated/generate.py`): 30 cells × 15 years × 52 weeks, a known seasonal peak per cell, negative-binomial noise, a step change ×1.6 from 2019, and 5 planted anomalies.

| Component | Test | Result |
|---|---|---|
| Calendar | seasonal peak week recovered | 13 cells exact, 16 within ±1 week, 1 off by more (of 30) |
| Anomalies (negative binomial) | planted anomalies found | 5 of 5 |
| Anomalies | false alarms | 260 of 23,400 cell-weeks (1.11%); 231 of them after the step change |
| Pettitt | step change located | first changed year 2019 (true 2019), p = 0.0107 (the floor for 15 years); no-step control p = 1.00 |
| Climatology forecast | skill on held-out years | Brier 0.174, BSS 0.286 vs. constant base rate 0.537 |
| Climatology forecast | reliability | max abs(observed − forecast) in bins with ≥ 200 cases: 0.130; figure `outputs/figures/reliability_simulated.png` |
| XGBoost | training | written; status "requires multi-year data" (xgboost is not installed in the env yet) |

The false alarms cluster after the step change: the baseline pools all other years, so a lasting increase reads as many moderate anomalies until a trend-aware baseline (Step 9 refinement) is used.

### On the real window (2026)

| Component | Status | Years available / required |
|---|---|---|
| calendar | insufficient_history | 1 / 3 |
| anomalies | insufficient_history | 1 / 5 |
| changepoint | insufficient_history | 1 / 8 |
| forecast_climatology | insufficient_history | 1 / 5 |
| forecast_xgboost | requires_multi_year_data | 1 / 5 |

## 7. What must be added to run 10–15 years

**Data**
- FIRMS standard-processing (SP) archive, global or per region, for every year: MODIS C6.1 (Terra, Aqua), VIIRS S-NPP, NOAA-20 (from 2018), NOAA-21 (from 2023). The FIRMS API used here serves at most a few days per request, so a full archive needs the FIRMS archive download (yearly files, requested with an Earthdata login) placed in `data/raw/archive/<year>/`, plus one window per year in the config.
- MCD12Q1 land cover (biome per cell per year) and MCD64A1 burned area (validation), from LAADS/LP DAAC.
- Himawari-8/9 AHI L1b bands B07 and B14 (NOAA open data on AWS, no account), for Step 7.
- Historical TLEs per date (Space-Track), so observation opportunities use the elements valid at the time instead of current elements back-propagated.
- A cloud mask (e.g. MODIS/VIIRS cloud products) to make observation opportunities cloud-adjusted.

**Accounts**
- NASA Earthdata login (FIRMS archive, LAADS, LP DAAC). The FIRMS MAP_KEY already in `backend/.env` covers API samples only.
- Space-Track.org account (historical TLEs).

**Compute and storage**: see the extrapolation table in section 3. All stages keep memory per day, so memory does not grow with the number of days; runtime and storage grow linearly. The largest single cost is `detect`, because each local day re-standardises three UTC days (D40).

**Code still to write**: Step 7 (Himawari diurnal), Step 8 (latent fire field and Monte Carlo), a trend-aware anomaly baseline, and the XGBoost forecast training run (`pip install xgboost`).
