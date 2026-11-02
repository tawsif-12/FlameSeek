"""LSA SAF IODC FRP-PIXEL list ingestion; missing observations stay unknown.

Raw files are never changed. HDF5/NetCDF4-HDF5 and bzip2-wrapped HDF5 are
supported. QualityProduct files are inventoried separately from fire lists.
"""
from contextlib import contextmanager
from pathlib import Path
import bz2
import hashlib
import io
import re
import numpy as np
import pandas as pd
from pipeline.config import ROOT
from pipeline import himawari as hw, partitions

FIELDS={
    'latitude':['LATITUDE','latitude','lat'],
    'longitude':['LONGITUDE','longitude','lon'],
    'frp_mw':['FRP','FRP_MW','frp'],
    'frp_uncertainty_mw':['FRP_UNCERTAINTY','FRP_UNCERTAINTY_MW','FRP_ERROR','frp_uncertainty'],
    'confidence_pct':['CONFIDENCE','FIRE_CONFIDENCE','FRP_CONFIDENCE','confidence'],
    'pixel_area_km2':['PIXEL_AREA','PIXEL_AREA_KM2','AREA','pixel_area'],
    'time':['TIME','time','acq_datetime_utc','SENSING_TIME'],
}


@contextmanager
def open_hdf(path):
    import h5py
    path=Path(path)
    if path.suffix.lower()=='.bz2':
        with bz2.open(path,'rb') as compressed:
            with io.BytesIO(compressed.read()) as buffer:
                with h5py.File(buffer,'r') as handle: yield handle
    else:
        with h5py.File(path,'r') as handle: yield handle


def scalar(value):
    a=np.asarray(value)
    v=a.reshape(-1)[0] if a.ndim else a.item()
    return v.decode('utf-8') if isinstance(v,bytes) else v


def decode(dataset):
    raw=np.asarray(dataset[...]).reshape(-1)
    if raw.dtype.kind not in 'iuf': return raw
    values=raw.astype(float)
    for key in ['_FillValue','missing_value','MISSING_VALUE','MISS_VALUE']:
        if key in dataset.attrs: values[raw==float(scalar(dataset.attrs[key]))]=np.nan
    if 'scale_factor' in dataset.attrs:
        values=values*float(scalar(dataset.attrs['scale_factor']))+float(scalar(dataset.attrs.get('add_offset',0)))
    elif 'SCALING_FACTOR' in dataset.attrs:
        factor=float(scalar(dataset.attrs['SCALING_FACTOR']))
        if not np.isfinite(factor) or factor==0: raise ValueError('Invalid LSA SAF scaling factor')
        values=values/factor+float(scalar(dataset.attrs.get('OFFSET',0)))
    elif 'OFFSET' in dataset.attrs and float(scalar(dataset.attrs['OFFSET']))!=0:
        raise ValueError('Offset without scaling convention; inspect product metadata')
    return values


def filename_time(path):
    matches=re.findall(r'(?<!\d)(20\d{10})(?!\d)',Path(path).name)
    if not matches: return None
    return pd.to_datetime(matches[-1],format='%Y%m%d%H%M',utc=True)


def select_dataset(handle, paths, aliases, override=None):
    if override:
        if override not in paths: raise ValueError(f'Configured dataset missing: {override}')
        return handle[override]
    for alias in aliases:
        matching=[p for p in paths if p.rsplit('/',1)[-1]==alias]
        if len(matching)>1: raise ValueError(f'Ambiguous dataset {alias}; configure field_overrides')
        if matching: return handle[matching[0]]
    return None


def numeric_field(dataset,n,field):
    if dataset is None: return np.full(n,np.nan)
    value=decode(dataset)
    if len(value)==1: value=np.repeat(value,n)
    if len(value)!=n: raise ValueError(f'{field} has {len(value)} values; expected {n}')
    if value.dtype.kind not in 'iuf': raise ValueError(f'{field} is not numeric')
    return value


