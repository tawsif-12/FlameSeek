"""Positive controls using real AHI imagery and HSD radiometric coefficients."""
from copy import deepcopy
import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter
from scipy.constants import Stefan_Boltzmann
from pipeline import himawari as hw


def band7_coefficients(scene):
    handler=scene._readers['ahi_hsd'].file_handlers['hsd_b07'][0]
    header=handler._header
    cal=header['calibration']
    return dict(wavelength_m=float(header['block5']['central_wave_length'][0])*1e-6,
                c=float(cal['speed_of_light'][0]),h=float(cal['planck_constant'][0]),k=float(cal['boltzmann_constant'][0]),
                c0=float(cal['c0_rad2tb_conversion'][0]),c1=float(cal['c1_rad2tb_conversion'][0]),c2=float(cal['c2_rad2tb_conversion'][0]))


def radiance_to_bt(radiance, coeff):
    w=coeff['wavelength_m']; c,h,k=[coeff[x] for x in ['c','h','k']]
    effective=h*c/(k*w)/np.log1p(2*h*c*c/(w**5*np.asarray(radiance)*1e6))
    return coeff['c0']+coeff['c1']*effective+coeff['c2']*effective**2


def bt_to_radiance(temperature, coeff):
    # Solve the exact radiance-to-BT quadratic with its physical near-linear root.
    t=np.asarray(temperature,dtype=float)
    a,b=coeff['c2'],coeff['c1']
    effective=2*(t-coeff['c0'])/(b+np.sqrt(b*b+4*a*(t-coeff['c0'])))
    w=coeff['wavelength_m']; c,h,k=[coeff[x] for x in ['c','h','k']]
    return 2*h*c*c/w**5/np.expm1(h*c/(k*w*effective))*1e-6


def inject(frame, row, col, fraction, temperature, coeff):
    if not 0 < fraction <= 1:
        raise ValueError('Fire fraction must be in (0, 1]')
    changed={key:np.copy(value) for key,value in frame.items()}
    original=float(frame['radiance'][row,col])
    hot=float(bt_to_radiance(temperature,coeff))
    changed['radiance'][row,col]=(1-fraction)*original+fraction*hot
    changed['b07'][row,col]=radiance_to_bt(changed['radiance'][row,col],coeff)
    return changed


