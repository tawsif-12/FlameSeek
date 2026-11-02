# Raw data inspection

Folder: `D:\nasa space\Burning_Activity\data\raw`

## Data problems found

- None

## FIRMS files

### `modis actual.csv`

- Rows: **35848** (of which 0 blank/unparseable)
- MD5: `62b6a4e2cf25763d71ba9ed1dcf96322`
- Columns (14): latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight
- Date range (acq_date): 2026-10-29 to 2026-11-02 (5 day(s)); raw date format example `10/29/2026`
- acq_time range (HHMM UTC): 1 to 2358
- `instrument`: `MODIS`: 35848
- `satellite`: `Aqua`: 23751, `Terra`: 12097
- `version`: `6.1NRT`: 35838, `6.1URT`: 10
- `confidence`: `0`: 210, `1`: 1, `10`: 21, `100`: 2129, `11`: 23, `12`: 18, `13`: 27, `14`: 34, `15`: 36, `16`: 47, `17`: 56, `18`: 75, `19`: 64, `20`: 64, `21`: 82, `22`: 87, `23`: 88, `24`: 100, `25`: 104, `26`: 107, `27`: 116, `28`: 136, `29`: 141, `3`: 4, `30`: 191, `31`: 153, `32`: 182, `33`: 186, `34`: 186, `35`: 211, `36`: 218, `37`: 221, `38`: 220, `39`: 272, `4`: 4, `40`: 238, `41`: 276, `42`: 281, `43`: 296, `44`: 302, `45`: 340, `46`: 330, `47`: 360, `48`: 378, `49`: 412, `5`: 10, `50`: 409, `51`: 433, `52`: 461, `53`: 469, `54`: 505, `55`: 530, `56`: 509, `57`: 594, `58`: 652, `59`: 659, `6`: 16, `60`: 620, `61`: 755, `62`: 736, `63`: 728, `64`: 738, `65`: 708, `66`: 780, `67`: 819, `68`: 799, `69`: 732, `7`: 13, `70`: 771, `71`: 789, `72`: 708, `73`: 766, `74`: 717, `75`: 690, `76`: 633, `77`: 635, `78`: 644, `79`: 591, `8`: 14, `80`: 535, `81`: 547, `82`: 544, `83`: 457, `84`: 477, `85`: 452, `86`: 442, `87`: 393, `88`: 377, `89`: 371, `9`: 18, `90`: 389, `91`: 306, `92`: 304, `93`: 279, `94`: 303, `95`: 228, `96`: 225, `97`: 175, `98`: 184, `99`: 182
- scan: 1.0 to 4.82 km; track: 1.0 to 2.0 km
- Latitude -44.37604 to 65.56489; longitude -157.83876 to 179.63452
- `type` column present: no (NRT file)
- Detections per platform per day: Aqua 2026-10-29: 7013; Aqua 2026-10-30: 4761; Aqua 2026-10-31: 5435; Aqua 2026-11-01: 5695; Aqua 2026-11-02: 847; Terra 2026-10-29: 3401; Terra 2026-10-30: 2379; Terra 2026-10-31: 2660; Terra 2026-11-01: 3247; Terra 2026-11-02: 410

### `viirs noa 20.csv`

- Rows: **200004** (of which 0 blank/unparseable)
- MD5: `222b395e3a957d279dddb3267fcb60bb`
- Columns (14): latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_ti5, frp, daynight
- Date range (acq_date): 2026-10-29 to 2026-11-02 (5 day(s)); raw date format example `10/29/2026`
- acq_time range (HHMM UTC): 1 to 2358
- `instrument`: `VIIRS`: 200004
- `satellite`: `N20`: 200004
- `version`: `2.0NRT`: 199680, `2.1URT`: 324
- `confidence`: `h`: 7406, `l`: 24401, `n`: 168197
- scan: 0.3 to 0.8 km; track: 0.36 to 0.8 km
- Latitude -51.64408 to 71.27129; longitude -178.77322 to 179.87115
- `type` column present: no (NRT file)
- Detections per platform per day: NOAA-20 2026-10-29: 52172; NOAA-20 2026-10-30: 47127; NOAA-20 2026-10-31: 48384; NOAA-20 2026-11-01: 44372; NOAA-20 2026-11-02: 7949

### `viirs noa 21.csv`

- Rows: **191961** (of which 0 blank/unparseable)
- MD5: `b6774959e1dd425a9c108b4ff3bf340a`
- Columns (14): latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_ti5, frp, daynight
- Date range (acq_date): 2026-10-29 to 2026-11-02 (5 day(s)); raw date format example `10/29/2026`
- acq_time range (HHMM UTC): 0 to 2358
- `instrument`: `VIIRS`: 191961
- `satellite`: `N21`: 191961
- `version`: `2.0NRT`: 191879, `2.0URT`: 82
- `confidence`: `h`: 9564, `l`: 23871, `n`: 158526
- scan: 0.3 to 0.8 km; track: 0.36 to 0.8 km
- Latitude -51.64441 to 71.42569; longitude -178.99461 to 179.86874
- `type` column present: no (NRT file)
- Detections per platform per day: NOAA-21 2026-10-29: 49467; NOAA-21 2026-10-30: 43404; NOAA-21 2026-10-31: 44882; NOAA-21 2026-11-01: 43133; NOAA-21 2026-11-02: 11075

### `viirs snpp.csv`

- Rows: **190372** (of which 0 blank/unparseable)
- MD5: `3b0a65481da48c7c56990a13ac4f7550`
- Columns (14): latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_ti5, frp, daynight
- Date range (acq_date): 2026-10-29 to 2026-11-02 (5 day(s)); raw date format example `10/29/2026`
- acq_time range (HHMM UTC): 1 to 2358
- `instrument`: `VIIRS`: 190372
- `satellite`: `N`: 190372
- `version`: `2.0NRT`: 189339, `2.0URT`: 1033
- `confidence`: `h`: 8751, `l`: 22660, `n`: 158961
- scan: 0.3 to 0.8 km; track: 0.36 to 0.8 km
- Latitude -73.30103 to 71.42462; longitude -179.30205 to 179.86937
- `type` column present: no (NRT file)
- Detections per platform per day: S-NPP 2026-10-29: 55435; S-NPP 2026-10-30: 38603; S-NPP 2026-10-31: 44745; S-NPP 2026-11-01: 44383; S-NPP 2026-11-02: 7206

## Himawari (later phase, not processed in this run)

`himawari/` does not exist under `data/raw/`. No Himawari data is present yet, so file count, format, time range, bands and segments cannot be listed.
