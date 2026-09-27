# FireHarmony

FireHarmony is a global, evidence-driven fire intelligence platform. It harmonizes NASA MODIS and VIIRS active-fire observations, visualizes current hotspots on a 3D Earth, analyzes historical burning patterns, and helps validate whether a thermal anomaly is likely to represent a real fire.

The project is designed to answer more than "Where did a satellite detect heat?"

- Is this likely to be a real fire?
- Is this activity normal for this place and season?
- Do other satellite or regional sources support the detection?
- Are local authorities or newspapers reporting the same event?
- How strong is the combined evidence?

## Core Workflow

```text
MODIS + VIIRS
      ->
Data Harmonization
      ->
Historical Fire Database
      ->
3D Interactive Globe
      ->
Area of Interest Selection
      ->
Burning Activity Calendar
      ->
Current vs Historical Comparison
      ->
Unusual Activity Detection
      ->
Hotspot Selection
      ->
Reverse Geocoding
      ->
Regional Satellite / Government Sources
      ->
Country-Specific English News Sources
      ->
NLP Event Extraction
      ->
Geographic Matching
      ->
Temporal Matching
      ->
Evidence Fusion
      ->
Fire Validation Status
      ->
Explainable Evidence + News Sources
```

## Main Capabilities

### 3D Fire Globe

The app plots MODIS and VIIRS hotspots directly on a Cesium 3D globe using real latitude and longitude values from NASA FIRMS. Hotspots on the far side of the Earth are hidden so the globe behaves like a solid planet rather than a transparent sphere.

The globe can show:

- MODIS-only detections in green
- VIIRS-only detections in yellow
- Nearby MODIS + VIIRS cross-sensor detections in red

Cross-sensor merging currently uses a configurable proximity concept: MODIS and VIIRS detections are treated as nearby confirmation when they occur close together in space and time.

### Burning Activity Calendar

For a selected area of interest, the backend fetches historical MODIS and VIIRS observations and builds a daily activity series. This supports analysis of seasonal burning patterns, recurring fire windows, unusually active periods, and current activity compared with expected historical behavior.

### Fire Confirmation and Evidence

MODIS or VIIRS detecting a hotspot does not automatically prove there is a wildfire. Heat signatures can come from wildfires, agricultural burning, controlled burns, industrial heat, gas flares, volcanoes, bare heated land, or other sources.

When a user clicks a hotspot, the app starts a second-stage evidence workflow:

1. Show original satellite detection details
2. Reverse-geocode the hotspot location
3. Select relevant regional satellite, environmental, and government sources
4. Search country-specific English-language news sources
5. Classify article/event relevance with rule-based NLP scoring
6. Compare article location and time against the hotspot
7. Fuse evidence into a final validation status
8. Show transparent reasoning and source links

### Validation Statuses

The evidence engine returns one of:

- `CONFIRMED FIRE`
- `HIGHLY LIKELY FIRE`
- `POSSIBLE FIRE - NEEDS VERIFICATION`
- `LIKELY NON-FIRE THERMAL ANOMALY`
- `NO EXTERNAL CONFIRMATION`

The score shown in the UI is a `System Evidence Score`, not a scientifically validated probability.

## Evidence Panel

The hotspot evidence panel can show:

- Satellite information: sensor, satellite, confidence, FRP, date/time, day/night
- Location information: country, region, locality, coordinates
- Validation stages
- Final status and evidence score
- Why the status was assigned
- Uncertainty notes
- Regional satellite/source checklist
- Government source checklist
- Local/national news cards
- AI-generated interpretation, clearly separated from original source links

Each news card may include:

- Headline
- Publication
- Country
- Published time
- Mentioned location
- Event type
- Location/time/relevance scores
- AI summary
- Original article URL

## Real Data vs Current Prototype Logic

Currently implemented as real/live:

- NASA FIRMS MODIS and VIIRS hotspot fetching
- 3D globe plotting from live hotspot coordinates
- FIRMS confidence, FRP, satellite, time, and day/night fields
- NASA Worldview links
- NewsAPI integration
- GDELT fallback search
- Evidence endpoint and cached evidence responses

Currently implemented as prototype/rule-based:

- Reverse geocoding uses fast approximate country/region bounding boxes
- Regional satellite and government source checks are configured source lists, not full live integrations for every agency
- NLP is keyword/location/time scoring, not a trained NER or semantic model
- Evidence fusion weights are heuristic and not scientifically validated

## Backend

The backend is a FastAPI service.

Key endpoints:

- `GET /api/current_hotspots`
- `GET /api/verified_hotspots`
- `POST /api/hotspot_evidence`
- `POST /api/generate_calendar`
- `POST /api/critical_periods`

Environment variables are stored in `backend/.env`:

```env
FIRMS_MAP_KEY=your_nasa_firms_key
NEWS_API_KEY=your_newsapi_key
```

## Frontend

The frontend is a React + Vite app using Cesium for the 3D globe.

Useful commands:

```bash
cd frontend
npm install
npm run dev
npm run build
```

## Backend Commands

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
python -m pytest
```

## Product Principle

FireHarmony preserves two separate ideas:

1. Original satellite detection: what MODIS or VIIRS observed.
2. Validation status: what the broader evidence suggests.

The app should never silently convert a thermal anomaly into a confirmed wildfire. Users should always be able to inspect the underlying evidence, uncertainty, and original sources.
