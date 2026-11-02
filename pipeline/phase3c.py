"""Data-gated regional and synchronized-window demonstrations for Phase 3c."""
from copy import deepcopy
import json
import numpy as np
import pandas as pd
from pipeline.config import ROOT,load_settings
from pipeline import himawari as hw, detection_limit as dl, calibration, diurnal, transfer, partitions, sync_gate, sync_window


def northern_australia(cfg):
    settings=cfg['phase3c']['northern_australia']; inventory=dl.segment_inventory(cfg,settings['segments'])
    if not inventory['n_complete_steps']:
        return dict(status='awaiting data',region='Northern_Australia',box=settings['box'],
                    required_segments=settings['segments'],raw_file_counts=inventory['raw_file_counts'],
                    reason='No complete Northern Australia B07/B14/B15 scans',role=settings['role'],transfer_to_south_asia=False)
    from run_phase3 import process,detection_fit
    regional=deepcopy(cfg)
    regional['himawari']['regions']={'Northern_Australia':settings['box']}
    regional['himawari']['segments']=settings['segments']
    regional['paths']['window_interim']=cfg['paths']['window_interim']/'phase3c_naus'
    regional['paths']['window_outputs']=cfg['paths']['window_outputs']/'phase3c_naus'
    regional['paths']['window_outputs'].mkdir(parents=True,exist_ok=True)
    inventory=hw.prepare(regional)
    if inventory['errors']: return dict(status='processing error',errors=inventory['errors'])
    refs=pd.read_parquet(cfg['paths']['window_processed']/'detections_clean.parquet')
    refs['acq_datetime_utc']=pd.to_datetime(refs.acq_datetime_utc,utc=True)
    stats,fires,cases,geom,first=process(regional,regional['himawari'],refs)
    fit,sample=detection_fit(cases)
    stats.to_csv(regional['paths']['window_outputs']/'scan_statistics.csv',index=False)
    cases.to_csv(regional['paths']['window_outputs']/'viirs_cases.csv',index=False)
    fires['reference_match']=hw.nearby(fires,refs,60,2)
    for date,day in fires.groupby(fires.acq_datetime_utc.dt.date):
        partitions.write(day,cfg['paths']['partition_root']/'geo_fires'/'platform=Himawari','region=Northern_Australia',date)
    model,points=diurnal.fit_region(stats,regional['himawari'])
    model.update(region='Northern_Australia',tier='A' if stats.valid_area_share.mean()>=.8 else 'B',
                 status='provisional – 4 days',role='method demonstration region',transfer_to_south_asia=False)
    if model['tier']!='A':
        model.update(fitted=False,parameters=None,intervals=None,reason='Insufficient valid-view coverage for a Tier A demonstration')
    models={'Northern_Australia':model}
    hw.json_write(ROOT/'params/diurnal_v2.json',dict(kind='diurnal',version=2,source_window=cfg['window']['name'],
                  status='provisional – 4 days',regions=models))
    ov=pd.read_csv(cfg['paths']['window_interim']/'event_overpasses.csv')
    ov=calibration.enrich_overpasses(ov,refs,cfg['grid']['cell_deg'])
    w,s,e,n=settings['box']; ov=ov[ov.lon.between(w,e)&ov.lat.between(s,n)].copy()
    pairs=transfer.adjusted_pairs(ov,models,regional)
    pairs['event_specific_ahi_ratio']=transfer.event_specific_ratios(pairs,fires,regional['himawari'])
    pairs.to_csv(regional['paths']['window_outputs']/'transfer_pairs.csv',index=False)
    frpfit=transfer.fit_adjusted(pairs,regional)
    hw.json_write(ROOT/'params/calibration_v3_transfer_naus.json',dict(kind='calibration',version=3,region='Northern_Australia',
                  status='provisional – transfer standard',role='method demonstration region',transfer_to_south_asia=False,
                  source_window=cfg['window']['name'],sample_size=frpfit['n'],fit=frpfit))
    if len(ov):
        perpass,daily,totals=transfer.energy_table(ov,models,regional)
        perpass.to_csv(regional['paths']['window_outputs']/'fre_overpasses.csv',index=False)
        daily.to_csv(regional['paths']['window_outputs']/'fre_daily.csv',index=False)
        events=pd.read_csv(cfg['paths']['window_processed']/'fire_events.csv',low_memory=False)
        events=events[events.fire_id.isin(ov.fire_id)].copy(); events['FRE_estimate']=events.fire_id.map(totals)
        events.to_csv(regional['paths']['window_outputs']/'fire_events_fre.csv',index=False)
        fre_n=int(events.FRE_estimate.notna().sum())
    else: fre_n=0
    plot_naus(points,model,pairs,cfg)
    return dict(status='completed',region='Northern_Australia',role='method demonstration region',transfer_to_south_asia=False,
                n_steps=len(stats),n_fires=len(fires),detection_fit=fit,
                detection_rate=float(sample.detected.mean()) if len(sample) else None,
                commission_rate=float((~fires.reference_match).mean()) if len(fires) else None,
                model=model,calibration=frpfit,n_fre_events=fre_n)


