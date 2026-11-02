# Phase 3c

Run `python run_phase3c.py --window current_2026` in the flameseek environment.
The runner checks each experiment independently. Missing inputs write an
`awaiting data` status and do not stop available experiments. It does not fetch
missing raw imagery or FIRMS files.

`phase3c` settings in `config/settings.yaml` hold the injection fractions,
near-nadir land box and scans, and Northern Australia box/segments. Fractions
are unitless: 0.00005 means 0.005% of a pixel. The Bangladesh injection reuses
the exact Phase 3b sites and HSD coefficients from
`outputs/himawari/positive_controls.json`, and reads copies of the original
calibrated tiles. It does not overwrite the Phase 3b audit or science data.

The F50 estimator reports an observed crossing or a descriptive interpolation
between bracketing tested powers, in log power. It refuses to extrapolate and
keeps a 50%-response plateau as an interval. The reported transition bracket
is grid resolution, not a confidence interval. Six contexts and MIR-only
blackbody injection do not establish regional sensor completeness.

Outputs:

- `outputs/phase3c_report.md`: experiment results and calibration comparison.
- `outputs/phase3c_status.json`: independent availability statuses.
- `outputs/himawari/detection_limit_phase3c.json` and `.csv`: all trials and summaries.
- `outputs/figures/detection_limit_synthetic.png`: observed fraction response.
- `outputs/phase3c_calibration_selection.json`: recommendations without changing active parameters.
- `outputs/phase3c_validation.json`: test and artifact audit.

The near-nadir and Northern Australia branches require their own complete
B07/B14/B15 segment groups. The regional branch reuses the verified preparation,
contextual detection, matching, diurnal bootstrap and transfer functions with
regional output isolation. Northern Australia is a method demonstration only;
no shape from it may adjust a South Asian event. Missing segments do not create
`params/diurnal_v2.json` or a transfer fit.

The 2016 branch requires FIRMS CSVs under `data/raw/archive/2016/`, then calls
the existing Phases 1–2. Synchronization uses median **absolute** Aqua–S-NPP time
difference <=20 min, with fits retaining the existing <=15-min pairing and
truncation rules. With absent inputs it does not make a drift plot or invent
pi_MODIS values. Historical observation opportunities still require appropriate
orbit inputs; the original Phase 2 assumptions remain applicable.

The Meteosat branch retains the Phase 3b ingest/observation-coverage gate. Missing
files mean awaiting data. Delivered ListProduct detections alone cannot supply
cloud-aware negative observations: native QualityProduct schema and geolocation
must be validated before South Asia fits can proceed.

Run pipeline tests with `python -m pytest tests -q -p no:cacheprovider` and a
new writable workspace `--basetemp` if the default temporary directory is denied.
Backend tests run from `backend/` in its own environment.
