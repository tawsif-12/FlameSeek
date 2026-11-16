# Smaller website dataset

Verified export: **2,159,309,727 bytes (2.16 GB)**, down **88.85%** from the
previous full inventory of 19.36 GB. The gzip archive is **877,388,016 bytes
(877 MB)**. It contains 52 files including all 29 public CSVs and all three
published snapshots. See `compact-audit.json` for counts, checksums and checks.

The live FIRMS key was checked with NASA's status endpoint and one tiny-area
MODIS_NRT request: both returned HTTP 200, and the observation response was a
valid CSV with zero detections in that test area. The key is not in the export.

The exporter reads original inputs and writes a separate deployment bundle. It
does not delete raw observations or alter pipeline results. Build it from the
repository root:

```sh
python deploy/compact_data.py --output deploy/bundles/published-website
python deploy/verify_bundle.py deploy/bundles/published-website/runtime
python deploy/check_compact_api.py deploy/bundles/published-website/runtime
```

The destination must be new. An interrupted export is retained for diagnosis;
use another destination to retry. SQLite databases are copied using SQLite's
backup API, vacuumed on the copy, integrity-checked and compared by row count.
The snapshot manifest is checked for changes during export. Run between daily
publication jobs for a consistent published generation.

## Included

- Only the three SQLite generations referenced by the snapshot manifest, with
  every event, detection, footprint, overpass, grid and raw-observation row intact.
- All 29 CSVs explicitly listed in the public dataset download API.
- Calibration parameter JSONs, orbit-drift measurements and saved TLE inputs.
- Frontend site-data JSON and published pipeline status.
- Independent harmonization evidence inputs if configured.
- A file manifest with SHA-256 checksums and snapshot row counts.

Code, Python dependencies, frontend assets and config/settings.yaml remain in
the source deployment. They are not replaced by this data export.

## Kept locally

Original satellite archives, repeated partitions, geospatial intermediates,
unreferenced SQLite generations, research outputs outside the public download
list, canonical ingestion database, and rebuildable network/history/model caches.
No `.env` or FIRMS key is included. The full originals remain the authoritative
research and ingestion archive.

## What works

The historical map and accumulated-history API keep their published records.
All reviewed CSV downloads remain available, including Himawari FRE tables.
Live fire requests still use backend FIRMS_MAP_KEY and outbound internet access.
On-demand forecasts keep their existing code and fetch historical FIRMS and
weather data again; first runs can be slower and validation can withhold a
forecast. This is not a collection of pretrained models or new predictions.
NASA MAP_KEY supports 5,000 transactions per 10 minutes, with larger queries
counting as multiple transactions:
https://firms.modaps.eosdis.nasa.gov/api/area/

Keep scheduled daily ingestion disabled for this profile. Its canonical
checkpoint and raw inputs were omitted; enabling it against this export alone
would start a new ingestion history rather than continue the full archive.
Continue ingestion locally and export updated published snapshots, or transfer
the full canonical ingestion database and its raw data for server-side ingestion.

## Deployment

`flameseek-runtime.tar.gz` preserves repository-relative paths. Extract into a
separate staging folder, verify it, then copy the selected directories to the
server's data layout. For the prepared Render service that layout is `/var/data`
for `data/`, `dataset/`, and `outputs/`; params and site-data are already built
from source. Keep secrets configured only in the backend environment. Use a
clean deployment target; this export is not a cleanup tool for a full archive.

Reducing the dataset does not itself make persistent storage free on Render.
The paid deployment is still deferred. A free service would need separate
durable file hosting or reproducible build-time data provisioning; prediction
memory requirements also remain to be measured.
