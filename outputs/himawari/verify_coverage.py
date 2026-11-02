"""Reproduce segment coverage using projection parameters from a downloaded HSD."""
import bz2
import json
from pathlib import Path
import struct
import sys

import numpy as np
from pyproj import Proj
import yaml

root = Path(__file__).resolve().parents[2]
sample = next((root / 'data/raw/himawari/current_2026').rglob('*.DAT.bz2'))
data = bz2.decompress(sample.read_bytes())
endian = '<' if data[5] == 0 else '>'
offset = 0
blocks = {}
for _ in range(struct.unpack_from(endian+'H', data, 3)[0]):
    number, size = struct.unpack_from(endian+'BH', data, offset)
    blocks[number] = data[offset:offset+size]
    offset += size
lon, cfac, lfac, coff, loff, radius, req, rpol = struct.unpack_from(endian+'diiffddd', blocks[3], 3)
height = (radius-req)*1000
proj = Proj(proj='geos', lon_0=lon, h=height, a=req*1000, b=rpol*1000, sweep='y')
cfg = yaml.safe_load((root/'config/settings.yaml').read_text())
result = {'sample':str(sample.relative_to(root)), 'sub_lon':lon, 'LFAC':lfac,
          'LOFF':loff, 'segment_lines':550, 'method':'Dense 501x501 lon/lat grid per configured bbox; actual HSD geostationary projection, then global HSD line = LOFF - degrees(y/h)*LFAC/65536.', 'regions':{}}
for region in ['Bangladesh', 'Indo-Gangetic Plain', 'Punjab-Haryana']:
    west,south,east,north = cfg['overpasses']['pilot_boxes'][region]
    xx,yy = np.meshgrid(np.linspace(west,east,501), np.linspace(south,north,501))
    x,y = proj(xx,yy)
    line = loff-np.degrees(y/height)*lfac/65536
    col = coff+np.degrees(x/height)*cfac/65536
    valid = np.isfinite(line) & np.isfinite(col)
    segments = sorted(set(((np.floor(line[valid]-1)/550).astype(int)+1).tolist()))
    result['regions'][region] = {'bbox': [west,south,east,north], 'visible_fraction':float(valid.mean()),
        'line_range':[float(line[valid].min()),float(line[valid].max())],
        'segments':[f'S{s:02d}10' for s in segments]}
path = root/'outputs/himawari/coverage_verification.json'
path.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
