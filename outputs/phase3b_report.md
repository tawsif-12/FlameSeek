# Phase 3b — detector controls and Indian Ocean source

Window: 29 October–2 November 2026 UTC; November 2 remains partial. Raw imagery is unchanged.

## Himawari verification (run before platform selection)

**Detector status: verified.**

Satpy metadata reports `brightness_temperature`, units `K`, for B07, B14 and B15 in all six scans. Independent HSD-coefficient inversion agrees with the cached B07 temperatures within 0.000061 K. The existing calibration setting is correct; no detector bug was found and Phase 3 was not re-run.

Statistics below use land pixels passing the existing cloud and valid-view screens; the screen may retain thin/residual cloud. Daytime B07 medians are about 297 K. Cold B14 values near the cloud cutoff indicate that this simple screen is not a validated clear-sky product.

| UTC scan | Day/night | Band | Pixels | Min K | P05 K | Median K | P95 K | Max K |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 2026-10-29 05:00:00+00:00 | D | B07 | 5114 | 279.24 | 286.81 | 297.09 | 303.52 | 307.15 |
| 2026-10-29 05:00:00+00:00 | D | B14 | 5114 | 265.03 | 265.32 | 269.22 | 279.53 | 290.61 |
| 2026-10-29 05:00:00+00:00 | D | B15 | 5114 | 260.19 | 263.16 | 266.52 | 274.99 | 285.69 |
| 2026-10-29 07:00:00+00:00 | D | B07 | 5103 | 277.64 | 288.24 | 297.05 | 304.11 | 308.49 |
| 2026-10-29 07:00:00+00:00 | D | B14 | 5103 | 265.03 | 265.64 | 269.22 | 286.86 | 289.89 |
| 2026-10-29 07:00:00+00:00 | D | B15 | 5103 | 260.11 | 262.98 | 267.15 | 282.32 | 285.11 |
| 2026-10-29 09:00:00+00:00 | D | B07 | 4775 | 269.21 | 286.09 | 296.90 | 304.14 | 308.19 |
| 2026-10-29 09:00:00+00:00 | D | B14 | 4775 | 265.03 | 265.53 | 272.10 | 288.90 | 290.53 |
| 2026-10-29 09:00:00+00:00 | D | B15 | 4775 | 260.34 | 263.27 | 269.01 | 284.17 | 285.69 |
| 2026-10-29 18:00:00+00:00 | N | B07 | 6066 | 264.02 | 266.83 | 283.56 | 293.05 | 297.31 |
| 2026-10-29 18:00:00+00:00 | N | B14 | 6066 | 265.03 | 265.74 | 275.07 | 288.96 | 290.86 |
| 2026-10-29 18:00:00+00:00 | N | B15 | 6066 | 260.26 | 262.98 | 271.60 | 284.81 | 286.44 |
| 2026-10-29 20:00:00+00:00 | N | B07 | 7048 | 263.29 | 268.09 | 282.74 | 293.13 | 296.79 |
| 2026-10-29 20:00:00+00:00 | N | B14 | 7048 | 265.03 | 265.56 | 275.16 | 289.58 | 291.41 |
| 2026-10-29 20:00:00+00:00 | N | B15 | 7048 | 260.30 | 263.13 | 271.92 | 285.54 | 286.95 |
| 2026-10-29 22:00:00+00:00 | N | B07 | 10570 | 263.14 | 267.57 | 282.87 | 293.05 | 297.05 |
| 2026-10-29 22:00:00+00:00 | N | B14 | 10570 | 265.03 | 265.74 | 275.16 | 289.33 | 291.69 |
| 2026-10-29 22:00:00+00:00 | N | B15 | 10570 | 260.38 | 263.97 | 271.99 | 285.38 | 287.33 |

### Synthetic injection

At each scan, one typical-temperature clear-land native pixel with at least 100 clear background pixels in its 11×11 neighborhood was selected. Each trial independently modifies a copy of a real 65×65 radiance tile: `L_mix = (1-f) L_background + f L(800 K)`. B07 brightness temperature is recomputed using the HSD Planck constants and band-specific quadratic correction. B14 and B15 remain unchanged as a controlled MIR-only test. No injected values are written into raw data, cached science scans or event tables.

Detected trials: 18/18. Smallest **tested** detected fire fraction: 0.1%. This is an upper bound on the minimum detectable fraction, not an estimated detection limit.

