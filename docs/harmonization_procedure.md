# FlameSeek Harmonization Procedure

Nov 2, 2026 · @Zamila

> Transcribed from `FlameSeek Harmonization Procedure.pdf` (repository root), which is the
> source of truth. If the two ever disagree, the PDF wins.

## Overview

This procedure turns raw MODIS, VIIRS and Himawari fire detections into one consistent record of
true fire activity, with uncertainty on every value. It is the method behind FlameSeek's Burning
Activity Calendar and fire outlook.

**Core idea (Latent Fire Field).** Satellites are not converted into one another. Each satellite is
treated as an imperfect observer of one true fire activity λ(c, t) in grid cell c on day t. Each
observer has its own revisit pattern, detection sensitivity and measurement error. The procedure
estimates λ(c, t) from all observers together.

**Principles that every step follows**

- A detection is a pixel footprint, not a point.
- Fire Radiative Power (FRP, MW) is instantaneous power: it is summed within one overpass, never across time.
- No detection is not the same as no fire. A cell with no observation opportunity has unknown activity, not zero.
- Sensors are compared only when they observe at nearly the same time.
- Every output carries an uncertainty, a confidence label and its provenance.

**Pipeline at a glance**

1. Clean and standardize all detections.
2. Remove weak and false detections.
3. Convert each detection into its scan × track footprint.
4. Group footprints into fire events.
5. Aggregate events to a common equal-area grid.
6. Calibrate sensors against each other and model detection sensitivity.
7. Correct for time of day using Himawari diurnal curves.
8. Estimate true fire activity λ with Monte Carlo uncertainty.
9. Build the burning calendar and flag anomalies.
10. Validate every stage.

## Inputs

| Sensor | Platforms | Pixel at nadir | Record starts | Source |
|---|---|---|---|---|
| MODIS C6.1 | Terra, Aqua | 1 km | Nov 2000 | NASA FIRMS |
| VIIRS 375 m | S-NPP, NOAA-20, NOAA-21 | 375 m | Jan 2012 (S-NPP) | NASA FIRMS |
| Himawari AHI | Himawari-8, Himawari-9 | 2 km, every 10 min | Jul 2015 | NOAA open data on AWS (L1b); FIRMS geostationary layer; JAXA P-Tree |

Supporting data: MCD12Q1 land cover (biome per cell per year), MCD64A1 burned area (validation),
CelesTrak TLEs (overpass times), GADM boundaries.

**FIRMS column formats**

| Field | VIIRS file | MODIS file |
|---|---|---|
| Fire brightness | bright_ti4 (3.7 µm, K) | brightness (4 µm, K) |
| Background brightness | bright_ti5 (11 µm, K) | bright_t31 (11 µm, K) |
| Confidence | l / n / h | 0–100 |
| satellite codes | N = S-NPP, N20 = NOAA-20, N21 = NOAA-21 | Terra / Aqua (or T / A) |
| instrument | VIIRS | MODIS |
| Shared fields | latitude, longitude, scan, track, acq_date, acq_time (HHMM, UTC), frp (MW), daynight, version | same |

Use the instrument column, not the file name, to decide the sensor. Near-real-time files (version
ending NRT) have no type column.

## Step 1: Clean and standardize

The output of this step is one table where every row is a detection described in the same units,
whatever sensor produced it.

1. **Merge** all files into one table. Never edit the original files.
2. **Label** each row with sensor (MODIS or VIIRS) and platform (Terra, Aqua, S-NPP, NOAA-20, NOAA-21).
3. **Unify brightness:** bt_k = bright_ti4 (VIIRS) or brightness (MODIS); bt_bg_k = bright_ti5 or bright_t31.
4. **Build time:** acq_datetime_utc from acq_date and acq_time (HHMM).
5. **Compute local solar time** from the actual timestamp, never from nominal overpass times. This removes the effect of Terra and Aqua orbit drift.
6. **Unify confidence** into one probability scale.

    lst = (h_UTC + longitude / 15) mod 24