def radiometric_and_injection(cfg):
    from satpy import Scene, DataQuery
    scans,_=hw.discover(cfg)
    cache=cfg['paths']['window_interim']/'himawari'
    geom=dict(np.load(cache/'geometry.npz'))
    constant=hw.derive_mir_constant(cfg)
    statistics=[]; injections=[]; metadata=[]
    settings=cfg['himawari']
    for hour in [5,7,9,18,20,22]:
        t=pd.Timestamp(str(cfg['window']['start'])+f' {hour:02}:00',tz='UTC')
        scene=Scene(reader='ahi_hsd',filenames=list(map(str,scans[t])))
        scene.load(['B07','B14','B15',DataQuery(name='B07',calibration='radiance')])
        coeff=band7_coefficients(scene)
        for band in ['B07','B14','B15']:
            attrs=scene[band].attrs
            metadata.append(dict(utc=str(t),band=band,units=attrs['units'],calibration=str(attrs['calibration'])))
        frame=dict(np.load(cache/t.strftime('%Y/%m/%d/%H%M.npz')))
        frame={k:v for k,v in frame.items() if k in ['b07','b14','b15','radiance','sza_deg','vza_deg']}
        geom['vza_deg']=frame.pop('vza_deg')
        result=hw.contextual(frame,geom,settings,constant)
        clear=geom['box_Bangladesh'] & geom['land'] & result['clear']
        assert clear.any(),f'No clear land pixels in {t}'
        for band in ['b07','b14','b15']:
            values=frame[band][clear]
            record=dict(utc=str(t),daynight='D' if hour<12 else 'N',band=band,n=len(values),
                        min=float(values.min()),p05=float(np.percentile(values,5)),median=float(np.median(values)),
                        p95=float(np.percentile(values,95)),max=float(values.max()),units='K')
            statistics.append(record)
            print('radiometric',record,flush=True)
        roundtrip=radiance_to_bt(frame['radiance'][clear],coeff)
        err=float(np.nanmax(abs(roundtrip-frame['b07'][clear])))
        metadata.append(dict(utc=str(t),radiance_bt_max_error_k=err,band7_coefficients=coeff))
        # Select an interior, clear, typical-temperature pixel with adequate clear background.
        count=uniform_filter((result['clear'] & geom['land']).astype(float),11,mode='constant')*121
        candidates=clear & (count>=100)
        candidates[:16,:]=False; candidates[-16:,:]=False; candidates[:,:16]=False; candidates[:,-16:]=False
        rr,cc=np.where(candidates)
        assert len(rr),'No injection site with sufficient clear background'
        target=np.argmin(abs(frame['b07'][rr,cc]-np.median(frame['b07'][clear])))
        row,col=int(rr[target]),int(cc[target])
        # Native 65x65 real tile preserves all contextual windows and isolates trials.
        sl=(slice(row-32,row+33),slice(col-32,col+33))
        tile={k:v[sl].copy() for k,v in frame.items()}
        gg={k:v[sl].copy() for k,v in geom.items()}
        for fraction in settings.get('positive_controls',{}).get('fractions',[.001,.005,.01]):
            changed=inject(tile,32,32,fraction,800.,coeff)
            res=hw.contextual(changed,gg,settings,constant)
            excess=float(changed['radiance'][32,32]-tile['radiance'][32,32])
            record=dict(utc=str(t),daynight='D' if hour<12 else 'N',fire_temperature_k=800.,fraction=fraction,
                        longitude=float(gg['longitude'][32,32]),latitude=float(gg['latitude'][32,32]),
                        pixel_area_km2=float(gg['pixel_area_km2'][32,32]),injected_b07_k=float(changed['b07'][32,32]),
                        original_b07_k=float(tile['b07'][32,32]),status=int(res['status'][32,32]),
                        detected=bool(res['fire'][32,32]),retrieved_frp_mw=float(res['frp_mw'][32,32]),
                        injected_mir_frp_mw=float(gg['pixel_area_km2'][32,32]*constant['sigma_over_a']*excess),
                        blackbody_fire_power_mw=float(gg['pixel_area_km2'][32,32]*fraction*Stefan_Boltzmann*800**4))
            injections.append(record); print('injection',record,flush=True)
    bt_verified=all(m.get('units','K')=='K' and m.get('calibration','brightness_temperature')=='brightness_temperature' for m in metadata)
    roundtrip_verified=all(m.get('radiance_bt_max_error_k',0)<.001 for m in metadata)
    synthetic_verified=all(any(x['detected'] for x in injections if x['utc']==str(t)) for t in pd.to_datetime([r['utc'] for r in injections],utc=True).unique())
    result=dict(window=cfg['window']['name'],radiometric=statistics,metadata=metadata,injections=injections,
                brightness_temperatures_verified=bt_verified,radiometric_roundtrip_verified=roundtrip_verified,
                synthetic_verified=synthetic_verified,bug_fixed=False)
    hw.json_write(cfg['paths']['window_outputs']/'himawari/positive_controls.json',result)
    return result


