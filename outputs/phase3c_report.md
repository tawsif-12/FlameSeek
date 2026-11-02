# Phase 3c — available-data science

> **Superseded in part (2026-11-02):** the synchronization verdict below used the old D61 rule. Under the D68 gate, sync_2016 passes and calibration v2 is fitted — see `docs/decisions.md` D68–D70 and `outputs/staged_continuation_report.md`.


Current window: 29 October–2 November 2026 UTC; final day partial. Synchronized comparison: 29 October–2 November 2016. Raw inputs are immutable.

## Synthetic detection limits

800 K MIR-only injections on independent copies of real native clear-land tiles. Bangladesh uses the six original Phase 3b sites; near-nadir uses the configured three scans where a suitable clear background exists. No thresholds were tuned.

| Region | Fraction | Detected / trials | Rate | Median added FRP MW | Added FRP range MW |
|---|---:|---:|---:|---:|---|
| Bangladesh | 0.005% | 0/6 | 0.0% | 11.36 | 11.06–12.13 |
| Bangladesh | 0.01% | 0/6 | 0.0% | 22.73 | 22.13–24.26 |
| Bangladesh | 0.02% | 0/6 | 0.0% | 45.46 | 44.25–48.52 |
| Bangladesh | 0.05% | 6/6 | 100.0% | 113.64 | 110.63–121.31 |
| Bangladesh | 0.1% | 6/6 | 100.0% | 227.28 | 221.27–242.61 |

**Bangladesh: completed; detection limit from synthetic injection:** F50 = 71.87218381730158 MW; tested transition bracket = [45.455959234056365, 113.63990318782726] MW.
| near_nadir | 0.005% | 0/3 | 0.0% | 4.73 | 4.73–4.73 |
| near_nadir | 0.01% | 0/3 | 0.0% | 9.47 | 9.46–9.47 |
| near_nadir | 0.02% | 3/3 | 100.0% | 18.94 | 18.92–18.94 |
| near_nadir | 0.05% | 3/3 | 100.0% | 47.34 | 47.30–47.35 |
| near_nadir | 0.1% | 3/3 | 100.0% | 94.68 | 94.61–94.70 |

**near_nadir: completed; detection limit from synthetic injection:** F50 = 13.38992181488362 MW; tested transition bracket = [9.468103454761179, 18.936211149925438] MW.

F50 is descriptive interpolation on log median added power, not a validated logistic sensitivity fit. Its bracket is tested-grid resolution, not a confidence interval. Only six Bangladesh and up to three near-nadir contexts are used. Atmosphere, reflection and instrument saturation are not modeled; longwave bands remain unchanged.

![Synthetic detection limits](figures/detection_limit_synthetic.png)

Full trials: `himawari/detection_limit_phase3c.json` and `.csv`.

## Northern Australia — method demonstration only

Status: **completed**. Box: 125–138°E, 11–20°S. No Australian shape is transferred to South Asia.

Scans: 108; fire pixels over time: 2195; detection rate vs clear-observed VIIRS events: 0.07965367965367966; commission within 2 km / 60 min: 0.26469248291571756 — **corrected to 0.786 (D72)**; the old value used a 1,000× too wide time tolerance.
Himawari logistic curve with VZA: `{"fitted": true, "n": 1155, "intercept": -4.875038314341668, "beta_log_frp": 1.1039129000839865, "beta_vza": -0.03654860191507508}`.
Tier A; diurnal fitted: True; full days: 4; fitting points: 64; status: provisional – 4 days.
Peak/width/base/peak parameters: `{'base': 0.17856275057604523, 'peak': 0.4994533293514552, 'h': 18.821000217160844, 'sigma': 2.68283732293802}`; day-bootstrap 90% intervals: `{'h': [16.67114329201512, 19.433630454612285], 'sigma': [2.4970171371293404, 5.368011477088301], 'base_over_peak': [0.19571858836742004, 0.5329244653958998]}`.
FRP transfer fit: `{"n_input": 136, "n": 136, "sync_max_dt_min": 360, "trunc_frp_mw": 0, "deming_delta": 1.0, "fitted": true, "a": -0.14565606643120632, "b": 1.1605870147568313, "a_ci": [-1.1383532208828042, 0.47941556932524587], "b_ci": [0.7984919766021573, 1.7169536845042546], "b_bounds_ols": [0.37265808392381383, 2.9823790255878655], "odr": {"a": -0.1453324916762909, "b": 1.1604043502475943}}`; events with FRE: 1165.
Files: `params/diurnal_v2.json`, `params/calibration_v3_transfer_naus.json`; event FRE in `phase3c_naus/fire_events_fre.csv`.