def plot_naus(points,model,pairs,cfg):
    import matplotlib.pyplot as plt
    folder=cfg['paths']['figures_dir']; folder.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    axes[0].scatter(pairs.frp_sum_mw_modis,pairs.frp_viirs_unadjusted_mw,s=5)
    good=pairs.dropna(subset=['time_ratio'])
    axes[1].scatter(good.frp_sum_mw_modis,good.frp_sum_mw_viirs,s=5)
    for ax,title in zip(axes,['Before time adjustment','After time adjustment']):
        ax.set(xlim=(.1,1e5),ylim=(.1,1e5),xscale='log',yscale='log',xlabel='Aqua FRP (MW)',ylabel='VIIRS FRP (MW)',title=title)
    fig.suptitle('Northern Australia: method demonstration only'); fig.tight_layout()
    fig.savefig(folder/'calibration_v1_vs_v3_naus.png',dpi=150,bbox_inches='tight'); plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4)); ax.scatter(points.lst_h,points.normalized_frp,s=8)
    if model['fitted']:
        grid=np.linspace(0,24,241); ax.plot(grid,diurnal.shape(grid,**model['parameters']))
        low,high=model['curve_interval_90']; ax.fill_between(grid,low,high,alpha=.2)
    else: ax.text(.5,.5,model['reason'],ha='center',transform=ax.transAxes,wrap=True)
    ax.set(xlim=(0,24),xlabel='Local solar time (h)',ylabel='Daily normalized FRP',title='Northern Australia — method demonstration')
    fig.tight_layout(); fig.savefig(folder/'diurnal_curve_Northern_Australia.png',dpi=150,bbox_inches='tight'); plt.close(fig)


# D61 rule, replaced by the D68 gate (pipeline/sync_gate.py); kept for the recorded comparison.
sync_eligible=sync_gate.old_rule


def synchronized_2016(cfg):
    sync=load_settings(window='sync_2016')
    raw=sync['paths']['raw_dir']; files=sorted(raw.rglob('*.csv')) if raw.exists() else []
    if not files:
        return dict(status='awaiting data',raw_dir=str(raw),reason='No FIRMS CSV files for sync_2016',
                    drift_comparison='awaiting data',pi_modis='awaiting data')
    import run_pipeline
    from pipeline import diagnostics
    run_pipeline.main(window='sync_2016',workers=1,partition_root=sync['paths']['window_processed']/'partitions')
    refs=pd.read_parquet(sync['paths']['window_processed']/'detections_clean.parquet')
    ov=pd.read_csv(sync['paths']['window_interim']/'event_overpasses.csv')
    nearest=diagnostics.aqua_viirs_dt(ov)
    comparison=drift_comparison(cfg,sync,refs,nearest)
    r=sync_window.process('sync_2016')
    awaiting='awaiting data: window fails the D68 sync gate'
    return dict(status='completed',timing=r['gate'],drift=comparison,n_detections=len(refs),
                calibration=r.get('calibration'),detection_curve=r.get('detection_curve',dict(fitted=False,n=0,reason=awaiting)),
                pi_modis=r.get('pi_modis',awaiting),observation_opportunities=r.get('opportunities',awaiting),latent=r.get('latent'))


def drift_comparison(cfg,sync,refs,nearest):
    import matplotlib.pyplot as plt
    from pipeline import diagnostics
    frames={2016:refs,2026:pd.read_parquet(cfg['paths']['window_processed']/'detections_clean.parquet')}
    rows=[]
    for year,d in frames.items():
        d=d[d.daynight.eq('D') & d.latitude.abs().le(30)].copy()
        d['acq_datetime_utc']=pd.to_datetime(d.acq_datetime_utc,utc=True)
        d['lst_h']=[hw.lst(t,lon) for t,lon in zip(d.acq_datetime_utc,d.longitude)]
        for name,g in d.groupby('platform'): rows.append(dict(year=year,platform=name,n=len(g),median_lst_h=float(g.lst_h.median())))
    now=diagnostics.aqua_viirs_dt(pd.read_csv(cfg['paths']['window_interim']/'event_overpasses.csv'))
    fig,(ax,ax_lst)=plt.subplots(1,2,figsize=(12,4))
    for label,d in [('2016',nearest),('2026',now)]:
        ax.hist(d.loc[d.platform.eq('S-NPP'),'dt_min'],bins=np.arange(-360,365,5),histtype='step',label=label,density=True)
    table=pd.DataFrame(rows).pivot(index='platform',columns='year',values='median_lst_h')
    table.plot.bar(ax=ax_lst); ax_lst.set(ylabel='Median daytime local solar time (h)',title='Measured detection times, |latitude| <=30')
    ax.legend(); ax.set(xlabel='S-NPP minus Aqua acquisition time (minutes)',ylabel='Density',title='Event-overpass time differences')
    fig.tight_layout(); fig.savefig(cfg['paths']['figures_dir']/'drift_2016_vs_2026.png',dpi=150,bbox_inches='tight'); plt.close(fig)
    return rows
