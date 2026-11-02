"""Stage 1A immutable yearly downloads and derived window extracts."""
from pathlib import Path
import hashlib,json
import pandas as pd
import requests
ROOT=Path(__file__).resolve().parent
out=ROOT/'outputs/stages';out.mkdir(parents=True,exist_ok=True)
full=ROOT/'data/raw/archive/2016_full';full.mkdir(parents=True,exist_ok=True)
extract=ROOT/'data/raw/archive/2016';extract.mkdir(parents=True,exist_ok=True)
report={'files':[],'errors':[]}
for sensor in ['modis','viirs-snpp']:
    for country in ['India','Bangladesh']:
        name=f'{sensor}_2016_{country}.csv';url=f'https://firms.modaps.eosdis.nasa.gov/data/country/{sensor}/2016/{name}'
        path=full/name;record={'url':url,'file':str(path)}
        try:
            if not path.exists():
                response=requests.get(url,timeout=(25,120));response.raise_for_status()
                if b'latitude' not in response.content[:1000].lower():raise ValueError('Not a FIRMS CSV response')
                tmp=path.with_suffix('.download.tmp');tmp.write_bytes(response.content);tmp.replace(path)
            frame=pd.read_csv(path,low_memory=False)
            record.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),yearly_rows=len(frame))
            dates=pd.to_datetime(frame.acq_date,errors='coerce')
            sub=frame[dates.between('2016-10-29','2016-11-02')&frame.longitude.between(73,92.7)&frame.latitude.between(20.5,32.5)]
            target=extract/name
            if target.exists():
                existing=pd.read_csv(target,low_memory=False)
                if not existing.equals(sub.reset_index(drop=True)):raise ValueError('Existing immutable extraction differs; not overwritten')
            else:
                tmp=target.with_suffix('.filter.tmp');sub.to_csv(tmp,index=False);tmp.replace(target)
            record.update(status='available',filtered_rows=len(sub),platform_counts=sub.satellite.astype(str).value_counts().to_dict(),filtered_file=str(target))
        except Exception as exc:
            record.update(status='failed',error=repr(exc));report['errors'].append({'url':url,'error':repr(exc)})
        report['files'].append(record);print(json.dumps(record),flush=True)
        (out/'stage1a_downloads.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
