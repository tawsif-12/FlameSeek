# Phase 2b: overpass-time drift history

Sample: daytime FIRMS detections on 10-29 (+1 day) each year, |lat| ≤ 30°. 2013–2025 from the FIRMS standard-processing archive (cached in `data/raw/firms_archive/`); 2026 from `data/raw/` (Phase 2 data). 1,839,381 daytime detections in all. Figure: `outputs/figures/overpass_lst_by_year.png`; table: `data/processed/drift_by_year.csv`.

## Median local solar time of daytime detections

| Year | Terra | Aqua | S-NPP | NOAA-20 | NOAA-21 | Aqua–S-NPP median abs(Δt) | Pairs | Calibration year |
|---|---|---|---|---|---|---|---|---|
| 2013 | 10:28 | 13:36 | 13:34 | – | – | 29.0 min | 4,198 | no |
| 2014 | 10:25 | 13:37 | 13:36 | – | – | 35.0 min | 4,336 | no |
| 2015 | 10:25 | 13:35 | 13:34 | – | – | 19.0 min | 2,879 | yes |
| 2016 | 10:28 | 13:36 | 13:27 | – | – | 32.0 min | 4,737 | no |
| 2017 | 10:33 | 13:32 | 13:21 | – | – | 38.0 min | 3,688 | no |
| 2018 | 10:27 | 13:38 | 13:29 | 13:33 | – | 18.0 min | 5,168 | yes |
| 2019 | 10:25 | 13:36 | 13:46 | 13:25 | – | 32.0 min | 8,179 | no |
| 2020 | 10:34 | 13:34 | 13:26 | 13:32 | – | 29.0 min | 4,079 | no |
| 2021 | 10:22 | 13:38 | 13:40 | 13:19 | – | 10.0 min | 5,080 | yes |
| 2022 | 10:14 | 13:39 | 13:25 | 13:33 | – | 30.0 min | 4,464 | no |
| 2023 | 09:59 | 13:58 | 13:36 | 13:27 | 13:29 | 37.0 min | 6,827 | no |
| 2024 | 09:38 | 14:21 | 13:27 | 13:35 | 13:28 | 63.0 min | 3,829 | no |
| 2025 | 09:15 | 14:58 | 13:44 | 13:32 | 13:30 | 88.0 min | 3,234 | no |
| 2026 | 08:32 | 15:49 | 13:37 | 13:36 | 13:26 | 145.0 min | 2,697 | no |

2026 overpass times computed from TLEs in Phase 2 (diamonds in the figure): Terra 08:35, NOAA-21 13:23, NOAA-20 13:30, S-NPP 13:37, Aqua 15:46.

## Drift

Early-archive value = median of 2013, 2014, 2015. A platform has drifted in the first year its median LST is more than 30 min from that value.

| Platform | Early-archive LST | First drifted year | LST that year | Latest LST |
|---|---|---|---|---|
| Terra | 10:25 | 2024 | 09:38 | 08:32 (2026) |
| Aqua | 13:36 | 2024 | 14:21 | 15:49 (2026) |
| S-NPP | 13:34 | none (no drift > 30 min) | – | 13:37 (2026) |

## Definitions now used by the pipeline

- **Calibration years** (median Aqua–S-NPP abs(Δt) ≤ 20 min, at least 30 pairs): 2015, 2018, 2021.
- **Drifted era**: a MODIS detection is `drifted_era = true` when its year is at or after its platform's first drifted year (Terra 2024, Aqua 2024). The values are stored in `config/settings.yaml` (`drift.first_drift_year`), and Step 1 writes the column for every MODIS row. VIIRS rows are left empty (not applicable).
- All MODIS detections in the current data (2026) are in the drifted era, and 2026 is not a calibration year. The Phase 2 FRP calibration therefore comes from drifted-era pairs; a calibration from calibration-year archive data is the next step.

## Limits

- **The calibration-year list is fragile.** Before any drift (2013–2023), the Aqua–S-NPP median abs(Δt) already ranges 10–38 min from year to year. Both satellites cross at about 13:30, but on any two given days their ground tracks are offset by a varying part of an orbit, so a 2-day sample mostly measures that phase, not drift. A wider sample per year (e.g. all of October) is needed before the ≤ 20 min rule is used to pick calibration data.
- One 2-day late-October sample per year. It shows the trend; it is not a full-year mean.
- Median LST of detections also depends on where fires are within the swath. The |lat| ≤ 30° band and the same calendar window keep this similar from year to year.
- The Aqua–S-NPP Δt uses detections, not events: the nearest S-NPP detection within 1.0 km on the same UTC day.
