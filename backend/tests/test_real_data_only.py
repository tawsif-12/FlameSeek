from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import firms_client
from demo_data import dhaka_demo_hotspots, scenario_for


def test_scripted_data_is_disabled():
    assert dhaka_demo_hotspots() == []
    assert scenario_for({"lat": 23.9, "lon": 90.3, "detections": [{"place_hint": "Ashulia"}]}) is None


def test_recent_cache_never_rebases_old_observations():
    cache_root = MagicMock()
    cache = cache_root.__truediv__.return_value
    cache.exists.return_value = True
    source = firms_client.FIRMS_NRT_SENSOR_SOURCES["modis"]
    cached_file = MagicMock()
    cached_file.name = f"{source}_world.csv"
    cached_file.stat.return_value.st_mtime = 1
    cached_file.read_text.return_value = "cached source"
    cache.rglob.return_value = [cached_file]
    now = datetime.now(timezone.utc)
    rows = [
        {"sensor": "modis", "lat": 1.0, "lon": 2.0, "acq_datetime": now - timedelta(days=90)},
        {"sensor": "modis", "lat": 3.0, "lon": 4.0, "acq_datetime": now - timedelta(hours=1)},
    ]
    with patch.object(firms_client, "CACHE_DIR", cache_root), patch.object(firms_client, "_parse_csv", return_value=rows):
        result = firms_client._cached_actual_hotspots(None, ["modis"], 1)
    assert result == [rows[1]]
