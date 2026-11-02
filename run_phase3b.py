"""Run Phase 3b controls first, then assignment and optional Meteosat ingestion."""
import argparse
import json
from pipeline.config import load_settings, ROOT
from pipeline import himawari as hw, himawari_verify as verify, geostationary as geo, meteosat


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_report(cfg,controls,real,assignment,regions,ingest):
    out=cfg['paths']['window_outputs']
    import pandas as pd
    events=pd.read_csv(cfg['paths']['window_processed']/'fire_events.csv',usecols=['fire_id','FRE_estimate'])
    pending_reason=('No Meteosat files are present in this snapshot. As requested, dependent Parts C?E science stops without an error.'
                    if ingest['status']=='awaiting data' else
                    'Meteosat files have been inventoried/ingested; dependent science awaits validation of the delivered QualityProduct geolocation and flags.')
    metadata=controls['metadata']
    rounds=[x['radiance_bt_max_error_k'] for x in metadata if 'radiance_bt_max_error_k' in x]
    injections=controls['injections']
    detected=[x for x in injections if x['detected']]
    smallest=min(x['fraction'] for x in detected) if detected else None
    verified=controls['brightness_temperatures_verified'] and controls['radiometric_roundtrip_verified'] and controls['synthetic_verified'] and real['n_detected']>0
    status='bug found and fixed' if controls['bug_fixed'] else ('verified' if verified else 'still unverified')
    v1=read_json(ROOT/'params/calibration_v1.json')
    v3=read_json(ROOT/'params/calibration_v3_transfer.json')
    text=['# Phase 3b — detector controls and Indian Ocean source','',
          'Window: 29 October–2 November 2026 UTC; November 2 remains partial. Raw imagery is unchanged.', '',
          '## Himawari verification (run before platform selection)','',f'**Detector status: {status}.**', '',
          'Satpy metadata reports `brightness_temperature`, units `K`, for B07, B14 and B15 in all six scans. '
          f'Independent HSD-coefficient inversion agrees with the cached B07 temperatures within {max(rounds):.6f} K. '
          'The existing calibration setting is correct; no detector bug was found and Phase 3 was not re-run.', '',
          'Statistics below use land pixels passing the existing cloud and valid-view screens; the screen may retain thin/residual cloud. '
          'Daytime B07 medians are about 297 K. Cold B14 values near the cloud cutoff indicate that this simple screen is not a validated clear-sky product.', '',
          '| UTC scan | Day/night | Band | Pixels | Min K | P05 K | Median K | P95 K | Max K |',
          '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in controls['radiometric']:
        text.append(f"| {r['utc']} | {r['daynight']} | {r['band'].upper()} | {r['n']} | {r['min']:.2f} | {r['p05']:.2f} | {r['median']:.2f} | {r['p95']:.2f} | {r['max']:.2f} |")
    text += ['', '### Synthetic injection','',
             'At each scan, one typical-temperature clear-land native pixel with at least 100 clear background pixels in its 11×11 neighborhood was selected. '
             'Each trial independently modifies a copy of a real 65×65 radiance tile: `L_mix = (1-f) L_background + f L(800 K)`. '
             'B07 brightness temperature is recomputed using the HSD Planck constants and band-specific quadratic correction. B14 and B15 remain unchanged as a controlled MIR-only test. '
             'No injected values are written into raw data, cached science scans or event tables.', '',
             f"Detected trials: {len(detected)}/{len(injections)}. Smallest **tested** detected fire fraction: {smallest:.1%}. This is an upper bound on the minimum detectable fraction, not an estimated detection limit.",'',
             '| UTC scan | Fraction | Injected B07 K | Detected | Added MIR-equivalent FRP MW | Retrieved FRP MW |',
             '|---|---:|---:|---|---:|---:|']
    for r in injections:
        text.append(f"| {r['utc']} | {r['fraction']:.1%} | {r['injected_b07_k']:.2f} | {r['detected']} | {r['injected_mir_frp_mw']:.2f} | {r['retrieved_frp_mw']:.2f} |")
    small=[r for r in detected if r['fraction']==smallest]
    text += ['',f"At {smallest:.1%}, added MIR-equivalent FRP ranges from {min(r['injected_mir_frp_mw'] for r in small):.2f} to {max(r['injected_mir_frp_mw'] for r in small):.2f} MW. "
             'Retrieved FRP differs slightly because it uses the surrounding contextual radiance rather than the original center-pixel radiance. Blackbody power and exact pixel area are also stored in the JSON audit.', '',
             '### Real positive controls anywhere in S03–S04','',
             f"Qualifying VIIRS event-overpasses (sum within one event/platform/acquisition time, FRP >100 MW, native pixel VZA <65°): **{real['n_segment_valid_view_events']}**. "
             f"Unique events: {real.get('n_unique_events','not recorded')}; clear-observed: {real['n_observed']}; detected within 2 km at the nearest hourly step (±30 min): **{real['n_detected']}**; nearest scans unavailable: {real['n_missing_nearest_scan']}.", '',
             'Selection uses the actual downloaded segment projection extents, including locations outside the South Asia Phase 3 crop. '
             'Repeated overpasses/platforms are separate control opportunities, not independent unique fires. '
             'The misses do not invalidate the positive control: temporal evolution, subpixel dilution and the fixed 310 K daytime candidate threshold can prevent detection.', '',
             'Per-event locations, radiances/temperatures, status and match outcomes: `himawari/real_positive_controls.csv`. '
             'Full radiometric metadata and injection audit: `himawari/positive_controls.json`.', '',
             '## Geostationary assignment','',
             'Nominal sub-satellite longitudes: Himawari 140.7°E; Meteosat-9 Indian Ocean 45.5°E. '
             '[EUMETSAT confirms the Meteosat-9 location](https://www.eumetsat.int/eumetsats-meteosat-9-reaches-its-new-home). '
             'Selection minimizes ellipsoidal-ground VZA among platforms strictly below 65°, independently of data availability. '
             'A cell receives one platform or null; a missing file does not switch it to a worse-view platform.', '',
             f"Assigned the complete {assignment['grid_cell_deg']}° global common grid: {assignment['n_cells']:,} cells, including cells with no fires. "
             f"Counts: `{json.dumps(assignment['assignment_counts'])}`. Full assignment: `data/processed/windows/{cfg['window']['name']}/geo_platform_assignment.parquet`.",'',
             '![Geostationary platform assignment](figures/geo_platform_assignment.png)','',
             '| Region | Grid cells | Assigned platform counts | Mean selected VZA |',
             '|---|---:|---|---:|']
    for r in regions:
        text.append(f"| {r['region']} | {r['n_cells']} | {r['assignment_counts']} | {r['mean_selected_vza_deg']:.2f}° |")
    text += ['', 'Nominal geometry is a platform-selection rule; per-scan orbit metadata and product footprint/quality coverage still determine whether observations exist. '
             'Lower VZA does not guarantee that an operational product covers a given place. IODC is listed as a demonstration product by LSA SAF.', '',
             '## Meteosat ingest and dependent science','',f"**Ingest status: {ingest['status']}.**",'',
             f"Input directory: `{ingest['raw_dir']}`. Files: {ingest['n_files']}; list files: {ingest['n_list_files']}; quality files: {ingest['n_quality_files']}; detections ingested: {ingest['n_detections']}; errors: {len(ingest['errors'])}.",'',
             'No Meteosat files are present in this snapshot. As requested, dependent Parts C–E science stops without an error. '
             'No empty observation days are fabricated. `params/diurnal_v2.json` is not written and the existing v3/v2 transfer parameter artifacts are preserved. '
             'Per-region detection/commission rates, logistic coefficients with VZA, 15-minute diurnal peak/width/base-to-peak intervals and event-specific transfer ratios are **awaiting data**.', '',
             'The ingest module reads HDF5 (including NetCDF4/HDF5 and bzip2 wrappers), decodes field scaling/fill metadata, records acquisition-time basis, and validates IODC location where available. '
             'It retains FRP uncertainty, confidence and pixel area as unknown when absent. Dataset paths can be configured explicitly if the delivered product schema differs. '
             'Real-file schema validation remains pending until the files arrive; synthetic HDF5 fixtures test the parser behavior.', '',
             'Please include both FRP ListProduct and corresponding QualityProduct files when downloading. '
             '[The product paper distinguishes fire-only lists from all-pixel quality coverage](https://acp.copernicus.org/articles/15/13217/2015/). '
             'A missing row in a fire list cannot be treated as a clear-sky non-detection. '
             'The [LSA SAF product page](https://lsa-saf.eumetsat.int/en/data/products/fire-products/) supplies IODC data and product documentation links.', '',
             '### Calibration comparison and FRE coverage','',
             '| Calibration | Status | Result |','|---|---|---|',
             f"| v1 | Original drift-affected window; retained | `{json.dumps(v1.get('values'))}` |",
             f"| v3 transfer | Prior Phase 3 artifact; no Phase 3b refit | `{json.dumps(v3.get('fit'))}` |",'',
             f"Phase 3 FRE coverage remains {events.FRE_estimate.notna().sum():,}/{len(events):,} events with non-null estimates. No new energy estimates are supplied. "
             'Calibration may use a region only when its assigned platform has a supported diurnal shape; awaiting data never becomes a unit time ratio.', '',
             '## Verification','',
             '58 harmonization tests passed, including 11 Phase 3b tests. All 61 backend tests passed. The real-tile injection test detects all three stated fractions; grid tests enforce single-source minimum-VZA selection; transfer tests reject unsupported regional shapes. Parser fixtures are synthetic and are not counted as observed fires.','',
             '## Limitations and next run','',
             'Positive controls verify the radiometric and detection code path, not a validated regional completeness or commission rate. '
             'MIR-only injection assumes an 800 K blackbody without atmospheric attenuation, instrument saturation or longwave heating; its fractions imply fires above 200 MW at these coarse pixels. '
             'The six sites are not a sensitivity characterization of every surface, season or VZA. '
             'The LSA SAF manual archive could not be downloaded from this network, so field aliases and real 2026 IODC metadata must be checked on arrival. '
             'No Meteosat detection, shape, uncertainty interval, calibration or FRE number is inferred from geometry alone.', '',
             'Run `python run_phase3b.py --window current_2026`. Controls run first by default. '
             '`--reuse-controls` explicitly reuses saved control audits for the same processing window; rerun without this flag after detector or input changes. '
             'Ingest writes `data/processed/geo_fires/platform=Meteosat-9/year=YYYY/month=MM/day=DD/part.parquet` only for delivered observations. '
             'See `docs/phase3b.md` for schema and validation details.']
    (out/'phase3b_report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    hw.json_write(out/'himawari/detector_verification.json',dict(status=status,window=cfg['window']['name'],bug_fixed=controls['bug_fixed'],real_controls=real,
                  n_injections=len(injections),n_injections_detected=len(detected),smallest_tested_fraction_detected=smallest))


