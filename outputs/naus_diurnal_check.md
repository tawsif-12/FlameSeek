# Northern Australia diurnal fit — check of the 18.8 h peak

Window: 29 Oct – 2 Nov 2026 UTC, box [125, −20, 138, −11] (method demonstration region).
This is a diagnosis only: no parameter file, threshold or active curve was changed. The
refits below were computed in memory.

## Conclusion

**The 18.8 h peak is a detection artifact, not a physical result.** Fires do burn in the
evening at these locations, but this detector cannot see the afternoon. The peak lands at
the first hours with good visibility after a blind daytime period.

**None of the fits should be used** as a diurnal shape: neither the published one nor any
refit below. Keep `params/diurnal_v2.json` unapplied. Treat the products built on it as
suspect until the daytime detector is fixed and refitted:
- the v3_transfer_naus time adjustment;
- Northern Australia FRE.

The evidence, strongest first:

1. **The fit has no daytime data.** The fit keeps only scans with at least 30% clear sky.
   Daytime clear fraction is 11–23% from 08 to 15 h, so the fit has **0 points between
   08 and 15 h**: 4 points per hour from 16 to 07 h and none in between. The curve can
   only peak at the start of the observable evening.
2. **The daytime cloud mask removes most of the land, fires included.** The split-window
   test (B14 − B15 > 5 K) flags 72–84% of daytime land as cloud. At night it flags 3–10%.
   The median B14 − B15 reaches 6.8–7.1 K at 10–12 h. That is the normal daytime
   split-window signal over hot land, not cloud. **90–93% of VIIRS-observed fires at
   12–14 h are classified as cloud by Himawari**, against 3–10% at 00–02 h.
3. **The daytime fires that remain visible are rarely detected.**
   - VIIRS detection rate: 10.0% by day (n = 850, median VIIRS FRP 9.9 MW) against 25.2%
     at night (n = 4,264, median 2.3 MW). Daytime fires are larger but detected less.
   - Fires above 20 MW: 7.5% detected by day against 81.2% at night.
   - Likely cause: the B07 − B14 contextual test. The daytime background mean of B07 − B14
     is 17–28 K, with standard deviation 6–9 K. At night these are 3–4 K and 3.3–3.5 K.
4. **Most daytime detections are false.** At 09–12 h, 92–98% of Himawari fire pixels are
   never confirmed by any polar-orbiter detection within 2 km at any time in the window.
   At 17–19 h, 89–91% are confirmed. So the evening detections are real fire locations,
   while the midday ones are largely false alarms.

## 1. Per local-solar-hour summary

Figure: `figures/naus_diurnal_diagnostics.png`. Full table:
`naus_diagnostics/hourly.csv`.

| LST h | Fire px | Summed FRP (MW) | Clear valid land px | VIIRS detection rate | Never confirmed |
|---:|---:|---:|---:|---:|---:|
| 0 | 57 | 1,742 | 701,037 | 0.26 | 0% |
| 1 | 63 | 2,575 | 719,445 | 0.25 | 2% |
| 2 | 41 | 1,165 | 739,614 | 0.28 | 0% |
| 3–6 | 141 | 4,727 | 3.16 M | — | 1% |
| 7 | 60 | 2,208 | 559,777 | — | 2% |
| 8 | 21 | 634 | 232,459 | — | 10% |
| 9 | 77 | 1,809 | 143,212 | — | 92% |
| 10 | 173 | 4,126 | 121,816 | — | 97% |
| 11 | 137 | 3,607 | 132,799 | — | 98% |
| 12 | 68 | 1,679 | 178,232 | 0.08 | 93% |
| 13 | 49 | 2,101 | 222,895 | 0.09 | 59% |
| 14 | 26 | 1,835 | 238,211 | 0.13 | 12% |
| 15 | 40 | 2,506 | 248,493 | — | 15% |
| 16 | 143 | 5,295 | 324,969 | — | 12% |
| 17 | 226 | 7,927 | 560,733 | — | 9% |
| 18 | 261 | 8,940 | 704,206 | — | 11% |
| 19 | 197 | 6,682 | 730,594 | — | 9% |
| 20–23 | 415 | 15,240 | 2.62 M | — | 5% |

VIIRS passes this box only at about 00–02 h and 12–14 h, so the VIIRS detection rate is
defined only at those hours.

## 2. Day vs night: threshold effect and background

| Run (in memory) | Day pixels (confirmed) | Night pixels (confirmed) | Fit peak |
|---|---|---|---|
| As published: 310 K day / 300 K night | 994 (48.6%) | 1,201 (94.2%) | 18.82 h |
| Day candidate at 300 K | 7,799 (8.6%) | 1,201 (94.2%) | 16.22 h |
| Night candidate at 310 K | 994 (48.6%) | 641 (94.7%) | 18.25 h |

- **The day/night threshold switch is not the cause.** Raising the night threshold to
  310 K removes 560 night pixels without changing their confirmation rate, and moves the
  peak only 0.6 h.
- **Lowering the day threshold adds false alarms.** The extra ~6,800 daytime pixels are
  only 8.6% confirmed.
- **Background B07 by hour** (`naus_diagnostics/hourly.csv`):
  - Day (07–15 h): mean 297–305 K, standard deviation 4.4–5.0 K.
  - Night: mean 291–296 K, standard deviation 6.8–9.2 K.
- **Daytime B07 noise does not suppress detection.** Its spread is lower than at night.
  Suppression comes from the cloud mask (item 2 above) and the B07 − B14 contextual test
  (item 3); see `naus_diagnostics/cloud_tests_by_hour.csv`.

## 3. Unmatched detections and the matching bug

