"""Fine-fraction synthetic detection limits on untouched real AHI backgrounds."""
from pathlib import Path
import json
import re
import numpy as np
import pandas as pd
from pipeline import himawari as hw, himawari_verify as verify


def segment_inventory(cfg,segments,hours=None):
    base=cfg['paths']['himawari_dir']/cfg['window']['name']
    pattern=re.compile(r'HS_H0[89]_(\d{8})_(\d{4})_(B\d{2})_FLDK_R20_(S\d{4})\.DAT\.bz2')
    groups={}; counts={s:0 for s in segments}
    for p in sorted(base.rglob('*.DAT.bz2')) if base.exists() else []:
        match=pattern.fullmatch(p.name)
        if not match: continue
        day,time,band,segment=match.groups()
        t=pd.to_datetime(day+time,format='%Y%m%d%H%M',utc=True)
        if not cfg['window']['start']<=t.date()<=cfg['window']['end']: continue
        if segment not in counts or band not in ['B07','B14','B15']: continue
        counts[segment]+=1
        groups.setdefault(t,{})[(band,segment)]=p
    required=[(band,seg) for band in ['B07','B14','B15'] for seg in segments]
    complete={t:[parts[key] for key in required] for t,parts in groups.items() if all(key in parts for key in required)}
    return dict(raw_file_counts=counts,n_complete_steps=len(complete),complete_steps=complete)


def trial_rows(tile,geom,coeff,cfg,time,region):
    rows=[]; settings=cfg['phase3c']['injection']
    # All tiles are centered on the selected unmodified real pixel.
    row,col=np.array(tile['b07'].shape)//2
    constant=json.loads((cfg['paths']['window_outputs']/'himawari/mir_constant.json').read_text())
    baseline=hw.contextual(tile,geom,cfg['himawari'],constant)
    if baseline['status'][row,col]!=0:
        raise ValueError('Injection requires a clear, valid non-fire land baseline')
    for fraction in settings['fractions']:
        changed=verify.inject(tile,row,col,fraction,settings['temperature_k'],coeff)
        result=hw.contextual(changed,geom,cfg['himawari'],constant)
        added=float(changed['radiance'][row,col]-tile['radiance'][row,col])
        rows.append(dict(region=region,utc=str(time),daynight='D' if tile['sza_deg'][row,col]<90 else 'N',
                         fraction=fraction,fraction_percent=fraction*100,
                         fire_temperature_k=settings['temperature_k'],vza_deg=float(geom['vza_deg'][row,col]),
                         pixel_area_km2=float(geom['pixel_area_km2'][row,col]),longitude=float(geom['longitude'][row,col]),
                         latitude=float(geom['latitude'][row,col]),original_b07_k=float(tile['b07'][row,col]),
                         injected_b07_k=float(changed['b07'][row,col]),status=int(result['status'][row,col]),
                         detected=bool(result['fire'][row,col]),
                         implied_frp_mw=float(geom['pixel_area_km2'][row,col]*constant['sigma_over_a']*added),
                         retrieved_frp_mw=float(result['frp_mw'][row,col])))
    return rows


def fraction_summary(trials):
    frame=pd.DataFrame(trials)
    if frame.empty: return []
    rows=[]
    for fraction,d in frame.groupby('fraction',sort=True):
        rows.append(dict(fraction=float(fraction),fraction_percent=float(fraction*100),n=len(d),
                         detected=int(d.detected.sum()),detection_rate=float(d.detected.mean()),
                         frp_median_mw=float(d.implied_frp_mw.median()),frp_min_mw=float(d.implied_frp_mw.min()),
                         frp_max_mw=float(d.implied_frp_mw.max())))
    return rows


def estimate_f50(summary):
    """Interpolate observed 50% crossing on log power; never extrapolate."""
    label='detection limit from synthetic injection'
    if not summary: return dict(status='awaiting data',label=label,frp50_mw=None,bracket_mw=None)
    power=np.array([r['frp_median_mw'] for r in summary],float)
    rates=np.array([r['detection_rate'] for r in summary],float)
    if np.any(np.diff(power)<=0) or np.any(np.diff(rates)<0):
        return dict(status='not estimable',label=label,frp50_mw=None,bracket_mw=None,reason='Nonmonotone trial response; inspect individual contexts')
    equal=np.where(rates==.5)[0]
    if len(equal):
        # A plateau at 50% does not determine a unique crossing.
        low,high=power[equal[0]],power[equal[-1]]
        return dict(status='estimated' if len(equal)==1 else 'interval only',label=label,
                    frp50_mw=float(low) if len(equal)==1 else None,bracket_mw=[float(low),float(high)],
                    method='Observed 50% response at tested fractions; plateau interval retained')
    upper=np.where(rates>.5)[0]
    lower=np.where(rates<.5)[0]
    if not len(upper) or not len(lower):
        return dict(status='not bracketed',label=label,frp50_mw=None,bracket_mw=None,
                    bound_mw=float(power[0] if rates[0]>.5 else power[-1]),
                    bound_direction='below' if rates[0]>.5 else 'above',reason='Tested powers do not bracket a 50% response')
    hi=upper[0]; lo=hi-1
    weight=(.5-rates[lo])/(rates[hi]-rates[lo])
    value=np.exp(np.log(power[lo])+weight*(np.log(power[hi])-np.log(power[lo])))
    return dict(status='estimated',label=label,frp50_mw=float(value),bracket_mw=[float(power[lo]),float(power[hi])],
                method='Linear interpolation of detection fraction against log median implied FRP between bracketing tested fractions; descriptive estimate, not logistic validation')


