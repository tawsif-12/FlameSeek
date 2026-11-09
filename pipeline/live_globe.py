"""Procedure Steps 1–4 for the live globe; no latent activity is invented."""
import json
import sys
from pathlib import Path

import pandas as pd

from pipeline import ingest, quality, footprints, events
from pipeline.config import load_settings


def harmonize(rows):
    cfg = load_settings()
    raw = []
    for i, r in enumerate(rows):
        t = pd.Timestamp(r['acq_datetime'])
        viirs = r['sensor'].startswith('viirs')
        c = float(r['confidence_pct'])
        raw.append(dict(instrument='VIIRS' if viirs else 'MODIS', satellite=r['satellite'],
                        latitude=r['lat'], longitude=r['lon'], acq_date=t.strftime('%Y-%m-%d'),
                        acq_time=t.hour * 100 + t.minute,
                        confidence=('h' if c >= 80 else 'n' if c >= 30 else 'l') if viirs else c,
                        frp=r.get('frp'), scan=r.get('scan_km'), track=r.get('track_km'),
                        bright_ti4=r.get('brightness_k'), brightness=r.get('brightness_k'),
                        bright_ti5=r.get('brightness_2_k'), bright_t31=r.get('brightness_2_k'),
                        daynight=r.get('daynight', ''), version=r.get('version', ''),
                        source_file=r.get('source', ''), source_row=i))
    metadata = dict(raw_hotspot_count=len(rows), method='FlameSeek procedure Steps 1–4',
                    status='Footprint-merged events; latent activity awaiting data',
                    pending=['Persistent-source history and Himawari transient checks',
                             'Common grid, sensor calibration, diurnal correction and Monte Carlo lambda'],
                    uncertainty='Pixel footprint union; fused confidence is not a calibrated fire probability')
    if not raw:
        return dict(hotspots=[], metadata={**metadata, 'filtered_hotspot_count': 0})
    det = ingest.standardize(pd.DataFrame(raw), cfg)
    q = quality.run(det, cfg, bbox=[-180, -90, 180, 90], quiet=True)
    metadata.update(filtered_hotspot_count=len(q['clean']), reason_counts=q['reason_counts'],
                    not_applied=q['not_applied'])
    if q['clean'].empty:
        return dict(hotspots=[], metadata=metadata)
    result = events.run(footprints.run(q['clean'], cfg), cfg)
    points = []
    # Pick representatives in one grouped pass instead of constructing and
    # sorting a separate DataFrame for every event.
    detections = result['detections']
    representative_indices = detections.groupby('fire_id', sort=False)['frp_mw'].idxmax()
    representatives = detections.loc[representative_indices].set_index('fire_id')['det_id'].to_dict()
    peak_power = result['overpasses'].groupby('fire_id')['frp_sum_mw'].max()
    for ev in result['events'].itertuples(index=False):
        idx = int(representatives[ev.fire_id])
        representative = rows[idx]
        power = peak_power.loc[ev.fire_id]
        points.append({**representative, 'lat': float(ev.centroid_lat), 'lon': float(ev.centroid_lon),
                       'acq_datetime': ev.end_time.isoformat(), 'frp': float(power),
                       'harmonized': dict(event_id=ev.fire_id, observations=int(ev.n_detections),
                                          platforms=ev.platforms_seen, confidence=float(ev.p_conf_fused),
                                          footprint_area_km2=float(ev.footprint_area_km2)),
                       'lookup_detection': {k: representative[k] for k in ('sensor', 'lat', 'lon', 'acq_datetime')}})
    metadata.update(events_total=len(points), clustering=result['stats'])
    return dict(hotspots=points, metadata=metadata)


if __name__ == '__main__':
    payload = harmonize(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    Path(sys.argv[2]).write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
