# FlameSeek staged continuation — final report

Processing date: 2026-11-02. Every number below is read from the files listed under
*Sources*. Nothing in this report is estimated outside those runs. Decisions D61–D70 in
`docs/decisions.md` record the reasoning. D68–D70 cover this update: the new
synchronization gate, the 2016 opportunities and the 2016 results.

## Status at a glance

| Stage | Result | Main limit |
|---|---|---|
| 1. Downloads | Done: 4 FIRMS country files (60.9 MB, 24,928 in-window rows) and 648 Himawari S06/S07 files (1.797 GB) were downloaded. Both test boxes have 100% coverage. | 72 Himawari files for the last day are missing upstream. **Meteosat: awaiting data.** The user must download it from LSA SAF (ListProduct + QualityProduct). |
| 2. Analyses | Done: 2016 window processed and Northern Australia fitted. Near-nadir detection limit estimated. | — |
| 5. Sync gate (new) | **2016 passes** the new gate; **v2 calibration fitted** (n = 534). 2026 fails, as expected. | 2014 window: awaiting data. |
| 5. 2016 opportunities | The 2016 detection curve, λ and degradation test now run on **detection-conditioned opportunities – lower bound on O_s**. | No archived 2016 TLEs yet, so λ is biased high. |
| 3. Latent λ | 2026 is provisional. 2016 is provisional on the lower-bound basis. | 2016 and 2026 means are not comparable. |
| 4. History, translation, API | Done; the API now serves the labelled 2016 λ. | Real history is too short (5 days). |

## Stage 1 — Data

- FIRMS 2016 (India, Bangladesh; MODIS + VIIRS S-NPP): 24,928 in-window rows, of which
  3,515 are Aqua, 188 Terra and 21,225 S-NPP. Bangladesh has no MODIS rows in this window.
- Himawari S06/S07: 648 files, 0 download errors, 72 missing upstream (partial final day).
  Northern Australia [125, −20, 138, −11] and near-nadir [138, −5, 145, −1] boxes:
  10,201 / 10,201 test points covered in each.

## Stage 2 — Analyses

**Detection limit from synthetic injection (Himawari)**

| Context | F50 (MW) | Tested transition bracket (MW) |
|---|---|---|
| Bangladesh VZA (6 scans) | 71.9 | 45.5 – 113.6 |
| Near-nadir | 13.4 | 9.5 – 18.9 |

These are descriptive interpolations, not logistic fits.

**Drift between 2016 and 2026.** Median daytime local solar time (|latitude| ≤ 30°):
Aqua 13.46 h → 15.80 h; S-NPP 13.30 h → 13.71 h. Aqua has drifted; S-NPP has not.

**Northern Australia (method demonstration region only)**

- 108 scans, 2,195 Himawari fire pixels. VIIRS detection rate 8.0%; unmatched
  commission 78.6% after the D72 matcher fix (was reported as 26.5%; 59.1% counting
  only hours when a polar satellite passes).
- Provisional diurnal peak 18.82 h local solar time (90% day-bootstrap interval
  16.67–19.43 h). Status: "provisional – 4 days".
- Transfer-standard calibration v3_transfer_naus: n = 136, a = −0.146
  [−1.138, 0.479], b = 1.161 [0.798, 1.717]. OLS bounds on b are 0.373–2.982.
- FRE estimated for 1,165 events.
- This curve is **not** applied to South Asia.
- **Under review (D71):** the 18.82 h peak is a detection artifact. The daytime cloud mask and contextual test hide afternoon fires, and the fit had no 08–15 h data. Do not use this curve, or the v3_transfer_naus time adjustment and FRE built on it, until the detector is fixed. See `outputs/naus_diurnal_check.md`.

## Stage 5 — Synchronization gate and 2016 opportunities

### New gate (D68)

The old rule (median |Aqua − S-NPP Δt| ≤ 20 min over all shared events) mostly measured
orbit phasing, not drift. It has been replaced by a rule with two parts, which must both
hold. The same thresholds apply to every window and were not tuned.

- **(a) No drift:** median daytime Aqua local solar time within 30 min of 13:30.
- **(b) Enough sample:** at least 100 Aqua–S-NPP event-overpass pairs with
  |Δt| ≤ 15 min after the truncation filter (both FRP ≥ 10 MW).

