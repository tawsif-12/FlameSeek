"""Offline harmonization snapshot endpoints; never perform live network requests."""
from pathlib import Path
from datetime import timedelta
import importlib.util
import json,math,sqlite3
from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.encoders import jsonable_encoder
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
    con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
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


def describe(row,con,meta):
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
                         now=meta['now'],cfg={'translation':manifest()['translation']})
    return event


@router.get('/meta')
def get_meta(window:str|None=None):
    con,window=connect(window)
    try:return {**metadata(window),'available_windows':list(manifest()['windows'])}
    finally:con.close()


@router.get('/fires/active')
def active_fires(window:str|None=None,bbox:str|None=None,limit:int=Query(500,ge=1,le=5000),offset:int=Query(0,ge=0)):
    con,window=connect(window);meta=metadata(window)
    try:
        now=_translation.utc(meta['now']);start=now-timedelta(hours=manifest()['translation'].get('active_hours',24))
        clauses=['end_time>=?','end_time<=?'];params=[start.isoformat(sep=' '),now.isoformat(sep=' ')]
        box=parse_bbox(bbox)
        if box:
            w,s,e,n=box;clauses+=['lon BETWEEN ? AND ?','lat BETWEEN ? AND ?'];params +=[w,e,s,n]
        where=' AND '.join(clauses)
        count=con.execute('SELECT count(*) FROM events WHERE '+where,params).fetchone()[0]
        rows=con.execute('SELECT payload FROM events WHERE '+where+' ORDER BY end_time DESC LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
        return {**meta,'data':[describe(row,con,meta) for row in rows],'count':count,'limit':limit,'offset':offset,'has_more':offset+len(rows)<count}
    finally:con.close()


@router.get('/events/{fire_id}')
def event_detail(fire_id:str,window:str|None=None):
    con,window=connect(window);meta=metadata(window)
    try:
        row=con.execute('SELECT payload FROM events WHERE fire_id=?',(fire_id,)).fetchone()
        if row is None:raise HTTPException(404,'Fire event not found in this window')
        return {**meta,'data':describe(row,con,meta)}
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
