"""Offline harmonization snapshot endpoints; never perform live network requests."""
from pathlib import Path
from datetime import timedelta
import importlib.util
import json,math,sqlite3
import logging
from time import perf_counter
from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from geo import AOI
from search_cache import COUNTS, BoundedCache, query_hash
from search_geometry import PreparedArea
from snapshot_connections import POOL
SEARCH_LOG=logging.getLogger('flameseek.search')
FALLBACK_WARNINGS=BoundedCache(size=128,ttl=3600)
ROOT=Path(__file__).resolve().parents[2]
MANIFEST_PATH=ROOT/'data/processed/snapshot_manifest.json'
_spec=importlib.util.spec_from_file_location('flameseek_snapshot_translation',ROOT/'pipeline/translate.py')
_translation=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_translation)


def manifest():
    if not MANIFEST_PATH.exists():return dict(default_window='current_2026',windows={},translation={})
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def metadata(window=None):
    data=manifest();window=window or data['default_window']
    return data['windows'].get(window,dict(window=window,data_version='awaiting data',last_observation_time=None,status='awaiting data'))


class SnapshotRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request:Request):
            try:return await original(request)
            except RequestValidationError as exc:
                return JSONResponse(status_code=422,content=jsonable_encoder({**metadata(request.query_params.get('window')),'detail':exc.errors(),'status':'error'}))
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code,content={**metadata(request.query_params.get('window')),'detail':exc.detail,'status':'error'})
        return handler

router=APIRouter(route_class=SnapshotRoute)


def connect(window):
    data=manifest();window=window or data['default_window']
    if window not in data['windows']:raise HTTPException(400,'Unknown or unavailable processing window')
    path=ROOT/'data/processed/snapshots'/(window+'.sqlite')
    if not path.exists():raise HTTPException(503,'Awaiting local snapshot build')
    con=POOL.acquire(path)
    return con,window


def parse_bbox(value):
    if value is None:return None
    try:
        box=tuple(float(x) for x in value.split(','))
        if len(box)!=4 or not all(math.isfinite(x) for x in box):raise ValueError()
        w,s,e,n=box
        if not (-180<=w<e<=180 and -90<=s<n<=90):raise ValueError()
    except (ValueError,TypeError):raise HTTPException(400,'bbox must be west,south,east,north in valid geographic bounds')
    return box


class FireSearch(BaseModel):
    bbox: tuple[float,float,float,float]
    geometry: dict | None = None
    center: tuple[float,float] | None = None
    radius_km: float | None = Field(default=None,gt=0,le=20000)


def search_area(payload):
    """Validate the boundary before registering an exact SQLite predicate."""
    parse_bbox(','.join(map(str,payload.bbox)))
    if (payload.center is None)!=(payload.radius_km is None):
        raise HTTPException(400,'center and radius_km must be supplied together')
    if payload.center:
        lon,lat=payload.center
        if not (-180<=lon<=180 and -90<=lat<=90 and math.isfinite(payload.radius_km)):
            raise HTTPException(400,'Invalid radius search')
    if payload.geometry is not None:
        try:
            kind=payload.geometry['type'];coords=payload.geometry['coordinates']
            if kind not in ('Polygon','MultiPolygon'):raise ValueError()
            polygons=[coords] if kind=='Polygon' else coords
            if not polygons:raise ValueError()
            count=0
            for polygon in polygons:
                if not polygon:raise ValueError()
                for ring in polygon:
                    if len(ring)<4 or ring[0]!=ring[-1]:raise ValueError()
                    for point in ring:
                        lon,lat=point[:2];count+=1
                        if not (-180<=lon<=180 and -90<=lat<=90):raise ValueError()
            if count>100000:raise ValueError()
        except (ValueError,TypeError,KeyError,IndexError):
            raise HTTPException(400,'Expected closed Polygon or MultiPolygon rings with valid coordinates (maximum 100000 vertices)')
    # Keep the supplied candidate box; exact radius/polygon tests follow it.
    from geo import geojson_to_polygons
    return AOI(payload.bbox,geojson_to_polygons(payload.geometry),payload.center,payload.radius_km)