**Bug found:** `pipeline/himawari.py` `nearby()` converts times with `astype('int64')` and
assumes nanoseconds. Under pandas 3 these columns are in microseconds, so every tolerance
is 1,000× too wide, and "±60 min" means ±1,000 h. As a result:
- The published Phase 3c "VIIRS-matched" flag is identical to "confirmed at this location
  at any time in the window" (verified on all 2,195 pixels).
- The published 26.5% "commission" is really the share of pixels never confirmed at
  their location.

With a corrected ±60 min match (`naus_diagnostics.time_match`):
- Only 21.4% of pixels are time-matched.
- In hours where a polar reference exists, 59.1% are unmatched (n = 975). Outside those
  hours, 94.3% are unmatched, by construction: no reference can match there.

Unmatched by 1° cell: `naus_diagnostics/unmatched_by_1deg_cell.csv`.

**Persistent unmatched locations: none.** No native pixel had ≥ 3 never-confirmed
detections on ≥ 2 days. **Sun glint:** 1 daytime detection has a glint angle below 12°.
The top-10 unconfirmed locations (0.05° grid) are each seen on a single day. Nine of
them are daytime detections at 09.5–12.5 h with glint angles of 26–52°. That pattern
fits scattered daytime false alarms, not static hot sources or glint.

| # | Lon | Lat | Unconfirmed | Days | LST range h | Median FRP MW | Glint ° |
|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 128.64 | −15.12 | 7 | 1 | 18.6–19.6 (night) | 31.3 | — |
| 2 | 130.32 | −17.42 | 7 | 1 | 10.7–11.7 | 23.8 | 26.3 |
| 3 | 130.37 | −17.42 | 6 | 1 | 10.7–11.7 | 29.9 | 26.3 |
| 4 | 132.97 | −18.08 | 6 | 1 | 10.9 | 19.7 | 32.4 |
| 5 | 133.62 | −17.88 | 6 | 1 | 11.9 | 30.8 | 26.5 |
| 6 | 128.02 | −19.41 | 5 | 1 | 9.5–11.5 | 25.2 | 52.0 |
| 7 | 128.07 | −19.73 | 5 | 1 | 12.5 | 26.6 | 28.9 |
| 8 | 128.07 | −19.38 | 5 | 1 | 11.5 | 34.8 | 33.0 |
| 9 | 128.67 | −15.12 | 5 | 1 | 17.6–18.6 | 33.3 | 67.6 |
| 10 | 129.83 | −14.27 | 5 | 1 | 10.7 | 24.9 | 31.5 |

## 4. Diagnostic refits (in memory; not saved, not applied)

| Fit | Peak h | 90% interval h | Note |
|---|---:|---|---|
| As published | 18.82 | 16.67–19.43 | Reproduced exactly; no 08–15 h points |
| VIIRS time-matched only (corrected ±60 min) | 24.0 | 1.42–24.00 | Not identifiable: σ at its lower bound; references exist only at a few hours |
| Location-confirmed only (what the published "matched" flag really means) | 19.01 | 16.76–19.38 | Same blind daytime |
| Excluding persistent unmatched locations | 18.82 | 16.67–19.43 | No persistent locations, so identical |
| Area-normalized, all scans, all detections | 14.77 | 10.96–16.19 | Includes midday false alarms |
| Area-normalized, all scans, location-confirmed | 18.07 | 17.47–18.76 | Daytime detection still suppressed ~2.5× |

No refit removes the cause: daytime fires are masked as cloud or missed by the
contextual test. The 14.8 h result is closer to the early-to-mid-afternoon peak usually
reported for savanna burning, but it is driven by unconfirmed midday detections, so it
cannot be trusted either.

## Recommendation (awaiting your confirmation)

1. Do not apply any of these curves.
2. **Before** refitting, fix the daytime detector:
   - Cloud mask: the B14 − B15 > 5 K test should not apply, or should be relaxed, over
     clear hot land by day.
   - Daytime contextual B07 − B14 test.
   - Validate against VIIRS at 12–14 h: daytime cloud classification of VIIRS fires
     should fall toward night levels, and the detection rate should rise with FRP.
3. Fix `himawari.nearby()` to use unit-safe times, then rerun the Phase 3 / 3b / 3c
   commission figures and the transfer event ratios. Affected uses: `phase3c.py:31`,
   `run_phase3.py:132/148`, `transfer.py:94`. Single-scan uses are unaffected
   (`run_phase3.py:71`).
4. Then refit on all scans with FRP per clear area, with the 30% clear-fraction gate
   applied only after the cloud mask is fixed.

Files: `run_naus_check.py`, `pipeline/naus_diagnostics.py`, `naus_diagnostics/*.csv`,
`naus_diagnostics/summary.json`.

## Limitation after one detector-fix round (D74)

One authorized improvement round (`outputs/naus_detector_fix.md`) replaced the daytime
split-window cloud test with a B04 reflectance test and capped the daytime B07 − B14
contextual term. It was tuned on Oct 29–30 and tested once on Oct 31 – Nov 1.

- Fixed: midday VIIRS fires classed as cloud fell from 91.8% to 6.8%. The daytime
  detection rate for fires ≥ 20 MW rose from 0% to 56%.
- Not fixed: midday Himawari detections rose from 86 to 4,085, and 95.9% are never
  confirmed (88.4% before).

The pre-registered check C3 failed, so the diurnal curve was **not refitted**. The
current detector cannot provide a trustworthy daytime FRP series for Northern Australia.
The 18.8 h peak remains an artifact (above). `diurnal_v2`, `calibration_v3_transfer_naus`
and the Northern Australia FRE stay unapplied and flagged.
