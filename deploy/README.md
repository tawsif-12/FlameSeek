# Full FlameSeek deployment

## Render

`render.yaml` deploys one Docker web service in Singapore with a 30 GB persistent
disk at `/var/data`. The combined ASGI server serves the SPA and API at the same
origin. The startup supervisor maps data directories to the disk, drops to UID
10001 and forwards shutdown signals to the API and optional daily scheduler.
Render supplies HTTPS, so Caddy is used only for the alternative Linux-server
deployment below.

The Blueprint starts with the smallest paid compute plan. Confirm actual memory
use before enabling scheduled ingestion or serving concurrent prediction jobs;
large historical jobs may require a larger compute plan. No sizing benchmark
has established that 512 MB supports the complete workload.

After the first successful Render build, transfer `data/`, `dataset/`, `outputs/`
and `backend/cache/` to the same paths under `/var/data` using Render SSH/SCP.
Keep ingestion disabled during the transfer. Run from the Render service shell:

```sh
cd /app
python deploy/check_data.py
```

Verify the public map, all historical windows, CSV downloads and an event outlook.
Then set `FLAMESEEK_DAILY_ENABLED=true` and redeploy. Set `FIRMS_MAP_KEY` through
Render's environment settings. Secrets are not present in `render.yaml`.

Blueprint planning is separate from applying infrastructure. The Render connector
requires approval of the generated plan before its first application. Dataset
transfer also requires working Render SSH access; the connector cannot upload
the local 19.4 GB data collection itself.

Includes React/Cesium, FastAPI, LightGBM prediction code, XGBoost and geospatial
pipeline dependencies, daily ingestion, and Caddy HTTPS. All local datasets,
snapshots, outputs and caches are mounted in their original layout. Only reviewed
CSV files are exposed by the existing download API.

## Server preparation

Use a Linux server with Docker Engine and the Compose plugin. Point your domain
at the server and allow TCP ports 80/443 (optional UDP 443). Size disk and RAM
using `data-inventory.json`; leave space for growing history, backups and images.

Securely copy the project to `/srv/flameseek`, including ALL of `data/`, `dataset/`,
`outputs/`, `params/`, `backend/cache/`, and `frontend/public/site-data/`.
Git ignores most datasets, so a GitHub clone alone is insufficient. Exclude `.git`,
`.env*`, node_modules, virtual environments, logs and test temp directories.
Stop ingestion and analysis writers during the final transfer to keep SQLite,
WAL files, snapshots and their manifest consistent. Retain the local originals.

Run from the repository root on the Linux server:

```sh
cp deploy/production.env.example deploy/production.env
# Edit production.env: FIRMS_MAP_KEY, SITE_ADDRESS, TLS_EMAIL.
mkdir -p data dataset outputs backend/cache
sudo chown -R 10001:10001 data outputs backend/cache
docker compose -f deploy/compose.yml build
docker compose -f deploy/compose.yml run --rm --no-deps -w /app backend python deploy/check_data.py
docker compose -f deploy/compose.yml up -d
docker compose -f deploy/compose.yml ps
docker compose -f deploy/compose.yml logs --tail=100 backend daily
```

UID 10001 also needs read access to `dataset/`. Caddy obtains and renews HTTPS
certificates. Only 80/443 are exposed publicly. Same-origin API proxying avoids
public backend URLs and production CORS changes. One API worker preserves the
existing in-memory job tracking.

## Verification

```sh
curl --fail https://YOUR_DOMAIN/health
curl --fail https://YOUR_DOMAIN/api/datasets
curl --fail https://YOUR_DOMAIN/meta
curl --fail https://YOUR_DOMAIN/api/pipeline/status
```

Open `/fire-map` and a historical record. Search a place, download a CSV, and run
an event's Past/Future/Exposure analysis. Forecasts retain existing validation
rules and may return FORECAST WITHHELD for insufficient history. Installing
dependencies does not create a validated model. The XGBoost module requires five
years under current settings; starting the deployment does not retrain it.

Optional Cesium/Google credentials must be supplied at frontend BUILD time.
Runtime Vite environment variables cannot change an already built frontend.
Local `.env` files are excluded from images.

Daily ingestion runs immediately and then at 02:00 UTC (08:00 Bangladesh), retrying
hourly after partial/failing runs. The API refreshes live hotspots every 12 minutes.

## Maintenance

Stop `daily` and `backend` before backing up all mounted directories together;
restart afterward. Preserve canonical SQLite/WAL files, manifest, snapshots,
raw observations, outputs and caches together. Securely back up production.env
separately. Retain Caddy volumes for certificate state.

For updates, retain host data and secrets, rebuild, check data, then run `up -d`.
Do not replace data directories with empty Git checkouts.

For local container testing with backend/.env set, run `docker compose up --build`
from the repository root and open http://localhost:5173. Public deployment uses
`deploy/compose.yml` instead.
