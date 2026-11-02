"""Shared fixtures: settings and a builder for synthetic FIRMS rows."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import ingest  # noqa: E402
from pipeline.config import load_settings  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    c = load_settings()
    c["study_bbox"] = None  # synthetic points may fall anywhere
    return c


def firms_rows(rows: list[dict]) -> pd.DataFrame:
    """Rows in raw FIRMS format. Defaults to a nominal VIIRS S-NPP daytime pixel at nadir."""
    base = {"latitude": 23.8, "longitude": 90.4, "scan": 0.39, "track": 0.36, "acq_date": "2026-11-02",
            "acq_time": 730, "satellite": "N", "instrument": "VIIRS", "confidence": "n",
            "version": "2.0NRT", "frp": 5.0, "daynight": "D", "bright_ti4": 330.0, "bright_ti5": 290.0,
            "brightness": None, "bright_t31": None}
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["source_file"], out["source_row"] = "synthetic", range(len(out))
    return out


@pytest.fixture
def make_detections(cfg):
    def _make(rows):
        return ingest.standardize(firms_rows(rows), cfg)
    return _make


# Window outputs of the default window (python run_pipeline.py --window current_2026).
PROCESSED = ROOT / "data" / "processed" / "windows" / "current_2026"
INTERIM = ROOT / "data" / "interim" / "windows" / "current_2026"
real_outputs = pytest.mark.skipif(not (PROCESSED / "fire_events.csv").exists(),
                                  reason="run `python run_pipeline.py` first")
