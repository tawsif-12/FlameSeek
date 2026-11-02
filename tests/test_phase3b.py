"""Positive controls and ingestion contracts, never populated with observed-science guesses."""
from copy import deepcopy
import bz2
import json
import numpy as np
import pandas as pd
import pytest
from pipeline.config import load_settings, ROOT
from pipeline import geostationary as geo, meteosat, himawari as hw, himawari_verify as verify, transfer


@pytest.fixture
def cfg():
    return load_settings(window='current_2026')


@pytest.fixture
def coefficients():
    # Real H09 B07 HSD header from the control window, not approximate central wavelength alone.
    return dict(wavelength_m=3.8289e-6,c=2.99792458e8,h=6.62606957e-34,k=1.3806488e-23,
                c0=-.4627945,c1=1.00143264,c2=-9.01426429e-7)


def test_injected_hot_source_detected_at_stated_fraction_on_real_tile(cfg,coefficients):
    cache=cfg['paths']['window_interim']/'himawari'
    path=cache/'2026/10/29/0700.npz'
    if not path.exists(): pytest.skip('Local real AHI control tile unavailable')
    frame=dict(np.load(path)); geom=dict(np.load(cache/'geometry.npz')); geom['vza_deg']=frame['vza_deg']
    point=(92.23277022341338,25.78901297389449)
    distance=(geom['longitude']-point[0])**2+(geom['latitude']-point[1])**2
    row,col=np.unravel_index(np.nanargmin(distance),distance.shape)
    crop=(slice(row-32,row+33),slice(col-32,col+33))
    tile={k:frame[k][crop].copy() for k in ['b07','b14','b15','radiance','sza_deg']}
    geometry={k:v[crop].copy() for k,v in geom.items()}
    constant=json.loads((cfg['paths']['window_outputs']/'himawari/mir_constant.json').read_text())
    before=tile['radiance'].copy()
    for fraction in [.001,.005,.01]:
        trial=verify.inject(tile,32,32,fraction,800.,coefficients)
        result=hw.contextual(trial,geometry,cfg['himawari'],constant)
        assert result['fire'][32,32]
        assert result['frp_mw'][32,32]>0
    np.testing.assert_array_equal(tile['radiance'],before)  # original image never changed


def test_hsd_radiance_temperature_inverse(coefficients):
    t=np.array([265.,285.,300.,320.,800.])
    np.testing.assert_allclose(verify.radiance_to_bt(verify.bt_to_radiance(t,coefficients),coefficients),t,atol=1e-8)


def test_assignment_is_single_minimum_vza(cfg):
    lo,la=np.meshgrid(np.linspace(-180,180,61),np.linspace(-89,89,41))
    chosen,minimum,angles=geo.assign(lo,la,cfg)
    names=list(cfg['geostationary']['platforms'])
    valid=minimum==minimum
    counts=np.stack([chosen==name for name in names]).sum(axis=0)
    assert np.all(counts<=1)
    assert np.all(counts[valid]==1)
    eligible=np.where(angles<65,angles,np.inf)
    np.testing.assert_allclose(minimum[valid],eligible.min(axis=-1)[valid])
    assert np.all(minimum[valid]<65)
    assert np.all(~np.isfinite(eligible.min(axis=-1)[~valid]))


def test_expected_regional_platforms(cfg):
    lo=np.array([75.6,86.5,90.4,116.4,139.7]); la=np.array([30.,26.,23.8,39.9,35.7])
    chosen,_,_=geo.assign(lo,la,cfg)
    assert chosen.tolist()==['Meteosat-9','Meteosat-9','Meteosat-9','Himawari','Himawari']


def test_unsupported_region_never_enters_calibration(cfg):
    times=pd.to_datetime(['2026-10-29T10:00Z','2026-10-29T07:30Z'])
    ov=pd.DataFrame(dict(fire_id=['event']*2,platform=['Aqua','S-NPP'],acq_datetime_utc=times,
                         lon=[90.,90.],lat=[24.,24.],frp_sum_mw=[100.,100.],daynight=['D','D']))
    models={'Bangladesh':dict(fitted=False,parameters=dict(base=.1,peak=1,h=14,sigma=2))}
    pairs=transfer.adjusted_pairs(ov,models,cfg)
    assert len(pairs)==1 and pairs.time_ratio.isna().all()
    assert not transfer.fit_adjusted(pairs,cfg)['fitted']


def make_list(path,longitude=45.5):
    import h5py
    with h5py.File(path,'w') as f:
        f.attrs['SUB_SATELLITE_POINT_START_LON']=longitude
        for key,values,scale,units in [('LATITUDE',[2400],100,'degrees_north'),('LONGITUDE',[9000],100,'degrees_east'),
                                     ('FRP',[10150],100,'MW'),('FRP_UNCERTAINTY',[1250],100,'MW'),
                                     ('CONFIDENCE',[8500],100,'%'),('PIXEL_AREA',[1600],100,'km2')]:
            ds=f.create_dataset(key,data=np.array(values,dtype='i4'))
            ds.attrs['SCALING_FACTOR']=scale; ds.attrs['OFFSET']=0.; ds.attrs['UNITS']=units
    return path


