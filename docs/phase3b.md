# Phase 3b: detector controls and Meteosat-9 IODC

Run from the repository root in the `flameseek` environment:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' run_phase3b.py --window current_2026
```

The command runs positive controls before platform assignment. `--reuse-controls`
reuses the saved audits for the same window. Do not reuse them after changing
radiometry, detection code, thresholds or the input scans. The detector status
is in `outputs/himawari/detector_verification.json`; statistics, injections and
real-fire matches are in adjacent audit files. No synthetic values enter science
caches or raw imagery. Phase 3 is rerun only after an actual detector bug fix.

The platform table is `geostationary.platforms` in `config/settings.yaml`.
Assignment covers the full 0.1-degree global grid (6,480,000 cell centers), is
streamed to Parquet, and chooses the lowest VZA strictly below 65 degrees. Ties
use configuration order. Cells outside both valid views are null. Source
selection does not depend on whether that platform currently has files.

Download the IODC FRP-PIXEL **ListProduct and QualityProduct** files for
2026-10-29 through 2026-11-02 into `data/raw/meteosat/current_2026/`, optionally
using dated subdirectories. No download is attempted by this pipeline.
No files is a successful `awaiting data` result. No zero-filled days,
`diurnal_v2.json`, new transfer fit or FRE estimates are fabricated in that case.

The HDF5 ingest supports `.h5`, `.hdf5`, `.nc` (HDF5-backed NetCDF4), extensionless
HDF5 product names and `.bz2` wrappers. It uses `h5py` (added to environment.yml).
It validates native files once available. The LSA SAF manual download timed out,
so ingestion is tested against explicit synthetic schema fixtures, not a claim
that the unprovided 2026 files have already been validated.

Canonical fields and accepted dataset names:

| Output | Typical dataset aliases | Units |
|---|---|---|
| latitude | LATITUDE, latitude, lat | degrees north |
| longitude | LONGITUDE, longitude, lon | degrees east |
| frp_mw | FRP, FRP_MW, frp | MW |
| frp_uncertainty_mw | FRP_UNCERTAINTY, FRP_ERROR | MW |
| confidence_pct | CONFIDENCE, FIRE_CONFIDENCE, FRP_CONFIDENCE | percent |
| pixel_area_km2 | PIXEL_AREA, PIXEL_AREA_KM2, AREA | km2 |
| acq_datetime_utc | TIME/time with units, or filename scan start | UTC |

`geostationary.meteosat.field_overrides` can map a canonical name to an exact
HDF5 dataset path. Ambiguous duplicate names are rejected. Latitude, longitude
and FRP are required. Optional absent fields remain null and are listed in the
file audit. Unknown numeric time encodings and conflicting units are rejected.
The parser preserves whether time is a pixel time or a file scan-start time.

Decoding supports uppercase LSA-style `SCALING_FACTOR` and `OFFSET` with
`physical = stored / factor + offset`, or CF lowercase `scale_factor` and
`add_offset` with `physical = stored * factor + offset`. Fill values are masked
before arithmetic. Verify these conventions against delivered product metadata
and the accompanying PUM; no scale is inferred from a plausible value range.
Longitude metadata must match 45.5 degrees E within 0.5 degrees, or the filename
must identify IODC. A zero-degree MSG product is not accepted as Meteosat-9 IODC.

Fires write atomically to
`data/processed/geo_fires/platform=Meteosat-9/year=YYYY/month=MM/day=DD/part.parquet`.
A source filename and checksum audit accompany each ingest. Only delivered days
are written. QualityProduct files are inventoried separately: they are not
mistaken for lists of fires, and absence from a ListProduct is never assigned
"clear/no fire". Quality-mask decoding, its geolocation and actual South Asia
product coverage must be validated with the delivered files before downstream
Phase 3b science can run. The current no-data execution intentionally stops at
that gate, as requested.

The existing transfer module already rejects Terra and leaves ratios undefined
in regions without fitted shapes. Tests exercise that gate, minimum-VZA single
assignment, real-tile injection at 0.1%, packed values, fill handling, pixel
and filename times, bzip2, day partitions, missing uncertainty and wrong-platform
rejection. Test fixture numbers are synthetic and are never reported as science.
