"""One-time, atomic upgrade of legacy AHI caches to per-scan orbital VZA."""
import numpy as np
from satpy import Scene
from pipeline.config import load_settings
from pipeline import himawari as hw

def update(window="current_2026"):
    cfg=load_settings(window=window)
    cache=cfg['paths']['window_interim']/'himawari'
    g=dict(np.load(cache/'geometry.npz'))
    scans,_=hw.discover(cfg)
    for i,(t,files) in enumerate(scans.items(),1):
        path=cache/t.strftime('%Y/%m/%d/%H%M.npz')
        frame=dict(np.load(path))
        if 'vza_deg' in frame:
            continue
        scene=Scene(reader='ahi_hsd',filenames=[str(f) for f in files if '_B07_' in f.name])
        scene.load(['B07'])
        orbit=scene['B07'].attrs['orbital_parameters']
        with np.errstate(invalid='ignore'):
            frame['vza_deg']=hw.view_zenith(g['longitude'],g['latitude'],orbit['satellite_actual_longitude'],orbit['satellite_actual_latitude'],orbit['satellite_actual_altitude']).astype(np.float32)
        tmp=path.with_suffix('.geometry.tmp.npz'); np.savez_compressed(tmp,**frame); tmp.replace(path)
        if i%12==0 or i==len(scans): print(f'Per-scan orbit geometry {i}/{len(scans)}',flush=True)


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--window",default="current_2026")
    update(parser.parse_args().window)
