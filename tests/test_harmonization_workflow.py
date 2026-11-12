"""Synthetic fixtures verify algorithms; these files are never live evidence."""
import json
from copy import deepcopy
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from pipeline.config import load_settings
from pipeline.harmonization import estimate_activity, temporal_energy, historical_summary, run
from pipeline.live_globe import harmonize


def exposure(platform, O=2, pi=.5, **changes):
    return dict(cell_id='r1130c2700',date='2026-11-03',platform=platform,O=O,
                pi_draws=[pi]*300,validated=True,coverage_complete=True,
                reference_population='test observable reference',source='independent test evidence',**changes)


def test_lambda_uses_opportunities_and_sensitivity_not_raw_hot_pixel_counts():
    counts=pd.DataFrame([dict(cell_id='r1130c2700',date='2026-11-03',platform=p,N=n) for p,n in [('Aqua',2),('NOAA-20',3)]])
    result=estimate_activity(counts,pd.DataFrame([exposure('Aqua'),exposure('NOAA-20',pi=.25)]))
    assert result.iloc[0].lambda_hat==pytest.approx(5/1.5)
    assert result.iloc[0].lambda_lo90<=result.iloc[0].lambda_hat<=result.iloc[0].lambda_hi90


@pytest.mark.parametrize('change',[{'coverage_complete':False},{'validated':False},{'O':0},{'pi_draws':[1.5]*300},{'pi_draws':[]}])
def test_missing_or_invalid_inputs_do_not_become_zero_activity(change):
    row=exposure('Aqua'); row.update(change)
    counts=pd.DataFrame(columns=['cell_id','date','platform','N'])
    result=estimate_activity(counts,pd.DataFrame([row]))
    assert result.iloc[0].status=='awaiting data'
    assert result.iloc[0].lambda_hat is None


def test_independently_observed_zero_is_distinct_from_unavailable():
    result=estimate_activity(pd.DataFrame(columns=['cell_id','date','platform','N']),pd.DataFrame([exposure('Aqua')]))
    assert result.iloc[0].lambda_hat==0
    assert result.iloc[0].lambda_hi90>0


def test_temporal_correction_combines_daily_energy_without_summing_across_time():
    rng=np.random.default_rng(1)
    shape=np.column_stack([np.full(300,.1),np.ones(300),rng.normal(14,.1,300),rng.normal(3,.1,300)])
    coeff=np.column_stack([rng.normal(0,.02,300),np.ones(300)])
    model=dict(cell_id='r1130c2700',date='2026-11-03',platform='NOAA-20',base=.1,peak=1,h=14,sigma=3,
               validated=True,source='synthetic test shape',tier='A',shape_draws=shape.tolist(),frp_draws=coeff.tolist())
    obs=dict(cell_id=model['cell_id'],date=model['date'],platform='NOAA-20',frp_mw=10,acq_datetime_utc='2026-11-03T06:00:00Z')
    one=temporal_energy(pd.DataFrame([obs]),pd.DataFrame([model]))
    two=temporal_energy(pd.DataFrame([obs,{**obs,'acq_datetime_utc':'2026-11-03T06:00:01Z'}]),pd.DataFrame([model]))
    assert one.fre_mj.iloc[0]>0
    assert two.fre_mj.iloc[0]==pytest.approx(one.fre_mj.iloc[0],rel=.001)
    model['validated']=False
    assert temporal_energy(pd.DataFrame([obs]),pd.DataFrame([model])).empty


def test_calendar_does_not_fill_missing_weeks_with_zeros():
    cfg=load_settings()
    history=pd.DataFrame([dict(cell_id='r1130c2700',year=y,week=w,value=1,
        coverage_complete=True,reference_population='test',model_version='test-v1')
        for y in range(2018,2023) for w in range(1,53)])
    activity=pd.DataFrame(columns=['status','reference_population'])
    complete=historical_summary(activity,history,cfg)
    assert complete['calendar']['status']=='ok'
    assert complete['anomalies']['status']=='ok'
    incomplete=historical_summary(activity,history.iloc[1:],cfg)
    assert incomplete['status']=='insufficient_history'


