"""Phase 3c: run only experiments whose source data are present."""
import argparse
import json
import numpy as np
from pipeline.config import load_settings,ROOT
from pipeline import detection_limit as dl,phase3c,himawari as hw,meteosat


def read_optional(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def calibration_row(label,path,pending,domain):
    doc=read_optional(path)
    if doc is None:
        return dict(version=label,sample_size=None,a=None,b=None,a_interval=None,b_interval=None,
                    status='awaiting data',fitted=False,domain=domain,reason=pending,path=str(path))
    fit=doc.get('fit')
    if fit is None:
        fit={**(doc.get('values') or {}),'n':doc.get('sample_size'),'fitted':doc.get('values') is not None}
    intervals=doc.get('intervals') or {}
    return dict(version=label,sample_size=fit.get('n',doc.get('sample_size')),a=fit.get('a'),b=fit.get('b'),
                a_interval=fit.get('a_ci',intervals.get('a_90')),b_interval=fit.get('b_ci',intervals.get('b_90')),
                status=('drift-affected source; '+doc['status']) if label=='v1' else doc['status'],
                fitted=bool(fit.get('fitted',False)),domain=domain,reason=fit.get('reason',pending if not fit.get('fitted') else None),path=str(path))


def calibration_table(cfg):
    return [calibration_row('v1',ROOT/'params/calibration_v1.json','', '2026 drifted timing; original diagnostic benchmark'),
            calibration_row('v2 sync 2016',ROOT/'params/calibration_v2_sync2016.json','2016 FIRMS archive absent','Synchronized window/era after the D68 gate (2016, India + Bangladesh)'),
            calibration_row('v2 sync 2014',ROOT/'params/calibration_v2_sync2014.json','awaiting data: 2014 FIRMS files absent','Synchronized window/era after the D68 gate (2014, India + Bangladesh)'),
            calibration_row('v3 transfer N. Australia',ROOT/'params/calibration_v3_transfer_naus.json','Northern Australia S06/S07 absent','Northern Australia only; method demonstration region'),
            calibration_row('v3 transfer South Asia',ROOT/'params/calibration_v3_transfer.json','Meteosat observations and supported shapes absent','South Asia only after regional Meteosat validation')]


def recommendations(rows):
    by_name={r['version']:r for r in rows}
    result=[]
    for era,region,name in [('synchronized / pre-drift','Regions represented and validated in sync_2016','v2 sync 2016'),
                            ('drifted 2026','Northern Australia','v3 transfer N. Australia'),
                            ('drifted 2026','South Asia','v3 transfer South Asia')]:
        row=by_name[name]
        eligible=row['fitted'] and (name!='v2 sync 2016' or row['status']=='validated – synchronized window')
        result.append(dict(era=era,region=region,preferred_version=name,currently_usable=name if eligible else None,
                           reason='Conditional on represented region/biome, source shape and validation; no universal cross-era transfer' if eligible else 'awaiting data / supported calibration',
                           apply_to_south_asia=False if name=='v3 transfer N. Australia' else None))
    return result


def plot_injections(cfg,result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,name in zip(axes,['Bangladesh','near_nadir']):
        data=result[name]; summary=data.get('summary',[])
        if summary:
            x=np.array([r['frp_median_mw'] for r in summary]); y=[r['detection_rate'] for r in summary]
            ax.plot(x,y,'o-',label='six real-background contexts' if name=='Bangladesh' else 'three real-background contexts')
            ax.errorbar(x,y,xerr=[x-np.array([r['frp_min_mw'] for r in summary]),np.array([r['frp_max_mw'] for r in summary])-x],fmt='none',capsize=3)
            if data['f50']['frp50_mw'] is not None:
                ax.plot(data['f50']['frp50_mw'],.5,'x',ms=10,label='interpolated 50%')
            ax.set_xscale('log'); ax.legend(fontsize=8)
        else:
            ax.text(.5,.5,'Awaiting data\nNear-nadir segment S0610 absent',ha='center',transform=ax.transAxes)
        ax.set(ylim=(-.05,1.05),xlabel='Added MIR-equivalent FRP (MW)',ylabel='Detected fraction of contexts',title=name.replace('_',' '))
        if summary: ax.axhline(.5,ls=':',color='gray')
        else: ax.set_axis_off()
    fig.suptitle('Detection limit from synthetic injection — 800 K source')
    fig.tight_layout(); path=cfg['paths']['figures_dir']/'detection_limit_synthetic.png'; path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=150,bbox_inches='tight'); plt.close(fig)


def report(cfg,injections,naus,sync,met,rows,selection):
    out=cfg['paths']['window_outputs']
    lines=['# Phase 3c — available-data science', '',
           'Current window: 29 October–2 November 2026 UTC; final day partial. Synchronized comparison: 29 October–2 November 2016. Raw inputs are immutable.', '',
           '## Synthetic detection limits','',
           '800 K MIR-only injections on independent copies of real native clear-land tiles. Bangladesh uses the six original Phase 3b sites; near-nadir uses the configured three scans where a suitable clear background exists. No thresholds were tuned.', '',
           '| Region | Fraction | Detected / trials | Rate | Median added FRP MW | Added FRP range MW |','|---|---:|---:|---:|---:|---|']
    for name,data in injections.items():
        for r in data.get('summary',[]):
            lines.append(f"| {name} | {r['fraction_percent']:.3g}% | {r['detected']}/{r['n']} | {r['detection_rate']:.1%} | {r['frp_median_mw']:.2f} | {r['frp_min_mw']:.2f}–{r['frp_max_mw']:.2f} |")
        fit=data.get('f50',{})
        lines += ['',f"**{name}: {data['status']}; detection limit from synthetic injection:** F50 = {fit.get('frp50_mw')} MW; tested transition bracket = {fit.get('bracket_mw')} MW. {fit.get('reason','')}"]
        if data.get('missing_scans'): lines.append(f"Unavailable contexts: {data['missing_scans']}")
    lines += ['', 'F50 is descriptive interpolation on log median added power, not a validated logistic sensitivity fit. Its bracket is tested-grid resolution, not a confidence interval. Only six Bangladesh and up to three near-nadir contexts are used. Atmosphere, reflection and instrument saturation are not modeled; longwave bands remain unchanged.', '',
              '![Synthetic detection limits](figures/detection_limit_synthetic.png)', '',
              'Full trials: `himawari/detection_limit_phase3c.json` and `.csv`.', '',
              '## Northern Australia — method demonstration only','',f"Status: **{naus['status']}**. Box: 125–138°E, 11–20°S. No Australian shape is transferred to South Asia."]
    if naus['status']=='completed':
        model=naus['model']
        lines += ['',f"Scans: {naus['n_steps']}; fire pixels over time: {naus['n_fires']}; detection rate vs clear-observed VIIRS events: {naus['detection_rate']}; commission within 2 km / 60 min: {naus['commission_rate']}.",
                  f"Himawari logistic curve with VZA: `{json.dumps(naus['detection_fit'])}`.",
                  f"Tier {model['tier']}; diurnal fitted: {model['fitted']}; full days: {model.get('n_days')}; fitting points: {model['sample_size']}; status: {model['status']}.",
                  f"Peak/width/base/peak parameters: `{model.get('parameters')}`; day-bootstrap 90% intervals: `{model.get('intervals')}`.",
                  f"FRP transfer fit: `{json.dumps(naus['calibration'])}`; events with FRE: {naus['n_fre_events']}.",
                  'Files: `params/diurnal_v2.json`, `params/calibration_v3_transfer_naus.json`; event FRE in `phase3c_naus/fire_events_fre.csv`.', '',
                  '![Australian diurnal fit](figures/diurnal_curve_Northern_Australia.png)', '',
                  '![Australian transfer comparison](figures/calibration_v1_vs_v3_naus.png)']
    else: lines += ['',f"Awaiting data / reason: {naus.get('reason',naus.get('errors'))}"]
    lines += ['', '## Synchronized 2016 window','',f"Status: **{sync['status']}**."]
    if sync['status']=='completed':
        lines += ['',f"Clean detections: {sync.get('n_detections')}; measured Aqua–S-NPP timing: `{json.dumps(sync['timing'])}`.",
                  f"FRP fit (15-min pairs, truncation, Deming error ratio 1, OLS/ODR comparison, bootstrap): `{json.dumps(sync.get('calibration'))}`.",
                  f"MODIS detection curve / nadir F50 / area coverage: `{json.dumps(sync.get('detection_curve'))}`.",
                  f"π_MODIS, empirical IGP/all: `{sync.get('pi_modis')}`.",
                  f"Observation opportunities: {sync.get('observation_opportunities','available')}", '',
                  '| Year | Platform | Daytime observations | Median LST h |','|---|---|---:|---:|']
        for r in sync.get('drift',[]): lines.append(f"| {r['year']} | {r['platform']} | {r['n']} | {r['median_lst_h']:.3f} |")
        lines += ['', '![Measured 2016–2026 drift](figures/drift_2016_vs_2026.png)', '',
                  'A 2026 TLE propagated ten years backward is never used as 2016 coverage. Without archived 2016 TLEs, opportunities are rebuilt from the detections themselves and labelled "detection-conditioned opportunities – lower bound on O_s" (D69). Synchronization eligibility is the D68 gate: median daytime Aqua local solar time within 30 min of 13:30 AND at least 100 Aqua–S-NPP pairs with |Δt| ≤ 15 min after truncation. The FRP calibration uses directly measured acquisition times and does not require orbit extrapolation.']
    else: lines += ['',sync.get('reason','awaiting data')]
    lines += ['', '## Meteosat South Asia','',f"**{met['status']}**; {met['n_files']} files; {len(met['errors'])} ingest errors. ListProduct and validated QualityProduct coverage are required. No account or login was used.", '',
              '## Calibration versions and applicability','',
              '`log10 FRP_VIIRS = a + b log10 FRP_Aqua`; transfer versions use VIIRS FRP adjusted to Aqua time. Coefficient intervals are 90%.', '',
              '| Version | n | a | b | a interval | b interval | Status | Region / era |','|---|---:|---:|---:|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['version']} | {r['sample_size']} | {r['a']} | {r['b']} | {r['a_interval']} | {r['b_interval']} | {r['status']} | {r['domain']} |")
    lines += ['', 'Unavailable coefficients are not zeros. v1 is a drift-affected diagnostic benchmark. A synchronized fit applies only where its sample and validation support it; Australian transfer applies only to its demonstration region. South Asia requires its own supported Meteosat shape.', '',
              '| Era / region | Preferred | Currently usable |','|---|---|---|']
    for r in selection: lines.append(f"| {r['era']} / {r['region']} | {r['preferred_version']} | {r['currently_usable'] or 'awaiting applicable fit'} |")
    lines += ['', 'Active selection is recorded separately in config and `docs/decisions.md` after eligibility and fit checks. A fitted FRP regression does not itself validate a detection curve or observation opportunities.', '',
              '## Reproduction','', '`python run_phase3c.py --window current_2026`. Detailed part states: `phase3c_status.json`. The Stage 1 download inventory documents added raw files. No existing raw file is changed.']
    validation=read_optional(out/'phase3c_validation.json')
    if validation: lines += ['',f"Previously recorded regression checks: {validation.get('harmonization_tests_passed')} pipeline; {validation.get('backend_tests_passed')} backend. Current-stage checks are recorded in outputs/status_report.md."]
    (out/'phase3c_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def run(cfg):
    out=cfg['paths']['window_outputs']
    injections=dict(Bangladesh=dl.bangladesh(cfg),near_nadir=dl.near_nadir(cfg))
    hw.json_write(out/'himawari/detection_limit_phase3c.json',injections)
    import pandas as pd
    pd.DataFrame([r for d in injections.values() for r in d.get('trials',[])]).to_csv(out/'himawari/detection_limit_phase3c.csv',index=False)
    plot_injections(cfg,injections)
    naus=phase3c.northern_australia(cfg)
    sync=phase3c.synchronized_2016(cfg)
    met=meteosat.ingest(cfg)
    rows=calibration_table(cfg); selection=recommendations(rows)
    hw.json_write(out/'phase3c_status.json',dict(part_a_bangladesh=injections['Bangladesh']['status'],part_a_near_nadir=injections['near_nadir']['status'],
                  part_b=naus,part_c=sync,part_d=met))
    hw.json_write(out/'phase3c_calibration_selection.json',dict(calibrations=rows,recommendations=selection,active_parameters_changed=False))
    report(cfg,injections,naus,sync,met,rows,selection)
    print('Phase 3c complete:',{k:v['status'] for k,v in injections.items()},naus['status'],sync['status'],met['status'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--window',default='current_2026')
    run(load_settings(window=parser.parse_args().window))
