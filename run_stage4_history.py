"""Re-use the existing long-history modules on the existing planted simulation."""
import importlib.util
import numpy as np
import pandas as pd
from pipeline.config import load_settings,ROOT
from pipeline import calendar,anomalies,himawari as hw
from forecast import climatology,evaluate
spec=importlib.util.spec_from_file_location('planted_fire_history',ROOT/'tests/simulated/generate.py')
generate=importlib.util.module_from_spec(spec);spec.loader.exec_module(generate)
cfg=load_settings();df,truth=generate.simulate()
cal=calendar.build_calendar(df,cfg);found=cal['peak'].set_index('cell_id').peak_week
errors=[generate.circ_dist(found[c],truth['peak_week'][c]) for c in found.index]
anomaly=anomalies.detect(df,cfg)['table'].set_index(['cell_id','year','week'])
recovered=sum(bool(anomaly.loc[k,'anomaly_flag']) for k in truth['anomalies'])
annual=df.groupby('year').value.sum();step=anomalies.pettitt(annual.values,annual.index,cfg)
years=sorted(df.year.unique());train=df[df.year<=years[-4]];test=df[df.year>years[-4]]
model=climatology.fit(train,cfg);pred=climatology.predict(model,test)
bs=evaluate.brier(pred.p,pred.y);bss=evaluate.brier_skill(pred.p,pred.y,(train.value>0).mean())
rel=evaluate.reliability(pred.p,pred.y);evaluate.plot_reliability(rel,ROOT/'outputs/figures/forecast_reliability_simulated.png',title='15-year synthetic demonstration — not an operational fire forecast')
raw=pd.read_csv(cfg['paths']['window_processed']/'grid_daily.csv',usecols=['cell_id','date','n_events_weighted'])
times=pd.to_datetime(raw.date);raw['year']=times.dt.year;raw['week']=times.dt.isocalendar().week
weekly=raw.groupby(['cell_id','year','week'],as_index=False).n_events_weighted.sum().rename(columns={'n_events_weighted':'value'})
real=dict(calendar=calendar.build_calendar(weekly,cfg)['status'],anomalies=anomalies.detect(weekly,cfg)['status'],forecast=climatology.fit(weekly,cfg)['status'])
result=dict(existing_modules_reused=True,synthetic_years=15,synthetic_rows=len(df),peak_within_one_week_share=float(np.mean(np.array(errors)<=1)),
 planted_anomalies=len(truth['anomalies']),recovered_anomalies=recovered,step_change=step,brier=bs,brier_skill_score=bss,real_short_history=real)
hw.json_write(ROOT/'outputs/stages/stage4_history.json',result);print(result,flush=True)
