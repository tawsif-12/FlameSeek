"""Read-only API snapshots assembled from local pipeline artifacts (stdlib SQLite)."""
from pathlib import Path
import csv,json,math,sqlite3
import numpy as np
from datetime import datetime,time,timezone
from pipeline.config import ROOT,load_settings
from pipeline import himawari as hw


def clean_row(row):
    result={}
    for key,value in row.items():
        if value is None or value.strip() in ['','nan','NaN','None']:result[key]=None;continue
        if value.lower() in ['true','false']:result[key]=value.lower()=='true';continue
        try:
            number=float(value);result[key]=number if math.isfinite(number) else None
        except ValueError:result[key]=value
    return result


def rows(path,data_version=None):
    if not path.exists():return
    with path.open(encoding='utf-8-sig',newline='') as handle:
        for row in csv.DictReader(handle):
            row=clean_row(row)
            # Stamp the window's own version: Phase 1-2 tables carry the global label.
            if data_version is not None:row['data_version']=data_version
            yield row


SIMPLIFY_DEG=0.0005  # ~50 m; footprints are 375 m-1 km pixels, so outlines stay true at map scale


def add_spatial(con,window,root=ROOT):
    """Event footprints (union of each event's detection footprints, GeoJSON) and clean
    detection points for the website map. Geometry is drawn from the pipeline's own
    Step 3 footprints; nothing is approximated by circles."""
    import geopandas as gpd
    import pandas as pd
    import shapely
    con.executescript('CREATE TABLE footprints(fire_id TEXT PRIMARY KEY,geojson TEXT); CREATE TABLE detections(fire_id TEXT,lon REAL,lat REAL,time TEXT,platform TEXT,sensor TEXT,frp REAL,conf_class TEXT); CREATE INDEX detection_time ON detections(time); CREATE INDEX detection_location ON detections(lon,lat);')
    fp=gpd.read_parquet(root/'data/interim/windows'/window/'footprints.geoparquet',columns=['fire_id','geometry'])
    order=fp.fire_id.to_numpy().argsort(kind='stable');fp=fp.iloc[order]
    ids,starts=np.unique(fp.fire_id.to_numpy(),return_index=True)
    geoms=fp.geometry.to_numpy();bounds=list(starts[1:])+[len(fp)]
    n=0
    for fire_id,a,b in zip(ids,starts,bounds):
        g=shapely.union_all(geoms[a:b]) if b-a>1 else geoms[a]
        g=shapely.simplify(g,SIMPLIFY_DEG,preserve_topology=True)
        con.execute('INSERT INTO footprints VALUES(?,?)',(fire_id,shapely.to_geojson(g,indent=None)));n+=1
    det=pd.read_parquet(root/'data/processed/windows'/window/'detections_clean.parquet',
                        columns=['fire_id','longitude','latitude','acq_datetime_utc','platform','sensor','frp_mw','conf_class'])
    det['acq_datetime_utc']=pd.to_datetime(det.acq_datetime_utc,utc=True).dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
    det['frp_mw']=det.frp_mw.where(np.isfinite(det.frp_mw))
    con.executemany('INSERT INTO detections VALUES(?,?,?,?,?,?,?,?)',det.astype(object).where(det.notna(),None).itertuples(index=False,name=None))
    return n,len(det)


def create_event_spatial_index(con):
    """Build once before publishing an immutable snapshot; rowids identify centroids."""
    con.execute('CREATE VIRTUAL TABLE event_spatial_index USING rtree(event_id,min_lon,max_lon,min_lat,max_lat)')
    con.execute('INSERT INTO event_spatial_index SELECT rowid,lon,lon,lat,lat FROM events WHERE lon IS NOT NULL AND lat IS NOT NULL')
    con.execute('CREATE INDEX event_order ON events(end_time DESC,fire_id ASC)')