| Class | MODIS (0–100) | VIIRS | p_conf |
|---|---|---|---|
| Low | below 30 | l | 0.3 |
| Nominal | 30–79 | n | 0.6 |
| High | 80 and above | h | 0.9 |

Keep the version column so data quality stays traceable (NRT vs standard processing).

## Step 2: Quality control and false-positive filtering

Keep nominal and high confidence detections for harmonization; flag suspicious ones rather than
deleting them.

1. **Confidence filter:** keep p_conf of 0.6 or 0.9. Store low-confidence rows in a separate table. Do not use a single 80% threshold: VIIRS has no percentage, and a high threshold removes small agricultural fires.
2. **Source type (archive data only):** drop MODIS type 1, 2 and 3 (volcano, static land source, offshore).
3. **Persistent hotspot mask:** a cell hot in more than 30% of years is a static source such as a factory, brick kiln or gas flare. Mask it.
4. **Known flares:** optionally mask VIIRS Nightfire gas-flare locations.
5. **Transient filter:** where Himawari covers the area, a detection with no Himawari signal within ±30 minutes and no persistence across consecutive frames is flagged transient_suspect (sun glint, hot roofs).
6. **Sanity checks:** flag missing times, negative FRP and coordinates outside the study area.

Every removed or flagged row keeps a reason code, so the filtering can be audited.

## Step 3: Pixel footprints

Each detection becomes a rectangle of its real pixel size, because FIRMS coordinates are pixel
centres, not fire locations.

    A_i = scan_i × track_i   (km²)

1. Build the rectangle in a local azimuthal-equidistant projection centred on the detection: scan_km wide (across-track) and track_km long (along-track).
2. Convert it back to WGS84 and store footprint_area_km2.
3. Do not use fixed 1 km or 375 m squares. Pixel size grows towards the swath edge, and scan and track already record that growth.

| Sensor | Pixel at nadir | Approximate pixel at swath edge |
|---|---|---|
| MODIS | 1 × 1 km | about 4.8 × 2 km |
| VIIRS I-band | 0.375 × 0.375 km | about 0.8 × 0.8 km |

Check: report the footprint area range per sensor. Values outside these ranges signal a parsing error.

## Step 4: Fire events

Overlapping footprints become one fire event, so a fire counts once whether one MODIS pixel or six
VIIRS pixels saw it.

**Projection.** Distances in UTM (UTM 46N, EPSG:32646, for Bangladesh); areas in an equal-area projection (EPSG:6933).

**A. Daily clustering.** Within one day, two detections belong together when their footprints
overlap, or when their centroids are closer than the sum of their half-diagonals:

    d_ij ≤ ½·sqrt(scan_i² + track_i²) + ½·sqrt(scan_j² + track_j²)

Build a graph of these links and take connected components. A fixed 500 m limit is not used: a
MODIS centroid can sit about 700 m from the fire at nadir and more than 2 km at the swath edge.

**B. Multi-day linking.** Link daily clusters on consecutive days when their footprints overlap.

**C. Anti-chaining caps.** In dense burning areas, field-to-field links can merge a whole district
into one event. Split any event larger than 25 km or longer than 14 days, and report how many were split.

**D. FRP rules.**

1. Sum FRP only within one overpass (same platform, same acquisition time). This gives the fire's total power at that moment.
2. Across overpasses take the maximum or mean. Never sum FRP across time.
3. Energy over time is FRE (MJ), computed in Step 7.

**E. Confidence fusion** across all detections of the event:

    p_fused = 1 − Π_k (1 − p_k)

**Event table fields:** fire_id, start_time, end_time, n_days, n_MODIS, n_VIIRS, n_overpasses,
platforms_seen, sensor_flag (MODIS_only, VIIRS_only, both), p_conf_fused, centroid,
footprint_area_km2 (union of footprints, not burned area), FRP_MODIS_max, FRP_VIIRS_max, biome.

