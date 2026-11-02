from pathlib import Path
import json
import numpy as np
from satpy import Scene
from pyproj import Transformer
base=Path('data/raw/himawari/current_2026/2026/10/29')
files=sorted(base.glob('*_0000_B07_*_S0[67]10.DAT.bz2'))
if len(files)!=2:raise RuntimeError('Waiting for first complete S06/S07 B07 pair')
s=Scene(reader='ahi_hsd',filenames=list(map(str,files)));s.load(['B07'])
areas=[h.get_area_def(None) for h in s._readers['ahi_hsd'].file_handlers['hsd_b07']]
tr=Transformer.from_crs(4326,areas[0].crs,always_xy=True)
result={}
for name,box in [('Northern_Australia',[125,-20,138,-11]),('near_nadir',[138,-5,145,-1])]:
    w,so,e,n=box;lo,la=np.meshgrid(np.linspace(w,e,101),np.linspace(so,n,101));x,y=tr.transform(lo,la)
    mask=np.zeros(lo.shape,bool)
    for a in areas:
        x0,y0,x1,y1=a.area_extent;mask|=(x>=x0)&(x<=x1)&(y>=y0)&(y<=y1)
    result[name]={'tested_points':mask.size,'covered_points':int(mask.sum()),'coverage_share':float(mask.mean()),'box':box}
print(json.dumps(result,indent=2));Path('outputs/stages/stage1b_coverage.json').write_text(json.dumps(result,indent=2))
