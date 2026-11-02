import copy
import json
import numpy as np
import pandas as pd
import pytest
from pipeline import latent
from pipeline.config import load_settings


def test_unobserved_is_null_not_zero():
    result=latent.ratio([0,3,0,2],[0,0,2,np.nan])
    assert np.isnan(result[[0,1,3]]).all() and result[2]==0


def test_known_poisson_expectation_recovers_lambda():
    opportunities=np.array([[2,3],[4,1]])
    pi=np.array([.2,1.])
    den=(opportunities*pi).sum(axis=1)
    truth=np.array([3.,7.])
    np.testing.assert_allclose(latent.ratio(den*truth,den),truth)


def test_event_counts_deduplicate_pixels_within_each_overpass(tmp_path):
    import geopandas as gpd
    from shapely.geometry import box
    cfg=copy.deepcopy(load_settings());cfg['paths']['window_interim']=tmp_path
    times=pd.to_datetime(['2026-10-29T05:00Z','2026-10-29T05:00Z','2026-10-29T06:00Z'])
    frame=gpd.GeoDataFrame(dict(fire_id=['event']*3,platform=['S-NPP']*3,acq_datetime_utc=times),geometry=[box(85.01,25.01,85.02,25.02)]*3,crs=4326)
    frame.to_parquet(tmp_path/'footprints.geoparquet',index=False)
    counts,_=latent.event_counts(cfg,latent.grid_cells(cfg))
    assert counts.N.sum()==pytest.approx(2)


def test_unfitted_response_has_no_fallback(tmp_path):
    cfg=load_settings(window='sync_2016');path=tmp_path/'curve.json';path.write_text(json.dumps(dict(fit=dict(fitted=False,reason='missing historical coverage'))))
    cfg['latent']['detection_curve_by_window']['sync_2016']=str(path)
    doc,reason=latent.curve_payload(cfg)
    assert doc is None and reason=='missing historical coverage'


def test_missing_curve_uncertainty_is_not_invented():
    with pytest.raises(ValueError,match='uncertainty'):
        latent.coefficient_draws(dict(values=dict(b0=0,b1=1,b2=1)),300,np.random.default_rng(2))


def test_degradation_zero_for_consistent_estimates_and_unknown_without_data():
    result=latent.degradation_bias([1,2,3],[1,2,3])
    assert result['bias']==0 and result['n']==3
    assert latent.degradation_bias([np.nan],[np.nan])['bias'] is None
