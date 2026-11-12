# Full live harmonization

The map publishes footprint-merged events first. A separate worker executes
Steps 5–10 without blocking the API or new merges. The sidebar reports all ten
stages. Partial, failed, and unavailable stages never become full harmonization.
Activity estimates are per grid cell and local solar day, not event centroids.

Artifacts: `.runlogs/live_harmonized/<run id>/full/`. Atomic `status.json`
reports progress, limitations and validation. Outputs include grid/overpasses,
matched pairs, calibration, sensitivity draws, FRP distributions, daily energy,
activity with intervals, and available calendar/anomaly tables.

## Evidence inputs

Copy `config/harmonization_evidence.example.json` to
`config/harmonization_evidence.json`, including only existing evidence files.
Relative paths resolve from the manifest. CSV and Parquet are supported.
Code, settings and evidence changes invalidate completed workflow results.
Do not set validation flags merely to make a stage green.

All dates are local solar dates (YYYY-MM-DD); cell IDs use `pipeline.grid`.

| Input | Required columns |
| --- | --- |
| opportunities (optional override) | cell_id, platform, overpass_time_utc, pixel_area_km2, scan_angle_deg, tle_epoch_utc, tle_source |
| temporal_models | cell_id, date, platform, base, peak, h, sigma, source, validated, tier, frp_draws, shape_draws |
| exposures | cell_id, date, platform, O, pi_draws, source, validated, coverage_complete, reference_population |
| history | cell_id, year, week, value, coverage_complete, reference_population, model_version |
| validation | cell_id, date, reference, source, independent, reference_population |

Without opportunity overrides, current cached TLEs are independently propagated
for observed cells. Epoch mismatch over 30 days is rejected. Detection-conditioned
looks do not establish clear misses. Clear-sky assumptions remain explicit.

Stage 6 fits Aqua/VIIRS event-overpass FRP, detection sensitivity and empirical/tail
power distributions. Global diagnostics are not silently transferred to other
biomes. Terra never inherits Aqua calibration. Physical sensitivity constraints
are checked separately from statistical convergence.

Temporal tiers: A measured geostationary shape, B validated transfer, C coarse
polar fit. `frp_draws` contains JSON `[a,b]` log10 FRP calibration draws;
`shape_draws` contains matching `[base,peak,h,sigma]` draws (at least 30).
Reference-platform identity coefficients must be explicit. Daily energy is
combined by inverse variance, never by summing power across time. Shared draw
indices preserve model covariance. Unavailable shapes remain unknown.

`O` is an independent opportunity count. `pi_draws` contains at least 30
applicable response/distribution-integral draws, with documented uncertainty
and cloud/coverage assumptions. Stage 8 calculates `sum(N)/sum(O*pi)` with
conditional Gamma-Poisson and sensitivity uncertainty. VIIRS-observable activity
is not automatically all physical fires. Unknown coverage is not zero activity.

Historical inputs must use comparable populations and one model version. Every
included cell needs 52 verified weeks per year. Missing weeks are never filled
with zero. Configured history thresholds gate seasonal calendars and anomalies.

Independent validation needs at least 30 comparable paired samples by default.
MAE/RMSE are reported separately from conservation and interval checks. Running
validation does not guarantee model accuracy. Existing four-day Northern
Australia shape fits are not automatically applicable worldwide.

## API / execution

* `GET /api/harmonization/<run id>/status`
* `GET /api/harmonization/<run id>/activity?offset=0&limit=1000`

In the geospatial Python environment:

```powershell
python -m pipeline.live_globe input.json merged.json run-artifacts
python -m pipeline.harmonization run-artifacts run-artifacts/full --evidence config/harmonization_evidence.json
```

This installation can finish the workflow with unavailable stages when evidence
is missing. Missing data must never be replaced with invented parameters or a
false validation pass.
