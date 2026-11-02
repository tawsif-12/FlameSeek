# FlameSeek Himawari download

Use the existing environment from VS Code:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' himawari_download.py --window current_2026 --dry-run
& 'E:\anaconda\envs\flameseek\python.exe' himawari_download.py --window current_2026 --test-hour 2026-10-29T00
& 'E:\anaconda\envs\flameseek\python.exe' himawari_download.py --window current_2026
```

The configured window is inclusive, in UTC. The full command preserves the
supplied script's hourly sampling (`--every 60`). For all 10-minute observations,
explicitly use `--every 10`. The test-hour option always checks all six scans.

Raw files stay compressed under
`data/raw/himawari/<window>/YYYY/MM/DD/`. Reports, hashes, missing file keys,
errors and the full download log are saved under `outputs/himawari/`.

Downloads use anonymous S3 access, bounded retries and `.part` files. Each file
must pass compressed size, single-part S3 ETag/MD5 (where available), bzip2
decompression/CRC, HSD length, image dimension and segment header checks before
the partial file is renamed. SHA-256 hashes are recorded. Existing files are
verified before reuse. Multipart S3 ETags are not treated as MD5 checksums.

Missing files and access errors are retained individually in JSON. The process
returns exit code 1 if any are present, including future dates in a window.
Available files are still downloaded. It never manufactures substitute data.

## Verified sources and naming

- [AWS public dataset registry](https://registry.opendata.aws/noaa-himawari/)
  identifies `noaa-himawari8` and `noaa-himawari9` in `us-east-1`, with no account
  required.
- [JMA HSD format guide](https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/hsd_sample/HS_D_users_guide_en_v13.pdf)
  specifies filenames, projection metadata, bands and segment headers.
- [JMA handover notice](https://www.data.jma.go.jp/mscweb/en/oper/switchover.html)
  specifies 2022-12-13 05:00 UTC as the operational transition to Himawari-9.

Live NOAA listings confirm this current prefix and filename:

```text
s3://noaa-himawari9/AHI-L1b-FLDK/2026/10/29/0000/
HS_H09_20261029_0000_B07_FLDK_R20_S0310.DAT.bz2
```

The inspected 2016 archive instead stores whole-disk files:

```text
s3://noaa-himawari8/AHI-L1b-FLDK/2016/10/29/0000/
HS_H08_20161029_0000_B07_FLDK_R20_S0101.DAT.bz2
```

The downloader detects listed whole-disk files when selected split segments are
absent, reports the layout change, and downloads each band only once. This was
checked with a six-scan historical dry run (18 files); historical whole-disk
downloads were not requested or performed.

## Geographic coverage

`outputs/himawari/verify_coverage.py` reads projection parameters from an actual
downloaded HSD and projects a dense grid over each configured pilot box. It
requires the project's existing NumPy and pyproj packages. Reproduce with:

```powershell
& 'E:\anaconda\envs\flameseek\python.exe' outputs/himawari/verify_coverage.py
```

The 2 km full disk has 5,500 lines, split into ten 550-line segments.
The downloaded projection has sub-satellite longitude 140.7 degrees,
LFAC 20466275 and LOFF 2750.5. Results:

| Configured region | Full-disk line range | Required segments |
| --- | --- | --- |
| Bangladesh: 88–92.7 E, 20.5–26.7 N | 1431.84–1728.92 | S0310, S0410 |
| Indo-Gangetic Plain: 73–89 E, 24–32.5 N | 1193.43–1607.72 | S0310 |
| Punjab-Haryana: 73.8–77.5 E, 28.5–32.5 N | 1230.97–1409.63 | S0310 |

Segments are image-line strips, not fixed latitude bands. This verifies geometric
coverage; subsequent science processing must still apply the project's view-angle,
cloud and other quality filters.
