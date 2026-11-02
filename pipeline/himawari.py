"""Day-partitioned AHI HSD preparation, contextual fires and observation masks.

Pixel states are retained even outside the valid view or under cloud. No raw
files are modified. Geometry uses WGS84 geodesic pixel corners, not A/cos(VZA).
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter
from scipy.constants import h, c, k, Stefan_Boltzmann
from sklearn.neighbors import BallTree

from pipeline.config import ROOT
from pipeline import partitions


def json_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def clean(v):
        if isinstance(v, dict):
            return {str(k):clean(x) for k,x in v.items()}
        if isinstance(v, (list, tuple, np.ndarray)):
            return [clean(x) for x in v]
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (float, np.floating)):
            return float(v) if np.isfinite(v) else None
        if isinstance(v, (datetime, pd.Timestamp, Path)):
            return str(v)
        return v
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(clean(data),indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def lst(utc, lon):
    t = pd.Timestamp(utc)
    longitude = np.asarray(lon)
    longitude = np.where(np.isfinite(longitude), longitude, np.nan)
    return (t.hour+t.minute/60+t.second/3600+longitude/15) % 24


def view_zenith(lon, lat, sat_lon=140.7, sat_lat=0., sat_alt_m=35785863.):
    from pyproj import Transformer
    tr = Transformer.from_crs(4979,4978,always_xy=True)
    x,y,z = tr.transform(lon,lat,np.zeros_like(lon))
    sx,sy,sz = tr.transform(sat_lon,sat_lat,sat_alt_m)
    ray = np.stack([sx-x,sy-y,sz-z],axis=-1)
    lo,la = np.radians(lon),np.radians(lat)
    normal = np.stack([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],axis=-1)
    return np.degrees(np.arccos(np.clip((ray*normal).sum(axis=-1)/np.linalg.norm(ray,axis=-1),-1,1)))


def derive_mir_constant(cfg):
    """Fit response-weighted L_lambda(T) = a*T^4, through zero, 650..1300 K.

    L is in W m-2 sr-1 um-1, matching Satpy AHI radiance. a therefore has
    units W m-2 sr-1 um-1 K-4; A in km2 makes returned FRP numerically MW.
    """
    p = ROOT/cfg['himawari']['srf_file']
    raw = np.loadtxt(p,skiprows=4)
    lam = 1e4/raw[:,0]  # cm-1 -> micrometres; response dimensionless
    order = np.argsort(lam)
    lam,response = lam[order],np.maximum(0,raw[order,1])
    T = np.arange(650.,1301.)
    lm = lam[:,None]*1e-6
    planck = (2*h*c*c/lm**5)/np.expm1(h*c/(lm*k*T[None,:]))*1e-6
    L = np.trapezoid(planck*response[:,None],lam,axis=0)/np.trapezoid(response,lam)
    X = T**4
    a = float(X@L/(X@X))
    result = {'a':a,'sigma':Stefan_Boltzmann,'sigma_over_a':Stefan_Boltzmann/a,
              'temperature_range_k':[650,1300], 'samples':len(T),
              'relative_rmse':float(np.sqrt(np.mean(((a*X-L)/L)**2))),
              'max_relative_error':float(np.max(np.abs((a*X-L)/L))),
              'radiance_units':'W m-2 sr-1 um-1',
              'a_units':'W m-2 sr-1 um-1 K-4',
              'method':'SRF weighted wavelength radiance; least squares through origin against T^4',
              'srf_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'source_url':cfg['himawari']['srf_url']}
    json_write(cfg['paths']['window_outputs']/'himawari/mir_constant.json',result)
    return result


def discover(cfg):
    base = cfg['paths']['himawari_dir']/cfg['window']['name']
    found = {}
    for f in sorted(base.rglob('*.DAT.bz2')):
        m = re.fullmatch(r'HS_H0[89]_(\d{8})_(\d{4})_(B\d{2})_FLDK_R20_(S\d{4})\.DAT.bz2',f.name)
        if m:
            d,hhmm,b,s = m.groups()
            time = pd.Timestamp(datetime.strptime(d+hhmm,'%Y%m%d%H%M'),tz='UTC')
            if cfg['window']['start'] <= time.date() <= cfg['window']['end'] and time.minute == 0:
                found.setdefault(time,{})[(b,s)] = f
    complete, missing = {},[]
    for day in partitions.days(cfg['window']['start'],cfg['window']['end']):
        for hour in range(24):
            t = pd.Timestamp(datetime.combine(day,datetime.min.time()),tz='UTC')+pd.Timedelta(hours=hour)
            group = found.get(t,{})
            required = [(b,s) for b in ('B07','B14','B15') for s in cfg['himawari'].get('segments',['S0310','S0410'])]
            if all(key in group for key in required):
                complete[t]=[group[key] for key in required]
            else:
                missing.append({'utc':t,'missing':[f'{b}_{s}' for b,s in required if (b,s) not in group]})
    return complete,missing


def geometry(area, cfg, orbit):
    from global_land_mask import globe
    from pyproj import Transformer
    lon,lat = area.get_lonlats()
    lon,lat=np.asarray(lon),np.asarray(lat)
    vza = view_zenith(lon,lat,orbit['satellite_actual_longitude'],
                       orbit['satellite_actual_latitude'],orbit['satellite_actual_altitude'])
    x,y = area.get_proj_coords()
    tr = Transformer.from_crs(area.crs,4326,always_xy=True)
    dx,dy=abs(area.pixel_size_x)/2,abs(area.pixel_size_y)/2
    corners = [tr.transform(x+ox,y+oy) for ox,oy in [(-dx,-dy),(dx,-dy),(dx,dy),(-dx,dy)]]
    # Equal-area shoelace, four geolocated corners per native AHI pixel.
    eq = Transformer.from_crs(4326,6933,always_xy=True)
    xy = [eq.transform(*pair) for pair in corners]
    pix_area=np.zeros(lon.shape)
    for i in range(4):
        pix_area += xy[i][0]*xy[(i+1)%4][1]-xy[(i+1)%4][0]*xy[i][1]
    pix_area=np.abs(pix_area)*.5/1e6
    finite=np.isfinite(lon)&np.isfinite(lat)
    land=np.zeros(lon.shape,bool)
    land[finite]=globe.is_land(lat[finite],lon[finite])
    out={'longitude':lon,'latitude':lat,'vza_deg':vza,'pixel_area_km2':pix_area,'land':land}
    union=np.zeros(lon.shape,bool)
    for name,(w,s,e,n) in cfg['himawari']['regions'].items():
        box=finite&(lon>=w)&(lon<=e)&(lat>=s)&(lat<=n)
        out['box_'+name]=box
        union |= box
    out['in_regions']=union
    return out


def prepare_scan(files, cfg, geom=None):
    import dask
    from satpy import Scene, DataQuery
    from pyorbital.astronomy import sun_zenith_angle
    scene=Scene(reader='ahi_hsd',filenames=[str(f) for f in files])
    rq=DataQuery(name='B07',calibration='radiance')
    scene.load(['B07','B14','B15',rq])
    boxes=list(cfg['himawari']['regions'].values())
    # Halo wider than the maximum contextual window; exact bbox masks follow.
    bbox=(min(b[0] for b in boxes)-2,min(b[1] for b in boxes)-2,
          max(b[2] for b in boxes)+2,max(b[3] for b in boxes)+2)
    crop=scene.crop(ll_bbox=bbox)
    attrs=crop['B07'].attrs
    if geom is None:
        geom=geometry(attrs['area'],cfg,attrs['orbital_parameters'])
    arrays=dask.compute(*[crop[b].data for b in ['B07','B14','B15',rq]],scheduler='threads',num_workers=3)
    frame={name:np.asarray(a,dtype=np.float32) for name,a in zip(['b07','b14','b15','radiance'],arrays)}
    if sorted(crop[rq].attrs['units'].split()) != sorted('W m-2 sr-1 um-1'.split()):
        # Satpy 0.60 writes 'W m-2 um-1 sr-1'; term order is irrelevant, but never silently
        # mix per-wavenumber (cm-1) and per-wavelength (um) radiance.
        raise ValueError(f'Unsupported radiance unit: {crop[rq].attrs["units"]}')
    orbit=attrs['orbital_parameters']
    frame['vza_deg']=view_zenith(geom['longitude'],geom['latitude'],orbit['satellite_actual_longitude'],
                                 orbit['satellite_actual_latitude'],orbit['satellite_actual_altitude']).astype(np.float32)
    obs=attrs['time_parameters']['observation_start_time']
    frame['sza_deg']=np.asarray(sun_zenith_angle(obs,geom['longitude'],geom['latitude']),np.float32)
    return frame,geom,obs


def contextual(frame, geom, settings, constant, day_fix=None):
    """Contextual fire test. day_fix (D73, Northern Australia check only; None = unchanged):
      {'reflectance': R0.86 µm reflectance factor on this grid (NaN where absent),
       'reflectance_max': daytime cloud threshold on R/cos(SZA),
       'sza_max_deg': reflectance test used where SZA < this,
       'delta_cap_k': cap on the daytime B07-B14 contextual term (None = no cap)}.
    Where the reflectance test applies, the B14-B15 > max test is not used; the cold and
    split-window-min tests stay. Night pixels are unchanged."""
    b7,b14,b15,L=[frame[x] for x in ['b07','b14','b15','radiance']]
    cc,dc=settings['cloud'],settings['detection']
    data_ok=np.isfinite(b7)&np.isfinite(b14)&np.isfinite(b15)&np.isfinite(L)
    valid=geom['vza_deg']<=settings['max_vza_deg']
    cloud=data_ok&((b14<cc['cold_b14_k'])|((b14-b15)<cc['split_window_min_k'])|
                   ((b14-b15)>cc['split_window_max_k']))
    day=frame['sza_deg']<settings['day_sza_deg']
    if day_fix is not None:
        sza=frame['sza_deg']
        reflective=day&(sza<day_fix['sza_max_deg'])
        r=day_fix['reflectance']/np.cos(np.radians(np.minimum(sza,89.)))
        data_ok=data_ok&~(reflective&~np.isfinite(r))  # absent reflectance by day = unknown, not IR-masked
        cloud_day=data_ok&((b14<cc['cold_b14_k'])|((b14-b15)<cc['split_window_min_k'])|(r>day_fix['reflectance_max']))
        cloud=np.where(reflective,cloud_day,cloud&data_ok)
    clear=data_ok&valid&~cloud
    delta=b7-b14
    candidate=clear&geom['land']&(b7>np.where(day,dc['candidate_day_k'],dc['candidate_night_k']))&(delta>dc['candidate_delta_k'])
    bg=clear&geom['land']&~candidate
    fire=np.zeros(b7.shape,bool)
    bgL=np.full(b7.shape,np.nan)
    bg_n=np.zeros(b7.shape,np.int32)
    bg_window=np.zeros(b7.shape,np.int16)
    unresolved=candidate.copy()
    for size in dc['background_windows']:
        count=uniform_filter(bg.astype(float),size,mode='constant')*size**2
        enough=unresolved&(count>=max(dc['background_min_pixels'],size**2*dc['background_min_fraction']))
        if not enough.any():
            continue
        def moments(a):
            mean=uniform_filter(np.where(bg,a,0).astype(float),size,mode='constant')*size**2/np.maximum(count,1)
            second=uniform_filter(np.where(bg,a*a,0).astype(float),size,mode='constant')*size**2/np.maximum(count,1)
            return mean,np.sqrt(np.maximum(second-mean*mean,0))
        mean,sd=moments(b7)
        md,sdd=moments(delta)
        ml,_=moments(L)
        delta_term=np.maximum(dc['sigma_multiplier']*sdd,dc['anomaly_floor_k'])
        if day_fix is not None and day_fix.get('delta_cap_k') is not None:
            delta_term=np.where(day,np.minimum(delta_term,day_fix['delta_cap_k']),delta_term)
        fire[enough]=(b7>mean+np.maximum(dc['sigma_multiplier']*sd,dc['anomaly_floor_k']))[enough]&(
            delta>md+delta_term)[enough]
        bgL[enough]=ml[enough]
        bg_n[enough]=np.rint(count[enough]).astype(int)
        bg_window[enough]=size
        unresolved[enough]=False
    frp=np.where(fire,geom['pixel_area_km2']*constant['sigma_over_a']*np.maximum(L-bgL,0),np.nan)
    # 0=clear/no fire, 1=fire, 2=cloud, 3=outside valid view, 4=missing, 5=water,
    # 6=candidate with insufficient background. Unknowns must not become zeros.
    status=np.zeros(b7.shape,np.uint8)
    status[~geom['land']]=5
    status[fire]=1
    status[unresolved]=6
    status[cloud]=2
    status[~valid]=3
    status[~data_ok]=4
    return dict(status=status,fire=fire,cloud=cloud,clear=clear,frp_mw=frp,day=day,
                bg_radiance=bgL,bg_n=bg_n,bg_window=bg_window)


def nearby(query, refs, minutes=60, radius_km=2):
    """Return any reference within both spatial and temporal limits per query."""
    if len(query)==0 or len(refs)==0:
        return np.zeros(len(query),bool)
    tree=BallTree(np.radians(refs[['latitude','longitude']].to_numpy()),metric='haversine')
    indices=tree.query_radius(np.radians(query[['latitude','longitude']].to_numpy()),r=radius_km/6371.0088)
    # Explicit seconds since epoch (D72): astype('int64') depends on the column's unit
    # (us under pandas 3), which once made every tolerance 1,000x too wide.
    epoch=pd.Timestamp('1970-01-01',tz='UTC'); second=pd.Timedelta(seconds=1)
    qt=((pd.to_datetime(query['acq_datetime_utc'],utc=True)-epoch)/second).to_numpy(float)
    rt=((pd.to_datetime(refs['acq_datetime_utc'],utc=True)-epoch)/second).to_numpy(float)
    return np.array([bool(np.any(np.abs(rt[ix]-t)<=minutes*60)) for ix,t in zip(indices,qt)])


def detection_frame(result, frame, geom, time, obs):
    row,col=np.where(result['fire']&geom['in_regions'])
    out=pd.DataFrame({'acq_datetime_utc':time,'observation_start_utc':pd.Timestamp(obs,tz='UTC'),
                      'pixel_id':row*result['fire'].shape[1]+col,'row':row,'col':col})
    for name in ['longitude','latitude','vza_deg','pixel_area_km2']:
        out[name]=geom[name][row,col]
    for name in ['b07','b14','b15','radiance','sza_deg']:
        out[name]=frame[name][row,col]
    for name in ['frp_mw','bg_radiance','bg_n','bg_window']:
        out[name]=result[name][row,col]
    out['daynight']=np.where(result['day'][row,col],'D','N')
    out['lst_h']=lst(time,out['longitude'])
    for name in (k for k in geom if k.startswith('box_')):
        out[name]=geom[name][row,col]
    return out


def scan_stats(result,geom,time,cfg):
    rows=[]
    for name in cfg['himawari']['regions']:
        box=geom['box_'+name]
        weights=geom['pixel_area_km2']
        valid=box&(geom['vza_deg']<=cfg['himawari']['max_vza_deg'])
        landvalid=valid&geom['land']
        clear=landvalid&result['clear']
        fire=box&result['fire']
        rows.append({'region':name,'acq_datetime_utc':time,'lst_h':lst(time,np.mean(geom['longitude'][box])),
                     'valid_area_share':weights[valid].sum()/weights[box].sum(),
                     'clear_sky_fraction':weights[clear].sum()/weights[landvalid].sum() if landvalid.any() else np.nan,
                     'fire_pixels':int(fire.sum()), 'frp_mw':float(np.nansum(result['frp_mw'][fire])) if clear.any() else np.nan,
                     'box_area_km2':weights[box].sum(),'valid_land_area_km2':weights[landvalid].sum()})
    return rows


def prepare(cfg, force=False):
    """Cache calibrated native grids day by day; incremental atomic scan writes."""
    scans,missing=discover(cfg)
    cache=cfg['paths']['window_interim']/'himawari'
    cache.mkdir(parents=True,exist_ok=True)
    gp=cache/'geometry.npz'
    geom=dict(np.load(gp)) if gp.exists() and not force else None
    inventory={'window':cfg['window']['name'],'missing_scans':missing,'prepared':[],'errors':[]}
    for i,(t,files) in enumerate(scans.items(),1):
        path=cache/t.strftime('%Y/%m/%d')/t.strftime('%H%M.npz')
        try:
            if force or not path.exists():
                frame,geom,obs=prepare_scan(files,cfg,geom)
                if not gp.exists() or force and i==1:
                    np.savez_compressed(gp,**geom)
                path.parent.mkdir(parents=True,exist_ok=True)
                tmp=path.with_suffix('.tmp.npz')
                np.savez_compressed(tmp,**frame,observation_start_utc=str(obs),nominal_utc=str(t))
                tmp.replace(path)
            inventory['prepared'].append({'utc':t,'cache':path})
        except Exception as exc:
            inventory['errors'].append({'utc':t,'error':repr(exc)})
            print(f'ERROR {t}: {exc}',flush=True)
        print(f'[prepare] {i}/{len(scans)} {t}',flush=True)
        json_write(cache/'inventory.json',inventory)
    return inventory


if __name__=='__main__':
    import argparse
    from pipeline.config import load_settings
    ap=argparse.ArgumentParser()
    ap.add_argument('--window',default='current_2026')
    ap.add_argument('--force',action='store_true')
    a=ap.parse_args()
    prepare(load_settings(window=a.window),a.force)
