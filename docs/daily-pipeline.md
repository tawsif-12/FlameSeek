# Automated FIRMS ingestion

## Verified local installation (November 9, 2026)

The Windows task `FlameSeek-Daily-FIRMS` is registered for 08:00 Bangladesh time
under the current interactive account. The API and frontend are running locally.
The original October 29–November 2 exports and the November 9 NASA download have
been published together: 650,742 canonical observations, 574,525 quality-filtered
detections and 148,188 reconstructed events. This date span is not continuous
coverage: November 3–8 have not yet been downloaded by this initial verification.
Normal scheduled runs catch those missing source-days within NASA availability.
Suomi NPP was unavailable for November 9; the run is correctly marked partial.
The previous offline snapshots remain in the catalog.

Validation: 149 pipeline tests passed; the latest focused ingestion tests passed
again after client/version-handling changes. Backend tests passed across the two
installed environments: 124 passed with one witness test deselected in Python
3.14, then all seven witness tests passed in the geospatial Python 3.11 environment
(the Python 3.14 scikit-learn DLL was blocked by Windows Application Control).
The frontend production build passed. Real API status, catalog, selected-area
history and `/fires/search` checks passed against the published snapshot, and
the ingestion ledger has no pending partitions. Recovery after interruption was
also exercised during the historical import without losing observations.

The previous `backend/.env.example` contained a key and now uses a placeholder.
Replacing the template does not remove older Git history; rotate that key if the
repository history was shared.

## Implementation and publication

`pipeline.daily_client` downloads the official worldwide Area CSV API, one UTC
source-day at a time. It checks NASA's source availability and shared-key quota,
uses timeouts/retries/backoff, and never logs secret URLs. The API permits 1–5
days per request; explicit dates support catch-up only within source availability.
Reference: https://firms.modaps.eosdis.nasa.gov/api/area

`daily_schema` preserves the 14 requested columns first, UTC HHMM with leading
zeros, categorical confidence, and the original decimal strings. VIIRS I-4/I-5
stay separate; MODIS temperature columns are null for VIIRS. Original source
values, source dataset, processing tier, timestamps, and fingerprints follow.
Missing measurements remain null. The existing quality filters decide whether
a detection can contribute to an event; ingestion retains low-confidence and
missing-FRP observations for history.

`daily_store` writes immutable raw Parquet and original CSV under source/acquisition
date partitions, then commits a SQLite canonical observation index and successful
download ledger in one transaction. Normalized Parquet is rebuilt only for dirty
source-days. Failed writes leave the canonical transaction unchanged. Unreferenced
raw files from an interruption are harmless audit artifacts and may be retained.

Identity = SHA256(source dataset, verified satellite, instrument, UTC minute,
latitude and longitude at their original decimal precision). Numeric coordinate
formatting alone does not change identity. Version/FRP/confidence changes update
the canonical record, and previous raw revisions remain permanently available.
NRT is preferred over RT/URT, and older numeric product versions cannot replace
newer versions within the same processing tier. A coordinate/time relocation is a new detection:
FIRMS does not supply a permanent pixel ID, so fuzzy matching could merge distinct
observations and is deliberately not used. Source datasets remain independent.

`daily_publish` invokes the existing `ingest.standardize`, `quality.run`,
`footprints.run`, `events.run`, and `snapshot.build_window`. It preserves the
existing clustering, local-solar-day grouping, duration/extent caps, overpass FRP
aggregation, exact search containment and deterministic ordering. Events spanning
midnight are reconstructed together. Observation membership reconciles IDs across
updates; a merge keeps one deterministic previous ID and a split keeps an old ID
on one deterministic piece. Other pieces receive source-derived IDs.

Publication currently rebuilds **all accumulated geospatial observations**, rather
than attempting unsafe partial event linking. Ingestion/Parquet export are daily
incremental. This first version is not an unbounded, constant-memory worldwide
history processor: plan RAM/runtime against growing history before long production
backfills. Partitioned geospatial recomputation remains future work.

