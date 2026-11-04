"""Reproducible HTTP benchmark; never writes published snapshots.

python benchmarks/search.py --output ../outputs/search-performance/01-baseline.json
Use --root .. to benchmark published data read-only rather than the seeded fixture.
"""
import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import random
import sqlite3
import statistics
import sys
import tempfile
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import snapshot


def fixture(root, size=30000):
    dest=root/'data/processed/snapshots';dest.mkdir(parents=True)
    con=sqlite3.connect(dest/'bench.sqlite')
    con.executescript('''CREATE TABLE events(fire_id TEXT PRIMARY KEY,start_time TEXT,end_time TEXT,lon REAL,lat REAL,payload TEXT);
    CREATE INDEX event_end ON events(end_time); CREATE INDEX event_order ON events(end_time DESC,fire_id ASC);
    CREATE TABLE overpasses(fire_id TEXT,platform TEXT,time TEXT,frp REAL); CREATE INDEX overpass_event_time ON overpasses(fire_id,time);
    CREATE TABLE footprints(fire_id TEXT PRIMARY KEY,geojson TEXT);
    CREATE VIRTUAL TABLE event_spatial_index USING rtree(event_id,min_lon,max_lon,min_lat,max_lat);''')
    rng=random.Random(43)
    for i in range(size):
        lon,lat=rng.uniform(-180,180),rng.uniform(-60,75)
        end=f'2026-11-{1+i%3:02d} 12:00:00+00:00';fire_id=f'e{i:07d}'
        event=dict(fire_id=fire_id,centroid_lon=lon,centroid_lat=lat,end_time=end,start_time=end,platforms_seen='Aqua;S-NPP',p_conf_max=.9,FRP_VIIRS_max=120.)
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(fire_id,end,end,lon,lat,json.dumps(event)))
        ring=[[lon+.01*math.cos(a*math.tau/64),lat+.01*math.sin(a*math.tau/64)] for a in range(64)];ring.append(ring[0])
        con.execute('INSERT INTO footprints VALUES(?,?)',(fire_id,json.dumps(dict(type='Polygon',coordinates=[ring]))))
    con.execute('INSERT INTO event_spatial_index SELECT rowid,lon,lon,lat,lat FROM events')
    con.commit();con.close()
    meta=dict(window='bench',data_version='seed43',now='2026-11-04T00:00:00+00:00',status='benchmark')
    (root/'data/processed/snapshot_manifest.json').write_text(json.dumps(dict(default_window='bench',windows=dict(bench=meta),translation={})))


def cases():
    ring=[[10+15*(1+.15*math.cos(13*a*math.tau/512))*math.cos(a*math.tau/512),10+15*(1+.15*math.cos(13*a*math.tau/512))*math.sin(a*math.tau/512)] for a in range(512)]
    ring.append(ring[0])
    return [('small',dict(bbox=[88,20,93,27]),0),('medium',dict(bbox=[60,0,110,40]),0),
            ('continent',dict(bbox=[-20,-40,60,60]),0),
            ('complex_polygon',dict(bbox=[-10,-10,30,30],geometry=dict(type='Polygon',coordinates=[ring])),0),
            ('circle',dict(bbox=[-20,-40,60,60],center=[20,10],radius_km=1200),0),
            ('deep_offset',dict(bbox=[-180,-60,180,75]),15000)]


class Capture(logging.Handler):
    def __init__(self):super().__init__();self.items=[]
    def emit(self,record):
        if record.getMessage().startswith('fire_search '):self.items.append(json.loads(record.getMessage()[12:]))


def run(args,root):
    snapshot.ROOT=root;snapshot.MANIFEST_PATH=root/'data/processed/snapshot_manifest.json'
    window=args.window or snapshot.manifest()['default_window']
    app=FastAPI();app.include_router(snapshot.router)
    if args.gzip:
        from search_http import SearchGZipMiddleware
        app.add_middleware(SearchGZipMiddleware)
    client=TestClient(app);capture=Capture();snapshot.SEARCH_LOG.addHandler(capture);snapshot.SEARCH_LOG.setLevel(logging.INFO)
    report=dict(dataset='published' if args.root else 'seed43-30000',window=window,repeats=args.repeats,cases={})
    for name,area,offset in cases():
        samples=[];hashes=[];stages=[]
        for i in range(args.repeats+1):
            params=dict(window=window,limit=args.limit,offset=offset,geometry=True)
            if args.simplify:params['simplify_footprints']=True
            tick=perf_counter();r=client.post('/fires/search',params=params,json=area)
            elapsed=(perf_counter()-tick)*1000;r.raise_for_status()
            if i:
                samples.append(elapsed);hashes.append(hashlib.sha256(r.content).hexdigest());stages.append(capture.items[-1])
        con,_=snapshot.connect(window)
        try:
            where,values=snapshot.event_candidates(con,area['bbox'])
            con.create_function('area_contains',2,lambda x,y:True)
            where+=' AND area_contains(lon,lat)'
            count_plan=[list(r) for r in con.execute('EXPLAIN QUERY PLAN SELECT count(*) FROM events WHERE '+where,values)]
            sql,page_params,_=snapshot.search_page_sql(con,area['bbox'],where,values,args.limit,offset,r.json()['count'])
            page_plan=[list(r) for r in con.execute('EXPLAIN QUERY PLAN '+sql,page_params)]
        finally:con.close()
        metrics={key:round(statistics.median([s[key] for s in stages]),3) for key in stages[0] if key.endswith('_ms')}
        report['cases'][name]=dict(p50_ms=round(statistics.median(samples),3),p95_ms=round(sorted(samples)[math.ceil(.95*len(samples))-1],3),sha256=hashes[0],stable=len(set(hashes))==1,stages_p50=metrics,path=stages[0]['path'],count=r.json()['count'],response_bytes=len(r.content),wire_bytes=int(r.headers.get('content-length',len(r.content))),count_plan=count_plan,page_plan=page_plan)
        print(name,report['cases'][name]['p50_ms'],report['cases'][name]['p95_ms'],flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    snapshot.POOL.clear()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path);parser.add_argument('--window');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--repeats',type=int,default=7);parser.add_argument('--limit',type=int,default=200);parser.add_argument('--gzip',action='store_true');parser.add_argument('--simplify',action='store_true');args=parser.parse_args()
    if args.root:run(args,args.root.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='fire-search-') as temp:
            root=Path(temp);fixture(root);run(args,root)
