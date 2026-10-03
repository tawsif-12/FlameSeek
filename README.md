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

## Four-Witness Fire Intelligence

The four fire satellites (Terra and Aqua MODIS, Suomi NPP and NOAA-20 VIIRS, plus NOAA-21) are treated as witnesses with known blind spots, following the *Four-Witness Fire Intelligence* solution report.

**Harmonization (`witness.py`)** runs the report's eight stages:

1. Detections from FIRMS, with observation opportunities from sensor availability and ERA5 cloud cover.
2. Vegetation fires only (FIRMS `type` 0), confidence filter, local solar time, pixel area, 0.1° cell.
3. MODIS same-overpass duplicates within 1 km merged (higher FRP kept); 375 m VIIRS pixels grouped into ~1 km clusters.
4. A **sensor detection profile**, P(MODIS detects | VIIRS FRP, pixel area), learned by logistic regression on Aqua/S-NPP matchups within 20 minutes (pre-drift years first), plus the MODIS/VIIRS FRP relation. Falls back to the Li et al. (2020) prior (50% at 4.3 MW nadir, 31.7 MW scan edge).
5. A daily fire curve fitted from Terra/Aqua and VIIRS day/night ratios (per month where data allow). Every observation is converted to its Aqua 13:30 equivalent, which also removes orbit-drift artifacts.
6. **Two tiers.** The *consistent record* (MODIS sensitivity, 2000 to now) drives the calendar, trends and anomalies. The *detailed layer* (every VIIRS detection) drives the globe.
7. Activity per **clear-sky look**: swath width / ground-track spacing at the latitude × clear fraction. This fixes equator gaps, polar over-sampling and cloudy days.
8. A **fused fire probability** per cell and local day. It starts from the cell's historical rate for that month; each detection raises the odds and each clear miss lowers them, weighted by that witness's detection chance; cloudy looks are ignored.

Fire Memory reports the **continuity test** (raw vs consistent ratio across the 2012 and 2018 sensor starts) and the **hide-one-witness test** (remove NOAA-20, then check how well the fused probability predicts its detections: AUC and Brier vs the historical rate alone).

**Fire Cases (`fire_case.py`, `overpass.py`)** open a case for every event and gather evidence from three streams into one time-ordered evidence block:

- **Stream A:** later polar passes. They are predicted with skyfield from current TLEs and classified as seen stronger/weaker, spread, clear miss, cloud/smoke or not covered.
- **Stream B:** GOES start/duration/end; Himawari and Meteosat as review links.
- **Stream C:** NLP-matched news and official reports.
- **Background facts:** land use, nearby heat sources, the local burning season and repeat heat on the same spot over the previous five years.

Each item votes for categories weighted by its reliability. The answer has three parts: **Is it real? What kind? What is it doing now?** A type is named only when the top category scores above 50% and leads the next by 20 points. Cases stay provisional until every satellite has passed or 24 h have elapsed. The open panel re-gathers evidence every 10 minutes. On the globe, a case marker is hollow until evidence is gathered; its fill colour shows the fire type, its outline weight the confirmation level, and it fades once the fire has ended.

### Demo scenarios

`backend/demo_data.py` scripts three complete Fire Cases in Bangladesh for walkthroughs and videos: a garment factory fire at Ashulia (Dhaka), paddy-straw burning at Shibganj (Bogura) and a forest fire in the Sundarbans' Chandpai range. Each has a fire-power curve and a cloud curve, sampled at realistic overpass times to produce the detections. The matching pass schedule, Himawari timeline, official report, news items, place, land use and burning-season history feed the case without any external calls, so the answer appears in stages over about 7 seconds. On Fire Now, choose the **Bangladesh** location: the three cases verify themselves and their markers fill in.

`backend/demo_outlook.py` scripts the **Past, Future and Exposure** tabs for the same three fires: five historical analogues each, a 6/12/24 h probability corridor stretched downwind with model-validation tables, and population, roads and facilities inside the corridor. "Run analysis" finishes in about 6 seconds.

All of this is synthetic. Outlets, reports and figures are invented (marked "(demo)"), have no links, and results carry `demo_scenario`. Edit `SCENARIOS` to change a story, or empty the list to run on live data only.

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
| 1–2 MODIS/VIIRS integration, sensor harmonization | `firms_client.py` (NRT and science archives, GOES, Landsat), `witness.py` (Four-Witness pipeline: detection profile, time of day, two tiers, effort, fused probability), `harmonize.py` (daily series and anomalies on the consistent record) |
| Fire Cases | `fire_case.py` (streams A/B/C, category votes, decision rules, three-part answer), `overpass.py` (skyfield + CelesTrak TLEs) |
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
- **Observation effort** uses orbit geometry and ERA5 cloud, not the MOD14A1/MYD14A1/VNP14A1/VJ114A1 daily masks (these need an Earthdata login). Detection profiles are regional and learned per area; land cover is not a profile input because FIRMS carries none.
- **Fire Case category percentages** are evidence scores, not calibrated probabilities, until they are tested on labelled cases. A clear miss after a short burn is weak evidence, and a missing news report is weaker still.
- **Fire Memory** accepts areas up to 20° across. Histories longer than about 10 years make thousands of FIRMS requests the first time.

## API

`GET /api/current_hotspots` · `GET /api/events` · `GET /api/events/{id}` · `GET /api/events/{id}/case` · `POST /api/events/{id}/evidence` (job, includes the Fire Case) · `POST /api/events/{id}/outlook` (job: analogues, forecast, exposure) · `POST /api/fire_memory` (job) · `GET /api/jobs/{id}` · `GET /api/places/search` · `GET /api/places/reverse` · `POST /api/generate_calendar` · `POST /api/critical_periods` · `GET /api/verified_hotspots` · `GET /data-sources`. Interactive docs are at `/docs`.