![Australian diurnal fit](figures/diurnal_curve_Northern_Australia.png)

![Australian transfer comparison](figures/calibration_v1_vs_v3_naus.png)

## Synchronized 2016 window

Status: **completed**.

Clean detections: 24025; measured Aqua–S-NPP timing: `{"n_pairs": 1698, "median_abs_dt_min": 21.0, "synchronized": false}`.
FRP fit (15-min pairs, truncation, Deming error ratio 1, OLS/ODR comparison, bootstrap): `{"fitted": false, "n": 0, "reason": "Window median absolute Aqua?S-NPP difference exceeds 20 minutes"}`.
MODIS detection curve / nadir F50 / area coverage: `{"fitted": false, "n": 0, "reason": "awaiting data: 2016 observation opportunities require historical orbital elements; only 2026 TLEs are cached"}`.
π_MODIS, empirical IGP/all: `awaiting data: 2016 observation opportunities require historical orbital elements; only 2026 TLEs are cached`.
Observation opportunities: awaiting data: 2016 observation opportunities require historical orbital elements; only 2026 TLEs are cached

| Year | Platform | Daytime observations | Median LST h |
|---|---|---:|---:|
| 2016 | Aqua | 718 | 13.455 |
| 2016 | S-NPP | 5113 | 13.300 |
| 2016 | Terra | 68 | 10.771 |
| 2026 | Aqua | 18153 | 15.800 |
| 2026 | NOAA-20 | 102409 | 13.598 |
| 2026 | NOAA-21 | 96022 | 13.513 |
| 2026 | S-NPP | 99857 | 13.712 |
| 2026 | Terra | 4062 | 8.569 |

![Measured 2016–2026 drift](figures/drift_2016_vs_2026.png)

Only valid historical orbital elements can support 2016 observation-opportunity and sensitivity estimates. A 2026 TLE propagated ten years backward is not used as validated 2016 coverage. Timing eligibility is median **absolute** event-overpass difference ≤20 min. The FRP calibration uses directly measured acquisition times and does not require orbit extrapolation.

## Meteosat South Asia

**awaiting data**; 0 files; 0 ingest errors. ListProduct and validated QualityProduct coverage are required. No account or login was used.

## Calibration versions and applicability

`log10 FRP_VIIRS = a + b log10 FRP_Aqua`; transfer versions use VIIRS FRP adjusted to Aqua time. Coefficient intervals are 90%.

| Version | n | a | b | a interval | b interval | Status | Region / era |
|---|---:|---:|---:|---|---|---|---|
| v1 | 396 | -0.8239771284434613 | 1.3196439470461132 | [-1.14289502918055, -0.5496525544318952] | [1.1622549357299004, 1.5000706877202734] | drift-affected source; provisional | 2026 drifted timing; original diagnostic benchmark |
| v2 sync 2016 | 0 | None | None | None | None | not_available | Synchronized window/era after timing and fit checks |
| v3 transfer N. Australia | 136 | -0.14565606643120632 | 1.1605870147568313 | [-1.1383532208828042, 0.47941556932524587] | [0.7984919766021573, 1.7169536845042546] | provisional – transfer standard | Northern Australia only; method demonstration region |
| v3 transfer South Asia | 0 | None | None | None | None | provisional – transfer standard | South Asia only after regional Meteosat validation |

Unavailable coefficients are not zeros. v1 is a drift-affected diagnostic benchmark. A synchronized fit applies only where its sample and validation support it; Australian transfer applies only to its demonstration region. South Asia requires its own supported Meteosat shape.

| Era / region | Preferred | Currently usable |
|---|---|---|
| synchronized / pre-drift / Regions represented and validated in sync_2016 | v2 sync 2016 | awaiting applicable fit |
| drifted 2026 / Northern Australia | v3 transfer N. Australia | v3 transfer N. Australia |
| drifted 2026 / South Asia | v3 transfer South Asia | awaiting applicable fit |

Active selection is recorded separately in config and `docs/decisions.md` after eligibility and fit checks. A fitted FRP regression does not itself validate a detection curve or observation opportunities.

## Reproduction

`python run_phase3c.py --window current_2026`. Detailed part states: `phase3c_status.json`. The Stage 1 download inventory documents added raw files. No existing raw file is changed.

Previously recorded regression checks: 67 pipeline; 61 backend. Current-stage checks are recorded in outputs/status_report.md.
