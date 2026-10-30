from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()

_VERIFIED = "2026-09-29"

SOURCES = [
    ("Observation", "NASA FIRMS Area API", "MODIS (MCD14) and VIIRS 375 m (SNPP, NOAA-20, NOAA-21) active fire detections, science-quality archives since Nov 2000.", "https://firms.modaps.eosdis.nasa.gov/", "automated"),
    ("Observation", "FIRMS data availability", "Per-source archive date ranges; used to tell a missing observation opportunity from a valid 'no fire' day.", "https://firms.modaps.eosdis.nasa.gov/api/data_availability/", "automated"),
    ("Observation quality", "Open-Meteo / ERA5", "Reanalysis cloud cover (observation sufficiency proxy), used for observation sufficiency.", "https://open-meteo.com/", "automated"),
    ("Regional satellite", "Himawari-9 (RAMMB/CIRA SLIDER)", "Asia-Pacific geostationary imagery; linked for manual review. Not yet used in the calendar.", "https://rammb-slider.cira.colostate.edu/", "review link"),
    ("Regional satellite", "NASA Worldview", "True-colour and thermal anomaly imagery for smoke plumes and burn scars.", "https://worldview.earthdata.nasa.gov/", "review link"),
    ("Geography", "OpenStreetMap Nominatim", "Reverse geocoding (country to village) and place search for area selection.", "https://nominatim.org/", "automated"),
]


@router.get("/data-sources")
async def data_sources() -> dict:
    return {
        "sources": [
            {"group": group, "name": name, "description": description, "url": url, "access": access, "last_verified": _VERIFIED}
            for group, name, description, url, access in SOURCES
        ]
    }
