"""Local-solar-time diurnal fits; unknown shapes never become unit corrections."""
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.integrate import quad


def shape(t, base, peak, h, sigma):
    return base + peak * np.exp(-((np.asarray(t)-h)**2)/(2*sigma**2))


def fit_region(stats, settings, seed=20261102):
    d = stats.copy()
    d['utc_day'] = pd.to_datetime(d.acq_datetime_utc, utc=True).dt.strftime('%Y-%m-%d')
    counts = d.groupby('utc_day').size()
    full = counts[counts >= settings['min_full_day_scans']].index
    d = d[d.utc_day.isin(full)].copy()
    maxima = d.groupby('utc_day').frp_mw.transform('max')
    d['normalized_frp'] = d.frp_mw / maxima.where(maxima > 0)
    use = d[(d.clear_sky_fraction >= settings['min_clear_fraction_fit']) & d.normalized_frp.notna()]
    result = dict(fitted=False, sample_size=len(use), full_days=list(full), n_days=len(full),
                  parameters=None, intervals=None, status='provisional – 4 days')
    if len(use) < settings['min_fit_points'] or use.utc_day.nunique() < 2:
        return {**result, 'reason':'Insufficient clear full-day observations with positive daily FRP maxima'}, d
    def fit(x):
        return curve_fit(shape, x.lst_h, x.normalized_frp, p0=[.05,.9,14.,3.],
                         bounds=([0,0,0,.25],[1,2,24,12]), maxfev=20000)[0]
    p = fit(use)
    rng = np.random.default_rng(seed)
    days = use.utc_day.unique()
    boot = []
    curves = []
    for _ in range(settings['bootstrap_days']):
        sample = pd.concat([use[use.utc_day == day] for day in rng.choice(days,len(days))])
        try:
            q = fit(sample)
            if q[1] > 1e-8:
                boot.append([q[2], q[3], q[0]/q[1]])
                curves.append(shape(np.linspace(0,24,241),*q))
        except (ValueError, RuntimeError):
            pass
    if p[1] <= 1e-8 or len(boot) < settings['bootstrap_days']*.8:
        return {**result,'reason':'Diurnal fit or day bootstrap not identifiable'}, d
    return {**result,'fitted':True,'parameters':dict(zip(['base','peak','h','sigma'],p)),
            'intervals':dict(zip(['h','sigma','base_over_peak'],np.percentile(boot,[5,95],axis=0).T.tolist())),
            'curve_interval_90':np.percentile(curves,[5,95],axis=0).tolist(),
            'bootstrap_successes':len(boot)}, d


def time_ratio(time_a, time_v, longitude, parameters):
    from pipeline.himawari import lst
    return float(shape(lst(time_a,longitude),**parameters)/shape(lst(time_v,longitude),**parameters))


def daily_energy(frp_mw, lst_h, parameters):
    integral = quad(lambda t: float(shape(t,**parameters)),0,24)[0]
    return float(frp_mw / shape(lst_h,**parameters) * integral * 3600)  # MW s = MJ
