"""Run the established procedure in its geospatial Python environment."""
import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from firms_client import fetch_recent_hotspots, recent_source_status, recent_missing_sensors, FirmsAPIError
from config import DEFAULT_SENSORS
from http_utils import disk_read, disk_write

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
_lock = asyncio.Lock()
_snapshots = {}
_jobs = {}
_ready = {}
_errors = {}
_retry_after = {}
FRESH_SECONDS = 15 * 60
MAX_CACHE_SECONDS = 6 * 60 * 60


def _save_snapshot(days, stamp, payload):
    disk_write('live_globe', f'days_{days}', json.dumps({'saved_at': stamp, 'payload': payload}))


def compute(rows):
    encoded = json.dumps(jsonable_encoder(rows), sort_keys=True)
    key = hashlib.sha256(('live-v1' + encoded).encode()).hexdigest()[:24]
    folder = ROOT / '.runlogs' / 'live_harmonized'
    folder.mkdir(parents=True, exist_ok=True)
    source, target = folder / f'{key}.input.json', folder / f'{key}.json'
    if not target.exists():
        source.write_text(encoded, encoding='utf-8')
        proc = subprocess.run([os.getenv('FLAMESEEK_PIPELINE_PYTHON', r'E:\anaconda\envs\flameseek\python.exe'),
                               '-m', 'pipeline.live_globe', str(source), str(target)],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-2000:])
    return json.loads(target.read_text(encoding='utf-8'))


async def _refresh(days):
    try:
        rows = await fetch_recent_hotspots(None, DEFAULT_SENSORS, days, include_demo=False)
        source_status = recent_source_status()
        missing_sensors = recent_missing_sensors()
        observed_at = datetime.now(timezone.utc).isoformat()
        # Publish actual observations first, without pretending event merging is complete.
        payload = await asyncio.to_thread(jsonable_encoder, {
            'hotspots': [],
            'raw_hotspots': rows,
            'metadata': {'raw_hotspot_count': len(rows), 'data_source': source_status,
                         'unavailable_live_sensors': missing_sensors, 'partial_coverage': bool(missing_sensors),
                         'snapshot_at': observed_at, 'processing_pending': True},
        })
        _snapshots[days] = (time.time(), payload)
        _ready[days].set()
        async with _lock:
            result = await asyncio.to_thread(compute, rows)
        payload = {**payload, 'hotspots': sorted(result['hotspots'], key=lambda p: p.get('frp') or 0, reverse=True),
                   'metadata': {**payload['metadata'], **result['metadata'], 'processing_pending': False}}
        stamp = time.time()
        _snapshots[days] = (stamp, payload)
        try:
            await asyncio.to_thread(_save_snapshot, days, stamp, payload)
        except OSError:
            pass  # A full or read-only cache must not discard successful observations.
        _errors.pop(days, None)
        _retry_after.pop(days, None)
    except Exception as exc:
        _errors[days] = str(exc)
        _retry_after[days] = time.time() + 60
        # Keep already downloaded real observations usable if processing fails.
        cached = _snapshots.get(days)
        if cached and cached[1]['metadata'].get('processing_pending'):
            payload = cached[1]
            _snapshots[days] = (cached[0], {**payload, 'metadata': {**payload['metadata'],
                'processing_pending': False, 'harmonization_unavailable': True}})
    finally:
        _ready[days].set()


def _start_refresh(days):
    if time.time() < _retry_after.get(days, 0) and days in _jobs:
        return _jobs[days]
    if days not in _jobs or _jobs[days].done():
        _ready[days] = asyncio.Event()
        _jobs[days] = asyncio.create_task(_refresh(days))
    return _jobs[days]


async def warm_harmonized(days=1):
    await asyncio.shield(_start_refresh(days))


def _read_snapshot(days):
    try:
        text = disk_read('live_globe', f'days_{days}', max_age_seconds=MAX_CACHE_SECONDS)
    except OSError:
        return None
    if text:
        try:
            saved = json.loads(text)
            if 0 <= time.time() - saved['saved_at'] <= MAX_CACHE_SECONDS:
                return saved['saved_at'], saved['payload']
        except (ValueError, KeyError, TypeError):
            pass
    return None


@router.get('/harmonized_hotspots')
async def harmonized_hotspots(days: int = Query(1, ge=1, le=5), limit: int | None = Query(None, ge=1, le=200000)):
    cached = _snapshots.get(days)
    if cached is None:
        cached = await asyncio.to_thread(_read_snapshot, days)
        if cached:
            _snapshots[days] = cached
    if cached and time.time() - cached[0] > MAX_CACHE_SECONDS:
        cached = None
        _snapshots.pop(days, None)
    stale = cached is not None and time.time() - cached[0] >= FRESH_SECONDS
    if cached is None or stale:
        _start_refresh(days)
    if cached is None:
        await _ready[days].wait()
        cached = _snapshots.get(days)
        if not cached:
            raise HTTPException(502, detail={'message': f'FIRMS observations unavailable: {_errors.get(days, "retry shortly")}'})
    stamp, payload = cached
    # Legacy snapshots may contain a raw preview in hotspots. Never publish it
    # as merged output, including after a failed or incomplete pipeline run.
    merged_ready = not payload['metadata'].get('processing_pending') and not payload['metadata'].get('harmonization_unavailable')
    merged = [point for point in payload['hotspots'] if point.get('harmonized')] if merged_ready else []
    points = merged if limit is None else merged[:limit]
    metadata = {**payload['metadata'], 'returned_hotspot_count': len(points),
                'merged_ready': merged_ready, 'harmonization_scope': 'footprint_events_steps_1_4',
                'full_harmonization_complete': False,
                'cache_age_seconds': round(time.time() - stamp), 'stale_snapshot': bool(stale),
                'refresh_in_progress': days in _jobs and not _jobs[days].done()}
    if stale:
        metadata['data_source'] = 'cached_actual'
    if days in _errors:
        metadata['refresh_warning'] = 'Latest refresh failed; showing previously downloaded observations.'
    body = {**payload, 'hotspots': points, 'metadata': metadata}
    # Avoid FastAPI's repeated traversal of tens of thousands of already encoded rows.
    encoded = await asyncio.to_thread(json.dumps, body, separators=(',', ':'), allow_nan=False)
    return Response(encoded, media_type='application/json')