| Window | (a) Aqua LST | (a) | (b) pairs | (b) | Gate | Old rule (for the record) |
|---|---|---|---:|---|---|---|
| sync_2016 | 13.475 h (−1.5 min) | pass | 534 | pass | **pass** | 21 min → fail |
| current_2026 | 15.755 h (+135.3 min) | **fail** | 17 | fail | **fail** | 136 min → fail |
| sync_2014 | — | — | — | — | **awaiting data** | — |

### Calibration v2 sync 2016

Status: **"validated – synchronized window"**. It was fitted exactly as specified
before: pairs with |Δt| ≤ 15 min, truncation filter at 10 MW, Deming with stated
error ratio 1, OLS/ODR bounds and a 1,000-sample bootstrap.

- n = 534 (of 1,366 pairs at any Δt within 60 min).
- a = −0.107 [−0.280, 0.065]; b = 1.082 [0.967, 1.200] (90% bootstrap).
- Slope bounds from OLS(y|x) and inverse OLS(x|y): 0.478–2.250. ODR gives a = −0.107,
  b = 1.082.

**2014 vs 2016 comparison: awaiting data.** `data/raw/archive/2014/` has no FIRMS
files. When they arrive, `run_sync_gate.py` will run Phases 1–2 and the gate on the
`sync_2014` window. If both windows pass, it checks whether their coefficient intervals
overlap.

### 2016 observation opportunities (D69)

There are no archived 2016 TLEs (`data/raw/tle/2016/` is absent). Instead, opportunities
are rebuilt from the 2016 detections themselves: pass times, pixel sizes (giving
cross-track distance), and a nominal sun-synchronous ground track. A cell counts only
where the detections prove it was inside the swath.

- **Label: "detection-conditioned opportunities – lower bound on O_s".**
- 2016 output: 31 passes kept, 5 dropped as inconsistent. Cell-overpasses: S-NPP
  117,154; Aqua 52,329; Terra 46,967.
- **Bias direction:** passes with no detections, and swath parts the detections don't
  prove, are missing. O_s is therefore **undercounted**, and λ = count / opportunities is
  **biased high**. In the detection-curve sample, Aqua passes with no detections at all
  are missing.
- **Check against real orbits (2026 South Asia, TLE-based Step 6A):** precision 100%
  (Aqua), 99.8% (Terra), 94.9% (S-NPP). Recovered share of true O_s: 37%, 36%, 41%.
  Median time error under 1 min. So in 2026 the fallback finds about 40% of the true
  opportunities, and the ones it finds are accurate. The share for 2016, which has fewer
  detections, is unknown and probably lower.

### 2016 MODIS detection curve (v3 sync 2016)

Status: **"synchronized window; detection-conditioned opportunities – lower bound on
O_s"**.

- n = 10,081 VIIRS event-overpasses under an Aqua pass; Aqua detected 1,361.
- Pixel areas 1.00–9.28 km² (median 1.66). **Near-nadir pixels included:** 4,057 cases
  at ≤ 1.5 km², 859 of them detected.
- F50 at nadir: **17.3 MW [16.1, 18.6]**. For context, the drift-affected 2026 v1 curve
  gives 38.1 MW.
- F50 at the 9.6 km² swath edge: 1,176 MW [904, 1,527]. This slightly extrapolates past
  the largest sampled area.
- Pseudo-R² 0.24.
- Empirical π_MODIS at nadir: 0.287 (all, n = 13,395); 0.294 (IGP, n = 12,679).

## Calibration versions

| Version | n | a [90%] | b [90%] | Status | Use for |
|---|---|---|---|---|---|
| v1 | 396 | −0.824 [−1.143, −0.550] | 1.320 [1.162, 1.500] | drift-affected; provisional | Current 2026 South Asia (only fit available); diagnostic benchmark |
| **v2 sync 2016** | **534** | **−0.107 [−0.280, 0.065]** | **1.082 [0.967, 1.200]** | **validated – synchronized window** | **Synchronized / pre-drift era, India + Bangladesh** |
| v2 sync 2014 | — | — | — | awaiting data | Second synchronized window, for a consistency check |
| v3 transfer N. Australia | 136 | −0.146 [−1.138, 0.479] | 1.161 [0.798, 1.717] | provisional – transfer standard | Northern Australia only |
| v3 transfer South Asia | 0 | — | — | awaiting Meteosat | South Asia, after regional Meteosat validation |

