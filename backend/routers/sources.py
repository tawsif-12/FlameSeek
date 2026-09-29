from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()

_VERIFIED = "2026-09-29"

SOURCES = [
    ("Observation", "NASA FIRMS Area API", "MODIS (MCD14) and VIIRS 375 m (SNPP, NOAA-20, NOAA-21) active fire detections, NRT and science-quality archives since Nov 2000.", "https://firms.modaps.eosdis.nasa.gov/", "automated"),
    ("Observation", "FIRMS data availability", "Per-source archive date ranges; used to tell a missing observation opportunity from a valid 'no fire' day.", "https://firms.modaps.eosdis.nasa.gov/api/data_availability/", "automated"),
    ("Observation quality", "Open-Meteo / ERA5", "Reanalysis cloud cover (observation sufficiency proxy), wind, humidity and temperature for analogues and forecasts.", "https://open-meteo.com/", "automated"),
    ("Regional satellite", "GOES-East/West fire product (FIRMS)", "Geostationary detections for the Americas every 10 minutes; independent confirmation of polar-orbiter detections.", "https://firms.modaps.eosdis.nasa.gov/", "automated"),
    ("Regional satellite", "Landsat 8/9 active fire (FIRMS)", "30 m detections over the US and Canada.", "https://firms.modaps.eosdis.nasa.gov/", "automated"),
    ("Regional satellite", "Sentinel-2 L2A (Earth Search STAC)", "Scene availability and cloud cover for visual burn-scar/smoke review in the Copernicus Browser.", "https://earth-search.aws.element84.com/v1", "automated"),
    ("Regional satellite", "EFFIS burnt areas (Copernicus EMS)", "Mapped burnt areas for Europe, the Middle East and North Africa.", "https://effis.jrc.ec.europa.eu/", "automated"),
    ("Regional satellite", "CWFIS M3 fire perimeters", "Canada's national satellite fire perimeters (Natural Resources Canada).", "https://cwfis.cfs.nrcan.gc.ca/", "automated"),
    ("Regional satellite", "Himawari-9 (RAMMB/CIRA SLIDER)", "Asia-Pacific geostationary imagery; linked for manual review (no public fire API).", "https://rammb-slider.cira.colostate.edu/", "review link"),
    ("Regional satellite", "Meteosat (EUMETView)", "Europe/Africa geostationary imagery; linked for manual review.", "https://view.eumetsat.int/", "review link"),
    ("Regional satellite", "NASA Worldview", "True-colour and thermal anomaly imagery for smoke plumes and burn scars.", "https://worldview.earthdata.nasa.gov/", "review link"),
    ("Official", "GDACS", "UN / European Commission global disaster alerts for large wildfires.", "https://www.gdacs.org/", "automated"),
    ("Official", "NIFC WFIGS incidents", "US wildland fire incidents, including prescribed (RX) burns.", "https://data-nifc.opendata.arcgis.com/", "automated"),
    ("Official", "NSW Rural Fire Service", "New South Wales major incidents feed, including hazard-reduction burns.", "https://www.rfs.nsw.gov.au/fire-information/fires-near-me", "automated"),
    ("Official", "National agencies (per country)", "Fire services, forestry departments and disaster agencies listed per country; linked where no machine-readable feed exists.", "", "review link"),
    ("News", "GDELT DOC 2.0", "Global English-language news search, filtered by place names from reverse geocoding.", "https://www.gdeltproject.org/", "automated"),
    ("News", "NewsAPI (optional)", "Additional English-language articles when NEWS_API_KEY is set.", "https://newsapi.org/", "optional"),
    ("Geography", "OpenStreetMap Nominatim", "Reverse geocoding (country to village) and place search for area selection.", "https://nominatim.org/", "automated"),
    ("Geography", "OpenStreetMap Overpass", "Forests, protected areas, known heat sources and exposure assets (roads, schools, hospitals, power, farmland).", "https://overpass-api.de/", "automated"),
    ("Exposure", "WorldPop", "Modelled 2020 population inside the forecast corridor.", "https://www.worldpop.org/", "automated"),
    ("Terrain", "Open-Meteo elevation (Copernicus DEM)", "Elevation for upslope/downslope forecast features.", "https://open-meteo.com/en/docs/elevation-api", "automated"),
]


@router.get("/data-sources")
async def data_sources() -> dict:
    return {
        "sources": [
            {"group": group, "name": name, "description": description, "url": url, "access": access, "last_verified": _VERIFIED}
            for group, name, description, url, access in SOURCES
        ]
    }
