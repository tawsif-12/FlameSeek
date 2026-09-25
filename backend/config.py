"""Application settings and harmonization constants."""

from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv


load_dotenv()


APP_NAME = "burning-activity-calendar-api"
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "DEMO_KEY")

CONFIDENCE_THRESHOLD = 30.0
VIIRS_CONFIDENCE_MAP = {"l": 25.0, "n": 60.0, "h": 90.0}
GRID_RES = 0.01
ANOMALY_THRESHOLD = 2.0
MAX_DAY_RANGE_PER_REQUEST = 5
MAX_AOI_DEGREES_SPAN = 20
MAX_DATE_RANGE_DAYS = 365 * 5
DEFAULT_SENSORS = ["modis", "viirs_snpp", "viirs_noaa20", "viirs_noaa21"]
FIRMS_NRT_SENSOR_SOURCES = {
    "modis": "MODIS_NRT",
    "viirs_snpp": "VIIRS_SNPP_NRT",
    "viirs_noaa20": "VIIRS_NOAA20_NRT",
    "viirs_noaa21": "VIIRS_NOAA21_NRT",
}
FIRMS_SP_SENSOR_SOURCES = {
    "modis": "MODIS_SP",
    "viirs_snpp": "VIIRS_SNPP_SP",
    "viirs_noaa20": "VIIRS_NOAA20_SP",
}
FIRMS_NRT_START_DATE = date(2026, 7, 1)
