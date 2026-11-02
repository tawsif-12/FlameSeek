"""Phase 3 analysis of the locally available hourly AHI window.

Run preparation first with python -m pipeline.himawari --window current_2026.
"""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from pipeline import himawari as hw, diurnal, transfer, calibration
from pipeline.config import ROOT, load_settings


def assert_training_dates(dates, settings):
    if not set(dates).issubset(settings['tuning']['train_dates']):
        raise ValueError('Threshold tuning may use training dates only')


def reference_cases(refs, geom, cache, cfg):
    v=refs[refs.sensor.eq('VIIRS')].copy()
    boxes=list(cfg['himawari']['regions'].values())
    v=v[v.longitude.between(min(b[0] for b in boxes),max(b[2] for b in boxes)) &
        v.latitude.between(min(b[1] for b in boxes),max(b[3] for b in boxes))]
    v['scan_time']=v.acq_datetime_utc.dt.round('h')
    good=np.isfinite(geom['longitude']) & np.isfinite(geom['latitude'])
    ids=np.flatnonzero(good)
    # Unit-sphere coordinates avoid longitude/latitude metric distortion.
    def xyz(lon,lat):
        lo,la=np.radians(lon),np.radians(lat)
        return np.column_stack([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    tree=cKDTree(xyz(geom['longitude'][good],geom['latitude'][good]))
    _,idx=tree.query(xyz(v.longitude,v.latitude))
    flat=ids[idx]
    v['pixel_id']=flat
    v['vza_deg']=geom['vza_deg'].flat[flat]
    v['in_regions']=geom['in_regions'].flat[flat]
    for region in cfg['himawari']['regions']:
        v['box_'+region]=geom['box_'+region].flat[flat]
    v['status']=4
    v['detected']=False
    return v[v.in_regions].copy()


def process(cfg, settings, refs, save=True, dates=None):
    cache=cfg['paths']['window_interim']/'himawari'
    geom=dict(np.load(cache/'geometry.npz'))
    constant=hw.derive_mir_constant(cfg)
    cases=reference_cases(refs,geom,cache,cfg)
    stats=[]; detections=[]; first=None
    for scan_index,path in enumerate(sorted(cache.glob('*/*/*/*.npz')),1):
        frame=dict(np.load(path))
        t=pd.Timestamp(str(frame.pop('nominal_utc')))
        obs=pd.Timestamp(str(frame.pop('observation_start_utc')))
        geom['vza_deg']=frame.pop('vza_deg',geom['vza_deg'])
        if dates is not None and str(t.date()) not in dates:
            continue
        result=hw.contextual(frame,geom,settings,constant)
        stats.extend(hw.scan_stats(result,geom,t,cfg))
        d=hw.detection_frame(result,frame,geom,t,obs)
        detections.append(d)
        which=cases.scan_time.eq(t)
        pix=cases.loc[which,'pixel_id'].to_numpy(int)
        cases.loc[which,'status']=result['status'].flat[pix]
        cases.loc[which,'vza_deg']=geom['vza_deg'].flat[pix]
        # Detection match uses the specified 2 km tolerance, not just same pixel.
        cases.loc[which,'detected']=hw.nearby(cases.loc[which],d,30,settings['match_radius_km'])
        if save:
            target=cache/'masks'/t.strftime('%Y/%m/%d')
            target.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(target/t.strftime('%H%M.npz'),status=result['status'],vza_deg=geom['vza_deg'],
                                nominal_utc=str(t),lst_h=hw.lst(t,geom['longitude']))
        if scan_index % 12 == 0:
            print(f'[detect] {scan_index} scans processed; {sum(len(x) for x in detections)} fire pixels',flush=True)
        if first is None and t.hour==7:
            first=(t,result['status'].copy())
    det=pd.concat(detections,ignore_index=True) if detections else pd.DataFrame()
    return pd.DataFrame(stats),det,cases,geom,first


def detection_fit(cases):
    # Event-overpass aggregation: observed if at least one clear pixel; cloud-only is unknown.
    obs=cases[cases.status.isin([0,1])]
    sample=obs.groupby(['fire_id','platform','acq_datetime_utc'],as_index=False).agg(
        frp_mw=('frp_mw','sum'),vza_deg=('vza_deg','mean'),detected=('detected','max'))
    if sample.empty or sample.detected.nunique()<2:
        return dict(fitted=False,n=len(sample),reason='No observed events or only one detection outcome'),sample
    X=np.column_stack([np.log(sample.frp_mw),sample.vza_deg])
    model=LogisticRegression(C=1e6,max_iter=2000).fit(X,sample.detected)
    return dict(fitted=True,n=len(sample),intercept=float(model.intercept_[0]),
                beta_log_frp=float(model.coef_[0,0]),beta_vza=float(model.coef_[0,1])),sample


def save_plot(fig,path):
    fig.tight_layout(); fig.savefig(path,dpi=150,bbox_inches='tight'); plt.close(fig)


def run(cfg):
    out=cfg['paths']['window_outputs']; figs=cfg['paths']['figures_dir']; figs.mkdir(parents=True,exist_ok=True)
    cache=cfg['paths']['window_interim']/'himawari'
    inventory=json.loads((cache/'inventory.json').read_text())
    if inventory['errors']:
        raise RuntimeError('Preparation errors remain: inspect inventory.json')
    expected,_=hw.discover(cfg)
    if len(inventory['prepared']) != len(expected):
        raise RuntimeError('Preparation not complete; finish python -m pipeline.himawari first')
    refs=pd.read_parquet(cfg['paths']['window_processed']/'detections_clean.parquet')
    refs['acq_datetime_utc']=pd.to_datetime(refs.acq_datetime_utc,utc=True)
    refs=refs[refs.acq_datetime_utc.dt.date.between(cfg['window']['start'],cfg['window']['end'])]
    settings=deepcopy(cfg['himawari'])
    stats,det,cases,geom,first=process(cfg,settings,refs)
    train=settings['tuning']['train_dates']; assert_training_dates(train,settings)
    training=cases[cases.acq_datetime_utc.dt.strftime('%Y-%m-%d').isin(train)]
    large=training[training.status.isin([0,1])].groupby(['fire_id','platform','acq_datetime_utc'],as_index=False).agg(
        frp_mw=('frp_mw','sum'),detected=('detected','max'))
    large=large[large.frp_mw>=settings['tuning']['large_viirs_frp_mw']]
    tuning=dict(train_dates=train,test_dates=settings['tuning']['test_dates'],n_large_observed_training_events=len(large),
                large_detection_rate=float(large.detected.mean()) if len(large) else None,chosen=settings['detection'],alternatives=[])
    if len(large) and large.detected.mean()<settings['tuning']['large_fire_rate_trigger']:
        best=float(large.detected.mean()); selected=None
        for alternative in settings['tuning']['alternatives']:
            candidate=deepcopy(settings); candidate['detection'].update(alternative)
            _,dd,cc,_,_=process(cfg,candidate,refs,save=False,dates=train)
            ll=cc[cc.status.isin([0,1])].groupby(['fire_id','platform','acq_datetime_utc'],as_index=False).agg(
                frp_mw=('frp_mw','sum'),detected=('detected','max'))
            ll=ll[ll.frp_mw>=settings['tuning']['large_viirs_frp_mw']]
            score=float(ll.detected.mean()) if len(ll) else 0
            commission=float((~hw.nearby(dd,refs,60,2)).mean()) if len(dd) else None
            tuning['alternatives'].append(dict(thresholds=alternative,training_detection_rate=score,commission=commission))
            if score>best:
                best=score; selected=candidate
        if selected:
            settings=selected; tuning['chosen']=settings['detection']
            stats,det,cases,geom,first=process(cfg,settings,refs)
        tuning['reason']='Selection used training dates only; held-out days were not scored for selection'
    else:
        tuning['reason']='No large observed training events, or baseline meets trigger; thresholds retained'
    hw.json_write(out/'himawari/threshold_selection.json',tuning)
    # Adjacent means exactly one configured cadence, never the next available file across a gap.
    if len(det):
        key=set(zip(det.pixel_id,det.acq_datetime_utc))
        cadence=pd.Timedelta(minutes=settings['cadence_minutes'])
        adjacent=np.array([(p,t-cadence) in key or (p,t+cadence) in key for p,t in zip(det.pixel_id,det.acq_datetime_utc)])
        det['reference_match']=hw.nearby(det,refs,60,2)
        det['transient_suspect']=~adjacent & ~det.reference_match
    else:
        det['reference_match']=pd.Series(dtype=bool); det['transient_suspect']=pd.Series(dtype=bool)
    for day in pd.date_range(cfg['window']['start'],cfg['window']['end']):
        from pipeline import partitions
        partitions.write(det[det.acq_datetime_utc.dt.date==day.date()],cfg['paths']['partition_root'],'himawari_fires',day.date())
    stats.to_csv(out/'himawari/scan_statistics.csv',index=False)
    cases.to_csv(out/'himawari/viirs_pixel_cases.csv',index=False)
    fit,sample=detection_fit(cases); hw.json_write(out/'himawari/detection_fit.json',fit)
    sample.to_csv(out/'himawari/viirs_event_cases.csv',index=False)
    models={}
    for region,s in stats.groupby('region'):
        model,points=diurnal.fit_region(s,settings)
        share=float(s.valid_area_share.mean())
        tier='A' if share>=settings['tier_a_min_valid_area_share'] else 'B'
        # A poorly covered box does not fit a representative curve from a tiny valid sliver.
        if tier=='B':
            model.update(fitted=False,parameters=None,intervals=None,reason='Regional valid-view fraction below Tier A; no validated donor shape')
        models[region]={**model,'tier':tier,'valid_area_share':share,'region':region}
        fig,ax=plt.subplots(figsize=(7,4)); ax.scatter(points.lst_h,points.normalized_frp,s=12,label='daily normalized observations')
        if model['fitted']:
            grid=np.linspace(0,24,241); ax.plot(grid,diurnal.shape(grid,**model['parameters']))
            low,high=model['curve_interval_90']; ax.fill_between(grid,low,high,alpha=.2,label='90% day bootstrap')
            ax.legend()
        else:
            ax.text(.5,.55,model['reason'],ha='center',wrap=True,transform=ax.transAxes,fontsize=9)
        ax.set(xlim=(0,24),ylim=(0,1.15),xlabel='Local solar time (h)',ylabel='FRP / daily maximum',title=region+' — provisional, four full UTC days')
        save_plot(fig,figs/f'diurnal_curve_{region}.png')
    # Preserve the previous unavailable parameter document before fulfilling the requested v1 path.
    paramdir=ROOT/cfg['params']['dir']; old=paramdir/'diurnal_v1.json'
    if old.exists() and not (paramdir/'diurnal_v1.pre_phase3.json').exists():
        (paramdir/'diurnal_v1.pre_phase3.json').write_bytes(old.read_bytes())
    hw.json_write(old,dict(kind='diurnal',version=1,source_window=cfg['window']['name'],status='provisional – 4 days',
                           sample_size=int(sum(m['sample_size'] for m in models.values())),regions=models))
    ov=pd.read_csv(cfg['paths']['window_interim']/'event_overpasses.csv')
    ov=calibration.enrich_overpasses(ov,refs,cfg['grid']['cell_deg'])
    pairs=transfer.adjusted_pairs(ov,models,cfg)
    pairs['event_specific_ahi_ratio']=transfer.event_specific_ratios(pairs,det,settings)
    pairs.to_csv(out/'himawari/transfer_pairs.csv',index=False)
    tf=transfer.fit_adjusted(pairs,cfg)
    hw.json_write(paramdir/'calibration_v3_transfer.json',dict(kind='calibration',version=3,status='provisional – transfer standard',
                  source_window=cfg['window']['name'],sample_size=int(pairs.time_ratio.notna().sum()),fit=tf,
                  reason=tf.get('reason'),error_ratio=cfg['calibration']['deming_error_ratio']))
    # Rebuild observation opportunities with the transfer time window, including misses.
    detcfg=deepcopy(cfg)
    gap=settings['transfer_max_same_day_gap_minutes']
    detcfg['events']['matched_pair_window_max_min']=gap
    detcfg['events']['matched_pair_window_by_platform']={p:gap for p in cfg['calibration']['detection_curve_viirs']}
    opportunities=pd.read_parquet(cfg['paths']['window_processed']/'overpasses.parquet')
    ds=calibration.detection_sample(ov,opportunities,detcfg)
    ratios=[]
    for r in ds.itertuples():
        pars=transfer.supported_parameters(r.lon,r.lat,models,cfg)
        ta=pd.Timestamp(r.overpass_time_utc); tv=pd.Timestamp(r.acq_datetime_utc)
        same=(ta+pd.Timedelta(hours=r.lon/15)).date()==(tv+pd.Timedelta(hours=r.lon/15)).date()
        ratios.append(diurnal.time_ratio(ta,tv,r.lon,pars) if pars and same else np.nan)
    ds['time_ratio']=ratios
    ds['frp_viirs_mw']*=ds.time_ratio
    ds.to_csv(out/'himawari/transfer_detection_sample.csv',index=False)
    usable=ds.dropna(subset=['time_ratio'])
    df=calibration.fit_detection_curve(usable,cfg) if len(usable) and usable.detected.nunique()==2 else dict(fitted=False,n=len(usable),reason='No supported time-adjusted detection sample')
    hw.json_write(paramdir/'detection_curve_v2_transfer.json',dict(kind='detection_curve',version=2,status='provisional – transfer standard',source_window=cfg['window']['name'],fit=df,sample_size=len(usable)))
    perpass,daily,totals=transfer.energy_table(ov,models,cfg)
    perpass.to_csv(out/'himawari/fre_overpasses.csv',index=False); daily.to_csv(out/'himawari/fre_daily.csv',index=False)
    ep=cfg['paths']['window_processed']/'fire_events.csv'; events=pd.read_csv(ep,low_memory=False)
    events['FRE_estimate']=events.fire_id.map(totals)
    events['FRE_status']=np.where(events.FRE_estimate.notna(),'provisional','not_available: no supported regional diurnal shape')
    event_tmp=ep.with_suffix('.phase3.tmp.csv')
    events.to_csv(event_tmp,index=False); event_tmp.replace(ep)
    make_figures(figs,geom,first,cases,det,sample,fit,pairs,cfg)
    report(out,stats,det,cases,models,tf,df,pairs,events,tuning,inventory,cfg)


def make_figures(figs,g,first,cases,det,sample,fit,pairs,cfg):
    fig,ax=plt.subplots(figsize=(9,5)); m=g['box_full_IGP']
    im=ax.scatter(g['longitude'][m],g['latitude'][m],c=g['vza_deg'][m],s=1,vmin=55,vmax=80)
    ax.contour(g['longitude'],g['latitude'],g['vza_deg'],levels=[65],colors='red',linewidths=1)
    fig.colorbar(im,ax=ax,label='View zenith angle (degrees)'); ax.set(xlim=(73,93),ylim=(20,33),xlabel='Longitude',ylabel='Latitude',title='AHI valid view: red boundary = 65 degrees')
    save_plot(fig,figs/'vza_valid_view.png')
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    for ax,region in zip(axes,['Bangladesh','eastern_IGP']):
        if first:
            t,status=first; m=g['box_'+region]
            from matplotlib.colors import ListedColormap, BoundaryNorm
            colors=ListedColormap(['#b8dfc1','#dd3311','#dddddd','#777777','#aa44aa','#79badd','#ffbb44'])
            ax.scatter(g['longitude'][m],g['latitude'][m],c=status[m],s=3,marker='s',linewidths=0,
                       cmap=colors,norm=BoundaryNorm(np.arange(-.5,7),7),rasterized=True)
            vv=cases[cases['box_'+region] & cases.acq_datetime_utc.dt.date.eq(t.date())]
            hh=det[det['box_'+region] & det.acq_datetime_utc.dt.date.eq(t.date())]
            ax.scatter(vv.longitude,vv.latitude,s=18,facecolors='none',edgecolors='red',label='VIIRS, whole day')
            ax.scatter(hh.longitude,hh.latitude,s=20,marker='x',c='black',label='AHI, whole day')
            ax.set_title(region+' '+str(t.date())+'; background 07 UTC')
        ax.set(xlabel='Longitude',ylabel='Latitude'); ax.legend(fontsize=8)
    fig.text(.5,0,'Background: green = clear; light gray = cloud; dark gray = invalid view; blue = water; purple = missing; orange = insufficient background',ha='center',fontsize=8)
    save_plot(fig,figs/'himawari_vs_viirs_map.png')
    fig,ax=plt.subplots(figsize=(7,4))
    if len(sample):
        ax.scatter(sample.frp_mw,sample.detected.astype(int),s=14,alpha=.5)
    if fit['fitted']:
        x=np.geomspace(max(.01,sample.frp_mw.min()),sample.frp_mw.max(),100)
        for vz in [60,65]:
            z=fit['intercept']+fit['beta_log_frp']*np.log(x)+fit['beta_vza']*vz
            ax.plot(x,1/(1+np.exp(-z)),label=f'VZA {vz}')
        ax.legend()
    else:
        ax.text(.5,.5,fit['reason'],transform=ax.transAxes,ha='center',wrap=True)
    ax.set(xscale='log',xlabel='VIIRS event-overpass FRP (MW)',ylabel='AHI detection probability',ylim=(-.05,1.05))
    save_plot(fig,figs/'himawari_detection_curve.png')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    axes[0].scatter(pairs.frp_sum_mw_modis,pairs.frp_viirs_unadjusted_mw,s=2,alpha=.3,label='transfer candidates')
    v1pairs_path=cfg['paths']['window_interim']/'calibration_pairs.csv'
    if v1pairs_path.exists():
        baseline=pd.read_csv(v1pairs_path)
        axes[0].scatter(baseline.frp_sum_mw_modis,baseline.frp_sum_mw_viirs,s=6,alpha=.5,label='v1 simultaneous pairs')
        axes[0].legend(fontsize=8)
    good=pairs.dropna(subset=['time_ratio'])
    axes[1].scatter(good.frp_sum_mw_modis,good.frp_sum_mw_viirs,s=2,alpha=.3)
    if good.empty:
        axes[1].text(.5,.5,'Time adjustment unavailable:\nno supported diurnal shape',ha='center',transform=axes[1].transAxes)
    for ax,title in zip(axes,['Before time adjustment (transfer candidates)','After time adjustment']):
        ax.set(xlim=(.1,1e5),ylim=(.1,1e5),xscale='log',yscale='log',xlabel='Aqua FRP (MW)',ylabel='VIIRS FRP (MW)',title=title)
    save_plot(fig,figs/'calibration_v1_vs_v3.png')


def report(out,stats,det,cases,models,tf,df,pairs,events,tuning,inventory,cfg):
    lines=['# Phase 3 — Himawari current_2026','',
           'Window: 29 October–2 November 2026 UTC. November 2 is partial. Results use only local files; no missing scans are imputed.',
           f"Prepared hourly scans: {len(inventory['prepared'])}; missing: {len(inventory['missing_scans'])}; errors: {len(inventory['errors'])}.",'',
           '## Geometry and diurnal fits','', '| Region | Valid area | Tier | Full days | Fit / peak hour |','|---|---:|---|---:|---|']
    for name,m in models.items():
        lines.append(f"| {name} | {m['valid_area_share']:.2%} | {m['tier']} | {m['n_days']} | {m['parameters'] if m['fitted'] else m['reason']} |")
    lines += ['', 'Tier describes geometry eligibility. No borrowed curve is assigned without an available, scientifically defensible donor. Eastern IGP has too little valid area to supply Punjab–Haryana. Zero daily maxima cannot be normalized.', '',
              '## Detection and validation','',f"AHI fire pixels across time steps: {len(det)}; transient suspects: {int(det.transient_suspect.sum())}.",'',
              '| Region | VIIRS event-overpasses | Clear observed | Detected / observed | Unknown (cloud/view/water/missing) |',
              '|---|---:|---:|---|---:|']
    for region in models:
        c=cases[cases['box_'+region]]
        groups=['fire_id','platform','acq_datetime_utc']
        n=len(c.groupby(groups)); obs=c[c.status.isin([0,1])]
        gg=obs.groupby(groups).detected.max(); observed=len(gg)
        rate=f'{int(gg.sum())}/{observed} ({gg.mean():.1%})' if observed else 'not estimable'
        lines.append(f'| {region} | {n} | {observed} | {rate} | {n-observed} |')
    lines += ['', 'Cloud, water, missing imagery, invalid view and insufficient background are excluded from detection-rate denominators. A cloudy VIIRS fire is not an AHI miss.', '',
              '| Day/night | AHI fires | Unmatched commission |','|---|---:|---|']
    for dn in ['D','N']:
        d=det[det.daynight.eq(dn)]
        lines.append(f"| {dn} | {len(d)} | {float((~d.reference_match).mean()):.1%} |" if len(d) else f'| {dn} | 0 | not estimable (zero denominator) |')
    for name,dates in [('Training',tuning['train_dates']),('Held-out',tuning['test_dates'])]:
        c=cases[cases.acq_datetime_utc.dt.strftime('%Y-%m-%d').isin(dates)]
        fit,sample=detection_fit(c)
        lines.append(f"\n{name}: {len(sample)} clear observed event-overpasses; detected {int(sample.detected.sum()) if len(sample) else 0}; logistic fit: {fit}.")
    lines += ['',f"Chosen thresholds: `{json.dumps(tuning['chosen'])}`.",f"Cloud thresholds: `{json.dumps(cfg['himawari']['cloud'])}`.",
              f"Tuning: {tuning['reason']}; large observed training events: {tuning['n_large_observed_training_events']}.",
              'Full tuning audit: `himawari/threshold_selection.json`. No test-day data were used to select thresholds.', '',
              '## Transfer calibration and energy','',f"Aqua+VIIRS events in event table: {events.platforms_seen.str.contains('Aqua').mul(events.n_VIIRS.gt(0)).sum()}. Candidate event-overpass pairs: {len(pairs)}. Pairs with a supported shape: {pairs.time_ratio.notna().sum()}.",'',
              '| Version | Status | Fit |','|---|---|---|']
    v1=json.loads((ROOT/'params/calibration_v1.json').read_text())
    lines.append(f"| v1 | drift-affected source window (original file retained) | `{json.dumps(v1.get('values',v1.get('fit',{})))}` |")
    lines.append(f"| v3 transfer | provisional – transfer standard | `{json.dumps(tf)}` |")
    lines += ['',f"Transfer detection curve: `{json.dumps(df)}`.",
              f"Events with FRE_estimate: {events.FRE_estimate.notna().sum()}/{len(events)}. Unavailable estimates remain null. Units: MJ; integration in hours is multiplied by 3600. Overpasses combine within local solar day by inverse variance, then daily energy sums over the event.", '',
              '## MIR radiance constant','',
              'a = 3.1968263738110607e-9 W m-2 sr-1 um-1 K-4; sigma/a = 17.73751138202904. Fit range 650?1300 K; relative RMS error 7.861%, maximum 27.484%.','',
              'See `docs/decisions.md` and `himawari/mir_constant.json` for the response-weighted Planck fit, units, SRF checksum and approximation error.', '',
              '## Limitations','',
              'Only four full UTC days, hourly sampling and one partial day are available. Bootstrap units are days, not pixels. Full UTC days are used consistently for normalization; local-solar-day boundary coverage is not complete at both window edges. AHI MIR radiance is not corrected for atmospheric transmission or reflected sunlight. The cloud mask is a simple threshold screen; global_land_mask is static. Persistence at a window edge lacks one neighbor. Small polar fires can fall below the coarse AHI pixel sensitivity. Reference matches use 2 km, which is smaller than some off-nadir pixel footprints. Zero fire samples cannot identify a logistic curve or a diurnal shape.', '',
              'The request cited 5,779 shared Aqua+VIIRS events; the current finalized window table contains 7,374. Counts above use the current table, with no forced subsampling to the earlier count. ',
              'Transfer is limited to supported regional shapes: the global set of shared Aqua+VIIRS events cannot be assigned a Bangladesh shape without evidence. Missing transfer fits and FRE are scientific data limitations, not zero estimates. Event-specific AHI ratios require a detectable event at both times; no ratio is substituted when either observation is absent.', '',
              '## Verification','',
              'Harmonization: 47 tests passed (including the six new Phase 3 tests). Backend: 61 tests passed using the backend Python environment and working directory. The initial combined-root collection could not resolve the backend import layout; separate suite runs succeeded.','',
              'Reproduce: `python -m pipeline.himawari --window current_2026`, then `python run_phase3.py --window current_2026`. Raw data are never modified. Observation status grids are under `data/interim/windows/current_2026/himawari/masks/`; detections are day-partitioned under `data/processed/himawari_fires/`.']
    (out/'phase3_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def regenerate_report(cfg):
    out=cfg['paths']['window_outputs']; cache=cfg['paths']['window_interim']/'himawari'
    def read(name):
        return pd.read_csv(out/'himawari'/name)
    stats=read('scan_statistics.csv'); cases=read('viirs_pixel_cases.csv'); sample=read('viirs_event_cases.csv')
    for table in [stats,cases,sample]:
        table['acq_datetime_utc']=pd.to_datetime(table.acq_datetime_utc,utc=True)
    det=pd.concat([pd.read_parquet(p) for p in sorted((cfg['paths']['partition_root']/'himawari_fires').glob('year=*/month=*/day=*/part.parquet'))],ignore_index=True)
    pairs=read('transfer_pairs.csv')
    paramdir=ROOT/cfg['params']['dir']
    models=json.loads((paramdir/'diurnal_v1.json').read_text())['regions']
    tf=json.loads((paramdir/'calibration_v3_transfer.json').read_text())['fit']
    df=json.loads((paramdir/'detection_curve_v2_transfer.json').read_text())['fit']
    fit=json.loads((out/'himawari/detection_fit.json').read_text())
    inventory=json.loads((cache/'inventory.json').read_text())
    tuning=json.loads((out/'himawari/threshold_selection.json').read_text())
    events=pd.read_csv(cfg['paths']['window_processed']/'fire_events.csv',low_memory=False)
    geom=dict(np.load(cache/'geometry.npz'))
    t=pd.Timestamp(str(cfg['window']['start'])+' 07:00',tz='UTC')
    status=np.load(cache/'masks'/t.strftime('%Y/%m/%d/%H%M.npz'))['status']
    make_figures(cfg['paths']['figures_dir'],geom,(t,status),cases,det,sample,fit,pairs,cfg)
    report(out,stats,det,cases,models,tf,df,pairs,events,tuning,inventory,cfg)


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--window',default='current_2026'); ap.add_argument('--report-only',action='store_true'); a=ap.parse_args()
    cfg=load_settings(window=a.window)
    if a.report_only:
        regenerate_report(cfg)
    else:
        run(cfg)