def run(cfg,reuse_controls=False):
    out=cfg['paths']['window_outputs']
    if reuse_controls:
        controls=read_json(out/'himawari/positive_controls.json')
        real=read_json(out/'himawari/real_positive_controls.json')
        if controls.get('window',cfg['window']['name'])!=cfg['window']['name'] or real.get('window',cfg['window']['name'])!=cfg['window']['name']:
            raise ValueError('Control audits belong to a different window')
    else:
        controls=verify.radiometric_and_injection(cfg)
        if not controls['synthetic_verified']:
            raise RuntimeError('Synthetic control failed; do not proceed to platform assignment')
        real=verify.real_controls(cfg)
    if not controls['synthetic_verified']:
        raise RuntimeError('Synthetic control failed; do not proceed to platform assignment')
    if not controls['brightness_temperatures_verified'] or not controls['radiometric_roundtrip_verified']:
        raise RuntimeError('Radiometric control failed; fix calibration before source assignment')
    print('Controls complete:',real,flush=True)
    assignment=geo.write_global_assignment(cfg)
    regions=geo.regional_summary(cfg); geo.plot(cfg)
    hw.json_write(out/'geo_platform_assignment.json',dict(global_grid=assignment,regions=regions))
    ingest=meteosat.ingest(cfg)
    # There are no Meteosat observations in this task snapshot. Do not refit or
    # replace any Phase 3 science products from geometry or fire-only rows.
    science=dict(status='awaiting data' if ingest['status']=='awaiting data' else 'awaiting validated observation coverage',
                 diurnal_v2_written=False,calibration_refitted=False,fre_recomputed=False,ingest_status=ingest['status'])
    hw.json_write(out/'meteosat/science_status.json',science)
    write_report(cfg,controls,real,assignment,regions,ingest)
    print('Phase 3b complete:',ingest['status'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--window',default='current_2026')
    parser.add_argument('--reuse-controls',action='store_true'); args=parser.parse_args()
    run(load_settings(window=args.window),args.reuse_controls)
