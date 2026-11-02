"""Aqua-only transfer pairs and daily energy, restricted to supported regional shapes."""
import numpy as np
import pandas as pd
from pipeline import calibration, diurnal, himawari as hw


def transfer_pairs(ov, cfg):
    if cfg['events']['matched_pair_modis'] != ['Aqua']:
        raise ValueError('Time-adjusted calibration requires Aqua only; Terra is forbidden')
    a = ov[ov.platform.eq('Aqua')]
    v = ov[ov.platform.isin(cfg['events']['matched_pair_viirs'])]
    p = a.merge(v,on='fire_id',suffixes=('_modis','_viirs'))
    p['dt_min'] = (p.acq_datetime_utc_viirs-p.acq_datetime_utc_modis).dt.total_seconds()/60
    # Both observations must represent the same local solar day.
    da = (p.acq_datetime_utc_modis+pd.to_timedelta(p.lon_modis/15,unit='h')).dt.date
    dv = (p.acq_datetime_utc_viirs+pd.to_timedelta(p.lon_viirs/15,unit='h')).dt.date
    p = p[(da == dv) & (p.dt_min.abs() <= cfg['himawari']['transfer_max_same_day_gap_minutes'])]
    p = p.sort_values('dt_min',key=abs).drop_duplicates(['fire_id','acq_datetime_utc_modis'])
    return p.reset_index(drop=True)


def region_for(lon,lat,cfg):
    priority=['Bangladesh','eastern_IGP','Punjab_Haryana','full_IGP']
    regions=cfg['himawari']['regions']
    for name in [r for r in priority if r in regions]+[r for r in regions if r not in priority]:
        w,s,e,n = cfg['himawari']['regions'][name]
        if w <= lon <= e and s <= lat <= n:
            return name
    return None


def supported_parameters(lon,lat,models,cfg):
    region = region_for(lon,lat,cfg)
    model = models.get(region,{})
    return model.get('parameters') if model.get('fitted') else None


def adjusted_pairs(ov,models,cfg):
    p = transfer_pairs(ov,cfg)
    ratios = []
    for r in p.itertuples():
        pars = supported_parameters(r.lon_modis,r.lat_modis,models,cfg)
        ratios.append(diurnal.time_ratio(r.acq_datetime_utc_modis,r.acq_datetime_utc_viirs,r.lon_modis,pars) if pars else np.nan)
    p['time_ratio'] = ratios
    p['frp_viirs_unadjusted_mw'] = p.frp_sum_mw_viirs
    p['frp_sum_mw_viirs'] *= p.time_ratio
    return p


def fit_adjusted(p,cfg):
    p = p[p.time_ratio.notna() & p.daynight_modis.eq('D')].copy()
    if len(p) < cfg['calibration']['min_pairs']:
        return dict(fitted=False,n=len(p),reason='No supported regional diurnal shape or too few adjusted day pairs')
    # Reuse tested errors-in-variables fitting without a simultaneous-pair cutoff.
    from copy import deepcopy
    fitcfg = deepcopy(cfg)
    fitcfg['calibration']['sync_max_dt_min'] = cfg['himawari']['transfer_max_same_day_gap_minutes']
    fitcfg['calibration']['trunc_frp_mw'] = 0
    return calibration.fit_sync(p,fitcfg)


def energy_table(ov,models,cfg):
    rows=[]
    for r in ov.itertuples():
        pars = supported_parameters(r.lon,r.lat,models,cfg)
        value = diurnal.daily_energy(r.frp_sum_mw,hw.lst(r.acq_datetime_utc,r.lon),pars) if pars else np.nan
        day = (r.acq_datetime_utc+pd.Timedelta(hours=r.lon/15)).date()
        sd = cfg['himawari']['fre_sensor_relative_sd'][r.sensor]
        rows.append(dict(fire_id=r.fire_id,day=str(day),platform=r.platform,FRE_MJ=value,
                         variance_MJ2=(value*sd)**2 if pars else np.nan))
    out=pd.DataFrame(rows)
    good=out.dropna(subset=['FRE_MJ','variance_MJ2']).copy()
    good=good[good.variance_MJ2 > 0]
    good['weight']=1/good.variance_MJ2
    good['weighted']=good.FRE_MJ*good.weight
    daily=good.groupby(['fire_id','day'])[['weighted','weight']].sum()
    daily['FRE_daily_MJ']=daily.weighted/daily.weight
    # Sum distinct daily energies, after combining each day's overpasses.
    totals=daily.groupby('fire_id').FRE_daily_MJ.sum(min_count=1)
    return out,daily.reset_index(),totals


def event_specific_ratios(pairs, detections, settings):
    """Use nearest AHI step per event at each polar time; never fill missing FRP."""
    ratios=[]
    for r in pairs.itertuples():
        sums=[]
        for time in [r.acq_datetime_utc_modis,r.acq_datetime_utc_viirs]:
            nearest=pd.Timestamp(time).round('h')
            d=detections[detections.acq_datetime_utc.eq(nearest)]
            if len(d):
                q=pd.DataFrame(dict(latitude=[r.lat_modis],longitude=[r.lon_modis],acq_datetime_utc=[time]))
                # Query AHI pixels against the event centroid with the same match radius.
                keep=hw.nearby(d,q,settings['viirs_tolerance_minutes'],settings['match_radius_km'])
                value=d.loc[keep,'frp_mw'].sum(min_count=1)
            else:
                value=np.nan
            sums.append(value)
        ratios.append(sums[0]/sums[1] if all(np.isfinite(sums)) and sums[1]>0 else np.nan)
    return ratios