Which version to use:
- **Synchronized / pre-drift era, India + Bangladesh:** v2 sync 2016.
- **Drifted 2026, Northern Australia:** v3 N. Australia.
- **Drifted 2026, South Asia:** awaiting Meteosat; v1 remains the only fit.

No active parameter was switched.

## Stage 3 — Latent fire rate λ

- **2026:** 81,220 cell-days, all estimated (provisional), 300 draws, mean λ = 0.0103.
  Basis: TLE-propagated opportunities and the v1 sensitivity curve. Reference
  population: fires observable by VIIRS (S-NPP reference). Platforms: Aqua, S-NPP,
  NOAA-20, NOAA-21. Terra is excluded because it has no independent response model.
- **2016:** 76,099 of 81,220 cell-days estimated, 300 draws, mean λ = 0.305.
  - Label: "detection-conditioned opportunities – lower bound on O_s"; **biased high**.
  - The 5,121 cell-days with no proven opportunity stay null.
  - Not comparable with the 2026 mean: fallback opportunities exist only near
    detected fires, so the estimated cells lean toward fire areas.
- **Degradation test (2016):** mean(λ_MODIS-only − λ_all-sensor) = −0.108 over 51,544
  cell-days, so **MODIS-only λ is 24.4% low**.
  - Same lower-bound label: both estimates use the fallback opportunities.
  - In the 2026 check, Aqua's recovered share (37%) was below S-NPP's (41%). If 2016
    behaves the same, the true MODIS-only shortfall is somewhat larger.
- FRE in South Asia: awaiting a supported regional diurnal shape.

## Stage 4 — History, translation and API

- History check on a 15-year simulation (existing modules): 5 of 5 planted anomalies
  recovered, 2019 step change detected (p = 0.011), 96.7% of peak weeks within one week,
  Brier Skill Score 0.286. The real 5-day record correctly returns `insufficient_history`.
- Translation layer (`pipeline/translate.py`): English and Bengali display words with
  configurable thresholds. Risk shows "Awaiting data" until a calibrated probability exists.
  The trend describes observed power, not fire-front movement. Three honesty notes are
  always attached.
- Snapshot API (`backend/routers/snapshot.py`): `/meta`, `/fires/active`,
  `/events/{fire_id}` and `/grid/lambda`. It reads read-only SQLite snapshots of
  2026 (138,576 events) and 2016 (12,289 events). "now" is the window end, not the wall
  clock. Every response, including errors, carries `data_version` and
  `last_observation_time`.
- The snapshots were rebuilt after this update. 2016 λ rows now carry the lower-bound
  label in `status` and `limitation`.
- D67: each window carries its own data-version label.

## What remains awaiting data

1. **Archived 2016 TLEs.** Run `tools/fetch_spacetrack_tle.py --start 2016-10-26 --end
   2016-11-06` with `SPACETRACK_USER` and `SPACETRACK_PASSWORD` set, then rerun
   `run_sync_gate.py`. TLE-based opportunities replace the lower bound, which unbiases
   the 2016 λ and the degradation test. The detection curve can then become "validated –
   synchronized window".
2. **FIRMS 2014 files** (India + Bangladesh, MODIS + VIIRS S-NPP, 2014-10-29 to
   2014-11-02) in `data/raw/archive/2014/`. This gives a second synchronized window and the
   2014 vs 2016 interval-overlap check.
3. **Meteosat LSA SAF FRP-PIXEL** (ListProduct + QualityProduct) for South Asia. This
   gives the South Asia diurnal shape, v3 South Asia calibration and FRE.

## Sources

`outputs/stages/stage1_summary.json`, `stage2_summary.json`, `stage2_sync.json`,
`stage4_history.json`, `stage4_snapshots.json`, `stage5_sync_gate.json`,
`fallback_opportunity_validation_2026.json`; `outputs/latent_summary.json`;
`outputs/windows/sync_2016/latent_summary.json`, `pi_modis_empirical.json`;
`params/calibration_v2_sync2016.json`, `params/detection_curve_v3_sync2016.json`;
`outputs/phase3c_calibration_selection.json`. Figure:
`outputs/windows/sync_2016/figures/detection_curve_v3_sync2016.png`.

Tests: see the closing line of this run.
