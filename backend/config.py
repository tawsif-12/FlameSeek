"""Application settings and harmonization constants."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


APP_NAME = "burning-activity-api"
APP_VERSION = "0.3.0"
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

BACKEND_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("BURNING_ACTIVITY_CACHE_DIR", BACKEND_DIR / "cache"))
HTTP_USER_AGENT = os.getenv("HTTP_USER_AGENT", "Burning_Activity/0.3 (NASA Space Apps research prototype)")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_AVAILABILITY_URL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "DEMO_KEY")
# FIRMS allows 5000 transactions per 10 minutes; stay below it so interactive calls keep working during long jobs.
FIRMS_TRANSACTION_BUDGET = int(os.getenv("FIRMS_TRANSACTION_BUDGET", "4200"))
FIRMS_TRANSACTION_WINDOW_SECONDS = 600
FIRMS_RECENT_CACHE_TTL_SECONDS = 15 * 60

CONFIDENCE_THRESHOLD = 30.0
VIIRS_CONFIDENCE_MAP = {"l": 25.0, "n": 60.0, "h": 90.0}
LANDSAT_CONFIDENCE_MAP = {"l": 25.0, "m": 60.0, "h": 90.0}
# ~1 km: the MODIS active-fire pixel size at nadir is the common analytical grid.
GRID_RES = 0.01
ANOMALY_THRESHOLD = 2.0
MAX_DAY_RANGE_PER_REQUEST = 5
MAX_AOI_DEGREES_SPAN = 20
MAX_DATE_RANGE_DAYS = 365 * 5
MAX_HISTORY_YEARS = 26
DEFAULT_SENSORS = ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]
HISTORY_SENSORS = ["modis", "viirs_snpp", "viirs_noaa20"]
FIRMS_NRT_SENSOR_SOURCES = {
    "modis": "MODIS_NRT",
    "viirs_snpp": "VIIRS_SNPP_NRT",
    "viirs_noaa20": "VIIRS_NOAA20_NRT",
    "viirs_noaa21": "VIIRS_NOAA21_NRT",
    "goes": "GOES_NRT",
    "landsat": "LANDSAT_NRT",
}
FIRMS_SP_SENSOR_SOURCES = {
    "modis": "MODIS_SP",
    "viirs_snpp": "VIIRS_SNPP_SP",
    "viirs_noaa20": "VIIRS_NOAA20_SP",
}
FIRMS_NRT_START_DATE = date(2026, 7, 1)

# First day each sensor can provide an observation opportunity (used for observation sufficiency).
SENSOR_START_DATES = {
    "modis": date(2000, 11, 1),
    "viirs_snpp": date(2012, 1, 20),
    "viirs_noaa20": date(2018, 4, 1),
    "viirs_noaa21": date(2024, 1, 17),
    "goes": date(2022, 8, 9),
    "landsat": date(2022, 6, 20),
}

# Nominal pixel size at nadir (km); used when FIRMS scan/track are missing.
NOMINAL_PIXEL_KM = {
    "modis": 1.0,
    "viirs_snpp": 0.375,
    "viirs_noaa20": 0.375,
    "viirs_noaa21": 0.375,
    "goes": 2.0,
    "landsat": 0.03,
}
# Approximate geolocation accuracy (km) added to footprint uncertainty.
GEOLOCATION_ERROR_KM = {
    "modis": 0.25,
    "viirs_snpp": 0.15,
    "viirs_noaa20": 0.15,
    "viirs_noaa21": 0.15,
    "goes": 2.0,
    "landsat": 0.05,
}

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
