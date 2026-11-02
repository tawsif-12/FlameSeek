import numpy as np
import pandas as pd
import pytest
from pipeline.config import load_settings
from pipeline import himawari as hw, diurnal, transfer
from run_phase3 import assert_training_dates, detection_fit


def test_tuning_rejects_holdout_days():
    s=load_settings()['himawari']
    assert_training_dates(['2026-10-29','2026-10-30'],s)
    with pytest.raises(ValueError):
        assert_training_dates(['2026-10-31'],s)


def test_clouds_are_unknown_not_negative_cases():
    s=load_settings()['himawari']
    frame={k:np.full((15,15),v,dtype=float) for k,v in
           dict(b07=320,b14=250,b15=249,radiance=1,sza_deg=30).items()}
    geom=dict(vza_deg=np.full((15,15),60.),land=np.ones((15,15),bool),pixel_area_km2=np.ones((15,15)))
    result=hw.contextual(frame,geom,s,dict(sigma_over_a=17.7))
    assert np.all(result['status']==2)
    assert not result['fire'].any()
    cases=pd.DataFrame(dict(status=[2,0],fire_id=['cloud','clear'],platform=['S-NPP']*2,
                            acq_datetime_utc=pd.to_datetime(['2026-10-29T07:00Z']*2),
                            frp_mw=[100,1],vza_deg=[60,60],detected=[False,False]))
    _,sample=detection_fit(cases)
    assert sample.fire_id.tolist()==['clear']


def test_adjustment_uses_local_solar_time():
    pars=dict(base=.1,peak=1,h=14,sigma=2)
    ta=pd.Timestamp('2026-10-29T10:00Z'); tv=pd.Timestamp('2026-10-29T07:30Z')
    expected=diurnal.shape(16,**pars)/diurnal.shape(13.5,**pars)
    assert diurnal.time_ratio(ta,tv,90,pars)==pytest.approx(expected)
    assert diurnal.time_ratio(ta,tv,0,pars)!=pytest.approx(expected)


def test_transfer_forbids_terra():
    cfg=load_settings(); cfg['events']['matched_pair_modis']=['Terra']
    with pytest.raises(ValueError,match='Terra'):
        transfer.transfer_pairs(pd.DataFrame(),cfg)


def test_daily_energy_units_and_amplitude_cancel():
    pars=dict(base=1,peak=0,h=14,sigma=3)
    assert diurnal.daily_energy(2,10,pars)==pytest.approx(2*86400)
    pars['base']=5
    assert diurnal.daily_energy(2,10,pars)==pytest.approx(2*86400)


def test_zero_fire_days_cannot_define_diurnal_curve():
    t=pd.date_range('2026-10-29',periods=96,freq='h',tz='UTC')
    stats=pd.DataFrame(dict(acq_datetime_utc=t,lst_h=(t.hour+6)%24,frp_mw=0.,clear_sky_fraction=1.))
    fit,_=diurnal.fit_region(stats,load_settings()['himawari'])
    assert not fit['fitted'] and fit['parameters'] is None