def event_candidates(con,box):
    w,s,e,n=box
    exact='lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?';params=[w,e,s,n]
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='event_spatial_index'").fetchone():
        # R-Tree uses outward-rounded float32 bounds; always recheck exact coordinates.
        exact='rowid IN (SELECT event_id FROM event_spatial_index WHERE min_lon<=? AND max_lon>=? AND min_lat<=? AND max_lat>=?) AND '+exact
        params=[e,w,n,s]+params
    return exact,params


def search_page_sql(con,box,where,params,limit,offset,matching_count=None):
    """Sort narrow IDs before fetching payloads. Broad boxes can walk event order."""
    w,s,e,n=box
    broad=(e-w)*(n-s)>=360*180*.15 or ('event_spatial_index' not in where and matching_count is not None and matching_count>limit*4)
    indexes={row[1] for row in con.execute('PRAGMA index_list(events)')}
    order_index='event_order' if 'event_order' in indexes else 'event_end' if 'event_end' in indexes else None
    if broad and order_index:
        source='events INDEXED BY '+order_index
        where='lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND area_contains(lon,lat)'
        params=[w,e,s,n];strategy='ordered_scan'
    else:
        # Prevent legacy snapshots walking the entire end_time index for a tiny box.
        source='events NOT INDEXED';strategy='rtree_ids_sort' if 'event_spatial_index' in where else 'scan_ids_sort'
    sql=('WITH page AS MATERIALIZED (SELECT rowid AS id,end_time,fire_id FROM '+source+' WHERE '+where+
         ' ORDER BY end_time DESC,fire_id ASC LIMIT ? OFFSET ?) '
         'SELECT events.payload FROM page JOIN events ON events.rowid=page.id ORDER BY page.end_time DESC,page.fire_id ASC')
    return sql,params+[limit,offset],strategy


@router.post('/fires/search')
def search_fires(payload:FireSearch,window:str|None=None,limit:int=Query(2000,ge=1,le=5000),offset:int=Query(0,ge=0),geometry:bool=False,simplify_footprints:bool=False):
    """Search event centroids: exact containment precedes counting and pagination."""
    started=perf_counter();exact_seconds=0.;exact_calls=0
    area=PreparedArea(search_area(payload))
    con,window=connect(window);meta=metadata(window)
    try:
        stage=perf_counter()
        where,params=event_candidates(con,area.bbox)
        candidate_ms=(perf_counter()-stage)*1000
        path='rtree' if 'event_spatial_index' in where else 'fallback'
        if path=='fallback' and FALLBACK_WARNINGS.get(con.identity) is None:
            SEARCH_LOG.warning('Snapshot %s lacks event_spatial_index; using coordinate-filter fallback. Rebuild with python -m pipeline.snapshot from the project root.',window)
            FALLBACK_WARNINGS.put(con.identity,True)
        def contains(lon,lat):
            nonlocal exact_seconds,exact_calls
            tick=perf_counter()
            try:return lon is not None and lat is not None and area.contains(lat,lon)
            finally:exact_seconds+=perf_counter()-tick;exact_calls+=1
        con.create_function('area_contains',2,contains,deterministic=True)
        where+=' AND area_contains(lon,lat)'
        stage=perf_counter()
        identity=con.identity
        count_key=(identity,query_hash(payload))
        count=COUNTS.get(count_key);count_cache_hit=count is not None
        if count is None:
            count=con.execute('SELECT count(*) FROM events WHERE '+where,params).fetchone()[0]
            COUNTS.put(count_key,count)
        count_ms=(perf_counter()-stage)*1000
        stage=perf_counter()
        sql,page_params,strategy=search_page_sql(con,area.bbox,where,params,limit,offset,count)
        rows=con.execute(sql,page_params).fetchall()
        sort_ms=(perf_counter()-stage)*1000
        stage=perf_counter()
        translation_settings=manifest()['translation']
        data=[describe(row,con,meta,translation_settings) for row in rows]
        if geometry:
            shapes=search_footprints(con,[event['fire_id'] for event in data],payload.bbox if simplify_footprints else None)
            for event in data:event['footprint']=shapes.get(event['fire_id'])
        response={**meta,'data':data,'count':count,'limit':limit,'offset':offset,'has_more':offset+len(data)<count,
                'basis':'event centroid inside selected area; exact containment before pagination'}
        encoded=JSONResponse(response)
        SEARCH_LOG.info('fire_search %s',json.dumps(dict(path=path,ordering_path=strategy,count_cache_hit=count_cache_hit,candidate_filter_ms=candidate_ms,
            exact_containment_ms=exact_seconds*1000,exact_calls=exact_calls,count_ms=count_ms,
            sort_limit_ms=sort_ms,serialization_ms=(perf_counter()-stage)*1000,
            total_ms=(perf_counter()-started)*1000,count=count,offset=offset,limit=limit)))
        return encoded
    finally:con.close()


