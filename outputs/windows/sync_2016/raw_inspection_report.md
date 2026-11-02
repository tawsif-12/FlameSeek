# Raw data inspection

Folder: `D:\nasa space\Burning_Activity\data\raw\archive\2016`

## Data problems found

- None

## FIRMS files

### `modis_2016_Bangladesh.csv`

- Rows: **0**; empty window extraction (no dates or acquisition times).
### `modis_2016_India.csv`

- Rows: **3703** (of which 0 blank/unparseable)
- MD5: `a8b40906f302bbe13299bf3aa4f15409`
- Columns (15): latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight, type
- Date range (acq_date): 2016-10-29 to 2016-11-02 (5 day(s)); raw date format example `2016-10-29`
- acq_time range (HHMM UTC): 424 to 2037
- `instrument`: `MODIS`: 3703
- `satellite`: `Aqua`: 3515, `Terra`: 188
- `version`: `6.2`: 3703
- `confidence`: `0`: 3, `10`: 1, `100`: 4, `11`: 1, `12`: 1, `13`: 3, `14`: 5, `15`: 4, `16`: 5, `17`: 9, `18`: 6, `19`: 8, `20`: 12, `21`: 15, `22`: 8, `23`: 19, `24`: 22, `25`: 18, `26`: 15, `27`: 22, `28`: 19, `29`: 19, `30`: 26, `31`: 32, `32`: 31, `33`: 24, `34`: 29, `35`: 29, `36`: 29, `37`: 35, `38`: 36, `39`: 37, `40`: 37, `41`: 36, `42`: 37, `43`: 35, `44`: 34, `45`: 45, `46`: 54, `47`: 61, `48`: 64, `49`: 53, `50`: 62, `51`: 59, `52`: 64, `53`: 61, `54`: 59, `55`: 71, `56`: 62, `57`: 75, `58`: 77, `59`: 86, `60`: 77, `61`: 92, `62`: 97, `63`: 81, `64`: 81, `65`: 98, `66`: 103, `67`: 90, `68`: 86, `69`: 78, `7`: 1, `70`: 76, `71`: 87, `72`: 89, `73`: 85, `74`: 62, `75`: 76, `76`: 61, `77`: 67, `78`: 71, `79`: 64, `8`: 2, `80`: 55, `81`: 57, `82`: 38, `83`: 42, `84`: 36, `85`: 34, `86`: 32, `87`: 27, `88`: 19, `89`: 24, `9`: 1, `90`: 10, `91`: 8, `92`: 11, `93`: 7, `94`: 4, `95`: 7, `96`: 4, `97`: 2, `98`: 1, `99`: 1
- scan: 1.0 to 3.5 km; track: 1.0 to 1.8 km
- Latitude 20.7494 to 32.3244; longitude 73.0434 to 91.0273
- `type` column present: yes
- Detections per platform per day: Aqua 2016-10-29: 451; Aqua 2016-10-30: 108; Aqua 2016-10-31: 1482; Aqua 2016-11-01: 98; Aqua 2016-11-02: 1376; Terra 2016-10-29: 74; Terra 2016-10-30: 16; Terra 2016-10-31: 23; Terra 2016-11-01: 62; Terra 2016-11-02: 13

### `viirs-snpp_2016_Bangladesh.csv`

- Rows: **7** (of which 0 blank/unparseable)
- MD5: `502b08976974dccf07bc2bb90ab90b52`
- Columns (15): latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_ti5, frp, daynight, type
- Date range (acq_date): 2016-10-30 to 2016-11-02 (3 day(s)); raw date format example `2016-10-30`
- acq_time range (HHMM UTC): 614 to 2021
- `instrument`: `VIIRS`: 7
- `satellite`: `N`: 7
- `version`: `2`: 7
- `confidence`: `n`: 7
- scan: 0.39 to 0.47 km; track: 0.36 to 0.64 km
- Latitude 22.47346 to 24.87381; longitude 90.26572 to 92.02205
- `type` column present: yes
- Detections per platform per day: S-NPP 2016-10-30: 2; S-NPP 2016-10-31: 1; S-NPP 2016-11-02: 4

### `viirs-snpp_2016_India.csv`

- Rows: **21218** (of which 0 blank/unparseable)
- MD5: `8b3b8aafffff71e6e14ced7200ffe0a4`
- Columns (15): latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_ti5, frp, daynight, type
- Date range (acq_date): 2016-10-29 to 2016-11-02 (5 day(s)); raw date format example `2016-10-29`
- acq_time range (HHMM UTC): 632 to 2137
- `instrument`: `VIIRS`: 21218
- `satellite`: `N`: 21218
- `version`: `2`: 21218
- `confidence`: `h`: 206, `l`: 631, `n`: 20381
- scan: 0.32 to 0.79 km; track: 0.36 to 0.78 km
- Latitude 20.51498 to 32.46339; longitude 73.00101 to 92.56453
- `type` column present: yes
- Detections per platform per day: S-NPP 2016-10-29: 2762; S-NPP 2016-10-30: 1967; S-NPP 2016-10-31: 6092; S-NPP 2016-11-01: 6088; S-NPP 2016-11-02: 4309

## Himawari (later phase, not processed in this run)

- Files: 1320; total size 3510.3 MB
- Formats: `.bz2` x1320
- Satellites: ['H09']
- Time range (UTC): 2026-10-29 00:00:00 to 2026-11-02 11:00:00 (113 time slots)
- Bands: ['B07', 'B14', 'B15']
- Areas: ['FLDK']; segments: ['20']