An immutable generation contains events, footprints, quality-filtered detections,
raw observation history, overpasses, metadata and an R-Tree. Counts and SQLite
integrity are checked before a single atomic manifest change publishes it. Old
generations and the existing `current_2026`/`sync_2016` windows are retained.
The API pool follows the manifest filename and invalidates identity-based caches.
`POST /fires/search` retains its contract. Back up the manifest, canonical SQLite
(using SQLite's backup API), raw files and referenced snapshots together.

No calibrated lambda, cross-sensor temperature conversion, observation opportunities,
forecast or containment/extinguishment claim is manufactured. Those advanced
historical analyses keep their existing workflow. The accumulated history panel
uses the newly published snapshot and exact selected boundary; existing long-term
Fire Memory jobs remain available independently. Counts distinguish raw observations
from reconstructed events. A downloaded empty day does not establish clear-sky
coverage or absence of fire.

## Environment and commands

Use the geospatial environment from `environment.yml` (Python 3.11+). If needed:

```powershell
E:\anaconda\envs\flameseek\python.exe -m pip install -r config/daily-requirements.txt
```

Put `FIRMS_MAP_KEY` in `backend/.env`, using `config/daily.env.example` as the
template. Environment variables take precedence. Never expose the key through
React/Vite. Source enable/disable and overlap are server environment settings.

Run these commands from the repository root with that environment's Python:

```powershell
# Optional one-time migration of the four original data/raw/*.csv exports.
# This preserves the old observations in the daily accumulated dataset.
python -m pipeline.daily import-existing

# Initial run: recent three days including the partial current UTC day.
# Later runs catch up missing dates and refresh the last three days.
python -m pipeline.daily run

# Request a recent backfill; source availability is checked for every date.
python -m pipeline.daily backfill --days 7
python -m pipeline.daily backfill --start 2026-11-03 --end 2026-11-09

# Re-export pending normalized partitions and rebuild/publish without NASA calls.
python -m pipeline.daily publish
python -m pipeline.daily status

# Focused tests; disable unrelated auto-loaded plugins if the host has broken DLLs.
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest tests/test_daily_pipeline.py -q -p no:cacheprovider
```

The backfill command refreshes dates inside the lookback and fills missing dates;
it does not rewrite already-collected older days unnecessarily. Set `--lookback`
to cover the requested interval to force a refresh of all those days.
If a date is outside NASA's available NRT range it is recorded as unavailable,
not as an empty success. Automatic standard-processed archive ingestion is not
implemented in this version. The existing archive windows remain accessible.

## Scheduling

Windows, while logged into the development account:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_daily_task.ps1 -PythonPath E:\anaconda\envs\flameseek\python.exe -At 08:00
Start-ScheduledTask -TaskName FlameSeek-Daily-FIRMS
Get-ScheduledTaskInfo -TaskName FlameSeek-Daily-FIRMS
```

The installer uses the computer's local timezone, runs with limited privileges,
starts missed jobs when available, retries failures and ignores overlapping task
instances. It is an interactive-account development task, so the user must be
logged in. For unattended deployment use a service account with appropriate
batch logon rights or the Linux scheduler below. No scheduler runs inside FastAPI.
An OS file lock also prevents overlap from CLI invocations; termination releases
the lock without requiring manual stale-lock deletion.

Linux: adapt `tools/flameseek-daily.cron.example` and install via `crontab -e`.
Create `data/logs` first; the example assumes UTC server time and runs at 02:00 UTC
(08:00 Bangladesh). Use an always-on host, TLS trust store, disk monitoring and
routine backups. The daily script loads `backend/.env` independently of FastAPI.

## Recovery and visibility

`GET /api/pipeline/status` exposes run status, attempt/success/publication times,
latest satellite observation, raw/processed counts, source-day coverage and
failures. It never exposes keys or raw exceptions. A full success means validated
publication; download-only success is recorded separately. Partial source failures
can publish verified data while retaining previous records, and do not advance
the last full-success timestamp. Exit codes: 0 full success; 2 partial; 1 failed.

Retry `run` after a network, write or harmonization failure. The download ledger
finds gaps; dirty partitions remain until publication. Use `publish` if downloads
succeeded and only processing/publication failed. Old published generations stay
readable throughout. A status left at `running` after termination means the run
was interrupted; the next invocation acquires the released OS lock and recovers.
Raw and normalized storage are private server files and must not be web-served.

The frontend polls status/history every minute. Fire Events uses the manifest's
new default daily snapshot after first publication. Fire Memory adds accumulated
history and analytics by selected boundary and optional UTC date interval through
`POST /api/pipeline/history?start=YYYY-MM-DD&end=YYYY-MM-DD`. Event counts use
centroid containment and interval overlap; observation counts use individual
point containment. An event can therefore touch a boundary while its centroid
lies outside. Per-source maximum detection FRP is reported without summing
repeated overpasses as if they were distinct fires.
