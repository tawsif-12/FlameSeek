import json,sqlite3
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import snapshot


@pytest.fixture
def client(tmp_path,monkeypatch):
    root=tmp_path;dest=root/'data/processed/snapshots';dest.mkdir(parents=True)
    windows={}
    for window in ['current_2026','sync_2016']:
        meta=dict(window=window,data_version='fixture-'+window,last_observation_time='2026-11-02T12:00:00+00:00',now='2026-11-02T23:59:59+00:00',now_basis='configured window end',is_live=False)
        windows[window]=meta
        con=sqlite3.connect(dest/(window+'.sqlite'))
        con.executescript('CREATE TABLE events(fire_id TEXT,start_time TEXT,end_time TEXT,lon REAL,lat REAL,payload TEXT); CREATE TABLE overpasses(fire_id TEXT,platform TEXT,time TEXT,frp REAL); CREATE TABLE grid(cell_id TEXT,day TEXT,lon REAL,lat REAL,payload TEXT);')
        for fire_id,end in [('recent','2026-11-02 12:00:00+00:00'),('old','2026-11-01 20:00:00+00:00')]:
            event=dict(fire_id=fire_id,end_time=end,platforms_seen='Aqua;S-NPP',p_conf_max=.9,FRP_VIIRS_max=120.)
            con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(fire_id,'2026-11-01',end,90.,24.,json.dumps(event)))
        for hour,power in [(5,100),(6,110),(7,120)]:con.execute('INSERT INTO overpasses VALUES(?,?,?,?)',('recent','Aqua',f'2026-11-02 0{hour}:00:00+00:00',power))
        value=None if window=='sync_2016' else .5
        grid=dict(cell_id='c1',date='2026-11-02',lambda_hat=value,status='awaiting data' if value is None else 'provisional')
        con.execute('INSERT INTO grid VALUES(?,?,?,?,?)',('c1','2026-11-02',90.,24.,json.dumps(grid)))
        if window=='current_2026':  # sync_2016 stays an older snapshot without spatial tables
            con.executescript('CREATE TABLE footprints(fire_id TEXT PRIMARY KEY,geojson TEXT); CREATE TABLE detections(fire_id TEXT,lon REAL,lat REAL,time TEXT,platform TEXT,sensor TEXT,frp REAL,conf_class TEXT);')
            con.execute('INSERT INTO footprints VALUES(?,?)',('recent',json.dumps({'type':'Polygon','coordinates':[[[90,24],[90.01,24],[90.01,24.01],[90,24]]]})))
            for when,lon in [('2026-11-02 11:00:00+00:00',90.),('2026-11-01 08:00:00+00:00',90.),('2026-11-02 11:00:00+00:00',75.)]:
                con.execute('INSERT INTO detections VALUES(?,?,?,?,?,?,?,?)',('recent',lon,24.,when,'S-NPP','VIIRS',12.5,'nominal'))
        con.commit();con.close()
    manifest=root/'data/processed/snapshot_manifest.json';manifest.write_text(json.dumps(dict(default_window='current_2026',windows=windows,translation={'active_hours':24})))
    monkeypatch.setattr(snapshot,'ROOT',root);monkeypatch.setattr(snapshot,'MANIFEST_PATH',manifest)
    app=FastAPI();app.include_router(snapshot.router)
    return TestClient(app)


def test_metadata_uses_window_end_not_wall_clock(client):
    body=client.get('/meta').json()
    assert body['now']=='2026-11-02T23:59:59+00:00' and body['is_live'] is False
    assert body['data_version'] and body['last_observation_time']


def test_active_events_and_bilingual_description(client):
    response=client.get('/fires/active?bbox=88,20,93,27');assert response.status_code==200
    body=response.json();assert body['count']==1 and body['data'][0]['fire_id']=='recent'
    display=body['data'][0]['translation']
    assert display['en']['trend']=='Spreading' and display['bn']['trend']!=display['en']['trend']
    assert display['risk_level'] is None and len(display['bn']['honesty_notes'])==3


def test_event_detail_and_not_found_keep_metadata(client):
    assert client.get('/events/recent').json()['data']['fire_id']=='recent'
    response=client.get('/events/missing');assert response.status_code==404
    assert 'data_version' in response.json() and 'last_observation_time' in response.json()


def test_lambda_null_survives_json_and_window_selection(client):
    body=client.get('/grid/lambda?window=sync_2016&bbox=88,20,93,27').json()
    assert body['data'][0]['lambda_hat'] is None and body['data_version']=='fixture-sync_2016'
    assert client.get('/grid/lambda?bbox=73,28,77,32').json()['count']==0


@pytest.mark.parametrize('query',['bbox=nan,20,93,27','bbox=93,20,88,27','window=../../backend/.env','limit=0'])
def test_invalid_queries_are_rejected_with_provenance(client,query):
    response=client.get('/grid/lambda?'+query)
    assert response.status_code in [400,422]
    assert 'data_version' in response.json() and 'last_observation_time' in response.json()


def test_snapshot_connection_is_read_only(client):
    con,_=snapshot.connect('current_2026')
    try:
        with pytest.raises(sqlite3.OperationalError,match='readonly'):con.execute('DELETE FROM events')
    finally:con.close()


def test_new_endpoints_are_registered_in_existing_backend():
    from main import app
    paths=set(app.openapi()['paths'])
    assert {'/meta','/fires/active','/events/{fire_id}','/grid/lambda'}<=paths


def test_footprints_on_request_and_in_event_detail(client):
    body=client.get('/fires/active?bbox=88,20,93,27&geometry=true').json()
    assert body['data'][0]['footprint']['type']=='Polygon'
    assert 'footprint' not in client.get('/fires/active?bbox=88,20,93,27').json()['data'][0]
    assert client.get('/events/recent').json()['data']['footprint']['type']=='Polygon'
    assert client.get('/events/recent?window=sync_2016').json()['data']['footprint'] is None


def test_detections_limited_to_active_period_and_bbox_with_provenance(client):
    body=client.get('/detections?bbox=88,20,93,27').json()
    assert body['count']==1 and body['data'][0]['platform']=='S-NPP' and 'last 24 h' in body['basis']
    assert body['data_version'] and body['last_observation_time']
    old=client.get('/detections?window=sync_2016')
    assert old.status_code==503 and 'data_version' in old.json()


def test_window_fires_returns_all_window_events_in_box_with_footprints(client):
    body=client.get('/fires?bbox=88,20,93,27&geometry=true').json()
    assert body['count']==2 and {e['fire_id'] for e in body['data']}=={'recent','old'}
    assert body['data'][0]['fire_id']=='recent' and body['data'][0]['footprint']['type']=='Polygon'
    assert 'whole' not in body['basis'] and body['data_version']
    assert client.get('/fires').status_code in [400,422]