def test_workflow_runs_every_stage_and_reports_missing_evidence(tmp_path,monkeypatch):
    from pipeline import harmonization as module
    rows=[dict(lat=23.051,lon=90.051,acq_datetime='2026-11-03T06:00:00Z',confidence_pct=80,
               frp=10,sensor='viirs_noaa20',satellite='N20',scan_km=.4,track_km=.4,daynight='D')]
    artifacts=tmp_path/'input'
    harmonize(rows,artifacts)
    det=gpd.read_parquet(artifacts/'detections.parquet'); ov=pd.read_parquet(artifacts/'event_overpasses.parquet')
    def unavailable(*args): raise ValueError('Test fixture has no independent orbital evidence')
    monkeypatch.setattr(module,'independent_opportunities',unavailable)
    report=run(det,ov,load_settings(),tmp_path/'output')
    assert [stage['stage'] for stage in report['stages']]==list(range(1,11))
    assert report['stages'][4]['energy']['pass']
    assert report['stages'][5]['status']=='failed'
    assert report['stages'][6]['status']=='awaiting data'
    assert report['stages'][7]['status']=='awaiting data'
    assert report['stages'][8]['status']=='awaiting data'
    assert report['stages'][9]['status']=='partial'
    assert report['full_harmonization_complete'] is False
    assert report['finished'] is True
    activity=json.loads((tmp_path/'output'/'activity.json').read_text())
    assert activity and all(row['lambda_hat'] is None for row in activity)


def test_all_ten_stages_connect_when_applicable_evidence_exists(tmp_path,monkeypatch):
    """Orchestration fixture: fitted-model functions are stubbed, not live data."""
    from pipeline import harmonization as module, frp_dist
    artifacts=tmp_path/'input'
    harmonize([dict(lat=23.051,lon=90.051,acq_datetime='2026-11-03T06:00:00Z',confidence_pct=80,
        frp=10,sensor='viirs_noaa20',satellite='N20',scan_km=.4,track_km=.4,daynight='D')],artifacts)
    det=gpd.read_parquet(artifacts/'detections.parquet'); ov=pd.read_parquet(artifacts/'event_overpasses.parquet')
    cell='r1130c2700'; day='2026-11-03'
    monkeypatch.setattr(module,'independent_opportunities',lambda *a:pd.DataFrame({'cell_id':[cell]}))
    monkeypatch.setattr(module.calibration,'calibrate',lambda *a:[{'fitted':True,'n':100,'a':0,'b':1}])
    monkeypatch.setattr(module.calibration,'detection_sample',lambda *a:pd.DataFrame({'detected':[0,1]}))
    monkeypatch.setattr(module.calibration,'fit_detection_curve',lambda *a:{'fitted':True,'b0':0,'b1':1,'b2':.2,'boot':[[0,1,.2]]*300})
    monkeypatch.setattr(frp_dist,'run',lambda *a:{'fits':{},'pi':{}})
    rng=np.random.default_rng(3)
    coeff=np.column_stack([rng.normal(0,.01,300),np.ones(300)])
    shape=np.column_stack([np.full(300,.1),np.ones(300),rng.normal(14,.1,300),np.full(300,3)])
    model=dict(cell_id=cell,date=day,platform='NOAA-20',base=.1,peak=1,h=14,sigma=3,
        source='synthetic model fixture',validated=True,tier='A',frp_draws=json.dumps(coeff.tolist()),shape_draws=json.dumps(shape.tolist()))
    history=pd.DataFrame([dict(cell_id=cell,year=y,week=w,value=1,coverage_complete=True,
        reference_population='test observable reference',model_version='fixture-v1') for y in range(2018,2023) for w in range(1,53)])
    tables={'temporal_models':pd.DataFrame([model]),'exposures':pd.DataFrame([exposure('NOAA-20')]),'history':history,
            'validation':pd.DataFrame([dict(cell_id=cell,date=day,reference=1,source='independent fixture',independent=True,
                reference_population='test observable reference')])}
    evidence={}
    for name,table in tables.items():
        table=table.copy()
        if name=='exposures': table['pi_draws']=table.pi_draws.map(json.dumps)
        path=tmp_path/f'{name}.csv'; table.to_csv(path,index=False); evidence[name]=str(path)
    cfg=load_settings(); cfg['full_harmonization']={'min_validation_samples':1}
    report=run(det,ov,cfg,tmp_path/'output',evidence)
    assert report['full_harmonization_complete'], report['stages']
    assert all(s['status']=='computed' for s in report['stages'])
    assert report['validation_metrics']['n']==1
