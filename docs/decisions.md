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

## Phase 3 (Step 7)

**D48. AHI band-7 MIR constant.** The measured Himawari-9 response is from
[NWP SAF's AHI-9 channel 7 SRF](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_himawari_9_ahi_srf/rtcoef_himawari_9_ahi_srf_ch07.txt).
Convert wavenumber to wavelength (lambda_um = 10000 / wavenumber_cm-1), sort,
and compute the response-weighted mean Planck spectral radiance in wavelength
space, in W m-2 sr-1 um-1. At each integer temperature 650–1300 K, regress
L(T) on T^4 through the origin: a = sum(T^4 L) / sum(T^8).
The result is a = 3.1968263738110607e-9 W m-2 sr-1 um-1 K-4;
sigma/a = 17.73751138202904. With pixel area in km2, A*(sigma/a)*delta_L
is numerically MW. The SRF SHA-256 and fit diagnostics are retained in
outputs/himawari/mir_constant.json. Relative RMS approximation error is 7.861%;
maximum relative error is 27.484%, so this is an approximate MIR conversion,
not an exact radiometric fire-temperature inversion. Atmospheric transmission
and daytime reflected solar radiance are not corrected.

**D49. Unknown observations and tuning.** Status grids retain cloud, invalid
view, missing data, water, and insufficient contextual background separately.
Only clear land states 0 and 1 enter detection denominators. Nearest hourly
AHI steps have a 30-minute tolerance; spatial reference matches use 2 km.
Tuning sees October 29–30 only; alternatives are considered only if large
(clear-observed, >=20 MW) training event-overpasses trigger the configured
rule. October 31–November 1 are held out. A detection without a match in either
exact adjacent hourly step and without a polar match is flagged, never deleted.

**D50. Fit availability and transfer domain.** A day with zero FRP has no
normalizable daily maximum. Such days do not identify a diurnal curve. A
geometrically Tier A region can still have an unavailable fit. Eastern IGP's
small valid sliver cannot represent its entire box or serve as an established
Tier A donor for Punjab–Haryana. No shape is silently transferred globally.
Transfer artifacts have the requested provisional status and explicit fitted
flags and nulls where unsupported. The original unavailable diurnal_v1 is
preserved as diurnal_v1.pre_phase3.json. Phase 3 is an explicit refit entry point,
an extension to D44's earlier refit_params-only rule.

**D51. Time and energy.** Ratios use each event's longitude to compute local
solar time; Aqua-only transfer pairs may be up to six hours apart on the same
local solar day. Terra is rejected. Daily energy is MJ (MW times seconds),
combining overpasses within each local solar day by inverse variance, then
summing distinct days. Sensor relative uncertainties are configured assumptions;
shape-transfer uncertainty remains unquantified where no shape exists, so FRE
is null there. Full UTC days are used for fitting (October 29–November 1), as
requested; the partial November 2 UTC day is excluded.

## Phase 3b

**D52. Positive controls before changing the detector.** On October 29, three
daytime (05, 07, 09 UTC) and three nighttime (18, 20, 22 UTC) scans report B07,
B14 and B15 brightness temperatures in K. HSD Planck constants and band-specific
quadratic correction independently reproduce cached B07 temperatures. Controlled
800 K sources are mixed into copies of real clear-land MIR radiance tiles at
0.1%, 0.5% and 1% area fractions. All 18 trials are detected. The smallest tested
fraction is not a fitted detection limit. B14/B15 are fixed for this MIR-only
code-path test. No raw or science-cache arrays are changed. The simple cloud
screen still permits cold/residual-cloud pixels; this is a validation limitation,
not evidence that the data are radiances instead of K.

**D53. Real controls use all downloaded segment coverage.** VIIRS detections are
summed within event/platform/acquisition time. Candidates above 100 MW are
located in the actual S03–S04 projection bounds, then screened at native-pixel
VZA <65 degrees. Local native tiles retain the detector background halo. Seven
of nine event-overpasses are detected within 2 km at the nearest hourly scan,
within 30 minutes. These are repeated observation opportunities, not nine
independent fires. Controls verify the implementation; they do not establish a
regional sensitivity or commission curve. No detector bug was found, so Phase 3
science is retained unchanged.

**D54. Platform assignment is independent of data availability.**
[EUMETSAT confirms Meteosat-9 at 45.5 degrees E](https://www.eumetsat.int/eumetsats-meteosat-9-reaches-its-new-home).
The configurable platforms are Himawari at 140.7 degrees E and Meteosat-9 at
45.5 degrees E, with nominal geostationary altitude 35,785,863 m. Every 0.1-degree
global cell receives the platform with the lowest VZA strictly below 65 degrees,
or null if neither qualifies. No double counting and no file-availability fallback.
All four South Asia boxes select Meteosat-9 at every cell center. Geometry does
not establish product availability or actual footprint coverage. Configured
cadences are 60 minutes for existing AHI data and 15 minutes for SEVIRI.

**D55. Meteosat no-data gate and file validation.** No files are present in
`data/raw/meteosat/current_2026/`. Ingest returns `awaiting data`, without creating
empty observation days or replacing diurnal/transfer/FRE products. The parser
supports HDF5 and compressed wrappers, checks units, scaling and platform
longitude, records pixel versus scan-start time, and retains missing uncertainty,
confidence and area as unknown. Native 2026 schema validation is pending. The
public LSA SAF documentation share timed out; accepted aliases and explicit
scaling conventions are documented in `docs/phase3b.md` and tested on synthetic
HDF5 fixtures, not represented as validated real-file parsing.

**D56. Fire lists are insufficient observation masks.**
[The LSA SAF product description](https://lsa-saf.eumetsat.int/en/data/products/fire-products/)
lists IODC FRP-PIXEL as a demonstration product. The
[product paper supplement](https://acp.copernicus.org/articles/15/13217/2015/acp-15-13217-2015-supplement.pdf)
distinguishes ListProduct detections from QualityProduct coverage. Download both.
Cloud, unprocessed pixels and missing files cannot be encoded as no fire. Before
fitting 15-minute regional diurnal shapes, validate the quality flags, their
geolocation and the actual South Asia footprint. Parts C–E science remain
awaiting data in this run; no diurnal_v2 is written and no unsupported region
enters transfer calibration.

## Phase 3c

**D57. Detection limit from synthetic injection.** Reuse the exact six Phase 3b
Bangladesh control sites and original calibrated tiles; do not select new warmer
sites after inspecting outcomes. The new 800 K unitless area fractions are
0.00005, 0.0001, 0.0002, 0.0005 and 0.001 (0.005%, 0.01%, 0.02%, 0.05%, 0.1%).
Each trial starts from the untouched background. Added MIR-equivalent power
uses native pixel area and the same sigma/a constant. Thirty trials produce
0/6, 0/6, 0/6, 6/6 and 6/6 detections. The transition is bracketed by median
powers 45.46 and 113.64 MW. Linear interpolation of response fraction against
log median power yields 71.87 MW, explicitly labeled "detection limit from
synthetic injection". This descriptive interpolation is not a fitted logistic
sensitivity curve. The wide bracket is resolution of the tested grid, not a
confidence interval; six fixed contexts cannot establish regional completeness.
Day/night results and all trial powers, temperatures, VZA and areas are saved.
The estimator does not extrapolate unbracketed responses or assign a point to
a 50%-response plateau.

**D58. Near-nadir and Northern Australia require their own data.** The near-nadir
land box is [138, -5, 145, -1] with VZA <10 degrees, requiring S0610. Three scans
are requested (00, 04, 12 UTC). Northern Australia is [125, -20, 138, -11], requiring
S0610/S0710. Only S0310/S0410 are locally present. Both experiments are awaiting
data; no near-nadir threshold is area-scaled from Bangladesh. No Australian
shape or transfer parameter is written. A future Australian fit is confined
to its configured box as a method demonstration and cannot adjust South Asian
observations. Its partitions and event FRE output are isolated from other regions.

**D59. Conditional synchronized-window analysis.** `data/raw/archive/2016/` has
no FIRMS CSV inputs, so Phases 1–2, the 2016/2026 drift comparison, synchronized
fits and empirical pi_MODIS are awaiting data. Prior short archive drift samples
are not substituted for the requested window. The synchronization test uses
median absolute event-level Aqua–S-NPP time differences, not a signed median.
The existing Phase 1–2 implementations remain unchanged. Future execution uses
isolated 2016 day partitions and the existing 15-min/truncation/Deming/OLS/ODR/
bootstrap method. Only a qualifying fitted result can receive the requested
"validated – synchronized window" status. Nadir observations are included when
present, never inferred from swath-edge samples.

**D60. Calibration recommendations are explicit and inactive.** Meteosat is
still awaiting data. The comparison table reads existing parameter files and
reports absent fits as unknown, not as zero coefficients or invented samples.
The drift-affected v1 (396 pairs) is a diagnostic benchmark. Conditional
preferences are synchronized v2 for represented synchronized-era conditions,
regional Australian v3 only for its demonstration box, and regional Meteosat
v3 for South Asia. None of the new alternatives is fitted in this snapshot.
No active parameters are switched and no Australian-to-South-Asia transfer is
allowed. Recommendations are saved separately from the parameter store.

## Staged continuation: Stage 2

**D61. The downloaded 2016 window fails the declared synchronization gate.**
Four yearly country files yield 24,928 in-window raw rows and 24,025 clean rows.
There are 1,698 event-level Aqua/S-NPP comparisons with median absolute difference
21 minutes. The criterion is <=20 minutes, so v2 is not activated and no
validated synchronized regression is claimed. The threshold was not relaxed.
The original Phase 1 algorithms ran unchanged; its raw-inspection report needed
an empty-CSV guard for the legitimate zero-row Bangladesh MODIS extraction.

**D62. Historical opportunity data remain absent.** Only 2026 TLEs are cached.
No ten-year extrapolation is accepted as valid 2016 observing coverage. Phase 2
matching, measured drift and eligibility calculations use observed detections;
the orbit-dependent 2016 detection curve, nadir F50, empirical pi and opportunity
counts remain awaiting historical orbital/coverage data. This also constrains
2016 latent estimation and the requested degradation bias.

**D63. Australian demonstration now has observations.** S06/S07 downloaded
under the authorized 5 GB limit (1.797 GB), with 648 available hourly band/segment
files and 72 missing final-day files. Both requested boxes pass projection
coverage checks. The provisional regional shape and regression use Australian
observations only; they are not activated in South Asia. Near-nadir synthetic
F50 is 13.39 MW, descriptively bracketed by 9.47 and 18.94 MW. The six original
Bangladesh contexts remain 71.87 MW with their original coarse bracket.

## Staged continuation: Stages 3–4

**D64. Latent λ is estimated for a VIIRS-observable reference population.**
The 2026 window has 81,220 day-partitioned cell records, all estimated as
provisional with 300 calibration draws and the existing v1 sensitivity curve
(S-NPP reference, pi_VIIRS = 1 by definition). Fires below VIIRS sensitivity are
not reconstructed. Terra is excluded because it has no independent response or
time correction; the Aqua curve is not substituted. FRE stays unavailable in
South Asia because no supported regional diurnal shape exists, and the Australian
shape is not used there. The 2016 λ values and the degradation-test bias stay null
(awaiting historical observation opportunities). They are not set to zero.

**D65. History modules are reused, not rewritten.** The 15-year simulation
recovered 5/5 planted anomalies and the 2019 step change (p = 0.011). 96.7% of
cells' peak weeks fell within one week of the planted peak, and the Brier Skill
Score was 0.286. The real five-day record returns `insufficient_history` for
calendar, anomalies and forecast.

**D66. Display translation and snapshot API are offline and provisional.**
`pipeline/translate.py` maps values to English and Bengali display words with
configurable thresholds (`translation:` in settings). Risk stays "Awaiting data"
without a calibrated probability. The trend describes the power of the last three
comparable overpasses, not fire-front motion. Three honesty notes are always
attached. `/meta`, `/fires/active`, `/events/{fire_id}` and `/grid/lambda` read
read-only SQLite snapshots. "now" is the configured window end, not wall-clock
time. Every response, including errors, carries `data_version` and
`last_observation_time`.

**D67. Each window carries its own data version.** Phase 1–2 tables stamp the
global `data_version`, so the 2016 window's events were labelled with the 2026
NRT version. The latent and snapshot code also had two different hardcoded 2016
labels. A window may now set `data_version` in settings (sync_2016:
`firms_country_sp_2016_India_Bangladesh_v1`). The config loader applies it, and
the snapshot build stamps it on every event and grid row. Snapshots were rebuilt;
row counts are unchanged (2016: 12,289 events / 81,220 grid rows; 2026:
138,576 / 81,220). The on-disk 2016 Phase 1–2 tables keep the old label until
they are next regenerated. No algorithm changed.

## Synchronization gate and 2016 opportunities

**D68. The synchronization gate is replaced.**
- *Old rule (D59/D61):* median absolute Aqua–S-NPP Δt over all shared
  event-overpasses ≤ 20 min.
- *Why it was replaced:* that median mostly measures orbit phasing — how far apart
  in time two satellites' tracks happen to fall over an area — not whether Aqua has
  drifted. It also does not check whether there are enough close-in-time pairs to fit.
- *New rule (`pipeline/sync_gate.py`, `sync_gate:` in settings):* both must hold:
  - (a) no-drift evidence: the median local solar time of the window's daytime Aqua
    detections is within 30 min of 13:30;
  - (b) enough sample: at least 100 Aqua–S-NPP event-overpass pairs with
    |Δt| ≤ 15 min after the truncation filter (both FRP ≥ 10 MW). These are exactly
    the pairs the v2 fit uses.
- The thresholds come from the request and were not tuned. The same rule applies to
  every window.

| Window | (a) median daytime Aqua LST | offset | (b) pairs | Old rule (median abs Δt) | New gate |
|---|---|---:|---:|---|---|
| sync_2016 | 13.475 h (n = 3,272) | −1.5 min | 534 (of 1,366 at any Δt) | 21 min → fail | **pass** |
| current_2026 | 15.755 h (n = 21,162) | +135.3 min | 17 (of 327) | — | **fail (a) and (b)** |

The (a) value uses all daytime Aqua detections in the window. D61's 13.455 h used
only |latitude| ≤ 30°. The old-rule value is still written to the gate record for
comparison but no longer decides anything.

**D69. 2016 observation opportunities: detection-conditioned lower bound.**
There are no archived 2016 TLEs (`data/raw/tle/2016/` is absent), and a 2026 TLE is
never propagated back. Opportunities are therefore rebuilt from the window's own
detections (`pipeline/observed_opportunities.py`):
- Passes are split per platform (gap > 20 min, segments ≤ 6 min).
- Each detection's cross-track distance comes from its FIRMS pixel size (MODIS
  along-scan, VIIRS along-track), keeping FIRMS rounding as an interval.
- The nadir track uses the local slope of a nominal sun-synchronous orbit. A cell
  counts only if it is inside the swath under every track offset consistent with the
  detections. Along-track coverage is cut to the latitude span of the detections.

Every result is labelled **"detection-conditioned opportunities – lower bound on
O_s"**. Passes with no detections, and swath parts the detections do not prove, are
missing. So O_s is undercounted, and λ = count / opportunities is biased **high**.

Validation on current_2026 (South Asia detections, same cells and period) against
TLE-based Step 6A opportunities:

| Platform | Precision | Share of true O_s recovered | Median time error | Median scan-angle error |
|---|---:|---:|---:|---:|
| Aqua | 100% | 37% | 0.64 min | 0.24° |
| Terra | 99.8% | 36% | 0.35 min | 0.15° |
| S-NPP | 94.9% | 41% | 0.46 min | 2.1° |

About 5% of S-NPP fallback rows have no TLE pass within 10 min. So "lower bound"
holds in aggregate, not for every row. The recovered share in 2016, which has fewer
detections, is unknown and probably lower. `tools/fetch_spacetrack_tle.py` (not run
here) fetches archived TLEs. Once `data/raw/tle/2016/` has epochs within 3 days of
the window midpoint for Terra, Aqua and S-NPP, the TLE path replaces the fallback
automatically (`pipeline/tle_archive.py`).

**D70. 2016 results under D68/D69 (`run_sync_gate.py`, `outputs/stages/stage5_sync_gate.json`).**
- **Calibration v2 sync 2016:** status "validated – synchronized window". It was
  fitted exactly as specified: pairs with |Δt| ≤ 15 min, truncation at 10 MW,
  Deming with stated error ratio 1, OLS/ODR bounds, 1,000-sample bootstrap, 90%
  intervals.
  - n = 534 of 1,366 pairs.
  - a = −0.107 [−0.280, 0.065]; b = 1.082 [0.967, 1.200].
  - The OLS(y|x) and inverse-OLS slope bounds are 0.478–2.250; the ODR fit gives
    a = −0.107, b = 1.082.
  - It is now the usable calibration for the synchronized era (India + Bangladesh).
    No 2026 parameter was switched.
- **MODIS detection curve v3 sync 2016:** status "synchronized window;
  detection-conditioned opportunities – lower bound on O_s".
  - n = 10,081 VIIRS event-overpasses, 1,361 of them detected by Aqua. Pixel areas
    range from 1.00 to 9.28 km² (median 1.66). 4,057 cases are near nadir
    (≤ 1.5 km²), 859 of them detected.
  - b0 = −3.18, b1 = 2.57, b2 = 4.79.
  - F50 at nadir is 17.3 MW [16.1, 18.6]. F50 at the 9.6 km² edge is 1,176 MW
    [904, 1,527]; this slightly extrapolates past the largest sampled area.
    Pseudo-R² is 0.24.
- **Empirical π_MODIS (nadir):** 0.287 (all, n = 13,395); 0.294 (IGP, n = 12,679).
- **λ sync_2016:** 76,099 of 81,220 cell-days estimated, 300 draws. The 5,121 cells
  with no proven opportunity stay null. Mean λ = 0.305, labelled as the lower-bound
  basis and biased high. It is **not** comparable with the 2026 mean (0.010), because
  fallback opportunities exist only near detected fires.
- **Degradation test** (mean λ_MODIS-only − λ_all over 51,544 cell-days): −0.108,
  i.e. MODIS-only is 24.4% low. It uses the same lower-bound opportunities. In 2026,
  Aqua's recovered share (37%) was below S-NPP's (41%). If 2016 behaves the same, the
  true gap is somewhat larger.
- **sync_2014:** awaiting data (`data/raw/archive/2014/` absent), so there is no
  2014 vs 2016 comparison.
- The snapshots were rebuilt, and the API now serves the labelled 2016 λ.

**D71. Northern Australia diurnal peak (18.82 h) is a detection artifact; nothing applied.**
This was a diagnosis only (`run_naus_check.py`, `outputs/naus_diurnal_check.md`). No params
or thresholds changed. Findings:
- *The fit sees no daytime data.* The diurnal fit drops scans below 30% clear sky. Daytime
  clear fraction is 11–23%, so the fit had **no points from 08 to 15 h** local solar time.
- *The cloud mask removes daytime fires.* The split-window test (B14 − B15 > 5 K) flags
  72–84% of daytime land as cloud. It flags 90–93% of VIIRS-observed fires at 12–14 h as
  cloud, against 3–10% at night.
- *Remaining daytime fires are rarely detected.* VIIRS detection rate is 10.0% by day vs
  25.2% at night; for fires above 20 MW it is 7.5% vs 81.2%. Likely cause: the daytime
  B07 − B14 contextual test (background mean 17–28 K, std 6–9 K). Daytime B07 background
  noise is *lower* than at night, so it is not the cause.
- *The day/night threshold switch is not the cause.* With 310 K at night the peak moves
  to 18.25 h; with 300 K by day it moves to 16.22 h but adds pixels that are only 8.6%
  location-confirmed.
- *Evening detections are real; midday ones mostly are not.* At 17–19 h, 89–91% are
  location-confirmed. At 09–12 h, 92–98% are never confirmed. There are no persistent
  unmatched pixels and one glint case (< 12°).
- *Matcher bug.* `himawari.nearby()` assumes nanosecond integers. Under pandas 3 the
  columns are in microseconds, so every tolerance is 1,000× wide and "±60 min" means
  ±1,000 h. The published Phase 3c "VIIRS-matched" flag therefore equals "location
  confirmed at any time", and the 26.5% "commission" is really "never confirmed". With a
  correct ±60 min match, only 21.4% of pixels are time-matched. Affected:
  `phase3c.py:31`, `run_phase3.py:132/148`, `transfer.py:94`.
  `tests/test_naus_diagnostics.py` pins the current behaviour; flip that assertion when
  the helper is fixed.
- *Refits (in memory).*
  - Corrected time-matched only: not identifiable.
  - Location-confirmed: 19.01 h [16.76, 19.38].
  - Excluding persistent: unchanged at 18.82 h.
  - Area-normalized, all scans: 14.77 h [10.96, 16.19] (driven by unconfirmed midday
    pixels).
  - Area-normalized, confirmed only: 18.07 h [17.47, 18.76].
- *Decision.* None of these fits is usable. `params/diurnal_v2.json` stays as written
  but should not be applied. The v3_transfer_naus time adjustment and Northern Australia
  FRE inherit the artifact. Next steps, awaiting user confirmation:
  1. Fix the daytime cloud mask and the contextual test, validated against VIIRS at
     12–14 h.
  2. Fix `nearby()`.
  3. Refit on area-normalized FRP using all scans.

## Detector fix round (Northern Australia)

**D72. `himawari.nearby()` is unit-safe; affected figures rerun.** The helper now converts
times to seconds since epoch via `Timedelta` division, not `astype('int64')`. The test that
pinned the old behaviour now asserts the fix. `pipeline/naus_diagnostics.time_match` now
delegates to it. `run_nearby_fix_rerun.py` recomputed the affected figures from stored
detections (`outputs/nearby_fix_rerun.json`) and wrote corrected values back to the
derived files: the geo_fires and himawari_fires `reference_match` flags, both
`transfer_pairs.csv` files, `stage2_summary.json` and `phase3c_status.json`.

| Figure | Old | New |
|---|---|---|
| Phase 3c N. Australia commission (2,195 px, ±60 min, 2 km) | 26.5% | **78.6%** (59.1% in hours with a polar reference; 94.3% outside them) |
| Phase 3 South Asia commission | not estimable (0 AHI fires) | unchanged |
| Phase 3 tuning-alternative commission | none scored | unchanged |
| N. Australia transfer event-specific AHI ratios (167 pairs) | 5 finite, median 0.988 | identical (max change 6e-17); single-step query, \|Δt\| ≤ 30 min by construction |
| South Asia transfer event-specific AHI ratios (6,568 pairs) | 0 finite | 0 finite |
| Phase 3b positive controls; Phase 3 VIIRS detection rates | single-scan comparisons | unaffected, not rerun |

The new commission figure is mostly a timing statement: polar references exist only at
about 00–04, 07–09, 12–16 and 20–21 h local solar time. Location confirmation (73.5%) is
reported separately (D71).

**D73. Daytime detector, one improvement round (Northern Australia only) — protocol,
recorded before scoring the test days.**
- *Cloud mask source.* The NOAA bucket does have a Level-2 cloud mask
  (`AHI-L2-FLDK-Clouds`, `AHI-CMSK_v1r1`, every 10 min for 29 Oct–2 Nov). But each file
  is a 374 MB full disk, about 40 GB for 108 hourly scans, which is over the 3 GB limit.
  S3 throughput from this machine was about 12 KB/s per connection, so remote subset
  reads were impractical. The user chose the B04 fallback: 0.86 µm, S0610/S0710, daytime
  UTC hours 21–09, 124 of 130 files, 1.22 GB. `himawari_download.py` gained `--bands`,
  `--segments` and `--utc-hours`; its defaults are unchanged.
- *Change (`hw.contextual(..., day_fix=...)`; `None` = old behaviour everywhere else).*
  - Where SZA < 80°: cloud = cold B14 (< 265 K) OR B14 − B15 < −1 K OR R0.86/cos(SZA)
    above a threshold. The B14 − B15 > 5 K test is not used there. Missing B04 by day
    means "unknown", not an IR-mask fallback.
  - Daytime B07 − B14 contextual term = min(max(3σ, 6 K), cap).
  - Night rules are unchanged.
- *Tuning.* Grid: reflectance threshold {0.25, 0.30, 0.35, 0.40, 0.45} × cap
  {6, 8, 10, 12 K, none}, scored on Oct 29–30 only. Objective = M1 + M3 (defined below);
  ties go to the stricter setting.
- *Evaluation.* Oct 31 – Nov 1, scored once with the chosen setting, no further tuning.
- *Metrics* (VIIRS-pixel level, as in D71):
  - M1: share of VIIRS fire pixels at 12–14 h local solar time classed as cloud.
  - M2: daytime detection rate of clear-observed VIIRS fire pixels in FRP bins
    < 5, 5–20 and ≥ 20 MW.
  - M3: share of Himawari detections at 09–13 h never confirmed within 2 km.
- *Pre-registered success checks* (all three needed to proceed to the refit):
  - C1: M1 closes at least half the gap to its 00–02 h night level.
  - C2: the ≥ 20 MW daytime rate exceeds the < 5 MW rate AND exceeds its own before-value
    (needs n ≥ 20 in both bins; otherwise "not evaluable", which counts as not passed).
  - C3: M3 falls by at least 20 percentage points AND ends at or below 50%.
  - The fitted peak hour is not a criterion.
- *Downloader fix (during D73).* `himawari_download.verify()` only accepted 2 km
  (5,500 × 550) segments, so every 1 km B04 file (11,000 × 1,100) downloaded completely,
  failed verification three times and was discarded. The first attempt also hit S3
  connection errors.
  - Expected dimensions now come from the file's resolution code (R05/R10/R20).
  - A complete `.part` file is verified in place instead of being fetched again.
  - Checked on one B04 and one B07 file.
  - Result: 124/124 B04 files verified, 0 errors, 6 absent upstream (1.221 GB).
  - B04 alignment on the cached grid was confirmed: same 675 × 903 crop, and the cropped
    B07 equals the cached B07. Box R0.86/cos(SZA) percentiles at 03 UTC on Oct 29:
    10% 0.22, 50% 0.31, 90% 0.71.

**D74. Detector-fix round result: C3 failed; stopped, nothing applied.**
- Chosen on training days: R0.86/cos(SZA) > 0.45, no cap. That is the edge of the grid;
  the cap barely mattered (objective changed by < 0.003).
- On training days, M3 was worse than baseline for every variant (97–98% vs 95%).
- Test days (Oct 31 – Nov 1):
  - C1 pass: VIIRS fire pixels at 12–14 h classed cloud 91.8% → 6.8% (night 11.2%).
  - C2 pass: daytime detection rate ≥ 20 MW 0% → 56.0% (n = 182), above the < 5 MW
    rate of 38.0%.
  - C3 fail: never-confirmed share at 09–13 h 88.4% (n = 86) → 95.9% (n = 4,085).
- Per the approved step 4: no refit; no new diurnal, transfer or FRE file; nothing
  applied. The limitation is written in `outputs/naus_diurnal_check.md`.
- The new code stays available but inactive:
  - `himawari.contextual(day_fix=...)`;
  - `pipeline/naus_detector.py`;
  - `run_naus_detector_fix.py`;
  - the B04 cache.

## Website MVP

**D75. The website shows only exported pipeline outputs, each with its status.**
- **Pages.** The existing React/Vite frontend is extended, not replaced. The new pages
  are at `/`, `/map`, `/methodology` and `/about`. The previous live FIRMS explorer
  moved from `/` to `/globe`; all its other routes are unchanged.
- **API additions (`backend/routers/snapshot.py`; tests added):**
  - Snapshots gained `footprints` (union of each event's Step 3 detection footprints,
    simplified by 0.0005°) and `detections` (clean points).
  - `/fires/active?geometry=true` and `/events/{fire_id}` return footprints.
  - New `/detections` endpoint: clean detections in the same last-24-h active period.
  - Older snapshots without these tables return null or 503, never fabricated data.
- **Numbers.** `tools/export_site_data.py` reads reports, JSON and parameter files and
  writes `frontend/public/site-data/site.json`. Every value carries a label, a status and
  its source file; missing items export as "awaiting data". Region boxes and intensity
  thresholds come from `config/settings.yaml`. The frontend contains no typed result
  numbers.
- **Event count.** The headline uses the current Phase 1 report: 618,185 raw rows →
  545,537 clean detections → 138,576 events. The 138,518 figure is the superseded batch
  run (scalability report).
- **Colour.** Intensity uses a 4-step single-hue orange ordinal ramp
  (#ee9157 / #d9592a / #a33d14 / #5e1e06), checked with the dataviz palette validator
  (`--ordinal`, light surface). Every colour has a text label. Charts use categorical
  slots 1–2 (blue/orange) with legends, direct labels, tooltips and table views.
- **Basemap.** OpenFreeMap "positron" (no key). CARTO raster tiles now require an API key.
- **Bangla.** Fire descriptions come from `pipeline/translate.py`. Interface strings are
  a first draft that needs native review.

**D76. Website rebuilt inside the existing frontend (supersedes the separate site in D75).**
- *What changed.* The user asked for the work to fit their project rather than replace
  it. The separate light-themed site was removed:
  - `frontend/src/site/` deleted;
  - `main.tsx`, `vite.config.ts` and `package.json` restored from git;
  - the `maplibre-gl` dependency dropped;
  - Home is back at `/`.
- *How it fits now.* It uses the project's own patterns:
  - **Home:** a `HarmonizedRecordSection` built from `oc-section` and
    `oc-dashboard-panel`.
  - **New pages** in `src/pages/` (`HarmonizedMapPage` at `/fire-events`,
    `MethodologyPage`, `AboutPage`), using the `content-page space-shell space-page`
    layout with hero strip, eyebrow pill, glass cards and method cards.
  - **Map:** react-leaflet with the Esri imagery already used on Fire DNA.
  - **Charts:** Plotly, as on Home.
  - **Data access** in `src/api/harmonized.ts`; the language switch in
    `src/context/LanguageContext.tsx` and the header nav.
  - Changes to existing files are additive only: `main.tsx` (+22 lines),
    `HomePage.tsx` (+6), `vite.config.ts` (+5).
- *Colours* were re-validated for the dark surface `#05080f`:
  - intensity ordinal ramp `#8f3a14`/`#d4561f`/`#ff8a4c`/`#ffc78a` (brighter = more
    power);
  - chart pair `#3987e5`/`#d95926`. The theme's own cyan and amber are too light for the
    dark-mode lightness band.
- *Unchanged:* the backend API additions and `tools/export_site_data.py` (D75).

**D77. Fire Events opens from Search; FireNow stays the main map.**
- *User feedback.* Fire Events should not replace FireNow in navigation, it should open
  after searching a place, and the low-zoom dots were meaningless.
- *Navigation.*
  - The "Fire Events" header link was removed; the nav is FireNow · Search · Methodology ·
    About · বাংলা.
  - The Home section's first card now links to FireNow.
  - Fire Events is destination "04" on the Search page, next to Fire Memory, Fire DNA and
    Burning Calendar. The destination grid has 4 columns.
- *Fire Events page.*
  - It uses the searched place (AppContext AOI). Without one, it shows a prompt that links
    to Search.
  - It draws the place's dashed outline and every event of the window whose centroid is
    inside the place. The new `/fires` endpoint returns all window events in a box, with
    footprints; tested.
  - Each event is its true footprint. Below zoom 11 the outline gets a thick border in its
    intensity colour so it stays visible; it is still the event's own shape, never a
    substitute dot.
  - A named list (intensity word, time, satellites, peak FRP) sorted strongest first. A
    row click zooms to the footprint and opens the detail panel. Hover tooltips name every
    shape.
  - The raw-detection point mode was removed.

**D78. Area Fire Intelligence hub (Search → "<Place> Fire Intelligence").**
- *Choices.* The user chose a hub page with deep-dive links, and an area climatology with
  validation for Future risk.
- *Entry point.* Choosing a place on Search shows an "Open <Place> Fire Intelligence"
  card. The existing four cards stay below it as "explore in depth". The hub is at `/area`.
- *Data.*
  - It runs the existing Fire Memory analysis for the place: 10 years by default, 20
    optional, same sensors, 30-day comparison. It's disk-cached and shared with the Fire
    Memory page.
  - Live FIRMS hotspots for the last 5 days in a box one place-width wider on every side.
- *Four tiles,* as in the concept:
  - fire history (full years with detections);
  - current activity (live hotspots inside the place, last 5 days);
  - seasonal patterns (peak months);
  - future risk (climatological probability, or "withheld").
- *Eight questions,* each with its source and status:
  1. Repeated activity: fire years out of full years, critical periods.
  2. Where: a hotspot-recurrence map (`hotspot_map`: detection days per cell, confidence
     ≥ 30%), with the top 5 cells.
  3. Neighbours: live hotspot density inside vs the surrounding ring, per 1,000 km².
  4. Seasons: Fire Memory seasonal profile and its peak months.
  5. Long-term change: yearly harmonized activity and PELT change points.
  6. Unusual now: robust z-score and percentile against the same dates in earlier years.
  7. Reliability: observation quality, calibration note, honesty notes.
  8. Model estimate (`area_risk`): P(at least one consistent-record fire in the next
     28 days) = (k + m·p0)/(n + m) with m = 2, from the same calendar window in past
     years, shrunk toward the all-year base rate. Validated leave-one-year-out over
     non-overlapping 28-day windows; the Brier Skill Score against the constant base rate
     is shown. Withheld with fewer than 5 complete years. Labelled "climatological
     baseline", not a weather-driven forecast.
- *Tests.* `backend/area_intel.py` is tested in `tests/test_area_intel.py`: recurrence
  counting, the short-history withholding, positive skill on a seasonal record, and no
  skill on a random one. Fire Memory's `RESULT_CACHE_VERSION` went from 2 to 3, so saved
  analyses recompute with the new fields.

**D79. Fire Intelligence loading made fast and visible.**
- *Measured causes.*
  - A 10-year, 4-satellite record needs about 2,300 NASA FIRMS requests: FIRMS rejects
    ranges over 5 days ("Expects [1..5]").
  - NASA answered in 5–32 s per request at busy times.
  - Concurrent analyses spent the shared 5,000-requests-per-10-minutes quota and then
    waited.
  - Results with quota-failed chunks were never saved, so they were recomputed on every
    visit.
- *Backend fixes.*
  - Request chunks sit on a fixed 5-day calendar grid, so overlapping periods reuse cached
    downloads.
  - Identical chunk requests in flight share one NASA call.
  - The download box snaps to 0.5°, so nearby and repeat searches reuse the cache; rows are
    still filtered to the exact area.
  - A place's live hotspots are cut from the shared worldwide 24-hour download when it is
    fresh, with no NASA call. A background task refreshes that download every 12 minutes.
  - Identical jobs were already de-duplicated.
  - Tests: chunk alignment and reuse, in-flight sharing, the snap, and the world-cache cut.
- *Frontend fixes.*
  - The hub loads in three visible steps: live hotspots → 12-month quick look → full
    history. Each answer appears when its data is ready.
  - It uses MODIS + Suomi-NPP only (NOAA-20/21 add requests without changing the long-term
    record).
  - The default history is 5 years (about 730 requests, within one quota window), with
    10 and 20 years as choices.
  - NASA's quota pause is explained on the page.
  - Future risk asks for 10 years when 5 complete years aren't available.
  - Areas with almost no fire read as plain statements instead of empty charts or
    degenerate legends.
- *Measured on the Sundarbans run.*
  - First visit, with NASA throttling: live 18 s, quick look 20 s, 5-year history 440 s
    (now saved with 0 failed chunks).
  - Repeat visits load from disk.
- *Remaining limit.* One FIRMS map key (5,000 requests per 10 minutes) is shared by FireNow,
  Fire Memory and the hub. Heavy use can still queue the first build of a new place's
  history.
