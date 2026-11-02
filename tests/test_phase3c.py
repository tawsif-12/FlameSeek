import copy
import numpy as np
import pandas as pd
import pytest
from pipeline.config import load_settings
from pipeline import detection_limit as dl,phase3c,transfer
from run_phase3 import reference_cases
from run_phase3c import recommendations,calibration_row


def test_fraction_units_are_percent_of_pixel():
    cfg=load_settings()
    assert [f*100 for f in cfg['phase3c']['injection']['fractions']]==pytest.approx([.005,.01,.02,.05,.1])


def test_f50_interpolates_only_inside_observed_transition():
    rows=[dict(frp_median_mw=p,detection_rate=r) for p,r in [(10,0),(40,0),(100,1),(200,1)]]
    fit=dl.estimate_f50(rows)
    assert fit['frp50_mw']==pytest.approx(np.sqrt(40*100))
    assert fit['bracket_mw']==[40,100]
    assert fit['label']=='detection limit from synthetic injection'


def test_no_extrapolated_f50_when_unbracketed():
    for value,direction in [(1,'below'),(0,'above')]:
        fit=dl.estimate_f50([dict(frp_median_mw=p,detection_rate=value) for p in [10,20,40]])
        assert fit['frp50_mw'] is None and fit['status']=='not bracketed'
        assert fit['bound_direction']==direction
    assert dl.estimate_f50([])['status']=='awaiting data'


def test_nonmonotone_response_and_half_probability_plateau_are_not_precise_fits():
    bad=dl.estimate_f50([dict(frp_median_mw=p,detection_rate=r) for p,r in [(10,0),(20,1),(40,0)]])
    assert bad['frp50_mw'] is None
    plateau=dl.estimate_f50([dict(frp_median_mw=p,detection_rate=r) for p,r in [(10,0),(20,.5),(40,.5),(80,1)]])
    assert plateau['status']=='interval only' and plateau['frp50_mw'] is None
    assert plateau['bracket_mw']==[20,40]


def test_synchronization_uses_absolute_time_and_rejects_missing_pairs():
    false=phase3c.sync_eligible(pd.DataFrame(dict(platform=['S-NPP']*2,dt_min=[-130,-140])))
    assert false['median_abs_dt_min']==135 and not false['synchronized']
    true=phase3c.sync_eligible(pd.DataFrame(dict(platform=['S-NPP']*2,dt_min=[-10,20])))
    assert true['median_abs_dt_min']==15 and true['synchronized']
    assert not phase3c.sync_eligible(pd.DataFrame(columns=['platform','dt_min']))['synchronized']


def test_australian_shape_cannot_adjust_south_asia():
    cfg=copy.deepcopy(load_settings())
    cfg['himawari']['regions']={'Northern_Australia':[125,-20,138,-11]}
    pars=dict(base=.1,peak=1.,h=14.,sigma=2.)
    models={'Northern_Australia':dict(fitted=True,parameters=pars)}
    assert transfer.supported_parameters(130,-15,models,cfg)==pars
    assert transfer.supported_parameters(90,24,models,cfg) is None


def test_reference_sampling_uses_configured_australian_box():
    cfg=load_settings(); cfg['himawari']['regions']={'Northern_Australia':[125,-20,138,-11]}
    geom=dict(longitude=np.array([[130.,131.]]),latitude=np.array([[-15.,-15.]]),
              vza_deg=np.array([[20.,20.]]),in_regions=np.array([[True,True]]),box_Northern_Australia=np.array([[True,True]]))
    refs=pd.DataFrame(dict(sensor=['VIIRS','VIIRS'],longitude=[130.,90.],latitude=[-15.,24.],
                           acq_datetime_utc=pd.to_datetime(['2026-10-29T05:00Z']*2)))
    result=reference_cases(refs,geom,None,cfg)
    assert len(result)==1 and result.longitude.iloc[0]==130.


def test_independent_missing_data_gates(tmp_path,monkeypatch):
    cfg=load_settings(); cfg['paths']['himawari_dir']=tmp_path/'himawari'
    naus=phase3c.northern_australia(cfg)
    assert naus['status']=='awaiting data' and naus['transfer_to_south_asia'] is False
    near=dl.near_nadir(cfg)
    assert near['status']=='awaiting data' and near['f50']['frp50_mw'] is None
    archive=copy.deepcopy(cfg); archive['paths']['raw_dir']=tmp_path/'archive'
    monkeypatch.setattr(phase3c,'load_settings',lambda **kwargs:archive)
    sync=phase3c.synchronized_2016(cfg)
    assert sync['status']=='awaiting data' and sync['pi_modis']=='awaiting data'


def test_missing_calibrations_have_unknown_n_and_no_active_recommendation(tmp_path):
    row=calibration_row('v2 sync 2016',tmp_path/'absent.json','missing archive','sync era')
    assert row['sample_size'] is None and row['a'] is None
    rows=[{**row,'version':name} for name in ['v2 sync 2016','v3 transfer N. Australia','v3 transfer South Asia']]
    assert all(r['currently_usable'] is None for r in recommendations(rows))
