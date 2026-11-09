import json
import sqlite3
from fastapi.testclient import TestClient
from main import app
from routers import snapshot, pipeline_status
from snapshot_connections import POOL


def test_daily_status_history_exact_boundary_and_search(tmp_path, monkeypatch):
    folder = tmp_path / 'data/processed/snapshots'
    folder.mkdir(parents=True)
    path = folder / 'daily_generation.sqlite'
    with sqlite3.connect(path) as con:
        con.executescript('CREATE TABLE events(fire_id TEXT PRIMARY KEY,start_time TEXT,end_time TEXT,lon REAL,lat REAL,payload TEXT); CREATE TABLE overpasses(fire_id TEXT,platform TEXT,time TEXT,frp REAL); CREATE TABLE raw_observations(record_id TEXT PRIMARY KEY,source TEXT,processing_type TEXT,time TEXT,lon REAL,lat REAL,frp REAL); CREATE VIRTUAL TABLE event_spatial_index USING rtree(event_id,min_lon,max_lon,min_lat,max_lat);')
        event = dict(fire_id='FD1', start_time='2026-11-08 23:59:00+00:00', end_time='2026-11-09 00:01:00+00:00', platforms_seen='Aqua', p_conf_max=.9)
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)', ('FD1',event['start_time'],event['end_time'],90,24,json.dumps(event)))
        con.execute('INSERT INTO event_spatial_index VALUES(1,90,90,24,24)')
        con.executemany('INSERT INTO raw_observations VALUES(?,?,?,?,?,?,?)', [('a','MODIS_NRT','NRT','2026-11-08T23:59:00+00:00',90,24,20),('b','MODIS_NRT','NRT','2026-11-09T00:01:00+00:00',91,25,25)])
    meta = dict(window='daily', snapshot_file=path.name, data_version='generation', now='2026-11-09T03:00:00+00:00',last_observation_time='2026-11-09T00:01:00+00:00')
    manifest_path = tmp_path / 'data/processed/snapshot_manifest.json'
    manifest_path.write_text(json.dumps(dict(default_window='daily',windows={'daily':meta},translation={})))
    monkeypatch.setattr(snapshot, 'ROOT', tmp_path)
    monkeypatch.setattr(snapshot, 'MANIFEST_PATH', manifest_path)
    monkeypatch.setattr(pipeline_status, 'ROOT', tmp_path)
    client = TestClient(app)
    assert client.get('/api/pipeline/status').json()['status'] == 'not_started'
    payload = {'bbox':[89,23,92,26], 'center':[90,24], 'radius_km':10}
    history = client.post('/api/pipeline/history', json=payload)
    assert history.status_code == 200, history.text
    assert history.json()['raw_detections'] == 1
    assert history.json()['reconstructed_events'] == 1
    assert client.post('/api/pipeline/history?start=2026-11-09',json=payload).json()['raw_detections'] == 0
    assert client.post('/api/pipeline/history?start=2026-11-09&end=2026-11-08',json=payload).status_code == 400
    response = client.post('/fires/search',json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['count'] == 1
    # Immutable generation filenames work with the unchanged search contract.
    assert response.json()['data'][0]['fire_id'] == 'FD1'
    POOL.clear()