def describe(row,con,meta,translation_settings=None):
    event=json.loads(row['payload']);fire_id=event['fire_id']
    recent=con.execute('SELECT platform,frp,time FROM overpasses WHERE fire_id=? ORDER BY time DESC LIMIT 1',(fire_id,)).fetchone()
    comparable=[];power=event.get('FRP_VIIRS_max') or event.get('FRP_MODIS_max')
    if recent:
        power=recent['frp']
        values=con.execute('SELECT frp FROM overpasses WHERE fire_id=? AND platform=? ORDER BY time DESC LIMIT 3',(fire_id,recent['platform'])).fetchall()
        comparable=[r['frp'] for r in reversed(values)]
    satellites=[s for s in (event.get('platforms_seen') or '').split(';') if s]
    event['translation']=_translation.translate(p=None,p_clim=None,frp_mw=power,last_overpasses=comparable,
                         confidence=event.get('p_conf_max'),last_seen=event.get('end_time'),satellites=satellites,
                         now=meta['now'],cfg={'translation':manifest()['translation'] if translation_settings is None else translation_settings})
    return event


def footprint(con,fire_id):
    """Event footprint as GeoJSON geometry; None for snapshots built before footprints existed."""
    try:row=con.execute('SELECT geojson FROM footprints WHERE fire_id=?',(fire_id,)).fetchone()
    except sqlite3.OperationalError:return None
    return json.loads(row['geojson']) if row else None


def search_footprints(con,fire_ids,simplify_bbox=None):
    shapes={}
    if not fire_ids:return shapes
    exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='footprints'").fetchone()
    if not exists:return shapes
    for start in range(0,len(fire_ids),400):
        ids=fire_ids[start:start+400];marks=','.join('?' for _ in ids)
        for row in con.execute('SELECT fire_id,geojson FROM footprints WHERE fire_id IN ('+marks+')',ids):
            shapes[row['fire_id']]=json.loads(row['geojson'])
    if simplify_bbox is not None:
        from shapely.geometry import shape,mapping
        w,s,e,n=simplify_bbox;tolerance=min(.05,max(.0005,max(e-w,n-s)/4000))
        for fire_id,geometry in shapes.items():
            simplified=shape(geometry).simplify(tolerance,preserve_topology=True)
            shapes[fire_id]=mapping(simplified)
    return shapes


def active_period(meta):
    now=_translation.utc(meta['now']);hours=manifest()['translation'].get('active_hours',24)
    return now-timedelta(hours=hours),now,hours


@router.get('/meta')
def get_meta(window:str|None=None):
    con,window=connect(window)
    try:return {**metadata(window),'available_windows':list(manifest()['windows'])}
    finally:con.close()


