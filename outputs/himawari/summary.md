# Himawari download result

Environment: `E:\anaconda\envs\flameseek\python.exe`; s3fs 2026.9.0, PyYAML 6.0.3. `pip check` passed.

Window: 2026-10-29 through 2026-11-02 inclusive, UTC. Full run uses the supplied hourly sampling (60 minutes).

- Dry run: 642/720 files, 1,636,674,135 bytes (1.637 GB).
- One-hour test: 2026-10-29 00:00?00:59 UTC, all six 10-minute scans; 36/36 files, 91,961,862 bytes. All integrity checks passed.
- Full run: all 642 available hourly files downloaded or reverified; zero download/access errors.
- Missing: 78 files across November 2, 11:00?23:00 UTC. These scans were in the future at the availability check. Every missing key is retained in `current_2026_download.json`.
- The full command returned exit code 1 to signal the missing files; it did not mark the configured window complete.
- Local inventory, including additional test scans: 672 unique files, 1,713,461,501 bytes; no partial files remain.

Bangladesh requires S0310 and S0410. The configured Indo-Gangetic Plain and Punjab-Haryana boxes require S0310. Verified from downloaded HSD projection metadata; see `coverage_verification.json` and `verify_coverage.py`.

NOAA public bucket paths and naming were checked directly. The 2016 Himawari-8 sample uses whole-disk S0101 files; a historical dry run verified 18/18 files, without downloading those files. Satellite handover was corrected to 2022-12-13 05:00 UTC.

File validation: S3 compressed size, single-part ETag/MD5, bzip2 decompression/CRC, HSD header/data lengths, dimensions and segment header. Per-file SHA-256 hashes are saved. Existing files are verified before reuse. Corrupted test copies were rejected.

Raw files: `data/raw/himawari/current_2026/YYYY/MM/DD/`. Reports and download log: `outputs/himawari/`. Usage and primary source links: `docs/himawari_download.md`.

Rerun the same command after November 2 UTC ends to fetch the unavailable hours:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' himawari_download.py --window current_2026
```