## Step 5: Common grid

Events are spread over grid cells in proportion to how much of each footprint falls in each cell,
so energy is conserved.

**Grid choice.** 0.1° for the calendar and forecast; 1 km for local detail. A degree grid is not
equal-area, so store each cell's true area in km².

**Overlap weight** of footprint i in cell c:

    w_ic = Area(F_i ∩ C_c) / Area(F_i),   Σ_c w_ic = 1

| Quantity | Type | Rule |
|---|---|---|
| FRP (MW) | Extensive, additive | FRP_c = Σ w_ic · FRP_i, per overpass |
| Brightness (K) | Intensive | Weighted maximum |
| Event count | Count | Events whose footprint overlaps the cell, weighted by overlap share |
| FRP density (MW/km²) | Normalized | FRP_i / A_i, for fair sensor comparison |

Assign by overlap, never by centroid: a 4.8 km MODIS edge pixel must not land in a single 1 km cell.

**Energy conservation test.** Total FRP before and after gridding must be equal. Print both values on every run.

## Step 6: Sensor calibration

This step measures how MODIS and VIIRS differ, using only fires both saw at almost the same time.

**A. Observation opportunities O_s(c, t).** From CelesTrak TLEs (skyfield), compute every overpass
of each platform over each cell, with its scan angle and expected pixel area. A cell is observed
when it lies inside the swath (MODIS about 2,330 km, VIIRS about 3,060 km). Version 1 assumes clear
sky; record that as a limitation. Long-term trends are anchored to one reference platform per era:
Aqua for MODIS, S-NPP for VIIRS.

**B. Matched pairs.** Pair Aqua MODIS with S-NPP or NOAA-20 VIIRS observations of the same event
within 30 minutes. Never pair Terra with VIIRS: their overpasses are about 3 hours apart. Compare
at event level, never pixel level.

**C. FRP calibration.** Fit per biome in log space with Deming (orthogonal) regression, because
both sensors have measurement error. Bootstrap the coefficients.

    log FRP_VIIRS = a + b · log FRP_MODIS

**D. Detection probability curve.** For every VIIRS-detected event in a matched overpass, record
whether MODIS also detected it. Fit a logistic curve against fire power F (from VIIRS) and MODIS
pixel area A:

    P_det^MODIS(F, A) = 1 / (1 + exp(−(β0 + β1·log F − β2·log A)))

Report the FRP at which MODIS detects 50% of fires, at nadir and at the swath edge.

**E. FRP distribution and tail correction.** Fit a power law to VIIRS event FRP above F_min (F_min
chosen by the Clauset method), and compare it with a lognormal by likelihood ratio:

    α̂ = 1 + n · [Σ_i ln(F_i / F_min)]^(−1)

The share of fires a sensor can see is then:

    π_s = ∫ P_det^s(F, A) · f(F) dF

This is what reconstructs the small fires MODIS missed before 2012.

## Step 7: Temporal harmonization

Polar satellites see each place only a few times a day, so each overpass is scaled to a full day
of burning using the diurnal shape measured by Himawari.

**A. Himawari fire detection.** From L1b imagery, use bands B07 (3.9 µm) and B14 (11.2 µm). A pixel
is fire when B07 is anomalously hot against its background window and B07 − B14 exceeds the
background mean plus k standard deviations; exclude cloud and water. Cross-check against the FIRMS
geostationary layer or JAXA's Wild Fire product. Optional upgrade: a random forest trained with
VIIRS detections as labels.

**B. Diurnal shape** per biome, region and month, in local solar time t:

    FRP(t) = FRP_base + FRP_peak · exp(−(t − h)² / (2σ²))

Himawari sets the shape only, not the amount: its 2 km pixels miss small fires.

**C. Coverage tiers** (stored as diurnal_source). Himawari is valid where the view zenith angle is
below 65° from its position near 140.7°E.

