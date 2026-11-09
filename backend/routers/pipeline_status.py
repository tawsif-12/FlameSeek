"""Read only published data; ingestion never runs inside API workers."""
import json
from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException
from routers.snapshot import FireSearch, connect, metadata, search_area, manifest
from search_geometry import PreparedArea

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter()


@router.get('/pipeline/catalog')
def pipeline_catalog():
    return manifest()


@router.get('/pipeline/status')
def pipeline_status():
    path = ROOT / 'data/metadata/pipeline_status.json'
    if not path.exists():
        return {'status': 'not_started', 'last_successful_run': None, 'latest_observation_time': None,
                'latest_published_snapshot': None, 'failure': None}
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        published = metadata('daily')
        if published.get('snapshot_file'):
            state['latest_published_snapshot'] = published
            state['latest_observation_time'] = published.get('last_observation_time')
        return state
    except (OSError, ValueError):
        raise HTTPException(503, 'Pipeline status temporarily unavailable') from None


@router.post('/pipeline/history')
def local_history(payload: FireSearch, start: date | None = None, end: date | None = None):
    if start and end and start > end:
        raise HTTPException(400, 'start must be before end')
    area = PreparedArea(search_area(payload))
    con, window = connect('daily')
    try:
        con.create_function('area_contains', 2, lambda lon, lat: area.contains(lat, lon), deterministic=True)
        w, s, e, n = area.bbox
        where = 'lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND area_contains(lon,lat)'
        params = [w, e, s, n]
        if start:
            where += ' AND substr(time,1,10)>=?'; params.append(str(start))
        if end:
            where += ' AND substr(time,1,10)<=?'; params.append(str(end))
        daily = [dict(r) for r in con.execute('SELECT substr(time,1,10) AS day,source,processing_type,count(*) AS detections,max(frp) AS maximum_detection_frp_mw FROM raw_observations WHERE ' + where + ' GROUP BY day,source,processing_type ORDER BY day,source,processing_type', params)]
        events_where = 'lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND area_contains(lon,lat)'
        event_params = [w, e, s, n]
        if start:
            events_where += ' AND substr(end_time,1,10)>=?'; event_params.append(str(start))
        if end:
            events_where += ' AND substr(start_time,1,10)<=?'; event_params.append(str(end))
        count = con.execute('SELECT count(*) FROM events WHERE ' + events_where, event_params).fetchone()[0]
        return {**metadata(window,con), 'daily': daily, 'raw_detections': sum(r['detections'] for r in daily),
                'reconstructed_events': count, 'event_filter_basis': 'event centroid contained by selected boundary; event lifetime overlaps requested dates',
                'coverage_status': 'Downloaded source-days do not establish clear-sky observation coverage; missing days are unknown'}
    finally:
        con.close()
