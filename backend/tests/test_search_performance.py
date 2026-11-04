"""Original ray casting is the compatibility oracle. All databases are pytest fixtures."""
import json
import random
import sqlite3

import pytest
from geo import AOI, geojson_to_polygons
from routers import snapshot
from test_snapshot_api import client


@pytest.mark.parametrize('indexed',[False,True])
@pytest.mark.parametrize('shape',['box','polygon','multi','circle','both','invalid_polygon'])
def test_search_matches_original(client,tmp_path,indexed,shape):
    outer=[[88,20],[93,20],[93,27],[88,27],[88,20]]
    hole=[[89,23],[91,23],[91,25],[89,25],[89,23]]
    payload=dict(bbox=[88,20,93,27])
    if shape in ('polygon','both'):payload['geometry']=dict(type='Polygon',coordinates=[outer,hole])
    if shape=='multi':payload['geometry']=dict(type='MultiPolygon',coordinates=[[outer,hole],[[[94,20],[95,20],[95,21],[94,20]]]])
    if shape=='invalid_polygon':payload['geometry']=dict(type='Polygon',coordinates=[[[88,20],[93,27],[93,20],[88,27],[88,20]]])
    if shape in ('circle','both'):payload.update(center=[90,24],radius_km=160)
    # The imported client fixture monkeypatches ROOT to this test's tmp_path.
    assert snapshot.ROOT.resolve()==tmp_path.resolve()
    path=tmp_path/'data/processed/snapshots/current_2026.sqlite'
    assert path.resolve().is_relative_to(tmp_path.resolve())
    rng=random.Random(1)
    points=[(88,20),(93,27),(88,24),(93,24),(90,20),(90,27),(89,24),(91,24),(90,23),(90,25),
            (88-1e-7,24),(88+1e-7,24),(93-1e-7,24),(93+1e-7,24),(90,24)]
    points += [(rng.uniform(87,94),rng.uniform(19,28)) for _ in range(120)]
    with sqlite3.connect(path) as con:
        for i,(lon,lat) in enumerate(points):
            event=dict(fire_id=f'f{i:04d}',end_time=f'2026-11-02 {i%24:02d}:00:00+00:00')
            con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(event['fire_id'],'2026-11-01',event['end_time'],lon,lat,json.dumps(event)))
        if indexed:
            con.execute('CREATE VIRTUAL TABLE event_spatial_index USING rtree(event_id,min_lon,max_lon,min_lat,max_lat)')
            con.execute('INSERT INTO event_spatial_index SELECT rowid,lon,lon,lat,lat FROM events')
        original=AOI(tuple(payload['bbox']),geojson_to_polygons(payload.get('geometry')),payload.get('center'),payload.get('radius_km'))
        con.row_factory=sqlite3.Row
        expected=[]
        for row in con.execute('SELECT payload,lon,lat FROM events ORDER BY end_time DESC,fire_id ASC'):
            if original.contains(row['lat'],row['lon']):expected.append(json.loads(row['payload'])['fire_id'])
    actual=[]
    for offset in range(0,len(expected)+7,7):
        response=client.post(f'/fires/search?limit=7&offset={offset}',json=payload)
        assert response.status_code==200,response.text
        body=response.json()
        assert body['count']==len(expected)
        assert body['has_more']==(offset+len(body['data'])<len(expected))
        actual.extend(e['fire_id'] for e in body['data'])
    assert actual==expected


def test_baseline_stage_log(client,caplog):
    with caplog.at_level('INFO',logger='flameseek.search'):
        client.post('/fires/search',json={'bbox':[88,20,93,27]})
    metric=json.loads(next(r.message[12:] for r in caplog.records if r.message.startswith('fire_search ')))
    assert metric['path']=='fallback'
    assert all(metric[name]>=0 for name in ['candidate_filter_ms','exact_containment_ms','count_ms','sort_limit_ms','serialization_ms'])


def test_query_plans_use_spatial_and_ordering_indexes(client,tmp_path):
    with sqlite3.connect(tmp_path/'data/processed/snapshots/current_2026.sqlite') as con:
        con.execute('CREATE VIRTUAL TABLE event_spatial_index USING rtree(event_id,min_lon,max_lon,min_lat,max_lat)')
        con.execute('INSERT INTO event_spatial_index SELECT rowid,lon,lon,lat,lat FROM events')
        con.execute('CREATE INDEX event_order ON events(end_time DESC,fire_id ASC)')
        con.create_function('area_contains',2,lambda x,y:True)
        for box,expected in [([88,20,93,27],'VIRTUAL TABLE INDEX'),([-180,-90,180,90],'USING INDEX event_order')]:
            where,params=snapshot.event_candidates(con,box)
            sql,params,strategy=snapshot.search_page_sql(con,box,where+' AND area_contains(lon,lat)',params,10,0)
            details=' '.join(row[3] for row in con.execute('EXPLAIN QUERY PLAN '+sql,params))
            assert expected in details


def test_count_cache_handles_deep_first_requests_and_snapshot_changes(client,tmp_path,caplog):
    area={'bbox':[88,20,93,27]}
    with caplog.at_level('INFO',logger='flameseek.search'):
        first=client.post('/fires/search?offset=100',json=area).json()
        second=client.post('/fires/search?limit=1',json=area).json()
    assert first['count']==second['count']==2 and first['data']==[]
    logs=[json.loads(r.message[12:]) for r in caplog.records if r.message.startswith('fire_search ')]
    assert not logs[0]['count_cache_hit'] and logs[1]['count_cache_hit']
    with sqlite3.connect(tmp_path/'data/processed/snapshots/current_2026.sqlite') as con:
        event={'fire_id':'extra','end_time':'2026-11-02 12:00:00+00:00'}
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',('extra','2026-11-01',event['end_time'],90.,24.,json.dumps(event)))
    assert client.post('/fires/search',json=area).json()['count']==3
