"""Step 8, with explicit reference population and unavailable-data gates.

Counts are event/overpass footprint-overlap shares, not hot-pixel counts.
VIIRS pi=1 defines a VIIRS-observable reference population. Provisional
2026 results do not purport to reconstruct fires below VIIRS sensitivity.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit
from pipeline.config import ROOT,load_settings
from pipeline import himawari as hw,partitions


def ratio(n,denominator):
    n,d=np.broadcast_arrays(np.asarray(n,float),np.asarray(denominator,float))
    return np.divide(n,d,out=np.full(n.shape,np.nan),where=np.isfinite(d)&(d>0))


def grid_cells(cfg):
    from pipeline.grid import cell_id,cell_index
    tables=[];deg=cfg['grid']['cell_deg']
    for name in ['full_IGP','Bangladesh']:
        w,s,e,n=cfg['himawari']['regions'][name]
        lon,lat=np.meshgrid(np.arange(w+deg/2,e,deg),np.arange(s+deg/2,n,deg))
        ix,iy=cell_index(lon.ravel(),lat.ravel(),deg)
        tables.append(pd.DataFrame(dict(cell_id=cell_id(ix,iy),cell_lon=lon.ravel(),cell_lat=lat.ravel())))
    cells=pd.concat(tables).drop_duplicates('cell_id').sort_values('cell_id').reset_index(drop=True)
    w,s,e,n=cfg['himawari']['regions']['Bangladesh']
    cells['reference_region']=np.where(cells.cell_lon.between(w,e)&cells.cell_lat.between(s,n),'Bangladesh','full_IGP')
    return cells


def event_counts(cfg,cells):
    import geopandas as gpd
    import shapely
    from pipeline.grid import overlay,cell_id
    path=cfg['paths']['window_interim']/'footprints.geoparquet'
    if not path.exists():return pd.DataFrame(columns=['cell_id','date','platform','N']),None
    det=gpd.read_parquet(path,columns=['fire_id','platform','acq_datetime_utc','geometry'])
    bounds=shapely.bounds(det.geometry.values)
    det=det[(bounds[:,2]>=72.9)&(bounds[:,0]<=92.8)&(bounds[:,3]>=20.4)&(bounds[:,1]<=32.6)].copy()
    det['acq_datetime_utc']=pd.to_datetime(det.acq_datetime_utc,utc=True)
    keys=[];geometries=[]
    for (fire_id,platform,time),g in det.groupby(['fire_id','platform','acq_datetime_utc'],sort=False):
        union=shapely.union_all(g.geometry.values)
        lon=float(shapely.get_x(shapely.centroid(union)))
        day=(time+pd.Timedelta(hours=lon/15)).date()
        if cfg['window']['start']<=day<=cfg['window']['end']:
            keys.append(dict(platform=platform,date=str(day)));geometries.append(union)
    if not keys:return pd.DataFrame(columns=['cell_id','date','platform','N']),None
    pieces=overlay(np.asarray(geometries,dtype=object),cfg['grid']['cell_deg'])
    keys=pd.DataFrame(keys)
    frame=pd.DataFrame(dict(cell_id=cell_id(pieces.ix.values,pieces.iy.values),date=keys.date.values[pieces.row.values],
                            platform=keys.platform.values[pieces.row.values],N=pieces.w.values))
    frame=frame[frame.cell_id.isin(cells.cell_id)]
    return frame.groupby(['cell_id','date','platform'],as_index=False).N.sum(),det.acq_datetime_utc.max()


def curve_payload(cfg):
    path=ROOT/cfg['latent']['detection_curve_by_window'][cfg['window']['name']]
    if not path.exists():return None,'awaiting applicable detection curve'
    doc=json.loads(path.read_text())
    fit=doc.get('fit') or doc.get('values') or {}
    if not fit or fit.get('fitted') is False or any(fit.get(x) is None for x in ['b0','b1','b2']):
        return None,fit.get('reason','awaiting fitted detection curve')
    return doc,None


def coefficient_draws(doc,n,rng):
    mean=doc.get('fit') or doc['values']; intervals=doc.get('intervals') or mean
    mu=np.array([mean[x] for x in ['b0','b1','b2']])
    errors=[]
    for key in ['b0','b1','b2']:
        ci=intervals.get(key+'_ci')
        if ci is None:raise ValueError('awaiting detection-curve coefficient uncertainty')
        errors.append((ci[1]-ci[0])/(2*1.6448536269514722))
    return rng.normal(mu,np.asarray(errors),size=(n,3))


def run_window(window):
    from pipeline.grid import cell_index
    cfg=load_settings(window=window);settings=cfg['latent'];rng=np.random.default_rng(settings['seed'])
    cells=grid_cells(cfg)
    frames=[cells.assign(date=str(day)) for day in partitions.days(cfg['window']['start'],cfg['window']['end'])]
    output=pd.concat(frames,ignore_index=True);index=pd.MultiIndex.from_frame(output[['cell_id','date']])
    counts,last_observation=event_counts(cfg,cells)
    included=settings['included_platforms']
    count_total=counts[counts.platform.isin(included)].groupby(['cell_id','date']).N.sum()
    modis_total=counts[counts.platform.eq('Aqua')].groupby(['cell_id','date']).N.sum()
    output['N_observed']=count_total.reindex(index).fillna(0).values
    output['N_MODIS']=modis_total.reindex(index).fillna(0).values
    output['n_obs_opportunities']=np.nan;output['denominator']=np.nan
    for col in ['lambda_hat','lambda_lo90','lambda_hi90','lambda_modis_only','fre_harm']:output[col]=np.nan
    output['status']='awaiting data';output['reference_sensor']=settings['reference_sensor']
    output['reference_population']='VIIRS-observable fires; pi_VIIRS=1 by definition'
    output['era']='multi_sensor';output['diurnal_source']='awaiting South Asia shape'
    output['data_version']=cfg['data_version']
    output['last_observation_time']=str(last_observation) if last_observation is not None else None
    opportunities_path=cfg['paths']['window_processed']/'overpasses.parquet'
    fallback_path=cfg['paths']['window_processed']/'observed_overpasses.parquet'
    doc,reason=curve_payload(cfg)
    opportunities=None;basis=None
    if opportunities_path.exists():
        opportunities=pd.read_parquet(opportunities_path)
        opportunities=opportunities[opportunities.cell_id.astype(str).isin(cells.cell_id)&opportunities.platform.astype(str).isin(included)].copy()
        opportunities['overpass_time_utc']=pd.to_datetime(opportunities.overpass_time_utc,utc=True)
        epochs=pd.to_datetime(opportunities.tle_epoch_utc,utc=True)
        if (epochs-opportunities.overpass_time_utc).abs().max()>pd.Timedelta(days=30):
            opportunities=None
        else:basis='TLE-propagated'
    if opportunities is None and fallback_path.exists():
        # D69: labelled lower bound on O_s, rebuilt from the window's own detections.
        opportunities=pd.read_parquet(fallback_path)
        opportunities=opportunities[opportunities.cell_id.astype(str).isin(cells.cell_id)&opportunities.platform.astype(str).isin(included)].copy()
        opportunities['overpass_time_utc']=pd.to_datetime(opportunities.overpass_time_utc,utc=True)
        basis=str(opportunities.opportunity_basis.iloc[0]) if len(opportunities) else None
    if opportunities is None:
        missing='awaiting historical observation opportunities (orbital epoch mismatch)' if opportunities_path.exists() else 'awaiting observation opportunities'
        reason=(reason+'; ' if reason else '')+missing
    if opportunities is not None:
        if last_observation is not None:opportunities=opportunities[opportunities.overpass_time_utc<=last_observation]
        local=opportunities.overpass_time_utc+pd.to_timedelta(opportunities.cell_lon/15,unit='h')
        opportunities['date']=local.dt.strftime('%Y-%m-%d')
        oi=pd.MultiIndex.from_frame(opportunities[['cell_id','date']]);positions=index.get_indexer(oi)
        opportunities=opportunities[positions>=0].copy();positions=positions[positions>=0]
        output['n_obs_opportunities']=np.bincount(positions,minlength=len(output))
    calibration_note='No physical FRP/FRE calibration applied to event-count numerators.'
    if not reason and doc is not None and opportunities is not None:
        beta=coefficient_draws(doc,settings['draws'],rng)
        refs=pd.read_parquet(cfg['paths']['window_processed']/'detections_clean.parquet',columns=['fire_id','platform','sensor','acq_datetime_utc','frp_mw','longitude','latitude'])
        refs=refs[refs.sensor.eq('VIIRS') & refs.frp_mw.gt(0)]
        refs=refs.groupby(['fire_id','platform','acq_datetime_utc'],as_index=False).agg(frp_mw=('frp_mw','sum'),lon=('longitude','mean'),lat=('latitude','mean'))
        logareas=np.linspace(np.log10(.8),np.log10(12),settings['area_nodes'])
        draws=np.full((settings['draws'],len(output)),np.nan,dtype=np.float32)
        denominator=np.zeros(len(output));modis_denominator=np.zeros(len(output))
        # Calibration is sampled for provenance but cancels from this count estimator:
        # its power distribution and curve covariate are already on the VIIRS scale.
        calpath=ROOT/settings['calibration_by_window'][window]
        if calpath.exists():
            cal=json.loads(calpath.read_text());ci=cal.get('intervals') or {};values=cal.get('values') or cal.get('fit') or {}
            if all(ci.get(k+'_90') is not None for k in ['a','b']) and values.get('a') is not None:
                cc=np.array([values['a'],values['b']]);sd=np.array([(ci[k+'_90'][1]-ci[k+'_90'][0])/(2*1.6448536269514722) for k in ['a','b']])
                cdraw=rng.normal(cc,sd,size=(settings['draws'],2))
                hw.json_write(cfg['paths']['window_outputs']/'latent_calibration_draws.json',dict(draws=cdraw.tolist(),role='Sampled; algebraically cancels for VIIRS-scale empirical power covariate. No unsupported FRE is inferred.'))
                calibration_note='300 calibration draws sampled; no artificial noise added to lambda because calibration cancels on the VIIRS reference scale. Diurnal/FRE unavailable in South Asia.'
        region_indices={}
        power_samples={}
        for region in ['Bangladesh','full_IGP']:
            w,s,e,n=cfg['himawari']['regions'][region]
            power=refs.loc[refs.lon.between(w,e)&refs.lat.between(s,n),'frp_mw'].to_numpy()
            if not len(power):reason='awaiting regional VIIRS empirical FRP distribution';break
            power_samples[region]=power
            region_indices[region]=output.index[output.reference_region.eq(region)].to_numpy()
        prepared={}
        for region in power_samples:
            use=np.isin(positions,region_indices[region])
            obs=opportunities.loc[use]
            prepared[region]=(positions[use],obs.sensor.astype(str).eq('VIIRS').to_numpy(),np.log10(obs.pixel_area_km2.to_numpy()))
        if reason is None:
            for draw in range(settings['draws']):
                den=np.zeros(len(output));md=np.zeros(len(output))
                for region,power in power_samples.items():
                    sampled=rng.choice(power,min(settings['frp_bootstrap_size'],len(power)),replace=True)
                    b0,b1,b2=beta[draw]
                    pi=np.mean(expit(b0+b1*np.log10(sampled)[None,:]-b2*logareas[:,None]),axis=1)
                    ix,is_viirs,log_area=prepared[region]
                    probability=np.where(is_viirs,settings['viirs_pi'],np.interp(log_area,logareas,pi))
                    den+=np.bincount(ix,weights=probability,minlength=len(output))
                    md+=np.bincount(ix,weights=np.where(~is_viirs,probability,0),minlength=len(output))
                draws[draw]=ratio(rng.gamma(output.N_observed.values+.5),den)
                denominator+=den/settings['draws'];modis_denominator+=md/settings['draws']
                if (draw+1)%50==0:
                    print(f'[{window}] Monte Carlo {draw+1}/{settings["draws"]}',flush=True)
                    hw.json_write(cfg['paths']['window_outputs']/'latent_progress.json',dict(window=window,draws_completed=draw+1))
            output['denominator']=denominator
            output['lambda_hat']=ratio(output.N_observed,denominator)
            output['lambda_modis_only']=ratio(output.N_MODIS,modis_denominator)
            known=denominator>0
            output.loc[known,'lambda_lo90']=np.nanpercentile(draws[:,known],5,axis=0)
            output.loc[known,'lambda_hi90']=np.nanpercentile(draws[:,known],95,axis=0)
            if basis=='TLE-propagated' and window=='current_2026':
                output.loc[known,'status']='provisional-reference-population'
                reason='Provisional current-window v1 sensitivity; swath-edge and timing limitations retained. Clear-sky opportunity assumption. Unknown diurnal systematic error excluded.'
            else:
                output.loc[known,'status']='provisional-reference-population; '+basis
                reason=(basis+('. Opportunities are undercounted, so lambda is biased HIGH (upper side); ' if 'lower bound' in basis else '. ')
                        +'synchronized-window detection curve; clear-sky opportunity assumption; unknown diurnal systematic error excluded.')
    output['limitation']=reason or 'awaiting applicable model'
    root=ROOT/'data/processed'/window
    for day,part in output.groupby('date',sort=True):
        directory=partitions.part_dir(root,'grid_daily_lambda',pd.Timestamp(day).date());directory.mkdir(parents=True,exist_ok=True)
        partitions.write(part,root,'grid_daily_lambda',pd.Timestamp(day).date())
        part.to_csv(directory/'part.csv',index=False)
    valid=output.lambda_hat.notna()
    summary=dict(window=window,n_cell_days=len(output),n_estimated=int(valid.sum()),n_unknown=int((~valid).sum()),
                 status='provisional' if valid.any() else 'awaiting data',mean_lambda=float(output.loc[valid,'lambda_hat'].mean()) if valid.any() else None,
                 total_observed_event_look_weight=float(output.N_observed.sum()),draws=settings['draws'] if valid.any() else 0,
                 limitation=reason,opportunity_basis=basis,calibration_uncertainty=calibration_note,fre_status='awaiting supported South Asia diurnal shape',
                 included_platforms=included,excluded_platforms=settings['excluded_platforms'],
                 degradation={**degradation_bias(output.lambda_modis_only.values,output.lambda_hat.values),'opportunity_basis':basis,'definition':'mean(lambda_MODIS_only - lambda_all_sensors) over cell-days where both are finite'} if window.startswith('sync_') and valid.any() else dict(status='awaiting synchronized sensitivity and coverage' if window=='sync_2016' else 'not a synchronized validation window',bias=None))
    hw.json_write(cfg['paths']['window_outputs']/'latent_summary.json',summary)
    plot_map(output,cfg)
    return summary


def plot_map(frame,cfg):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,region in zip(axes,['full_IGP','Bangladesh']):
        w,s,e,n=cfg['himawari']['regions'][region]
        sub=frame[frame.cell_lon.between(w,e)&frame.cell_lat.between(s,n)].groupby('cell_id').agg(lon=('cell_lon','first'),lat=('cell_lat','first'),value=('lambda_hat','mean'))
        if sub.value.notna().any():
            im=ax.scatter(sub.lon,sub.lat,c=sub.value,s=5,marker='s',vmin=0,vmax=float(sub.value.quantile(.98)))
            fig.colorbar(im,ax=ax,label='Mean provisional lambda (reference-population units)')
        else:ax.text(.5,.5,'Awaiting data\nNo applicable sensitivity / coverage',transform=ax.transAxes,ha='center')
        ax.set(xlim=(w,e),ylim=(s,n),xlabel='Longitude',ylabel='Latitude',title=region)
    fig.suptitle(cfg['window']['name']+' — conditional latent estimate; clear-sky assumptions')
    fig.tight_layout();path=ROOT/'outputs/figures'/f"lambda_map_{cfg['window']['name']}.png";fig.savefig(path,dpi=150,bbox_inches='tight');plt.close(fig)


def degradation_bias(modis,all_sensors):
    modis,all_sensors=np.broadcast_arrays(np.asarray(modis,float),np.asarray(all_sensors,float))
    valid=np.isfinite(modis)&np.isfinite(all_sensors)
    if not valid.any():return dict(status='awaiting comparable estimates',n=0,bias=None,relative_bias=None)
    difference=modis[valid]-all_sensors[valid]
    base=float(all_sensors[valid].mean())
    return dict(status='computed',n=int(valid.sum()),bias=float(difference.mean()),relative_bias=float(difference.mean()/base) if base>0 else None)


if __name__=='__main__':
    for window in ['sync_2016','current_2026']:
        print(run_window(window),flush=True)