| UTC scan | Fraction | Injected B07 K | Detected | Added MIR-equivalent FRP MW | Retrieved FRP MW |
|---|---:|---:|---|---:|---:|
| 2026-10-29 05:00:00+00:00 | 0.1% | 332.58 | True | 242.61 | 243.34 |
| 2026-10-29 05:00:00+00:00 | 0.5% | 378.77 | True | 1213.07 | 1213.79 |
| 2026-10-29 05:00:00+00:00 | 1.0% | 405.78 | True | 2426.13 | 2426.86 |
| 2026-10-29 07:00:00+00:00 | 0.1% | 332.56 | True | 226.66 | 227.40 |
| 2026-10-29 07:00:00+00:00 | 0.5% | 378.77 | True | 1133.32 | 1134.05 |
| 2026-10-29 07:00:00+00:00 | 1.0% | 405.78 | True | 2266.63 | 2267.37 |
| 2026-10-29 09:00:00+00:00 | 0.1% | 332.52 | True | 227.90 | 216.99 |
| 2026-10-29 09:00:00+00:00 | 0.5% | 378.75 | True | 1139.48 | 1128.58 |
| 2026-10-29 09:00:00+00:00 | 1.0% | 405.77 | True | 2278.96 | 2268.06 |
| 2026-10-29 18:00:00+00:00 | 0.1% | 328.93 | True | 225.52 | 222.94 |
| 2026-10-29 18:00:00+00:00 | 0.5% | 377.63 | True | 1127.61 | 1125.03 |
| 2026-10-29 18:00:00+00:00 | 1.0% | 405.11 | True | 2255.22 | 2252.64 |
| 2026-10-29 20:00:00+00:00 | 0.1% | 328.76 | True | 228.17 | 226.02 |
| 2026-10-29 20:00:00+00:00 | 0.5% | 377.58 | True | 1140.86 | 1138.71 |
| 2026-10-29 20:00:00+00:00 | 1.0% | 405.08 | True | 2281.72 | 2279.57 |
| 2026-10-29 22:00:00+00:00 | 0.1% | 328.79 | True | 221.27 | 221.96 |
| 2026-10-29 22:00:00+00:00 | 0.5% | 377.58 | True | 1106.34 | 1107.03 |
| 2026-10-29 22:00:00+00:00 | 1.0% | 405.08 | True | 2212.68 | 2213.37 |

At 0.1%, added MIR-equivalent FRP ranges from 221.27 to 242.61 MW. Retrieved FRP differs slightly because it uses the surrounding contextual radiance rather than the original center-pixel radiance. Blackbody power and exact pixel area are also stored in the JSON audit.

### Real positive controls anywhere in S03–S04

Qualifying VIIRS event-overpasses (sum within one event/platform/acquisition time, FRP >100 MW, native pixel VZA <65°): **9**. Unique events: 6; clear-observed: 9; detected within 2 km at the nearest hourly step (±30 min): **7**; nearest scans unavailable: 0.

Selection uses the actual downloaded segment projection extents, including locations outside the South Asia Phase 3 crop. Repeated overpasses/platforms are separate control opportunities, not independent unique fires. The misses do not invalidate the positive control: temporal evolution, subpixel dilution and the fixed 310 K daytime candidate threshold can prevent detection.

Per-event locations, radiances/temperatures, status and match outcomes: `himawari/real_positive_controls.csv`. Full radiometric metadata and injection audit: `himawari/positive_controls.json`.

## Geostationary assignment

