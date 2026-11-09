import asyncio
import json
import threading
import time

import pytest
from firms_client import FirmsAPIError
from routers import live_harmonized as live


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    for name in ('_snapshots', '_jobs', '_ready', '_errors', '_retry_after'):
        monkeypatch.setattr(live, name, {})
    monkeypatch.setattr(live, '_lock', asyncio.Lock())
    monkeypatch.setattr(live, 'disk_read', lambda *a, **k: None)
    monkeypatch.setattr(live, 'disk_write', lambda *a, **k: None)
    monkeypatch.setattr(live, 'recent_source_status', lambda: 'live')
    monkeypatch.setattr(live, 'recent_missing_sensors', lambda: [])


def test_real_points_return_before_merging_and_concurrent_requests_share_work(monkeypatch):
    gate = threading.Event()
    calls = []
    point = {'lat': 23, 'lon': 90, 'frp': 12, 'sensor': 'modis'}

    async def fetch(*a, **k):
        calls.append('fetch')
        return [point]

    def compute(rows):
        calls.append('compute')
        assert gate.wait(5)
        return {'hotspots': [{**point, 'harmonized': {'event_id': 'test'}}], 'metadata': {'events_total': 1}}

    monkeypatch.setattr(live, 'fetch_recent_hotspots', fetch)
    monkeypatch.setattr(live, 'compute', compute)

    async def check():
        try:
            responses = await asyncio.wait_for(asyncio.gather(*(live.harmonized_hotspots(1, 5) for _ in range(3))), 2)
            for response in responses:
                payload = json.loads(response.body)
                assert payload['hotspots'][0]['lat'] == 23
                assert payload['metadata']['processing_pending'] is True
                assert 'events_total' not in payload['metadata']
        finally:
            gate.set()
        await live._jobs[1]
        payload = json.loads((await live.harmonized_hotspots(1, 5)).body)
        assert payload['metadata']['events_total'] == 1
        assert payload['metadata']['processing_pending'] is False
        assert calls.count('fetch') == calls.count('compute') == 1
    asyncio.run(check())


def test_recent_real_snapshot_survives_nasa_failure_and_retry_is_throttled(monkeypatch):
    payload = {'hotspots': [{'lat': 23, 'lon': 90}], 'raw_hotspots': [],
               'metadata': {'data_source': 'live', 'snapshot_at': '2026-11-09T10:00:00+00:00'}}
    live._snapshots[1] = (time.time() - live.FRESH_SECONDS - 10, payload)
    calls = []

    async def fail(*a, **k):
        calls.append(1)
        raise FirmsAPIError(503, 'NASA unavailable', 'test')
    monkeypatch.setattr(live, 'fetch_recent_hotspots', fail)

    async def check():
        response = await live.harmonized_hotspots(1, 5)
        data = json.loads(response.body)
        assert data['metadata']['data_source'] == 'cached_actual'
        assert data['metadata']['stale_snapshot'] is True
        await live._jobs[1]
        data = json.loads((await live.harmonized_hotspots(1, 5)).body)
        assert data['hotspots'] == payload['hotspots']
        assert 'refresh_warning' in data['metadata']
        assert len(calls) == 1
    asyncio.run(check())


def test_processing_failure_preserves_downloaded_observations(monkeypatch):
    async def fetch(*a, **k):
        return [{'lat': 23, 'lon': 90}]
    def fail(rows):
        raise RuntimeError('pipeline unavailable')
    monkeypatch.setattr(live, 'fetch_recent_hotspots', fetch)
    monkeypatch.setattr(live, 'compute', fail)

    async def check():
        await live.harmonized_hotspots(1, 5)
        await live._jobs[1]
        data = json.loads((await live.harmonized_hotspots(1, 5)).body)
        assert data['hotspots'][0]['lat'] == 23
        assert data['metadata']['harmonization_unavailable'] is True
        assert data['metadata']['processing_pending'] is False
    asyncio.run(check())


def test_full_merged_set_is_returned_without_limit():
    points = [{'lat': 23, 'lon': 90, 'harmonized': {'event_id': str(i)}} for i in range(34704)]
    live._snapshots[1] = (time.time(), {'hotspots': points, 'raw_hotspots': [], 'metadata': {'events_total': len(points)}})

    async def check():
        full = json.loads((await live.harmonized_hotspots(1, None)).body)
        assert len(full['hotspots']) == 34704
        assert full['metadata']['returned_hotspot_count'] == 34704
        limited = json.loads((await live.harmonized_hotspots(1, 100)).body)
        assert len(limited['hotspots']) == 100
        assert limited['metadata']['events_total'] == 34704
    asyncio.run(check())