def parse_time(dataset,n,nominal):
    if dataset is None:
        if nominal is None: raise ValueError('No acquisition time in file name or metadata')
        return pd.DatetimeIndex([nominal]*n),'file_scan_start'
    data=decode(dataset)
    if len(data)==1: data=np.repeat(data,n)
    if len(data)!=n: raise ValueError('Time coordinate length differs from fire list')
    if data.dtype.kind in 'SUO':
        return pd.to_datetime([scalar(x) for x in data],utc=True,errors='raise'),'pixel_time'
    units=str(scalar(dataset.attrs.get('units',dataset.attrs.get('UNITS',''))))
    match=re.fullmatch(r'(seconds|minutes|hours|days|s) since (.+)',units.strip(),flags=re.I)
    if not match: raise ValueError(f'Ambiguous numeric time units: {units!r}')
    unit={'seconds':'s','s':'s','minutes':'m','hours':'h','days':'D'}[match.group(1).lower()]
    origin=pd.Timestamp(match.group(2)); origin=origin.tz_localize('UTC') if origin.tz is None else origin.tz_convert('UTC')
    return pd.DatetimeIndex(origin+pd.to_timedelta(data,unit=unit)),'pixel_time'


def read_file(path,cfg):
    settings=cfg['geostationary']['meteosat']; platform=settings['platform']; path=Path(path)
    with open_hdf(path) as handle:
        import h5py
        paths=[]
        handle.visititems(lambda name,obj: paths.append(name) if isinstance(obj,h5py.Dataset) else None)
        found={field:select_dataset(handle,paths,aliases,settings.get('field_overrides',{}).get(field)) for field,aliases in FIELDS.items()}
        for required in ['latitude','longitude','frp_mw']:
            if found[required] is None: raise ValueError(f'Missing {required}; datasets: {paths}')
        n=np.asarray(found['frp_mw'][...]).size
        out=pd.DataFrame({k:numeric_field(ds,n,k) for k,ds in found.items() if k!='time'})
        nominal=filename_time(path)
        if nominal is None and 'SENSING_START_TIME' in handle.attrs:
            nominal=pd.to_datetime(scalar(handle.attrs['SENSING_START_TIME']),utc=True)
        times,basis=parse_time(found['time'],n,nominal)
        out['acq_datetime_utc']=times
        expected=cfg['geostationary']['platforms'][platform]['sub_lon_deg']
        longitude_metadata=None
        for key in ['SUB_SATELLITE_POINT_START_LON','SUB_SATELLITE_LONGITUDE','sub_satellite_longitude']:
            if key in handle.attrs:
                longitude_metadata=float(scalar(handle.attrs[key])); break
        if longitude_metadata is not None and abs(longitude_metadata-expected)>.5:
            raise ValueError(f'Platform longitude {longitude_metadata} does not match {platform} at {expected}')
        if longitude_metadata is None and not re.search(r'IODC',path.name,re.I):
            raise ValueError('Cannot verify Indian Ocean platform: need IODC filename or sub-satellite longitude metadata')
        missing=[k for k,ds in found.items() if ds is None and k!='time']
        # Numeric units must agree with the canonical schema; do not silently mix W and MW.
        expected_units={'frp_mw':{'MW','megawatt','megawatts'},'frp_uncertainty_mw':{'MW','megawatt','megawatts'},
                        'pixel_area_km2':{'km2','km^2','km**2','km²'},'confidence_pct':{'%','percent','percentage'}}
        for key,allowed in expected_units.items():
            ds=found[key]
            if ds is not None:
                units=str(scalar(ds.attrs.get('units',ds.attrs.get('UNITS','')))).strip()
                if units and units not in allowed: raise ValueError(f'Unsupported units for {key}: {units}')
        meta=dict(path=str(path),n_records=n,missing_fields=missing,time_basis=basis,
                  longitude_metadata=longitude_metadata,dataset_paths={k:ds.name if ds is not None else None for k,ds in found.items()},
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if not (out.latitude.between(-90,90)&out.longitude.between(-180,180)&out.frp_mw.ge(0)).all():
        raise ValueError('Invalid fire coordinates or FRP; inspect packed values and missing-value metadata')
    if not (out.frp_uncertainty_mw.isna()|out.frp_uncertainty_mw.ge(0)).all(): raise ValueError('Negative FRP uncertainty')
    if not (out.confidence_pct.isna()|out.confidence_pct.between(0,100)).all(): raise ValueError('Confidence outside [0,100]')
    if not (out.pixel_area_km2.isna()|out.pixel_area_km2.gt(0)).all(): raise ValueError('Invalid pixel area')
    out['platform']=platform; out['sensor']='SEVIRI'; out['time_basis']=basis; out['source_file']=str(path)
    out['vza_deg']=hw.view_zenith(out.longitude.values,out.latitude.values,expected)
    out['outside_valid_view']=out.vza_deg>=cfg['geostationary']['max_vza_deg']
    out['lst_h']=[hw.lst(t,lo) for t,lo in zip(out.acq_datetime_utc,out.longitude)]
    return out,meta


def discover(cfg):
    settings=cfg['geostationary']['meteosat']
    base=ROOT/settings['raw_dir']/cfg['window']['name']
    candidates=sorted({p for pattern in settings['file_globs'] for p in base.rglob(pattern)}) if base.exists() else []
    # EUMETCast may distribute extensionless HDF5 files.
    candidates=sorted(set(candidates)|{p for p in base.rglob('*') if p.is_file() and p.name.startswith(('HDF5_','S-LSA_'))}) if base.exists() else []
    files=[]
    for p in candidates:
        t=filename_time(p)
        if t is None or cfg['window']['start']<=t.date()<=cfg['window']['end']: files.append(p)
    return base,files


def ingest(cfg):
    base,files=discover(cfg)
    output=cfg['paths']['window_outputs']/'meteosat'; output.mkdir(parents=True,exist_ok=True)
    status=dict(window=cfg['window']['name'],platform=cfg['geostationary']['meteosat']['platform'],raw_dir=str(base),
                status='awaiting data',n_files=len(files),n_list_files=0,n_quality_files=0,n_detections=0,errors=[],days=[])
    if not files:
        status['reason']='No FRP-PIXEL files present; Parts C–E dependent science is not run'
        hw.json_write(output/'ingest_status.json',status)
        return status
    quality=[p for p in files if 'quality' in p.name.lower()]
    lists=[p for p in files if p not in quality]
    status['n_list_files']=len(lists); status['n_quality_files']=len(quality)
    audit=[]; by_day={}
    # Parse once per input file; disk-backed staging keeps the ingestion day partitioned.
    stage=cfg['paths']['window_interim']/'meteosat_ingest'; stage.mkdir(parents=True,exist_ok=True)
    for index,path in enumerate(lists):
        try:
            frame,meta=read_file(path,cfg); audit.append(meta)
            frame=frame[frame.acq_datetime_utc.dt.date.between(cfg['window']['start'],cfg['window']['end'])]
            groups=list(frame.groupby(frame.acq_datetime_utc.dt.date))
            if frame.empty:
                nominal=filename_time(path)
                if nominal is not None and cfg['window']['start']<=nominal.date()<=cfg['window']['end']:
                    groups=[(nominal.date(),frame)]
            for day,part in groups:
                target=stage/str(day); target.mkdir(parents=True,exist_ok=True)
                temporary=target/f'{index:06}.parquet'; part.to_parquet(temporary,index=False)
                by_day.setdefault(day,[]).append(temporary)
        except Exception as exc:
            status['errors'].append(dict(file=str(path),error=repr(exc)))
    root=cfg['paths']['partition_root']/'geo_fires'
    platform=cfg['geostationary']['meteosat']['platform']
    for day,paths in sorted(by_day.items()):
        frame=pd.concat([pd.read_parquet(p) for p in paths],ignore_index=True)
        frame=frame.drop_duplicates(['platform','acq_datetime_utc','latitude','longitude'])
        partitions.write(frame,root,'platform='+platform,day)
        status['days'].append(dict(day=str(day),n_detections=len(frame))); status['n_detections']+=len(frame)
    status['status']='ingest_error' if status['errors'] else ('ingested' if lists else 'awaiting list data')
    status['science_status']='requires quality coverage validation' if quality else 'awaiting QualityProduct observation masks'
    status['quality_files']=[str(p) for p in quality]
    status['file_audit']=audit
    hw.json_write(output/'ingest_status.json',status)
    return status