def real_controls(cfg):
    """Search all downloaded S03-S04 native locations, not just South Asia crops."""
    import dask
    from satpy import Scene, DataQuery
    from pyproj import Transformer
    from pyorbital.astronomy import sun_zenith_angle
    scans,_=hw.discover(cfg)
    refs=pd.read_parquet(cfg['paths']['window_processed']/'detections_clean.parquet')
    v=refs[refs.sensor.eq('VIIRS')].groupby(['fire_id','platform','acq_datetime_utc'],as_index=False).agg(
        frp_mw=('frp_mw','sum'),longitude=('longitude','mean'),latitude=('latitude','mean'))
    v['acq_datetime_utc']=pd.to_datetime(v.acq_datetime_utc,utc=True)
    v=v[v.frp_mw>100].copy()
    v['nearest_step']=v.acq_datetime_utc.dt.round('h')
    first=Scene(reader='ahi_hsd',filenames=list(map(str,next(iter(scans.values())))))
    first.load(['B07'])
    handlers=first._readers['ahi_hsd'].file_handlers['hsd_b07']
    areas=[x.get_area_def(None) for x in handlers]
    project=Transformer.from_crs(4326,areas[0].crs,always_xy=True)
    x,y=project.transform(v.longitude.values,v.latitude.values)
    inside=np.zeros(len(v),bool)
    for a in areas:
        w,s,e,n=a.area_extent
        inside |= np.isfinite(x)&np.isfinite(y)&(x>=w)&(x<=e)&(y>=s)&(y<=n)
    v=v[inside].copy()
    v['nominal_vza']=hw.view_zenith(v.longitude.values,v.latitude.values)
    # A small margin admits near-boundary events for exact native-pixel screening.
    v=v[v.nominal_vza<65.2].copy()
    constant=hw.derive_mir_constant(cfg); rows=[]
    for index,r in enumerate(v.itertuples(),1):
        record=r._asdict(); record.pop('Index',None)
        if r.nearest_step not in scans:
            record.update(observed=False,detected=None,reason='nearest scan unavailable'); rows.append(record); continue
        scene=Scene(reader='ahi_hsd',filenames=list(map(str,scans[r.nearest_step])))
        rq=DataQuery(name='B07',calibration='radiance')
        scene.load(['B07','B14','B15',rq])
        area=scene['B07'].attrs['area']
        col,row=area.get_array_indices_from_lonlat(r.longitude,r.latitude)
        # Slice by native indices, maintaining a full 31-pixel contextual halo.
        crop=scene.crop(area=area[max(0,int(row)-40):int(row)+41,max(0,int(col)-40):int(col)+41])
        attrs=crop['B07'].attrs
        gg=hw.geometry(attrs['area'],cfg,attrs['orbital_parameters'])
        values=dask.compute(*[crop[b].data for b in ['B07','B14','B15',rq]],scheduler='synchronous')
        frame={key:np.asarray(value,dtype=np.float32) for key,value in zip(['b07','b14','b15','radiance'],values)}
        obs=attrs['time_parameters']['observation_start_time']
        frame['sza_deg']=sun_zenith_angle(obs,gg['longitude'],gg['latitude'])
        d=(gg['longitude']-r.longitude)**2+(gg['latitude']-r.latitude)**2
        pix=np.unravel_index(np.nanargmin(d),d.shape)
        vza=float(gg['vza_deg'][pix])
        if vza>=65:
            continue
        result=hw.contextual(frame,gg,cfg['himawari'],constant)
        hh=hw.detection_frame(result,frame,{**gg,'in_regions':np.ones(d.shape,bool)},r.nearest_step,obs)
        query=pd.DataFrame(dict(latitude=[r.latitude],longitude=[r.longitude],acq_datetime_utc=[r.acq_datetime_utc]))
        detected=bool(hw.nearby(query,hh,30,2)[0])
        status=int(result['status'][pix])
        record.update(vza_deg=vza,status=status,observed=status in [0,1],detected=detected,
                      b07_k=float(frame['b07'][pix]),b14_k=float(frame['b14'][pix]),b15_k=float(frame['b15'][pix]),
                      reason='clear' if status in [0,1] else 'cloud/water/missing/background unknown')
        rows.append(record)
        print(f'[real control] {index}/{len(v)} FRP={r.frp_mw:.1f} MW, VZA={vza:.1f}, status={status}, detected={detected}',flush=True)
    result=pd.DataFrame(rows)
    result.to_csv(cfg['paths']['window_outputs']/'himawari/real_positive_controls.csv',index=False)
    summary=dict(n_segment_valid_view_events=len(result),n_observed=int(result.observed.sum()) if len(result) else 0,
                 n_detected=int(result.detected.fillna(False).sum()) if len(result) else 0,
                 n_missing_nearest_scan=int(result.reason.eq('nearest scan unavailable').sum()) if len(result) else 0,
                 frp_threshold_mw=100.,match_radius_km=2,match_minutes=30,window=cfg['window']['name'],
                 n_unique_events=int(result.fire_id.nunique()) if len(result) else 0)
    hw.json_write(cfg['paths']['window_outputs']/'himawari/real_positive_controls.json',summary)
    return summary


if __name__=='__main__':
    from pipeline.config import load_settings
    cfg=load_settings()
    a=radiometric_and_injection(cfg)
    if not a['synthetic_verified']:
        raise RuntimeError('Positive synthetic control failed; inspect detector before continuing')
    b=real_controls(cfg)
    print('Real positive controls:',b,flush=True)