@router.get('/fires/active')
def active_fires(window:str|None=None,bbox:str|None=None,limit:int=Query(500,ge=1,le=5000),offset:int=Query(0,ge=0),
                 geometry:bool=False):
    con,window=connect(window);meta=metadata(window)
    try:
        start,now,_=active_period(meta)
        clauses=['end_time>=?','end_time<=?'];params=[start.isoformat(sep=' '),now.isoformat(sep=' ')]
        box=parse_bbox(bbox)
        if box:
            w,s,e,n=box;clauses+=['lon BETWEEN ? AND ?','lat BETWEEN ? AND ?'];params +=[w,e,s,n]
        where=' AND '.join(clauses)
        count=con.execute('SELECT count(*) FROM events WHERE '+where,params).fetchone()[0]
        rows=con.execute('SELECT payload FROM events WHERE '+where+' ORDER BY end_time DESC LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        data=[describe(row,con,meta) for row in rows]
        if geometry:
            for event in data:event['footprint']=footprint(con,event['fire_id'])
        return {**meta,'data':data,'count':count,'limit':limit,'offset':offset,'has_more':offset+len(rows)<count}
    finally:con.close()


@router.get('/fires')
def window_fires(bbox:str,window:str|None=None,limit:int=Query(2000,ge=1,le=5000),offset:int=Query(0,ge=0),geometry:bool=False):
    """All fire events of the window inside a box (e.g. a searched place), most recent first."""
    con,window=connect(window);meta=metadata(window)
    try:
        where,params=event_candidates(con,parse_bbox(bbox))
        count=con.execute('SELECT count(*) FROM events WHERE '+where,params).fetchone()[0]
        rows=con.execute('SELECT payload FROM events WHERE '+where+' ORDER BY end_time DESC,fire_id ASC LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        data=[describe(row,con,meta) for row in rows]
        if geometry:
            for event in data:event['footprint']=footprint(con,event['fire_id'])
        return {**meta,'data':data,'count':count,'limit':limit,'offset':offset,'has_more':offset+len(rows)<count,
                'basis':'all fire events of the window whose centroid lies in the box'}
    finally:con.close()


@router.get('/detections')
def detections(window:str|None=None,bbox:str|None=None,limit:int=Query(5000,ge=1,le=20000),offset:int=Query(0,ge=0)):
    """Clean (quality-filtered) satellite detections in the active period, before event grouping."""
    con,window=connect(window);meta=metadata(window)
    try:
        start,now,hours=active_period(meta)
        clauses=['time>=?','time<=?'];params=[start.isoformat(sep=' '),now.isoformat(sep=' ')]
        box=parse_bbox(bbox)
        if box:
            w,s,e,n=box;clauses+=['lon BETWEEN ? AND ?','lat BETWEEN ? AND ?'];params+=[w,e,s,n]
        where=' AND '.join(clauses)
        try:
            count=con.execute('SELECT count(*) FROM detections WHERE '+where,params).fetchone()[0]
            rows=con.execute('SELECT * FROM detections WHERE '+where+' ORDER BY time DESC LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        except sqlite3.OperationalError:raise HTTPException(503,'Awaiting snapshot rebuild with detection points')
        return {**meta,'data':[dict(r) for r in rows],'count':count,'limit':limit,'offset':offset,'has_more':offset+len(rows)<count,
                'basis':f'clean detections (nominal + high confidence) acquired in the last {hours} h of the window'}
    finally:con.close()


@router.get('/events/{fire_id}')
def event_detail(fire_id:str,window:str|None=None):
    con,window=connect(window);meta=metadata(window)
    try:
        row=con.execute('SELECT payload FROM events WHERE fire_id=?',(fire_id,)).fetchone()
        if row is None:raise HTTPException(404,'Fire event not found in this window')
        event=describe(row,con,meta);event['footprint']=footprint(con,fire_id)
        return {**meta,'data':event}
    finally:con.close()


@router.get('/grid/lambda')
def grid_lambda(window:str|None=None,bbox:str|None=None,limit:int=Query(500,ge=1,le=5000),offset:int=Query(0,ge=0)):
    con,window=connect(window);meta=metadata(window)
    try:
        box=parse_bbox(bbox);where='';params=[]
        if box:
            w,s,e,n=box;where=' WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?';params=[w,e,s,n]
        count=con.execute('SELECT count(*) FROM grid'+where,params).fetchone()[0]
        rows=con.execute('SELECT payload FROM grid'+where+' ORDER BY day,cell_id LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        return {**meta,'data':[json.loads(row['payload']) for row in rows],'count':count,'limit':limit,'offset':offset,'has_more':offset+len(rows)<count}
    finally:con.close()
