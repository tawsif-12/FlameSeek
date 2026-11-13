"""Execute Steps 5–10 after the normal footprint/event pipeline.

Physical activity estimates require independent observation opportunities and
applicable model evidence. Missing inputs yield explicit nulls, never unit
corrections, fabricated clear misses, or zeros. All files are run-local.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline import grid, calibration, diurnal, calendar, anomalies
from pipeline.config import ROOT, load_settings

NAMES = ['Standardization', 'Quality filtering', 'Pixel footprints', 'Event merging',
         'Common grid', 'Sensor calibration', 'Temporal correction',
         'Activity and uncertainty', 'Calendar and anomalies', 'Validation']


def clean_json(value):
    if isinstance(value, dict): return {str(k): clean_json(v) for k, v in value.items()
                                        if not (k=='fit' and hasattr(v,'power_law'))}
    if isinstance(value, (list, tuple, np.ndarray)): return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, Path)): return str(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    return value


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(clean_json(value), allow_nan=False), encoding='utf-8')
    temp.replace(path)


def read_table(path):
    return pd.read_parquet(path) if str(path).endswith('.parquet') else pd.read_csv(path)


def independent_opportunities(daily, det, cfg, evidence):
    """Use independent coverage; detections themselves never define clear misses."""
    if evidence.get('opportunities'):
        frame = read_table(evidence['opportunities'])
    else:
        from pipeline import overpasses
        from skyfield.api import EarthSatellite, load
        cells = daily[['cell_id', 'cell_lat', 'cell_lon']].drop_duplicates('cell_id').rename(columns={'cell_lat':'lat', 'cell_lon':'lon'})
        t0 = pd.to_datetime(det.acq_datetime_utc, utc=True).min().floor('D') - pd.Timedelta(days=1)
        t1 = pd.to_datetime(det.acq_datetime_utc, utc=True).max().ceil('D') + pd.Timedelta(days=1)
        frames = []
        for platform in cfg['overpasses']['norad_ids']:
            cache = ROOT / cfg['overpasses']['tle_cache_dir'] / f'{platform}.json'
            if not cache.exists(): continue
            tle = json.loads(cache.read_text())
            sat = EarthSatellite(tle['line1'], tle['line2'], platform, load.timescale())
            epoch = pd.Timestamp(sat.epoch.utc_datetime())
            if max(abs(epoch-t0), abs(epoch-t1)) > pd.Timedelta(days=30): continue
            frame = overpasses.passes_for_platform(platform, tle, cells, t0, t1, cfg)
            if not frame.empty:
                frame['coverage_basis'] = 'independent orbital propagation; clear-sky assumption'
                frames.append(frame)
        if not frames: raise ValueError('No applicable orbital elements within 30 days of the observations')
        frame = pd.concat(frames, ignore_index=True)
    required = {'cell_id','platform','overpass_time_utc','pixel_area_km2','scan_angle_deg','tle_epoch_utc','tle_source'}
    if not required.issubset(frame): raise ValueError(f'Opportunity input missing {sorted(required-set(frame))}')
    frame = frame.copy()
    frame['overpass_time_utc'] = pd.to_datetime(frame.overpass_time_utc, utc=True)
    epoch = pd.to_datetime(frame.tle_epoch_utc, utc=True)
    if ((epoch-frame.overpass_time_utc).abs() > pd.Timedelta(days=30)).any():
        raise ValueError('Orbital epoch is outside its 30-day applicability interval')
    if not np.isfinite(frame.pixel_area_km2).all() or (frame.pixel_area_km2 <= 0).any():
        raise ValueError('Opportunity pixel areas must be finite and positive')
    if frame.duplicated(['cell_id','platform','overpass_time_utc']).any():
        raise ValueError('Duplicate observation opportunities')
    centers = daily[['cell_id','cell_lon']].drop_duplicates('cell_id')
    frame = frame.drop(columns=['cell_lon'], errors='ignore').merge(centers, on='cell_id')
    frame['date'] = (frame.overpass_time_utc + pd.to_timedelta(frame.cell_lon/15, unit='h')).dt.strftime('%Y-%m-%d')
    return frame


def event_counts(det, cfg):
    """Event-overpass footprint shares, rather than numbers of hot pixels."""
    import shapely
    keys, shapes = [], []
    for (fire, platform, stamp), group in det.groupby(['fire_id','platform','acq_datetime_utc'], sort=False):
        shape = shapely.union_all(group.geometry.values)
        longitude = float(shapely.get_x(shapely.centroid(shape)))
        day = (pd.Timestamp(stamp) + pd.Timedelta(hours=longitude/15)).strftime('%Y-%m-%d')
        keys.append((platform, day)); shapes.append(shape)
    if not keys: return pd.DataFrame(columns=['cell_id','date','platform','N'])
    pieces = grid.overlay(np.array(shapes, dtype=object), cfg['grid']['cell_deg'])
    keys = pd.DataFrame(keys, columns=['platform','date'])
    result = pd.DataFrame({'cell_id': grid.cell_id(pieces.ix.values, pieces.iy.values),
                           'platform':keys.platform.values[pieces.row.values],
                           'date':keys.date.values[pieces.row.values], 'N':pieces.w.values})
    return result.groupby(['cell_id','date','platform'], as_index=False).N.sum()


def temporal_energy(gov, models, cell_deg=.1):
    """Applicable cell/platform/day models; bootstrap draws carry model uncertainty.

    Each model supplies [base,peak,h,sigma] and calibrated log10 FRP
    [a,b] coefficient draws, with a source and validation flag. Identity FRP
    coefficients are allowed only when explicitly supplied for the reference
    sensor. Unknown curves and uncalibrated Terra are never substituted.
    """
    columns = ['cell_id','date','platform','base','peak','h','sigma','source','validated','frp_draws','shape_draws','tier']
    if not set(columns).issubset(models): raise ValueError('Temporal models need scoped parameters, sources and uncertainty draws')
    if models.duplicated(['cell_id','date','platform']).any(): raise ValueError('Duplicate scoped temporal models')
    rows = gov.merge(models, on=['cell_id','date','platform'], how='left')
    result = []
    for (cell, day), group in rows.groupby(['cell_id','date'], sort=False):
        looks, tiers, sources = {}, set(), set()
        accepted=0
        for row in group.itertuples():
            if row.validated is not True and row.validated != True: continue
            if not isinstance(row.source, str) or not row.source.strip(): continue
            if row.tier not in ('A','B','C'): continue
            coefficients = np.asarray(json.loads(row.frp_draws) if isinstance(row.frp_draws,str) else row.frp_draws, float)
            shapes = np.asarray(json.loads(row.shape_draws) if isinstance(row.shape_draws,str) else row.shape_draws, float)
            if coefficients.ndim != 2 or coefficients.shape[1] != 2 or shapes.ndim != 2 or shapes.shape[1] != 4: continue
            if len(shapes) < 30 or len(coefficients) != len(shapes) or not np.isfinite(coefficients).all() or not np.isfinite(shapes).all(): continue
            if (shapes[:,0] < 0).any() or (shapes[:,1] <= 0).any() or (shapes[:,3] <= 0).any(): continue
            stamp = pd.Timestamp(row.acq_datetime_utc)
            lon = -180 + (int(str(cell)[6:10])+.5)*cell_deg
            local = (stamp.hour + stamp.minute/60 + stamp.second/3600 + lon/15)%24
            # Calibrate whole event-overpass power BEFORE allocating its share
            # to a cell. A nonlinear power law must not act on a split pixel.
            whole = getattr(row,'event_frp_mw',row.frp_mw)
            fraction = getattr(row,'overlap_weight',1.)
            power = 10**(coefficients[:,0] + coefficients[:,1]*np.log10(max(whole,1e-12)))*fraction
            energy = np.array([diurnal.daily_energy(f,local,dict(zip(['base','peak','h','sigma'],p))) for f,p in zip(power,shapes)])
            if not np.isfinite(energy).all() or energy.var() <= 0: continue
            key=(row.platform,str(row.acq_datetime_utc))
            if key in looks:
                size=min(len(looks[key]),len(energy)); looks[key]=looks[key][:size]+energy[:size]
            else: looks[key]=energy
            accepted+=1
            tiers.add(row.tier); sources.add(row.source)
        if looks:
            draws=list(looks.values())
            # Align shared parameter draws across overpasses; never sum FRP across time.
            size = min(map(len,draws)); values=np.stack([d[:size] for d in draws])
            weights=1/values.var(axis=1); combined=np.average(values,axis=0,weights=weights)
            result.append(dict(cell_id=cell,date=day,fre_mj=float(np.mean(combined)),
                               fre_lo90_mj=float(np.quantile(combined,.05)),fre_hi90_mj=float(np.quantile(combined,.95)),
                               diurnal_source=';'.join(sorted(tiers)),source=';'.join(sorted(sources)),temporal_complete=accepted==len(group)))
    return pd.DataFrame(result, columns=['cell_id','date','fre_mj','fre_lo90_mj','fre_hi90_mj','diurnal_source','source','temporal_complete'])


def estimate_activity(counts, exposures, draws=300, seed=20261102):
    """Monte Carlo lambda=N/sum(O*pi), with unknown coverage withheld.

    Exposure rows are independent cell/day/platform aggregates. pi_draws come
    from a fitted, applicable sensor response + FRP-distribution integral;
    reference_population makes the estimand explicit. Full estimates cannot
    quietly assume pi=1 for every physical fire.
    """
    required={'cell_id','date','platform','O','pi_draws','source','validated','coverage_complete','reference_population'}
    if not required.issubset(exposures): raise ValueError(f'Exposure evidence missing {sorted(required-set(exposures))}')
    if exposures.duplicated(['cell_id','date','platform']).any(): raise ValueError('Duplicate exposure rows')
    data=exposures.merge(counts,on=['cell_id','date','platform'],how='outer')
    rng=np.random.default_rng(seed); output=[]
    for (cell,day), group in data.groupby(['cell_id','date'],sort=False):
        record=dict(cell_id=cell,date=day,lambda_hat=None,lambda_lo90=None,lambda_hi90=None,status='awaiting data')
        if not group.validated.eq(True).all() or not group.coverage_complete.eq(True).all():
            output.append({**record,'reason':'Independent complete coverage and applicable sensitivity are required'}); continue
        if not group.O.notna().all() or not np.isfinite(group.O).all() or (group.O<0).any() or group.source.isna().any():
            output.append({**record,'reason':'Invalid observation opportunities or provenance'}); continue
        if group.reference_population.nunique()!=1:
            output.append({**record,'reason':'Incompatible reference populations'}); continue
        denominator=np.zeros(draws); valid=True
        for row in group.itertuples():
            try: pi=np.asarray(json.loads(row.pi_draws) if isinstance(row.pi_draws,str) else row.pi_draws,float)
            except (ValueError,TypeError): valid=False; break
            if pi.ndim!=1 or len(pi)<30 or not np.isfinite(pi).all() or ((pi<=0)|(pi>1)).any(): valid=False; break
            denominator+=float(row.O)*rng.choice(pi,draws,replace=True)
        if not valid or (denominator<=0).any():
            output.append({**record,'reason':'Invalid sensitivity draws or no independent observation opportunities'}); continue
        observed=float(group.N.fillna(0).sum())
        # Gamma-Poisson sampling is conditional count uncertainty, explicitly
        # distinguished from the MLE point estimate and omitted systematics.
        samples=rng.gamma(observed+.5,1,size=draws)/denominator
        estimate=observed/float(denominator.mean())
        output.append({**record,'N_observed':observed,'denominator':float(denominator.mean()),'lambda_hat':estimate,
                       'lambda_lo90':min(estimate,float(np.quantile(samples,.05))),
                       'lambda_hi90':max(estimate,float(np.quantile(samples,.95))),'status':'computed',
                       'reference_population':group.reference_population.iloc[0],
                       'uncertainty':'Conditional Gamma-Poisson and supplied sensitivity draws; unmeasured systematic errors excluded',
                       'source':';'.join(sorted(set(group.source.astype(str))))})
    return pd.DataFrame(output)


def historical_summary(activity, history, cfg):
    """Never fill missing historical weeks with no-fire zeros."""
    if history is None or history.empty:
        return {'status':'insufficient_history','reason':'No coverage-verified harmonized historical weekly series supplied'}
    required={'cell_id','year','week','value','coverage_complete','reference_population','model_version'}
    if not required.issubset(history): return {'status':'insufficient_history','reason':'Historical coverage and model provenance missing'}
    h=history[history.coverage_complete.eq(True)&history.value.notna()].copy()
    if h.duplicated(['cell_id','year','week']).any(): raise ValueError('Duplicate historical weeks')
    if h.empty or h.reference_population.nunique()!=1 or h.model_version.nunique()!=1:
        return {'status':'insufficient_history','reason':'History has incompatible models or populations'}
    populations=set(activity.loc[activity.status.eq('computed'),'reference_population']) if 'reference_population' in activity else set()
    if populations and populations!={h.reference_population.iloc[0]}:
        return {'status':'insufficient_history','reason':'Historical and current reference populations differ'}
    years=sorted(h.year.unique()); cells=sorted(h.cell_id.unique())
    complete=h.groupby('cell_id').apply(lambda g: len(g)==len(years)*52 and g.week.between(1,52).all(),include_groups=False)
    h=h[h.cell_id.isin(complete[complete].index)]
    if h.empty: return {'status':'insufficient_history','reason':'Missing historical weeks remain unknown; no complete cell histories'}
    return {'status':'computed','calendar':calendar.build_calendar(h,cfg),'anomalies':anomalies.detect(h,cfg),
            'excluded_incomplete_cells':len(cells)-int(complete.sum()),'reference_population':h.reference_population.iloc[0]}


def run(det, ov, cfg, output, evidence=None, initial=None):
    """Run all stages independently; publish real partial progress atomically."""
    evidence=evidence or {}; output=Path(output); output.mkdir(parents=True,exist_ok=True)
    stages=[dict(stage=i+1,name=name,status='pending') for i,name in enumerate(NAMES)]
    for i in range(4): stages[i].update(status='computed',note='Normal ingest / quality / footprint / event pipeline')
    summary={'version':1,'stages':stages,'full_harmonization_complete':False,'scope':'cells with footprint observations; unobserved world cells are not assumed fire-free'}
    def publish(i,status,**extra):
        stages[i-1].update(status=status,**clean_json(extra))
        summary['updated_at']=pd.Timestamp.now(tz='UTC').isoformat()
        write_json(output/'status.json',summary)
    def attempt(i, operation):
        start=time.perf_counter(); publish(i,'running')
        try: return operation()
        except Exception as exc:
            publish(i,'failed',reason=f'{type(exc).__name__}: {exc}',seconds=round(time.perf_counter()-start,3))
            return None
    # Preserve known missing filters rather than declaring every upstream check complete.
    if initial and initial.get('not_applied'): stages[1].update(status='partial',limitations=initial['not_applied'])
    if det.empty:
        for i in range(5,11): publish(i,'awaiting data',reason='No quality-filtered detections')
        return summary
    gr=attempt(5,lambda:grid.run(det,cfg))
    if gr is None:
        for i in range(6,11): publish(i,'awaiting data',reason='Common grid failed')
        return summary
    daily=gr['daily']; gov=gr['overpass']; daily['date']=daily.date.astype(str); gov['date']=gov.date.astype(str)
    daily.to_parquet(output/'grid_daily.parquet',index=False)
    gov.to_parquet(output/'grid_overpasses.parquet',index=False)
    publish(5,'computed' if gr['energy']['pass'] else 'failed',energy=gr['energy'],cell_days=len(daily),cell_overpasses=len(gov))
    def calibrate():
        enriched=calibration.enrich_overpasses(ov,det,cfg['grid']['cell_deg'])
        pairs=calibration.build_pairs(enriched,cfg)
        pairs.to_parquet(output/'matched_pairs.parquet',index=False)
        fits=calibration.calibrate(pairs,cfg)
        write_json(output/'calibration.json',fits)
        opportunities=independent_opportunities(daily,det,cfg,evidence)
        opportunities.to_parquet(output/'opportunities.parquet',index=False)
        sample=calibration.detection_sample(enriched,opportunities,cfg)
        curve=calibration.fit_detection_curve(sample,cfg)
        curve['applicable']=bool(curve.get('fitted') and curve.get('b1',0)>0 and curve.get('b2',-1)>=0)
        sample.to_parquet(output/'detection_sample.parquet',index=False)
        write_json(output/'detection_curve.json',curve)
        distribution=None
        if curve.get('fitted'):
            from pipeline import frp_dist
            distribution=frp_dist.run(enriched,curve,cfg)
            write_json(output/'frp_distribution.json',distribution)
        publish(6,'computed' if fits[0].get('fitted') and curve.get('applicable') else 'partial',
                matched_pairs=len(pairs),frp_fit=fits[0],detection_curve={k:v for k,v in curve.items() if k!='boot'},
                opportunity_count=len(opportunities),scope='current sample; global fit is diagnostic, not a validated biome transfer',
                reason=(None if fits[0].get('fitted') and curve.get('applicable') else
                        'Insufficient matched calibration pairs or sensitivity fit outside physical constraints (power increases detection; larger pixels reduce it)'),
                applicability='No unvalidated global calibration is applied to activity estimates. Scoped exposure and temporal evidence are required.')
        return opportunities
    attempt(6,calibrate)
    energy=pd.DataFrame()
    def temporal():
        nonlocal energy
        if not evidence.get('temporal_models'):
            publish(7,'awaiting data',reason='Need applicable cell/day/platform diurnal curves and calibrated FRP uncertainty draws; provisional Northern Australia fits cannot be applied globally')
            return
        pieces=gr['pieces']
        if 'fire_id' not in pieces: pieces=pieces.merge(det[['det_id','fire_id']],on='det_id',how='left')
        allocated=pieces.groupby(['cell_id','date','fire_id','platform','acq_datetime_utc'],as_index=False).agg(frp_mw=('frp_w','sum'))
        totals=ov[['fire_id','platform','acq_datetime_utc','frp_sum_mw']].rename(columns={'frp_sum_mw':'event_frp_mw'})
        allocated=allocated.merge(totals,on=['fire_id','platform','acq_datetime_utc'],how='left')
        allocated['overlap_weight']=allocated.frp_mw/allocated.event_frp_mw
        allocated['date']=allocated.date.astype(str)
        energy=temporal_energy(allocated,read_table(evidence['temporal_models']),cfg['grid']['cell_deg'])
        energy.to_parquet(output/'daily_energy.parquet',index=False)
        complete=len(energy)==len(daily) and energy.temporal_complete.all()
        publish(7,'computed' if complete else 'partial',computed_cell_days=len(energy),total_cell_days=len(daily),
                reason=None if complete else 'Some observations lack applicable independently validated temporal models')
    attempt(7,temporal)
    counts=event_counts(det,cfg); counts.to_parquet(output/'event_counts.parquet',index=False)
    activity=daily[['cell_id','date','cell_lat','cell_lon']].copy()
    activity['lambda_hat']=np.nan; activity['lambda_lo90']=np.nan; activity['lambda_hi90']=np.nan
    activity['status']='awaiting data'
    def latent():
        nonlocal activity
        if not evidence.get('exposures'):
            publish(8,'awaiting data',reason='Need complete independent opportunities and applicable sensor-sensitivity distribution draws; detections alone cannot supply the denominator')
            return
        exposures=read_table(evidence['exposures'])
        first,last=daily.date.min(),daily.date.max()
        exposures['date']=exposures.date.astype(str)
        exposures=exposures[exposures.date.between(first,last)]
        estimated=estimate_activity(counts,exposures,cfg['later_steps']['monte_carlo_draws'])
        # Publish only cell-days in the current run; include independent observed
        # zero-detection cells through the supplied exposure evidence as well.
        centers=daily[['cell_id','cell_lat','cell_lon']].drop_duplicates('cell_id')
        activity=estimated.merge(centers,on='cell_id',how='left')
        # Decode geometry for independently observed zero-detection cells too.
        missing=activity.cell_lat.isna()
        deg=cfg['grid']['cell_deg']
        activity.loc[missing,'cell_lat']=-90+(activity.loc[missing,'cell_id'].str[1:5].astype(int)+.5)*deg
        activity.loc[missing,'cell_lon']=-180+(activity.loc[missing,'cell_id'].str[6:10].astype(int)+.5)*deg
        if not energy.empty: activity=activity.merge(energy,on=['cell_id','date'],how='left')
        complete=activity.status.eq('computed')
        publish(8,'computed' if complete.all() and len(activity) else 'partial',computed_cell_days=int(complete.sum()),total_cell_days=len(activity))
    attempt(8,latent)
    activity.to_parquet(output/'activity.parquet',index=False)
    write_json(output/'activity.json',activity.to_dict('records'))
    def history():
        table=read_table(evidence['history']) if evidence.get('history') else None
        result=historical_summary(activity,table,cfg)
        for name in ['calendar','anomalies']:
            part=result.get(name,{})
            for key,value in list(part.items()):
                if isinstance(value,pd.DataFrame): value.to_parquet(output/f'{name}_{key}.parquet',index=False); part[key]=f'{name}_{key}.parquet'
        write_json(output/'calendar.json',result)
        good=result.get('calendar',{}).get('status')=='ok' and result.get('anomalies',{}).get('status')=='ok'
        publish(9,'computed' if good else 'awaiting data',result=result)
    attempt(9,history)
    computed=activity[activity.status.eq('computed')]
    interval_ok=bool(((computed.lambda_lo90<=computed.lambda_hat)&(computed.lambda_hat<=computed.lambda_hi90)&(computed.lambda_lo90>=0)).all())
    checks={'energy_conserved':bool(gr['energy']['pass']),
            'unique_cell_days':not activity.duplicated(['cell_id','date']).any(),
            'finite_nonnegative_estimates':bool(np.isfinite(computed.lambda_hat).all() and computed.lambda_hat.ge(0).all()),
            'ordered_uncertainty_intervals':interval_ok,
            'missing_inputs_not_filled_with_zero':bool(activity.loc[~activity.status.eq('computed'),'lambda_hat'].isna().all()),
            'independent_validation':False}
    # External validation is separate from internal consistency.
    if evidence.get('validation') and not computed.empty:
        validation=read_table(evidence['validation'])
        required={'cell_id','date','reference','source','independent','reference_population'}
        if required.issubset(validation) and not validation.duplicated(['cell_id','date']).any():
            matched=computed.merge(validation,on=['cell_id','date'])
            matched=matched[np.isfinite(matched.reference)&matched.source_y.notna()&matched.independent.eq(True)&
                            matched.reference_population_x.eq(matched.reference_population_y)&matched.source_x.ne(matched.source_y)]
            if len(matched)>=cfg.get('full_harmonization',{}).get('min_validation_samples',30):
                checks['independent_validation']=True
                summary['validation_metrics']={'n':len(matched),'mae':float(np.mean(np.abs(matched.lambda_hat-matched.reference))),
                                               'rmse':float(np.sqrt(np.mean((matched.lambda_hat-matched.reference)**2)))}
    publish(10,'computed' if all(checks.values()) else 'partial',checks=checks,
            reason=None if checks['independent_validation'] else 'Independent ground/agency/burned-area validation is not supplied or has insufficient comparable samples')
    summary['full_harmonization_complete']=all(stage['status']=='computed' for stage in stages)
    summary['computed_activity_cell_days']=len(computed)
    summary['finished']=True
    write_json(output/'status.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('artifacts'); parser.add_argument('output'); parser.add_argument('--evidence')
    args=parser.parse_args(); folder=Path(args.artifacts)
    cfg=load_settings(); evidence={}
    if args.evidence:
        path=Path(args.evidence).resolve(); evidence=json.loads(path.read_text())
        evidence={key:str((path.parent/value).resolve()) for key,value in evidence.items()}
    det=gpd.read_parquet(folder/'detections.parquet')
    ov=pd.read_parquet(folder/'event_overpasses.parquet')
    initial=json.loads((folder/'metadata.json').read_text())
    run(det,ov,cfg,args.output,evidence,initial)


if __name__=='__main__': main()
