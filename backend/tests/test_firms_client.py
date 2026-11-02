from __future__ import annotations

from datetime import date

import pytest
import firms_client

from firms_client import FirmsAPIError, _normalize_confidence, _require_firms_key, _source_for_sensor, firms_key_configured


def test_viirs_confidence_mapping():
    assert _normalize_confidence("l", "viirs_snpp") == 25.0
    assert _normalize_confidence("n", "viirs_noaa20") == 60.0
    assert _normalize_confidence("h", "viirs_noaa21") == 90.0


def test_modis_confidence_is_numeric():
    assert _normalize_confidence("72", "modis") == 72.0


def test_historical_dates_use_science_processing_sources():
    assert _source_for_sensor("modis", date(2024, 8, 1)) == "MODIS_SP"
    assert _source_for_sensor("viirs_snpp", date(2024, 8, 1)) == "VIIRS_SNPP_SP"


def test_recent_dates_use_nrt_sources():
    assert _source_for_sensor("modis", date(2026, 8, 1)) == "MODIS_NRT"


def test_placeholder_map_key_fails_locally_with_setup_instructions(monkeypatch):
    monkeypatch.setattr(firms_client, "FIRMS_MAP_KEY", "DEMO_KEY")
    assert not firms_key_configured()
    with pytest.raises(FirmsAPIError) as error:
        _require_firms_key()
    assert error.value.status_code == 503
    assert "backend/.env" in error.value.message


def test_chunks_are_aligned_so_overlapping_periods_share_requests():
    from datetime import date, timedelta
    from firms_client import _chunks, MAX_DAY_RANGE_PER_REQUEST
    end = date(2026, 11, 1)
    short = _chunks(end - timedelta(days=364), end)
    long = _chunks(end - timedelta(days=3650), end)
    for chunks, start in ((short, end - timedelta(days=364)), (long, end - timedelta(days=3650))):
        assert chunks[0][0] == start and sum(d for _, d in chunks) == (end - start).days + 1
        assert all(d <= MAX_DAY_RANGE_PER_REQUEST for _, d in chunks)
    interior = set(short[1:-1])
    assert interior and interior <= set(long)  # every full chunk of the quick look is reused


def test_snap_bbox_contains_area_and_lands_on_grid():
    from firms_client import snap_bbox
    w, s, e, n = snap_bbox((88.676, 21.54, 89.935, 22.50))
    assert (w, s, e, n) == (88.5, 21.5, 90.0, 22.5)
    assert snap_bbox((179.9, -89.9, 180.0, -89.8)) == (179.5, -90.0, 180.0, -89.5)


def test_simultaneous_requests_for_one_chunk_share_a_single_download(monkeypatch):
    import asyncio
    from datetime import date
    import firms_client as fc
    calls = []

    async def fake_get(client, url):
        calls.append(url)
        await asyncio.sleep(0.05)
        return "latitude,longitude\n1,2\n"

    monkeypatch.setattr(fc, "_get_with_retries", fake_get)
    monkeypatch.setattr(fc, "disk_read", lambda *a, **k: None)
    monkeypatch.setattr(fc, "disk_write", lambda *a, **k: None)
    fc._CSV_CACHE.clear()

    async def both():
        return await asyncio.gather(*(fc._fetch_csv(None, "modis", (88.5, 21.5, 90.0, 22.5), date(2020, 3, 1), 5) for _ in range(3)))

    results = asyncio.run(both())
    assert len(calls) == 1 and all(r[0].startswith("latitude") for r in results)
    assert not fc._IN_FLIGHT


def test_place_live_request_is_cut_from_fresh_world_cache_without_nasa_call(monkeypatch):
    import asyncio, time
    import firms_client as fc
    csv = "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n22.0,89.3,2026-11-02,0730,n,5.0,N,D\n10.0,10.0,2026-11-02,0730,n,5.0,N,D\n"
    fc._CSV_CACHE.clear(); fc._WORLD_PARSED.clear()
    fc._CSV_CACHE[(fc.FIRMS_NRT_SENSOR_SOURCES["viirs_snpp"], "world", 1, "recent")] = (time.time(), csv)

    async def boom(*a, **k):
        raise AssertionError("NASA must not be called")

    monkeypatch.setattr(fc, "_fetch_recent_csv", boom)
    rows = asyncio.run(fc.fetch_recent_hotspots((88.5, 21.5, 90.0, 22.5), ["viirs_snpp"], 1))
    assert len(rows) == 1 and rows[0]["lat"] == 22.0
    fc._CSV_CACHE.clear(); fc._WORLD_PARSED.clear()
