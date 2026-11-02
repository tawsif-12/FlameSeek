# Northern Australia detector fix — report

Status on 2026-11-02: **Step 1 done. Step 2 done: one round, and the checks did NOT all
pass (C1 and C2 pass, C3 fails). Step 3 (refit) was not run. Step 4 applies: everything
stays unapplied.** No active parameter, threshold or curve has changed. Decisions D72–D74
in `docs/decisions.md`.

## Step 1 — `himawari.nearby()` fixed (D72): done

The function now converts times to seconds via `Timedelta` division instead of
`astype('int64')`. The old version treated pandas-3 microseconds as nanoseconds, so every
tolerance was 1,000× too wide ("±60 min" really meant ±1,000 h). The test that pinned the
bug now asserts the fix. Every affected figure was recomputed from stored detections by
`run_nearby_fix_rerun.py`, and corrected values were written back.

| Figure | Old | New |
|---|---|---|
| Phase 3c N. Australia commission (2,195 pixels, ±60 min, 2 km) | 26.5% | **78.6%** |
| — only hours with a polar-orbiter reference | — | 59.1% |
| — hours without any reference (unmatched by construction) | — | 94.3% |
| Phase 3 South Asia commission | not estimable (0 Himawari fires) | unchanged |
| Phase 3 tuning-alternative commission | none scored | unchanged |
| N. Australia transfer event-specific Himawari ratios (167 pairs) | 5 finite, median 0.988 | identical (largest change 6×10⁻¹⁷) |
| South Asia transfer event-specific ratios (6,568 pairs) | 0 finite | 0 finite |
| Phase 3b positive controls; Phase 3 VIIRS detection rates | single-scan comparisons | unaffected |

Why the transfer ratios didn't change: they compare each event against detections from
the nearest hourly scan, so the time gap is always 30 min or less; the over-wide tolerance
never mattered there.

The new 78.6% is mostly a timing statement, not evidence of false detections. Polar
satellites pass this box only at about 00–04, 07–09, 12–16 and 20–21 h local solar time.
Location confirmation, i.e. a polar detection within 2 km at any time, stays at 73.5% (D71).

Corrected in: geo_fires and himawari_fires `reference_match`, both `transfer_pairs.csv`,
`stage2_summary.json`, `phase3c_status.json`, `phase3c_report.md`,
`staged_continuation_report.md`. Details: `outputs/nearby_fix_rerun.json`.

## Step 2 — daytime detector, one round (D73, D74): checks not all passed

**2a. Cloud mask source.** The NOAA bucket *does* have a Level-2 cloud mask
(`AHI-L2-FLDK-Clouds`, `AHI-CMSK_v1r1`). But each file is a 374 MB full disk, about 40 GB
for the window, which is over the 3 GB limit, and S3 throughput here was too low for
remote subset reads. You chose the **B04 fallback**: 0.86 µm, S0610/S0710, daytime UTC
hours 21–09.
- 124 of 130 files downloaded and verified (6 absent upstream), 1.221 GB, 0 errors.
- The first download attempt discarded every file: the downloader's integrity check only
  accepted 2 km segments. It now reads the expected size from the resolution code (D73).
- B04 was aggregated to the cached 2 km grid for 62 of 62 daytime scans, with 0
  misaligned. The cropped B07 reproduces the cached B07 exactly.

**2b. Change** (`himawari.contextual(..., day_fix=...)`; without it, behaviour is
unchanged):
- Daytime cloud (SZA < 80°): cold B14, B14 − B15 < −1 K, or R0.86/cos(SZA) above the
  threshold. The B14 − B15 > 5 K test is not used by day.
- Daytime B07 − B14 contextual term = min(max(3σ, 6 K), cap).
- Night unchanged.

**2c. Tuning (Oct 29–30 only).** 25 variants plus baseline; objective M1 + M3.

| Variant (train days) | M1 cloud share 12–14 h | M3 never-confirmed 09–13 h (n) | Day detection rate < 5 / 5–20 / ≥ 20 MW |
|---|---:|---:|---|
| Baseline | 88.5% | 95.2% (332) | 13% / 8% / 12% |
| R 0.25, cap 6 | 27.0% | 98.1% (2,174) | 45% / 73% / 96% |
| R 0.35, cap 10 | 13.4% | 98.1% (3,288) | 57% / 58% / 70% |
| **R 0.45, no cap (chosen)** | **9.0%** | **97.3% (3,074)** | 54% / 46% / 49% |

The objective fell steadily as the reflectance threshold rose, and the cap changed it by
less than 0.003. The chosen setting sits at the edge of the grid. **M3 got worse than
baseline in every variant**, so all of the training gain came from M1.

**2d. Test days (Oct 31 – Nov 1), scored once:**

| Check | Before | After | Pass rule | Result |
|---|---|---|---|---|
| C1: VIIRS fire pixels at 12–14 h classed cloud (n = 5,628) | 91.8% | **6.8%** (night level 11.2%) | close ≥ half the gap to night | **pass** |
| C2: daytime detection rate, < 5 / 5–20 / ≥ 20 MW | 4.4% / 6.3% / **0.0%** (n = 45 / 256 / 89) | 38.0% / 61.9% / **56.0%** (n = 150 / 729 / 182) | ≥ 20 MW > < 5 MW and > before | **pass** |
| C3: Himawari detections at 09–13 h never confirmed | 88.4% (n = 86) | **95.9% (n = 4,085)** | fall ≥ 20 points and end ≤ 50% | **fail** |

What this means:
- **The cloud fix works.** VIIRS fires at midday are no longer hidden as cloud; the share
  is now at night level.
- **Real daytime fires are now detected.** For fires ≥ 20 MW the rate went from 0% to
  56%. The rate is not strictly monotonic: the 5–20 MW bin is higher. Chance matches with
  false alarms are small: about 400 detections per midday scan × a 12.6 km² match disk
  covers about 0.4% of the box.
- **Midday false alarms grew about 48-fold, from 86 to 4,085 pixels**, and 95.9% of them
  are never confirmed by any polar detection within 2 km. Unmasking the land exposed
  far more spurious hot pixels than real fires. The contextual test, with or without a
  cap, does not reject them.

## Step 3 — not run

The refit runs only if C1–C3 all pass. No new diurnal, transfer or FRE file was written.

## Step 4 — stopped; limitation recorded

Everything stays unapplied. `params/diurnal_v2.json`, `calibration_v3_transfer_naus.json`
and the Northern Australia FRE stay as they were and remain flagged as not to be used
(D71). The limitation is in `outputs/naus_diurnal_check.md`.

A daytime Northern Australia diurnal curve needs a further round that targets daytime
commission directly. Suggestions, not done (one round was authorized):
- the official L2 cloud mask, if reachable;
- cloud-edge and cloud-shadow buffers;
- persistence or temporal-consistency tests across adjacent scans;
- a daytime B07 threshold that adapts to surface temperature.

Full numbers: `outputs/naus_detector_fix.json`.

## Tests

129 harmonization tests (including 3 new daytime-fix tests) and 71 backend tests pass.