| Tier | Where | Shape source | Uncertainty |
|---|---|---|---|
| A | Inside Himawari coverage, 2015 onward | Fitted from Himawari | Lowest |
| B | Outside coverage, or before 2015 | Transferred from a Tier A area with the same biome, latitude band and month | Medium |
| C | No matching Tier A area | Coarse curve from polar overpasses only | Highest |

Test the transfer assumption by comparing shapes from early and late years.

**D. Daily energy.** Convert each polar overpass at local solar time t_obs into daily Fire Radiative
Energy, then combine the day's overpasses with inverse-variance weights:

    FRE_daily = FRP_obs / shape(t_obs) · ∫_0^24 shape(t) dt

**E. Triple collocation (advanced).** Where Aqua, VIIRS and Himawari observe within 15 minutes,
estimate each sensor's error variance without ground truth, in log-FRP space:

    σ²_ε,x = Var(x) − Cov(x,y)·Cov(x,z) / Cov(y,z)

These variances weight each sensor when FRP is combined. Himawari also acts as a transfer standard
linking Terra (about 10:30) to VIIRS (about 13:30). The method assumes independent errors; state it.

## Step 8: Latent Fire Field estimate

All sensors are combined into one estimate of true fire activity per cell and day, with a 90% interval.

**Observation model.** Sensor s counts N_s fires in cell c on day t, depending on true activity λ,
how often it looked (O_s) and how sensitive it is (π_s):

    N_s(c,t) ~ Poisson(λ(c,t) · O_s(c,t) · π_s(c,t))

**Estimate.** The maximum-likelihood estimate combining all sensors:

    λ̂(c,t) = Σ_s N_s(c,t) / Σ_s O_s(c,t) · π_s(c,t)

If the denominator is zero, the cell was not observed: λ̂ is null, never 0.

| Problem | How the estimate handles it |
|---|---|
| VIIRS sees more small fires | Higher π for VIIRS in the denominator |
| MODIS-only years (2000–2011) | Only MODIS terms present; λ stays on the same scale |
| New satellites (NOAA-20, NOAA-21) | More overpasses enter O, so counts do not inflate |
| Clouds and gaps | Fewer observation opportunities lower O instead of implying no fire |
| Swath-edge pixels | Larger pixel area lowers π |

**Monte Carlo uncertainty.** Repeat the whole estimate 300 times, each time drawing the
detection-curve parameters (β), the distribution exponent (α), the Deming coefficients and the
diurnal parameters from their fitted uncertainty. The 5th and 95th percentiles give lambda_lo90
and lambda_hi90.

**Output per cell-day and cell-week:** lambda_hat, lambda_lo90, lambda_hi90, fre_harm,
n_obs_opportunities, reference_sensor, era (MODIS_only or multi_sensor), diurnal_source.

## Step 9: Burning calendar and anomalies

The harmonized λ̂ is arranged by week and year, and unusual weeks are flagged with a count model
rather than plain z-scores.

**Calendar.** A matrix of cell (or user-drawn area) × week of year (1–52) × year, holding λ̂, FRE
and the anomaly score, plus an era flag marking reconstructed MODIS-only values.

**Season onset.** The first week each year in which cumulative activity passes 20% of that cell's
seasonal total. Track its trend over years to see whether seasons start earlier.

**Anomalies (negative binomial).** Fire counts are skewed and full of zeros, so mean and standard
deviation mislead.

1. Baseline per cell and week: pool a ±2-week window across all other years (about 120 values), leaving the evaluated year out.
2. Fit mean μ and dispersion k by method of moments; if the variance does not exceed μ, use the Poisson limit.
3. Compute the upper-tail probability of the observed count x and convert it to an equivalent z-score.
4. Flag an anomaly when z_equiv is at least 2.0 and the week has at least 3 harmonized events.

    Var(X) = μ + μ²/k,   z_equiv = Φ⁻¹(1 − P(X ≥ x))

## Validation

Each test answers one question a reviewer will ask; a test that needs data not yet available is
reported as pending, never filled with a placeholder.