Nominal sub-satellite longitudes: Himawari 140.7°E; Meteosat-9 Indian Ocean 45.5°E. [EUMETSAT confirms the Meteosat-9 location](https://www.eumetsat.int/eumetsats-meteosat-9-reaches-its-new-home). Selection minimizes ellipsoidal-ground VZA among platforms strictly below 65°, independently of data availability. A cell receives one platform or null; a missing file does not switch it to a worse-view platform.

Assigned the complete 0.1° global common grid: 6,480,000 cells, including cells with no fires. Counts: `{"No valid view": 4419432, "Meteosat-9": 1030284, "Himawari": 1030284}`. Full assignment: `data/processed/windows/current_2026/geo_platform_assignment.parquet`.

![Geostationary platform assignment](figures/geo_platform_assignment.png)

| Region | Grid cells | Assigned platform counts | Mean selected VZA |
|---|---:|---|---:|
| Bangladesh | 2914 | {'Meteosat-9': 2914} | 56.77° |
| eastern_IGP | 2000 | {'Meteosat-9': 2000} | 54.35° |
| full_IGP | 13600 | {'Meteosat-9': 13600} | 51.03° |
| Punjab_Haryana | 1480 | {'Meteosat-9': 1480} | 48.32° |

Nominal geometry is a platform-selection rule; per-scan orbit metadata and product footprint/quality coverage still determine whether observations exist. Lower VZA does not guarantee that an operational product covers a given place. IODC is listed as a demonstration product by LSA SAF.

## Meteosat ingest and dependent science

**Ingest status: awaiting data.**

Input directory: `D:\nasa space\Burning_Activity\data\raw\meteosat\current_2026`. Files: 0; list files: 0; quality files: 0; detections ingested: 0; errors: 0.

No Meteosat files are present in this snapshot. As requested, dependent Parts C–E science stops without an error. No empty observation days are fabricated. `params/diurnal_v2.json` is not written and the existing v3/v2 transfer parameter artifacts are preserved. Per-region detection/commission rates, logistic coefficients with VZA, 15-minute diurnal peak/width/base-to-peak intervals and event-specific transfer ratios are **awaiting data**.

The ingest module reads HDF5 (including NetCDF4/HDF5 and bzip2 wrappers), decodes field scaling/fill metadata, records acquisition-time basis, and validates IODC location where available. It retains FRP uncertainty, confidence and pixel area as unknown when absent. Dataset paths can be configured explicitly if the delivered product schema differs. Real-file schema validation remains pending until the files arrive; synthetic HDF5 fixtures test the parser behavior.

Please include both FRP ListProduct and corresponding QualityProduct files when downloading. [The product paper distinguishes fire-only lists from all-pixel quality coverage](https://acp.copernicus.org/articles/15/13217/2015/). A missing row in a fire list cannot be treated as a clear-sky non-detection. The [LSA SAF product page](https://lsa-saf.eumetsat.int/en/data/products/fire-products/) supplies IODC data and product documentation links.

### Calibration comparison and FRE coverage

| Calibration | Status | Result |
|---|---|---|
| v1 | Original drift-affected window; retained | `{"a": -0.8239771284434613, "b": 1.3196439470461132, "by_daynight": {"day": {"n": 357, "a": -0.7297585160117105, "b": 1.2726277286278793}, "night": {"n": 39, "a": -1.9927899854071245, "b": 1.9394699532959596}}}` |
| v3 transfer | Prior Phase 3 artifact; no Phase 3b refit | `{"fitted": false, "n": 0, "reason": "No supported regional diurnal shape or too few adjusted day pairs"}` |

Phase 3 FRE coverage remains 0/138,576 events with non-null estimates. No new energy estimates are supplied. Calibration may use a region only when its assigned platform has a supported diurnal shape; awaiting data never becomes a unit time ratio.

## Verification

58 harmonization tests passed, including 11 Phase 3b tests. All 61 backend tests passed. The real-tile injection test detects all three stated fractions; grid tests enforce single-source minimum-VZA selection; transfer tests reject unsupported regional shapes. Parser fixtures are synthetic and are not counted as observed fires.

## Limitations and next run

Positive controls verify the radiometric and detection code path, not a validated regional completeness or commission rate. MIR-only injection assumes an 800 K blackbody without atmospheric attenuation, instrument saturation or longwave heating; its fractions imply fires above 200 MW at these coarse pixels. The six sites are not a sensitivity characterization of every surface, season or VZA. The LSA SAF manual archive could not be downloaded from this network, so field aliases and real 2026 IODC metadata must be checked on arrival. No Meteosat detection, shape, uncertainty interval, calibration or FRE number is inferred from geometry alone.

Run `python run_phase3b.py --window current_2026`. Controls run first by default. `--reuse-controls` explicitly reuses saved control audits for the same processing window; rerun without this flag after detector or input changes. Ingest writes `data/processed/geo_fires/platform=Meteosat-9/year=YYYY/month=MM/day=DD/part.parquet` only for delivered observations. See `docs/phase3b.md` for schema and validation details.
