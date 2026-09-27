from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/data-sources")
async def data_sources() -> dict:
    return {
        "sources": [
            {
                "name": "NASA FIRMS",
                "description": "Fire Information for Resource Management System Area API for active fire hotspots.",
                "url": "https://firms.modaps.eosdis.nasa.gov/",
                "last_verified": "2026-09-25",
            },
            {
                "name": "FIRMS Historical Downloads",
                "description": "CSV/SHP archive downloads for historical active fire data.",
                "url": "https://firms.modaps.eosdis.nasa.gov/download/",
                "last_verified": "2026-09-25",
            },
            {
                "name": "NASA Earthdata Search",
                "description": "Catalog for discovering MODIS and VIIRS gridded fire products.",
                "url": "https://search.earthdata.nasa.gov/",
                "last_verified": "2026-09-25",
            },
            {
                "name": "MODIS Thermal Anomalies/Fire",
                "description": "MOD14/MYD14 active fire products with roughly 1 km detections.",
                "url": "https://www.earthdata.nasa.gov/data/instruments/modis",
                "last_verified": "2026-09-25",
            },
            {
                "name": "VIIRS Thermal Anomalies and Fire",
                "description": "SNPP, NOAA-20, and NOAA-21 VIIRS active fire products with 375 m detections.",
                "url": "https://www.earthdata.nasa.gov/data/instruments/viirs",
                "last_verified": "2026-09-25",
            },
            {
                "name": "NASA Worldview",
                "description": "Imagery viewer used to visually verify selected fire dates.",
                "url": "https://worldview.earthdata.nasa.gov/",
                "last_verified": "2026-09-25",
            },
            {
                "name": "GDELT Project",
                "description": "Fast global news/events feed used to corroborate fire, smoke, burning, and disaster reports near detections.",
                "url": "https://www.gdeltproject.org/",
                "last_verified": "2026-09-25",
            },
            {
                "name": "Regional confirmation sources",
                "description": "Sentinel, Landsat, INPE, LAPAN, FSI, Bhuvan, and Global Forest Watch can validate burn scars or local corrections after FIRMS detection.",
                "url": "https://www.globalforestwatch.org/map/",
                "last_verified": "2026-09-25",
            },
        ]
    }
