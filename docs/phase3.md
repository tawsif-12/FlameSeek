# Phase 3: local hourly Himawari analysis

Use the `flameseek` environment documented in `environment.yml`:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' -m pipeline.himawari --window current_2026
& 'E:\anaconda\envs\flameseek\python.exe' run_phase3.py --window current_2026
```

Preparation is incremental and scans run sequentially. Each cached scan stores
its own VZA calculated from the HSD satellite orbital metadata, calibrated bands,
MIR radiance, and solar zenith angle. Pixel footprints and land masks share the
native projection grid. The one-time `update_phase3_geometry.py` utility migrates
older caches created before per-scan VZA was stored, without recalibrating bands.

The analysis writes masks for every available scan and day partitions for fires,
including empty days. It keeps transient suspects. Parameters and unavailable
results are explicit JSON artifacts; it does not supply a default diurnal shape.
`--report-only` regenerates the report and comparison figures from saved outputs.
The initial `diurnal_v1.json` is preserved as `diurnal_v1.pre_phase3.json`.

Results are in `outputs/phase3_report.md`. Tables and fit audits are under
`outputs/himawari/`. Figures are under `outputs/figures/`. The event table gains
`FRE_estimate` in MJ and an accompanying `FRE_status`; unsupported estimates are
null. The partial November 2 day is excluded from fitting.

Thresholds, training/test dates, cloud tests, SRF source, bootstrap size and
sensor-error assumptions are in `config/settings.yaml`, under `himawari` and
`calibration`. Physical derivation and deviations are in `docs/decisions.md`.
No tuning uses October 31 or November 1. Transfer pairing explicitly rejects
Terra and restricts corrections to regions with supported shapes.

Run the harmonization tests from the repository root, with a new writable
workspace temporary directory:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' -m pytest tests -q -p no:cacheprovider --basetemp '.test-tmp-phase3-check'
```

Backend tests use the backend environment, from `backend/`: `python -m pytest tests`.
