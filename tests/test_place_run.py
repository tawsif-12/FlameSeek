"""Per-place pipeline on a tiny input: a two-detection day (pandas 3 RangeIndex overflow with
int64 hash ids), a day whose detections all fall outside the place (zero-row quality step),
and month partitions of mixed types at finalize. Also checks the summary's inside-the-place rule."""
import json
import shutil
import uuid
from datetime import date

import numpy as np
import pytest

from pipeline import place_run, stages
from pipeline.config import ROOT

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
ROWS = [  # two nominal detections 400 m apart on one day; one far outside the place next day
    "22.000,89.000,330.1,0.40,0.37,2023-01-02,725,N,VIIRS,n,2,296.0,3.10,D,0",
    "22.003,89.002,328.7,0.40,0.37,2023-01-02,725,N,VIIRS,n,2,295.5,2.40,D,0",
    "25.000,92.000,331.0,0.40,0.37,2023-01-03,710,N,VIIRS,n,2,296.2,4.00,D,0",
]
BBOX = [88.9, 21.9, 89.1, 22.1]


@pytest.fixture
def place(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "VIIRS_SNPP_SP.csv").write_text(HEADER + "\n".join(ROWS) + "\n")
    pid = f"pytest_{uuid.uuid4().hex[:8]}"
    yield pid, raw
    shutil.rmtree(ROOT / "data" / "places" / pid, ignore_errors=True)


def _extreme_ids(files, rows):
    """Neighbouring rows get huge ids of opposite sign: their difference overflows int64, which is
    what made pandas 3 build an empty RangeIndex for a two-detection day."""
    r = np.asarray(rows, dtype=np.int64)
    return np.where(r % 2 == 0, -9_000_000_000_000_000_000 + r, 9_000_000_000_000_000_000 - r).astype(np.int64)


def test_place_pipeline_end_to_end(place, monkeypatch):
    pid, raw = place
    monkeypatch.setattr(stages, "stable_ids", _extreme_ids)
    cfg = place_run.place_cfg(pid, raw, date(2023, 1, 1), date(2023, 1, 4), BBOX)
    fin = place_run.run_stages(cfg, workers=1)
    out = place_run.summarize(cfg, fin, pid, BBOX, None, 0.0)

    assert out["quality"]["clean_detections"] == 2          # the detection outside the place is not counted
    assert out["quality"]["events"] == 1                    # the two neighbours link into one event
    assert out["quality"]["energy_conservation"]["pass"]
    assert [y["n_events"] for y in out["yearly"]] == [1]
    assert out["yearly"][0]["calibration"]["version"] in ("v1", "v2", None)
    cells = out["hotspot_map"]["cells"]
    assert len(cells) == 1 and cells[0]["days"] == 1        # map uses the same inside rule as the counts
    assert BBOX[0] <= cells[0]["lon"] <= BBOX[2] and BBOX[1] <= cells[0]["lat"] <= BBOX[3]
    json.dumps(out, default=str)                            # summary is serializable for the API
