# Phase 3 — Himawari current_2026

Window: 29 October–2 November 2026 UTC. November 2 is partial. Results use only local files; no missing scans are imputed.
Prepared hourly scans: 107; missing: 13; errors: 0.

## Geometry and diurnal fits

| Region | Valid area | Tier | Full days | Fit / peak hour |
|---|---:|---|---:|---|
| Bangladesh | 99.84% | A | 4 | Insufficient clear full-day observations with positive daily FRP maxima |
| Punjab_Haryana | 0.00% | B | 4 | Regional valid-view fraction below Tier A; no validated donor shape |
| eastern_IGP | 21.34% | B | 4 | Regional valid-view fraction below Tier A; no validated donor shape |
| full_IGP | 3.28% | B | 4 | Regional valid-view fraction below Tier A; no validated donor shape |

Tier describes geometry eligibility. No borrowed curve is assigned without an available, scientifically defensible donor. Eastern IGP has too little valid area to supply Punjab–Haryana. Zero daily maxima cannot be normalized.

## Detection and validation

AHI fire pixels across time steps: 0; transient suspects: 0.

| Region | VIIRS event-overpasses | Clear observed | Detected / observed | Unknown (cloud/view/water/missing) |
|---|---:|---:|---|---:|
| Bangladesh | 37 | 30 | 0/30 (0.0%) | 7 |
| Punjab_Haryana | 2223 | 0 | not estimable | 2223 |
| eastern_IGP | 12 | 2 | 0/2 (0.0%) | 10 |
| full_IGP | 4551 | 2 | 0/2 (0.0%) | 4549 |

Cloud, water, missing imagery, invalid view and insufficient background are excluded from detection-rate denominators. A cloudy VIIRS fire is not an AHI miss.

| Day/night | AHI fires | Unmatched commission |
|---|---:|---|
| D | 0 | not estimable (zero denominator) |
| N | 0 | not estimable (zero denominator) |

Training: 2 clear observed event-overpasses; detected 0; logistic fit: {'fitted': False, 'n': 2, 'reason': 'No observed events or only one detection outcome'}.

Held-out: 27 clear observed event-overpasses; detected 0; logistic fit: {'fitted': False, 'n': 27, 'reason': 'No observed events or only one detection outcome'}.

Chosen thresholds: `{"candidate_day_k": 310, "candidate_night_k": 300, "candidate_delta_k": 10, "background_windows": [11, 21, 31], "background_min_pixels": 20, "background_min_fraction": 0.2, "sigma_multiplier": 3, "anomaly_floor_k": 6}`.
Cloud thresholds: `{"cold_b14_k": 265, "split_window_min_k": -1.0, "split_window_max_k": 5.0}`.
Tuning: No large observed training events, or baseline meets trigger; thresholds retained; large observed training events: 0.
Full tuning audit: `himawari/threshold_selection.json`. No test-day data were used to select thresholds.

## Transfer calibration and energy

Aqua+VIIRS events in event table: 7374. Candidate event-overpass pairs: 6568. Pairs with a supported shape: 0.

| Version | Status | Fit |
|---|---|---|
| v1 | drift-affected source window (original file retained) | `{"a": -0.8239771284434613, "b": 1.3196439470461132, "by_daynight": {"day": {"n": 357, "a": -0.7297585160117105, "b": 1.2726277286278793}, "night": {"n": 39, "a": -1.9927899854071245, "b": 1.9394699532959596}}}` |
| v3 transfer | provisional – transfer standard | `{"fitted": false, "n": 0, "reason": "No supported regional diurnal shape or too few adjusted day pairs"}` |

Transfer detection curve: `{"fitted": false, "n": 0, "reason": "No supported time-adjusted detection sample"}`.
Events with FRE_estimate: 0/138576. Unavailable estimates remain null. Units: MJ; integration in hours is multiplied by 3600. Overpasses combine within local solar day by inverse variance, then daily energy sums over the event.

## MIR radiance constant

a = 3.1968263738110607e-9 W m-2 sr-1 um-1 K-4; sigma/a = 17.73751138202904. Fit range 650?1300 K; relative RMS error 7.861%, maximum 27.484%.

See `docs/decisions.md` and `himawari/mir_constant.json` for the response-weighted Planck fit, units, SRF checksum and approximation error.

## Limitations

Only four full UTC days, hourly sampling and one partial day are available. Bootstrap units are days, not pixels. Full UTC days are used consistently for normalization; local-solar-day boundary coverage is not complete at both window edges. AHI MIR radiance is not corrected for atmospheric transmission or reflected sunlight. The cloud mask is a simple threshold screen; global_land_mask is static. Persistence at a window edge lacks one neighbor. Small polar fires can fall below the coarse AHI pixel sensitivity. Reference matches use 2 km, which is smaller than some off-nadir pixel footprints. Zero fire samples cannot identify a logistic curve or a diurnal shape.

The request cited 5,779 shared Aqua+VIIRS events; the current finalized window table contains 7,374. Counts above use the current table, with no forced subsampling to the earlier count.
Transfer is limited to supported regional shapes: the global set of shared Aqua+VIIRS events cannot be assigned a Bangladesh shape without evidence. Missing transfer fits and FRE are scientific data limitations, not zero estimates. Event-specific AHI ratios require a detectable event at both times; no ratio is substituted when either observation is absent.

## Verification

Harmonization: 47 tests passed (including the six new Phase 3 tests). Backend: 61 tests passed using the backend Python environment and working directory. The initial combined-root collection could not resolve the backend import layout; separate suite runs succeeded.

Reproduce: `python -m pipeline.himawari --window current_2026`, then `python run_phase3.py --window current_2026`. Raw data are never modified. Observation status grids are under `data/interim/windows/current_2026/himawari/masks/`; detections are day-partitioned under `data/processed/himawari_fires/`.
