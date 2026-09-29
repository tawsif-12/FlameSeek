# Burning_Activity

A global, evidence-driven fire monitoring, verification and forecasting platform built on NASA MODIS and VIIRS active-fire observations.

**Past → Present → Identify → Verify → Compare → Forecast → Exposure**
(Fire Memory → Fire Now → Fire Identity → Fire Evidence → Fire Past → Fire Future → Exposure)

A satellite hotspot is an observation, not automatically a confirmed wildfire, and the absence of a hotspot is not proof that no fire exists. Every result is labelled as one of four things:

| Layer | Meaning |
|---|---|
| **Observation** | What MODIS/VIIRS actually detected (sensor, time, footprint, FRP, confidence) |
| **Inference** | What the system concludes (harmonized activity, anomalies, events, behaviour, evidence status) |
| **External evidence** | What independent satellites, agencies and news report, always with the original link |
| **Forecast** | Where new satellite-observed activity may appear in the next 6–24 h, or `FORECAST WITHHELD` |

## Running it

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
python -m pytest

# frontend
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

`backend/.env`:

```env
FIRMS_MAP_KEY=your_nasa_firms_key      # required: https://firms.modaps.eosdis.nasa.gov/api/map_key/
NEWS_API_KEY=your_newsapi_key          # optional: adds NewsAPI articles to GDELT
```

`frontend/.env.local` (optional): `VITE_API_BASE_URL`, `VITE_CESIUM_ION_TOKEN` (terrain and imagery), `VITE_GOOGLE_MAPS_API_KEY` (photorealistic tiles).

All other data sources are free and keyless. Responses are cached under `backend/cache/`; FIRMS science archives are cached permanently, so the first Fire Memory or event outlook for an area takes minutes and later runs take seconds. The FIRMS key allows 5000 transactions per 10 minutes. The backend reads the key's live usage: interactive requests fail fast with a clear message when the budget is nearly spent, and long jobs wait for the window to roll over.

## Where each capability lives

| Spec section | Implementation |
|---|---|
| 1–2 MODIS/VIIRS integration, sensor harmonization | `firms_client.py` (NRT and science archives, GOES, Landsat), `harmonize.py` (median MODIS/VIIRS ratio on co-observed day-blocks yields the *Harmonized Observed Burning Activity*) |
| 3 Footprint-aware mapping | `geo.py`: FIRMS scan × track footprints, fractional attribution to the ~1 km grid, location uncertainty. The globe draws the footprints of the selected event |
| 4 Observation quality | `quality.py`: six observation classes, Observation Sufficiency Score, `UNKNOWN` / `AMBIGUOUS` / `INSUFFICIENT OBSERVATION`, provenance |
| 5 3D globe (Fire Now) | `CesiumFireGlobe.tsx`: far-side occlusion; last 24 h / 48 h / 5 days or any historical date; event, corridor and exposure layers |
| 6 Area of interest | Country, state, district, forest or protected-area search (OSM Nominatim), rectangle, custom polygon, radius (`AOISelector.tsx`, globe AOI tools, `geo.AOI`) |
| 7–9 Calendar, seasonal profile, current vs historical | `routers/memory.py`, `seasonal.py`, Fire Memory page |
| 10 Anomalies | Robust median/MAD z: Normal, Above Normal, Unusual, Highly Unusual |
| 11 Change points | `changepoint.py`: PELT, reported as *statistically detected changes* |
| 12–13 Fire events and behaviour | `events.py`: spatio-temporal linking, event attributes, association confidence, *Inferred Fire Behaviour States* |
| 14 Reverse geocoding | `geocode.py`: country to village, nearest settlement, forests and protected areas, nearby non-fire heat sources |
| 15 Regional satellites | `corroboration.py`: other MODIS/VIIRS platforms, GOES (Americas), Landsat (US/CA), Sentinel-2 scenes, EFFIS (Europe/MENA), CWFIS M3 (Canada); Himawari and Meteosat as review links |
| 16 Government sources | GDACS (global), NIFC WFIGS (US, including prescribed burns), NSW RFS; per-country agency directory (`source_directory.py`) |
| 17–20 News, NLP, geographic and temporal matching | `evidence.py`, `nlp.py`: GDELT (plus optional NewsAPI), event-type classification, cause, impact, area, infrastructure; geocoded distance and time-to-detection scoring |
| 21–25 Fusion, status, score, explanation, news panel | `evidence.fuse`: component breakdown, status labels, generated explanation; original source vs system summary vs system interpretation in the UI |
| 26–27 Historical analogues | `history.py`, `analogues.py`: same-age truncation, KNN with shrinkage-regularized Mahalanobis distance, outcomes |
| 28–31 Forecast | `forecast.py`: persistence, seasonal and wind-only baselines vs LightGBM on temporal and spatial holdouts (Brier, BSS, POD, FAR, CSI, footprint IoU, calibration); probability corridor or `FORECAST WITHHELD` |
| 32 Exposure | `exposure.py`: WorldPop population and OSM settlements, roads, farmland, forests, protected areas, schools, hospitals, power, critical facilities |
| 33 Event side panel | `EventPanel.tsx`: Satellite, Event, Quality, Evidence, Past, Future and Exposure tabs; `/fire-map?event=EV-…` deep links |

## Honest limits

- **Evidence score** weights are expert-set, so the score is evidence strength, not a probability. "Confirmed Fire" is used only when an official incident report lies within 15 km and matches in time, and no controlled burn is reported.
- **Cloud cover** comes from ERA5 reanalysis and is a proxy for the satellites' own cloud masks.
- **NLP** is transparent rule-based extraction, not a trained language model. News summaries are generated from extracted facts and are labelled as system-generated.
- **Himawari, Meteosat and most national agencies** have no public machine-readable fire feed, so they are linked for manual review and never counted as checked.
- **Forecasts** predict *satellite-observed activity*, not fire spread. They do not use land cover or fuel moisture. Training uses reanalysis winds for the forecast window (perfect-prognosis), so live skill may be lower than the holdout scores. When the chosen model's skill against climatology is negative, the UI says so.
- **Fire Memory** accepts areas up to 20° across. Histories longer than about 10 years make thousands of FIRMS requests the first time.

## API

`GET /api/current_hotspots` · `GET /api/events` · `GET /api/events/{id}` · `POST /api/events/{id}/evidence` (job) · `POST /api/events/{id}/outlook` (job: analogues, forecast, exposure) · `POST /api/fire_memory` (job) · `GET /api/jobs/{id}` · `GET /api/places/search` · `GET /api/places/reverse` · `POST /api/generate_calendar` · `POST /api/critical_periods` · `GET /api/verified_hotspots` · `GET /data-sources`. Interactive docs are at `/docs`.
