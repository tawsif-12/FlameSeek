# Decisions and deviations (Phase 1, Steps 1–5)

Each entry says what the procedure asks, what the code does, and why.

## Data and environment

**D1. Raw data location.** The brief puts FIRMS files in `data/raw/`; they were delivered in
`dataset/`. The four CSVs were copied byte-for-byte (MD5 checked) into `data/raw/`. `dataset/` is
left untouched. The pipeline reads only `data/raw/` and never writes there.

**D2. `modis.csv` is not MODIS.** It is byte-identical to `viirs noa 20.csv` (same MD5): VIIRS
columns, `instrument = VIIRS`, `satellite = N20`. Following the procedure ("use the instrument
column, not the file name"), its rows are read as NOAA-20 VIIRS. The duplicate copy of each row is
then removed in Step 2 with reason code `duplicate_detection`. The run continues with VIIRS only.

**D3. Procedure document.** `docs/harmonization_procedure.md` did not exist, and the root
`Harmonization_procedure.md` is empty. The procedure was transcribed from
`FlameSeek Harmonization Procedure.pdf`, which stays the source of truth.

**D4. Conda channels.** The brief asks for conda-forge. On this PC, Windows Smart App Control
(enforce mode) blocks some unsigned DLLs from recent conda-forge builds: `pandas._libs` and
`pyproj._context` failed with "An Application Control policy has blocked this file", and the
scikit-learn import hung. The Anaconda `defaults` builds load, so `environment.yml` lists
`defaults` first and keeps `conda-forge` as fallback. On a machine without Smart App Control, put
conda-forge first again. `pyyaml` and `pytest` were added because the pipeline and tests need them.

**D5. Date format.** These files store `acq_date` as `11/2/2026` (M/D/YYYY, typical after a save in
Excel) instead of FIRMS' `2026-11-02`. Both formats are accepted. The US reading (2 November) agrees
with the download date.

## Step 2

**D6. Filters that cannot run on this data** are listed in the report, not faked: the MODIS `type`
filter (NRT files have no `type`), the persistent-hotspot mask (needs multi-year data), the Nightfire
flare mask (optional; no list) and the Himawari transient filter (no Himawari data).

**D7. Extra reason codes.** Besides the procedure's sanity checks, rows are also set aside for
`duplicate_detection`, `invalid_scan_track`, `unknown_sensor`, `sensor_platform_mismatch` and
`missing_confidence`. Set-aside rows go to `data/interim/detections_removed.parquet` with their codes.

**D8. Study bbox.** None was set, so it was detected from the data (outer bounds plus 0.1°). The
FIRMS extract is global, so the bbox is near-global. To restrict the run to the Bangladesh pilot,
set `study_bbox: [88.0, 20.5, 92.7, 26.7]`.

## Step 3

**D9. Rectangle orientation.** The procedure fixes the size (scan across-track, track along-track)
but not the direction. FIRMS has no heading column. By default the rectangle is rotated to the
approximate ground-track heading of a sun-synchronous orbit (inclination 98.7°):
sin(dev) = |cos i| / cos(lat). Heading is NNW on ascending passes (daytime for Aqua, S-NPP, NOAA-20
and NOAA-21, night-time for Terra) and SSW on descending passes. Earth rotation (a few degrees) is
ignored. Set `footprints.orientation: north_up` to disable the rotation. Area is the same either way.

**D10. AEQD inverse in closed form.** Building one pyproj AEQD projection per detection is slow.
AEQD keeps distance and azimuth from its centre exactly, so each corner is computed as the geodesic
point at that distance and azimuth (`pyproj.Geod.fwd`), which is the same result. A unit test checks
this against an explicit AEQD transform (agreement to 1e-8°).

**D11. Expected area ranges.** The procedure gives pixel sizes at nadir and swath edge. The check
uses [0.9·nadir, 1.1·edge] in km²: VIIRS 0.127–0.704, MODIS 0.9–10.6.

## Step 4

**D12. "Day" for clustering = local solar date.** The data is global, and a UTC day cuts through
the local night differently at each longitude. Detections are grouped by the local solar date
(UTC time + longitude/15 h), the same clock as `lst`. Set `events.day_basis: utc` to use UTC dates.
As a result, one UTC day of data spans two local dates.

**D13. Multi-day linking at detection level.** The procedure links daily clusters when their
footprints overlap. Two clusters overlap exactly when some pair of their footprints overlaps, so
the code links those detection pairs directly. The result is the same, and the cap-splitting step
can reuse one graph.

**D14. Overlap and half-diagonal tests.** Both tests are computed and recorded. Note that overlapping
rectangles always satisfy the half-diagonal test, so overlap never adds a link the distance test
would miss.

**D15. UTM zone selection.** Each pair distance is computed in the UTM zone of the pair's
great-circle midpoint (EPSG:326zz/327zz). For Bangladesh this is mostly EPSG:32646, as the
procedure states. Norway and Svalbard zone exceptions are ignored.

**D16. How caps split.** Extent is the largest corner-to-corner distance of the event's footprints.
An event longer than 14 days is first cut into 14-day windows. An event wider than 25 km is split by
complete-linkage clustering of centroids with threshold 25 km − 2 × (largest half-diagonal), which
guarantees every piece is ≤ 25 km. Each piece is then split into its connected components, so no
event joins footprints that were not linked.

**D17. "Same acquisition time".** An overpass is (platform, `acq_datetime_utc`), exactly as written.
FIRMS times are per granule, so one fire that straddles two granules of the same orbit (1–2 min
apart) counts as two overpasses, and its FRP is not added across them. This is conservative.
Merging granules within a few minutes is a possible later refinement.

**D18. Fields not filled.** `biome` is left empty (no MCD12Q1). `FRE_estimate` (Step 7) and
`cause_label` are not produced. Extra fields: `n_detections`, `extent_km`, `p_conf_max`, per-sensor
mean-per-overpass FRP, `split_from` and `split_reason`.

## Step 5

**D19. Weight normalisation.** w_ic is computed in EPSG:6933, with each piece shifted to longitude 0
(area in 6933 does not depend on longitude, and this avoids antimeridian problems). Pieces partition
the footprint, so Σ w_ic is 1 up to small projection error (this run: 5e-6, because the extra vertices added
at cell edges slightly change the projected shape). The weights are renormalised to exactly 1 and the raw
deviation is reported.

**D20. Daily grid FRP.** FRP is additive per overpass (`data/interim/grid_overpass.csv`). In
`grid_daily.csv` it is reported as the max and mean across overpasses, never the sum. Event counts
are weighted by the share of each event's same-day footprint union inside the cell. The energy
check compares Σ FRP of detections with Σ FRP over all cell-overpass rows.

**D21. Grid days** use the same local solar date as Step 4 (D12).

## Phase 2 (Step 6)

**D22. Matching window: 60 min for every VIIRS platform (capped).** For every Aqua overpass of an
event that VIIRS also saw, the nearest overpass of each VIIRS platform in the same event was found.
Results, from `outputs/figures/aqua_viirs_dt_hist.png`:

| VIIRS | Aqua overpasses | Median abs(Δt) | ≤ 30 min | ≤ 45 min | ≤ 60 min | Main peak |
|---|---|---|---|---|---|---|
| S-NPP | 6,761 | 136 min | 0.6% | 1.2% | 4.8% | 150–155 min |
| NOAA-20 | 6,903 | 130 min | 0.2% | 0.8% | 1.3% | 125–130 min |
| NOAA-21 | 6,615 | 156 min | 0.1% | 0.3% | 1.7% | 155–160 min |

VIIRS almost always looks *before* Aqua: Δt (VIIRS − Aqua) is negative. The computed orbits agree:
Aqua's daytime passes now fall at about 15:45 local solar time, against 13:50–14:05 for the VIIRS
platforms. Aqua's orbit has drifted. The rule ("smallest window that captures the main peak, at
most 60 min") cannot reach a peak at 125–160 min, so every window is capped at 60 min. Matched pairs
are therefore the leading edge of the distribution, mostly at high latitude or towards the swath
edge, not typical viewing. Windows are stored per platform in `config/settings.yaml`
(`matched_pair_window_by_platform`). Each pair keeps `dt_min` (signed) and `window_min`.
Terra is never paired, and the code raises an error if it is configured.

**D23. One pair per Aqua overpass.** An event can have several Aqua and VIIRS overpasses. For each
Aqua event-overpass, the nearest S-NPP or NOAA-20 overpass inside its window is used, so the same
MODIS value is not counted twice. NOAA-21 is left out of the calibration pairs, as in the procedure
(Aqua with S-NPP or NOAA-20), but it is included in the detection-curve sample, as Part E asks.

**D24. Night calibration is unstable.** The night fit has 39 pairs, which passes the 15-pair minimum,
but its bootstrap interval for b is very wide. Use the day or the all-pairs fit.

**D25. Observation-opportunity cells.** The opportunities are computed for every 0.1° cell with a
detection, plus every cell inside the five candidate pilot boxes (109,054 cells). A global run over
all 6.5 million cells is not needed for Step 6. Step 8 will need it over the study area, including
cells with no fire.

**D26. Overpass computation.** skyfield/SGP4 propagates each orbit once at 30 s steps. A KD-tree on
the track then finds each cell's passes, and the closest approach is refined by projecting the cell
onto the neighbouring track segments. This avoids running skyfield's per-location event search
6.5 × 10⁵ times. Check: 99.96% of clean detections lie inside a computed overpass of their own
platform within ±10 min.

**D27. TLE source.** CelesTrak timed out from this network, so the public mirror
`tle.ivanstanojevic.me` was used. These are current elements with epochs of 1 Nov 2026, propagated
back over 29 Oct–2 Nov. Historical TLEs need a Space-Track account. The source and epoch are stored
with every overpass row.

**D28. Pixel-area model.** Geometric (Ichoku & Kaufman 2005) for MODIS. For VIIRS, the same geometry
on a native sample of a third of the nadir pixel, aggregated 3/2/1 along-scan by scan-angle zone.
The ratio of observed scan × track to expected area per platform is reported in the Phase 2 report.

**D29. Detection-curve sample and its limits.** A case is a VIIRS event-overpass in a cell with a
computed Aqua overpass within the platform's window. It counts as detected if an Aqua detection of
the same event lies within ±10 min of that Aqua overpass. Because of D22 the sample is dominated by
large MODIS pixels (median expected area about 5.6 km²), so the nadir 50% FRP is an extrapolation.
Checks done:
- the detected share hardly changes between 15 and 60 min windows (3.5–6.4%);
- none of the 7,292 misses had a low-confidence Aqua detection nearby.
Neither timing nor the confidence filter explains the misses.

**D30. F_min search.** The Clauset method picks the x_min that minimises the KS distance. To keep the
search fast on about 175k values, the candidates are 60 log-spaced quantiles (1st–99th percentile)
instead of every unique value.

**D31. π_MODIS two ways.** "Empirical" is the mean of P_det over every VIIRS event-overpass, with no
tail model. "Power-law tail" is the procedure's integral over the fitted power law above F_min. The
likelihood ratio favours the lognormal, so the power-law-tail value describes the large-fire tail only.

**D32. scipy.odr is deprecated** (SciPy 1.17, removal planned for 1.19). It is used as the brief
asks, and works in the pinned environment. Before upgrading SciPy, switch to `odrpack`.

**D33. skyfield** (plus sgp4 and jplephem) was installed with pip into the `flameseek` env and
added to `environment.yml`.

## Phase 2b (drift history)

**D34. How the drift history is sampled.** Local disk only had the 2026 data, so one sample per
year was downloaded from the FIRMS standard-processing archive. The FIRMS key comes from
`backend/.env` and is never printed or stored in outputs. Each sample:
- covers 29–30 October, the same season as the 2026 data;
- uses daytime detections only, in |lat| ≤ 30°;
- comes from MODIS_SP (Terra and Aqua) and VIIRS_SNPP_SP for 2013–2025, plus VIIRS_NOAA20_SP from
  2018 and VIIRS_NOAA21_SP from 2023.

The 2026 values come from `data/raw/` using the same rule. Downloads are cached once in
`data/raw/firms_archive/` and never modified. Results: `data/processed/drift_by_year.csv`,
`outputs/figures/overpass_lst_by_year.png`, `outputs/phase2b_drift_report.md`.

**D35. First drifted year = 2024 for both Terra and Aqua.** The early-archive value is the median of
2013–2015:

| Platform | Early-archive value | 2023 | 2024 | 2026 |
|---|---|---|---|---|
| Terra | 10:25 | 09:59 (26 min) | 09:38 (47 min) | 08:32 |
| Aqua | 13:36 | 13:58 (22 min) | 14:21 (45 min) | 15:49 |

S-NPP never moves more than 30 min (13:21–13:46). The 2026 detection-based values agree with the
TLE-computed Phase 2 overpasses (Terra 08:35, Aqua 15:46) to within 3 min.

**D36. `drifted_era` column.** Step 1 (`pipeline/ingest.py`) sets `drifted_era = true` for a MODIS
detection when its year is at or after `drift.first_drift_year` for its platform (Terra 2024,
Aqua 2024, both stored in `config/settings.yaml`), and `false` otherwise. VIIRS rows are empty
(not applicable). When no year is configured, MODIS rows stay empty (unknown) rather than false.
Every MODIS detection in the current 2026 data is in the drifted era.

**D37. Calibration years: 2015, 2018 and 2021, but treat the list as provisional.** By the rule
(median Aqua–S-NPP abs(Δt) ≤ 20 min, at least 30 detection pairs), only these three years qualify.
Before any drift, the yearly median abs(Δt) already ranges from 10 to 38 min. Both satellites cross
at about 13:30, but on two particular days their ground tracks are a varying fraction of an orbit
apart, so a 2-day sample mostly measures that phase. Before these years are used to select
calibration data, the Δt should be recomputed from a wider sample per year (for example all of
October). Under this definition, 2026 is not a calibration year (Δt 145 min). So the Phase 2 FRP
calibration (D22–D24) is a drifted-era calibration.

## Scalable architecture (day partitions, windows, params, eras)

**D38. Day-by-day pipeline, and the small difference from batch.** Steps 1–5 now run one local solar
day at a time (`pipeline/stages.py`, `run_pipeline.py`). Partitions are written to
`data/processed/<stage>/year=YYYY/month=MM/day=DD/`. Multi-day linking reads only the previous day:
its detections, its fire ids and an `event_state` table with the convex hull and start day of each
active event.

When a day joins two older events, the pipeline writes a `merges` row instead of rewriting past
days, and `finalize` resolves merges with a union-find. The caps are checked as each day is linked:
- if joining would exceed 25 km or 14 days, today's pieces start new events;
- the batch version split a whole multi-day component after the fact (complete linkage).

On the 5-day window, against the batch snapshot (`data/interim/legacy_batch/`):

| Check | Result |
|---|---|
| Clean detections | identical (545,537, same rows) |
| Total FRP | identical |
| Aqua–VIIRS pairs | identical (416) |
| Grid cell-days | identical (114,903) |
| Fire events | 138,576 vs 138,518 (+0.04%) |
| Event groupings identical | 138,484 of 138,518 (99.98%) |

The rest differ only where a cap split a multi-day component. `n_events_weighted` in `grid_daily` is
0.7% higher, because a day's grid is written before any later merge is known. Every event still
respects both caps (largest extent 24.87 km).

**D39. Identical reruns.** Each detection's id is a 64-bit hash of (source file, source row), every
partition is sorted before writing, and writes are atomic (temp file, then rename). A `--force`
rerun reproduces every partition exactly (`tests/test_partitioned.py`). Without `--force`, days whose
partitions exist are skipped. `--force` reprocesses every stage for the selected days.

**D40. A local day reads three UTC days.** A local solar day spans UTC days D−1 to D+1, so `detect`
reads those three raw parts. Duplicate and URT checks therefore see their neighbours across midnight,
exactly as in batch. This triples the ingest work per day, the main cost of `detect` (benchmark).
Caching the standardized UTC days is the obvious next optimisation.

**D41. Region first.** With a bbox in the window or config, rows outside it are dropped at ingest,
before footprints. They are counted, not kept in the removed table.

**D42. Window facts are computed once per window** in `raw_split`: bbox detection, partial days,
coverage and era measurements. A single day cannot judge them.

**D43. Eras are measured, not dated.** For each platform and month, `raw_split` builds a one-minute
histogram of daytime local solar time (|lat| ≤ 30°) and takes its median. The reference is the
platform's measured early-archive median from `drift_by_year.csv` (its first three years), or its
nominal crossing time when that file is missing. Classification:
- **drifted:** more than 30 min from the reference;
- **multi_sensor:** any VIIRS platform present that month; otherwise **MODIS_only**.

Results for Oct–Nov 2026: Aqua +131 min and Terra −111 min (drifted); S-NPP, NOAA-20 and NOAA-21
within 11 min (not drifted). `drifted_era` on every MODIS detection now comes from this table.
`drift.first_drift_year` is kept only as the fallback for the older batch path.

**D44. Parameters are versioned files** (`params/<kind>_vN.json`, `pipeline/params.py`). Only
`refit_params.py --window` writes them; processing stages only read them. The status comes from
measured facts:
- **validated-sync-window:** the window's Aqua–S-NPP median abs(Δt) ≤ 20 min. In that case the
  calibration uses the sync method (pairs ≤ 15 min, both FRP ≥ 10 MW truncation filter, Deming with
  stated error ratio 1.0, OLS(y|x) and inverse-OLS slope bounds, ODR for comparison, bootstrap), and
  earlier provisional fits from drifted windows are re-marked drift-affected, with history kept.
- **provisional:** otherwise.

v1 comes from `current_2026` (Δt 136 min, Aqua drifted): calibration, detection_curve and pi_modis
are provisional; diurnal is not_available (no Step 7, no Himawari).

**D45. sync_2016 window not run.** `data/raw/archive/2016/` does not exist, so the v1 params stay
provisional and no 2016 drift comparison was made. The 2-day archive sample from Phase 2b gives
29–30 Oct 2016 an Aqua–S-NPP median abs(Δt) of 32 min, so even with 2016 data this window may fail
the ≤ 20 min sync rule. 2015, 2018 and 2021 met it in that sample (D37), but a wider sample per year
should confirm the choice before downloading.

**D46. DuckDB pinned to UTC.** DuckDB returns time-zone-aware timestamps in the computer's local
zone (+06:00 here) unless told otherwise, which put local times into `*_utc` columns.
`partitions.connect()` sets `TimeZone = 'UTC'`, and a test checks it.

**D47. Multi-year components are built and tested on simulated data** (`pipeline/calendar.py`,
`pipeline/anomalies.py`, `forecast/`, `tests/simulated/`). On real data they need at least
3 (calendar), 5 (anomalies, forecast) or 8 (change point) years, set in `history:` in the config.
Below that they return `insufficient_history` (XGBoost: `requires_multi_year_data`) and no numbers.
The Pettitt p-value has a floor that depends on record length: with 15 years and the change after
year 8, the smallest attainable p is 0.0107. The test therefore uses p < 0.05.