def bangladesh(cfg):
    cache=cfg['paths']['window_interim']/'himawari'; out=cfg['paths']['window_outputs']
    audit_path=out/'himawari/positive_controls.json'
    if not audit_path.exists() or not (cache/'geometry.npz').exists():
        return dict(status='awaiting data',reason='Phase 3b control metadata or real calibrated scans absent',trials=[])
    audit=json.loads(audit_path.read_text())
    original={r['utc']:r for r in audit['injections'] if r['fraction']==.001}
    coefficients={r['utc']:r['band7_coefficients'] for r in audit['metadata'] if 'band7_coefficients' in r}
    geom=dict(np.load(cache/'geometry.npz'))
    rows=[]; missing=[]
    for hour in cfg['phase3c']['injection']['bangladesh_hours_utc']:
        t=pd.Timestamp(str(cfg['window']['start'])+f' {hour:02}:00',tz='UTC')
        path=cache/t.strftime('%Y/%m/%d/%H%M.npz'); key=str(t)
        if not path.exists() or key not in original or key not in coefficients:
            missing.append(str(t)); continue
        frame=dict(np.load(path)); geom['vza_deg']=frame['vza_deg']
        site=original[key]
        distance=(geom['longitude']-site['longitude'])**2+(geom['latitude']-site['latitude'])**2
        row,col=np.unravel_index(np.nanargmin(distance),distance.shape)
        if min(row,col)<32 or row+32>=distance.shape[0] or col+32>=distance.shape[1]:
            raise ValueError('Original control site lacks a 32-pixel halo')
        patch=(slice(row-32,row+33),slice(col-32,col+33))
        tile={k:frame[k][patch].copy() for k in ['b07','b14','b15','radiance','sza_deg']}
        geometry={k:v[patch].copy() for k,v in geom.items()}
        rows.extend(trial_rows(tile,geometry,coefficients[key],cfg,t,'Bangladesh'))
        print(f'[injection limit] {t}: five fractions tested',flush=True)
    summary=fraction_summary(rows)
    by_dn={dn:dict(summary=fraction_summary([r for r in rows if r['daynight']==dn])) for dn in ['D','N']}
    for dn in by_dn: by_dn[dn]['f50']=estimate_f50(by_dn[dn]['summary'])
    return dict(status='completed' if not missing else 'partial; awaiting data',trials=rows,summary=summary,
                f50=estimate_f50(summary),by_daynight=by_dn,missing_scans=missing,n_contexts=len(rows)//len(cfg['phase3c']['injection']['fractions']))


def near_nadir(cfg):
    settings=cfg['phase3c']['injection']['near_nadir']
    inv=segment_inventory(cfg,settings['segments'])
    if inv['n_complete_steps']==0:
        return dict(status='awaiting data',reason='No complete B07/B14/B15 scans for near-nadir land box',
                    box=settings['box'],required_segments=settings['segments'],raw_file_counts=inv['raw_file_counts'],
                    summary=[],trials=[],f50=estimate_f50([]))
    from satpy import Scene,DataQuery
    from scipy.ndimage import uniform_filter
    import dask
    from pyorbital.astronomy import sun_zenith_angle
    rows=[]; missing=[]
    for hour in settings['hours_utc']:
        t=pd.Timestamp(str(cfg['window']['start'])+f' {hour:02}:00',tz='UTC')
        if t not in inv['complete_steps']: missing.append(str(t)); continue
        scene=Scene(reader='ahi_hsd',filenames=list(map(str,inv['complete_steps'][t])))
        rq=DataQuery(name='B07',calibration='radiance'); scene.load(['B07','B14','B15',rq])
        w,s,e,n=settings['box']; crop=scene.crop(ll_bbox=(w-1,s-1,e+1,n+1))
        attrs=crop['B07'].attrs
        gg=hw.geometry(attrs['area'],cfg,attrs['orbital_parameters'])
        arrays=dask.compute(*[crop[b].data for b in ['B07','B14','B15',rq]],scheduler='synchronous')
        frame={name:np.asarray(a,np.float32) for name,a in zip(['b07','b14','b15','radiance'],arrays)}
        frame['sza_deg']=sun_zenith_angle(attrs['time_parameters']['observation_start_time'],gg['longitude'],gg['latitude'])
        constant=json.loads((cfg['paths']['window_outputs']/'himawari/mir_constant.json').read_text())
        result=hw.contextual(frame,gg,cfg['himawari'],constant)
        target=result['status']==0
        count=uniform_filter((result['clear']&gg['land']).astype(float),11,mode='constant')*121
        target &= (count>=100)&(gg['vza_deg']<settings['max_vza_deg'])&(gg['longitude']>=w)&(gg['longitude']<=e)&(gg['latitude']>=s)&(gg['latitude']<=n)
        target[:32]=False; target[-32:]=False; target[:,:32]=False; target[:,-32:]=False
        rr,cc=np.where(target)
        if not len(rr): missing.append(str(t)+' no usable clear-land site'); continue
        idx=np.argmin(abs(frame['b07'][rr,cc]-np.median(frame['b07'][rr,cc])))
        r,c=int(rr[idx]),int(cc[idx]); patch=(slice(r-32,r+33),slice(c-32,c+33))
        tile={k:v[patch].copy() for k,v in frame.items()}; geom={k:v[patch].copy() for k,v in gg.items()}
        rows.extend(trial_rows(tile,geom,verify.band7_coefficients(scene),cfg,t,'near_nadir'))
    summary=fraction_summary(rows)
    return dict(status='completed' if not missing else 'partial; awaiting data',box=settings['box'],trials=rows,summary=summary,
                f50=estimate_f50(summary),missing_scans=missing,n_contexts=len(rows)//len(cfg['phase3c']['injection']['fractions']))