| Test | Question it answers | Pass condition | Data needed |
|---|---|---|---|
| Energy conservation | Does gridding lose or create energy? | Total FRP equal before and after | Any |
| Footprint ranges | Were scan and track read correctly? | Areas within sensor ranges | Any |
| Detection curve fit | How sensitive is MODIS? | Curve with confidence bands; 50% FRP reported | Matched Aqua–VIIRS pairs |
| Distribution fit | Power law or lognormal? | Likelihood-ratio result per biome | VIIRS FRP |
| Calibration hold-out | Do coefficients generalize? | Low error on later years | Multi-year overlap |
| Synthetic degradation | Can MODIS alone reconstruct the VIIRS era? | Small bias and RMSE per biome | Multi-year overlap |
| Changepoint (Pettitt) | Is the 2012 jump removed? | Break in raw series, none in harmonized | 2001 onward |
| Burned-area check | Does activity match burned area? | Positive correlation with MCD64A1 per cell-month | MCD64A1 |
| Himawari agreement | Is own fire detection reliable? | Agreement with FIRMS geostationary or JAXA | Himawari + reference |

With 5 days of data, the first four tests can run. The rest are planned for the multi-year dataset.

## Outputs

The procedure produces four tables; each carries data_version and processing date.

| Table | One row per | Key fields |
|---|---|---|
| detections_clean | Detection | sensor, platform, acq_datetime_utc, lst, bt_k, bt_bg_k, p_conf, frp, scan, track, footprint_area_km2, flags, version |
| fire_events | Fire event | fire_id, start_time, end_time, n_MODIS, n_VIIRS, n_overpasses, sensor_flag, p_conf_fused, centroid, footprint_area_km2, FRP_MODIS_max, FRP_VIIRS_max, FRE_estimate, biome, cause_label |
| grid_daily | Cell and day | cell_id, date, lambda_hat, lambda_lo90, lambda_hi90, fre_harm, n_obs_opportunities, reference_sensor, era, diurnal_source |
| calendar | Cell, week and year | cell_id, year, week, lambda_hat, fre_harm, z_equiv, tail_prob, anomaly_flag, onset_week |

**Field notes**

- sensor_flag: MODIS_only, VIIRS_only or both.
- era: MODIS_only marks reconstructed values (before 2012).
- diurnal_source: A, B or C (Step 7).
- footprint_area_km2 is detected pixel area, not burned area.

## Rules, limitations and defaults

**Rules that are never broken**

1. Never sum FRP across time.
2. Never calibrate Terra directly against VIIRS.
3. Never treat a cell with no observation opportunity as zero fire.
4. Never modify raw files.
5. Never report a value without its uncertainty or confidence label.

**Known limitations**

- Himawari covers East and Southeast Asia and Oceania only; elsewhere diurnal shapes are transferred (Tier B or C).
- Bangladesh lies about 50° of longitude from Himawari, so its pixels there are larger than 2 km.
- Version 1 assumes clear sky when counting observation opportunities.
- Pre-2015 diurnal shapes assume burning habits have not changed.
- Near-real-time FIRMS files lack the type field and are lower quality than standard processing.

**Parameter defaults** (all set in config and reported with results)

| Parameter | Default |
|---|---|
| Confidence kept | Nominal and high (p_conf 0.6, 0.9) |
| Persistent hotspot threshold | Hot in more than 30% of years |
| Transient filter window | ±30 minutes |
| Event caps | 25 km extent, 14 days |
| Matched-pair window | 30 minutes (Aqua with S-NPP or NOAA-20) |
| Calendar grid | 0.1°, true cell area stored |
| Himawari valid view zenith angle | Below 65° |
| Monte Carlo draws | 300 |
| Anomaly baseline window | ±2 weeks, evaluated year excluded |
| Anomaly flag | z_equiv at least 2.0 and at least 3 events |
| Season onset | 20% of seasonal total |