def test_native_hdf_decodes_fields_and_time(tmp_path,cfg):
    path=make_list(tmp_path/'HDF5_LSASAF_MSG-IODC_FRP_ListProduct_MSG-Disk_202610290715.h5')
    frame,audit=meteosat.read_file(path,cfg)
    r=frame.iloc[0]
    assert (r.latitude,r.longitude,r.frp_mw,r.frp_uncertainty_mw,r.confidence_pct,r.pixel_area_km2)==(24.,90.,101.5,12.5,85.,16.)
    assert r.acq_datetime_utc==pd.Timestamp('2026-10-29T07:15Z')
    assert audit['time_basis']=='file_scan_start' and audit['missing_fields']==[]


def test_cf_scale_fill_and_pixel_time(tmp_path,cfg):
    import h5py
    path=make_list(tmp_path/'control.h5')
    with h5py.File(path,'a') as f:
        ds=f['FRP']; del ds.attrs['SCALING_FACTOR']; ds.attrs['scale_factor']=.01
        ds=f.create_dataset('time',data=[26100.]); ds.attrs['units']='seconds since 2026-10-29 00:00:00'
        ds=f.create_dataset('fill_test',data=[-999,200]); ds.attrs['_FillValue']=-999; ds.attrs['scale_factor']=.01
        a=meteosat.decode(ds); assert np.isnan(a[0]) and a[1]==2.
    frame,audit=meteosat.read_file(path,cfg)
    assert frame.frp_mw.iloc[0]==101.5 and frame.acq_datetime_utc.iloc[0]==pd.Timestamp('2026-10-29T07:15Z')
    assert audit['time_basis']=='pixel_time'


def test_wrong_satellite_and_units_rejected(tmp_path,cfg):
    import h5py
    path=make_list(tmp_path/'ListProduct_202610290715.h5',longitude=0)
    with pytest.raises(ValueError,match='longitude'): meteosat.read_file(path,cfg)
    with h5py.File(path,'a') as f:
        f.attrs['SUB_SATELLITE_POINT_START_LON']=45.5; f['FRP'].attrs['UNITS']='W'
    with pytest.raises(ValueError,match='units'): meteosat.read_file(path,cfg)


def test_missing_optional_fields_are_unknown(tmp_path,cfg):
    import h5py
    path=make_list(tmp_path/'ListProduct_202610290715.h5')
    with h5py.File(path,'a') as f:
        del f['FRP_UNCERTAINTY']; del f['CONFIDENCE']; del f['PIXEL_AREA']
    frame,audit=meteosat.read_file(path,cfg)
    assert frame[['frp_uncertainty_mw','confidence_pct','pixel_area_km2']].isna().all().all()
    assert set(audit['missing_fields'])=={'frp_uncertainty_mw','confidence_pct','pixel_area_km2'}


def test_no_files_is_awaiting_data_without_partitions(tmp_path,cfg):
    cfg=deepcopy(cfg); cfg['geostationary']['meteosat']['raw_dir']=str(tmp_path/'raw')
    cfg['paths']['window_outputs']=tmp_path/'outputs'; cfg['paths']['partition_root']=tmp_path/'parts'
    status=meteosat.ingest(cfg)
    assert status['status']=='awaiting data' and status['errors']==[]
    assert not cfg['paths']['partition_root'].exists()


def test_day_partitions_and_bzip_wrapper(tmp_path,cfg):
    cfg=deepcopy(cfg); raw=tmp_path/'raw'/'current_2026'; raw.mkdir(parents=True)
    cfg['geostationary']['meteosat']['raw_dir']=str(tmp_path/'raw')
    cfg['paths']['window_outputs']=tmp_path/'outputs'; cfg['paths']['window_interim']=tmp_path/'interim'; cfg['paths']['partition_root']=tmp_path/'parts'
    path=make_list(raw/'HDF5_LSASAF_MSG-IODC_FRP_ListProduct_MSG-Disk_202610290715.h5')
    wrapped=raw/(path.name+'.bz2'); wrapped.write_bytes(bz2.compress(path.read_bytes()))
    make_list(raw/'HDF5_LSASAF_MSG-IODC_FRP_ListProduct_MSG-Disk_202610300715.h5')
    result=meteosat.ingest(cfg)
    assert result['status']=='ingested' and not result['errors'] and result['n_detections']==2
    parts=sorted((tmp_path/'parts'/'geo_fires'/'platform=Meteosat-9').glob('year=*/month=*/day=*/part.parquet'))
    assert len(parts)==2 and all(len(pd.read_parquet(p))==1 for p in parts)