def build_window(window,root=ROOT):
    cfg=load_settings(window=window);processed=root/'data/processed/windows'/window
    dest=root/'data/processed/snapshots';dest.mkdir(parents=True,exist_ok=True)
    path=dest/(window+'.sqlite');tmp=path.with_suffix('.tmp.sqlite')
    # Task-owned temporary DB only; existing published snapshot remains readable until replacement.
    if tmp.exists():tmp.unlink()
    con=sqlite3.connect(tmp)
    con.executescript('CREATE TABLE events(fire_id TEXT PRIMARY KEY,start_time TEXT,end_time TEXT,lon REAL,lat REAL,payload TEXT); CREATE INDEX event_end ON events(end_time); CREATE TABLE overpasses(fire_id TEXT,platform TEXT,time TEXT,frp REAL); CREATE TABLE grid(cell_id TEXT,day TEXT,lon REAL,lat REAL,payload TEXT); CREATE INDEX grid_location ON grid(lon,lat); CREATE TABLE metadata(key TEXT PRIMARY KEY,payload TEXT);')
    n_overpasses=0
    for row in rows(root/'data/interim/windows'/window/'event_overpasses.csv'):
        con.execute('INSERT INTO overpasses VALUES(?,?,?,?)',(row['fire_id'],row['platform'],row['acq_datetime_utc'],row['frp_sum_mw']));n_overpasses+=1
    con.execute('CREATE INDEX overpass_event_time ON overpasses(fire_id,time)')
    n_events=0;last=None
    for row in rows(processed/'fire_events.csv',cfg['data_version']):
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(row['fire_id'],row['start_time'],row['end_time'],row['centroid_lon'],row['centroid_lat'],json.dumps(row,ensure_ascii=False,allow_nan=False)))
        when=row.get('end_time')
        if when is not None and (last is None or when>last):last=when
        n_events+=1
    create_event_spatial_index(con)
    n_grid=0
    for file in sorted((root/'data/processed'/window/'grid_daily_lambda').glob('year=*/month=*/day=*/part.csv')):
        for row in rows(file,cfg['data_version']):
            con.execute('INSERT INTO grid VALUES(?,?,?,?,?)',(row['cell_id'],row['date'],row['cell_lon'],row['cell_lat'],json.dumps(row,ensure_ascii=False,allow_nan=False)));n_grid+=1
    n_footprints,n_detections=add_spatial(con,window,root)
    now=datetime.combine(cfg['window']['end'],time.max,tzinfo=timezone.utc).isoformat()
    summary_path=(root/'outputs' if window=='current_2026' else root/'outputs/windows'/window)/'latent_summary.json'
    latent=json.loads(summary_path.read_text()) if summary_path.exists() else dict(status='awaiting data')
    meta=dict(window=window,data_version=cfg['data_version'],
              last_observation_time=last,now=now,now_basis='configured UTC window end; not wall-clock time',is_live=False,
              start=str(cfg['window']['start']),end=str(cfg['window']['end']),n_events=n_events,n_grid_rows=n_grid,n_overpasses=n_overpasses,
              n_footprints=n_footprints,n_detections=n_detections,
              lambda_status=latent['status'],lambda_limitation=latent.get('limitation'),
              status='offline snapshot',translation_status='provisional configurable display rules; calibrated forecast unavailable')
    con.execute('INSERT INTO metadata VALUES(?,?)',('meta',json.dumps(meta,ensure_ascii=False,allow_nan=False)))
    con.commit();con.close();tmp.replace(path)
    return meta


def build_all():
    cfg=load_settings();manifest=dict(default_window=cfg['default_window'],translation=cfg['translation'],windows={})
    for window in ['current_2026','sync_2016']:
        meta=build_window(window);manifest['windows'][window]=meta;print('Snapshot',meta,flush=True)
    hw.json_write(ROOT/'data/processed/snapshot_manifest.json',manifest)
    hw.json_write(ROOT/'outputs/stages/stage4_snapshots.json',manifest)
    return manifest


if __name__=='__main__':build_all()
