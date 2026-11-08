# Area Fire Intelligence loading

This screen uses NASA archive downloads and Fire Memory/place harmonization jobs.
It does not use the `/fires/search` snapshot endpoint. A five-year, two-sensor cold
request needs hundreds of five-day chunks; an R-Tree cannot accelerate those network
downloads. Existing chunk caching and in-flight download sharing remain in place.

The page now independently requests `/api/fire_memory/saved` and
`/api/place_pipeline/saved`. These endpoints do not contact NASA or start jobs.
They look up the exact AOI, sensors, history length and analysis settings in the
existing result cache for the current end date and the preceding seven days.
Explicit Fire Memory end dates only match that date. Refresh requests bypass previews.
Only unexpired cached results are returned, preserving their original period and values.

Saved previews appear while the usual fresh analysis runs in the background. The UI
labels them `Saved through <date>; updating in background`, and the coverage notice
continues to show the saved period. Fresh results replace previews; a late preview
cannot replace an already-finished fresh result. An update failure leaves the dated
saved result available and reports the failure. No saved result means the normal
loading flow remains. This improves repeat visits, not first-time NASA transfer speed.

The place pipeline consumes original CSV files directly, so its archive fetch now
skips building parsed row dictionaries that it previously discarded. Fire Memory
still parses the same records, off the event loop so progress polling stays responsive.
Progress labels distinguish checked archive chunks from actual new HTTP downloads.

The locally launched backend originally had network-restricted execution: outbound
NASA calls failed with Windows error 10013. Restarting it in the network-enabled
runner restored NASA connectivity and the live-hotspot endpoint. Downloaded cache
chunks were retained. Restarting loses in-process jobs; reloading resumes via saved
chunks and new jobs. A restricted-runner health check alone does not establish that
external data providers are reachable.

Verification for the existing Bangladesh five-year record through 2026-11-01:
local saved-cache lookup about 20 ms; repeated requests through the frontend proxy
about 186–213 ms, including its 1.4 MB response. Initial startup was slower. The live
hotspot API returned HTTP 200 after the network-enabled restart. These measurements
do not promise the same timing for uncached places or a complete fresh analysis.

Regression coverage: exact query matching, unchanged coverage dates, explicit-date
and refresh behavior, no jobs/downloads from preview endpoints, and no discarded
CSV parsing in raw-only mode.
