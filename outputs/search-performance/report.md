# Search performance checkpoints

Recorded on the local Windows host. Each cell is HTTP p50 / p95 in milliseconds.
These are sequential checkpoints: compare each column with the column immediately before it.
Warm filesystem; one warm-up per case, 7 measured requests for the seeded R-Tree fixture
(30,000 events) and 5 for the published fallback snapshot (138,576 events).
At this small sample size p95 is the slowest observed request, not a load-test percentile.
Limit is 200, geometry=true. This is a bounded reproducible HTTP workload, not a 5000-event browser load test.
Count caches are warm after task 3. Shapely preparation caches are warm after task 4.
Task 5 onward enables negotiated gzip for published-data measurements; decoded response hashes are compared.
Host load and filesystem noise affect small differences. No published snapshot was modified.

## Published snapshot (coordinate fallback)

| Query | T1 baseline | T2 plan | T3 count | T4 geometry | T5 payload | T6 SQLite | T7 fallback | T8 final |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| small | 298.2 / 333.0 | 232.0 / 377.9 | 120.5 / 149.5 | 125.9 / 170.6 | 105.6 / 114.7 | 94.1 / 101.3 | 89.7 / 108.1 | 87.5 / 88.8 |
| medium | 161.7 / 180.8 | 175.0 / 182.7 | 70.1 / 83.7 | 86.5 / 88.2 | 38.2 / 39.5 | 36.6 / 40.6 | 38.1 / 41.5 | 37.7 / 40.6 |
| continent | 216.6 / 220.8 | 232.6 / 242.5 | 112.2 / 124.6 | 91.6 / 128.3 | 63.8 / 65.4 | 58.0 / 64.6 | 56.4 / 57.5 | 58.2 / 82.0 |
| complex_polygon | 1735.6 / 2084.1 | 1700.5 / 1735.0 | 125.9 / 136.2 | 112.6 / 128.4 | 93.8 / 123.1 | 73.2 / 79.6 | 70.2 / 83.6 | 76.2 / 101.8 |
| circle | 285.0 / 300.5 | 306.2 / 308.7 | 129.1 / 157.8 | 127.6 / 153.3 | 81.4 / 92.6 | 70.1 / 71.9 | 70.9 / 76.2 | 71.4 / 73.7 |
| deep_offset | 304.2 / 313.5 | 303.5 / 322.9 | 145.4 / 203.9 | 124.2 / 142.0 | 88.9 / 92.7 | 73.9 / 75.1 | 74.5 / 80.3 | 71.0 / 71.8 |

## Seeded R-Tree fixture

| Query | T1 baseline | T2 plan | T3 count | T4 geometry | T5 payload | T6 SQLite | T7 fallback | T8 final |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| small | 23.7 / 31.3 | 24.1 / 29.9 | 24.5 / 27.8 | 27.2 / 29.5 | 21.3 / 28.0 | 15.3 / 19.2 | 15.3 / 18.4 | 19.7 / 23.0 |
| medium | 108.6 / 112.8 | 130.2 / 232.4 | 114.2 / 117.0 | 127.8 / 159.1 | 63.1 / 65.1 | 60.8 / 73.8 | 60.2 / 82.2 | 83.5 / 102.8 |
| continent | 128.6 / 132.0 | 146.6 / 183.1 | 127.8 / 166.7 | 142.0 / 146.7 | 72.0 / 88.3 | 68.4 / 75.7 | 70.4 / 94.4 | 80.1 / 89.3 |
| complex_polygon | 220.8 / 274.9 | 235.7 / 279.1 | 174.3 / 183.4 | 124.8 / 131.6 | 88.8 / 107.8 | 72.3 / 82.0 | 67.1 / 79.6 | 78.5 / 87.4 |
| circle | 134.5 / 164.0 | 144.6 / 172.4 | 130.8 / 143.5 | 119.9 / 165.0 | 62.5 / 70.6 | 57.9 / 71.0 | 58.0 / 70.9 | 66.9 / 78.7 |
| deep_offset | 231.0 / 236.4 | 186.1 / 200.8 | 138.7 / 143.6 | 140.9 / 148.8 | 81.4 / 89.0 | 77.6 / 85.9 | 75.4 / 76.2 | 88.9 / 94.9 |

## Trade-offs by task

1. Baseline: timing and EXPLAIN capture only; no optimization. Instrumentation itself has overhead.
   `candidate_filter_ms` measures candidate SQL construction/schema lookup, not an isolated table scan.
   Actual candidate traversal is pipelined within `count_ms` and `sort_limit_ms`.
   `exact_containment_ms` is measured inside SQLite predicate callbacks and overlaps those two SQL timings.
   `serialization_ms` includes event enrichment, footprints, JSON parsing and final JSONResponse encoding.
   These stages must not be added together as exclusive timings.
2. Plans: selective searches use R-Tree rowids followed by a narrow-ID sort and late payload fetch.
   Broad boxes can walk event_order (or the legacy event_end index). Legacy selective boxes avoid a full ordered-index walk.
   The broad-box threshold is a conservative heuristic, not a universal planner cost model; synthetic medium-box timings regress slightly.
3. Counts: bounded 120-second process-local LRU. First use at any offset still computes the full exact count.
   Warm hits avoid repeated full scans; cold requests and other worker processes pay the count cost.
4. Geometry: Shapely is an added backend dependency. Preparation costs CPU/memory on cold queries.
   Invalid polygons and near-boundary points retain ray casting. Circle boxes are conservative near poles/date line.
   The approved combined-shape fix intentionally excludes centroids that pass the circle but fail the polygon.
5. Payload: batching and one translation-config read reduce enrichment cost. Gzip spends server CPU to reduce wire bytes.
   Simplification is opt-in; it changes footprint vertices, never event membership or order. Defaults are byte-identical.
6. SQLite: readonly, mmap and cache tuning help repeated reads. At most 8 active leases, 8 MiB page cache each.
   Persistent reuse defaults off on Windows to preserve atomic replacement; POSIX reuses idle connections.
   Immutable mode is explicit opt-in for guaranteed immutable files, never inferred for writable snapshots.
7. Fallback: rate-limited warnings and documentation only; timing differences are measurement noise.
8. Frontend: 250 ms debounce adds intentional interaction latency before uncached requests.
   A 30-second bounded cache can show recently fetched data until expiry; version changes produce new keys.
   Low-zoom clustering retains every event; full-place search remains the default. Viewport filtering is opt-in.
   Backend code is unchanged between T7 and T8; server timing differences are measurement noise.

## Frontend lifecycle simulation

Twenty rapidly superseded query changes: 20 immediate requests in the old request-lifecycle model versus 1 with debounce.
Repeating the final query: 1 request versus 0 from cache.
At zoom 3, 5000 event shapes become 416 clusters representing all 5000 events.
Grouping CPU p50/p95: 0.492/0.854 ms.
This is a Node simulation, not browser rendering or network latency. The original page did not issue map-move searches;
the new map-view mode is opt-in. The simulation compares immediate versus debounced request lifecycles for changing query keys.

## Compression and optional detail

| Published query | Decoded bytes | Gzip wire bytes | Reduction |
|---|---:|---:|---:|
| small | 84082 | 7038 | 91.6% |
| medium | 641598 | 36356 | 94.3% |
| continent | 806379 | 113924 | 85.9% |
| complex_polygon | 951946 | 174910 | 81.6% |
| circle | 979530 | 185150 | 81.1% |
| deep_offset | 659134 | 44357 | 93.3% |

The optional-detail workload is separately recorded in [05-payload-opt-in.json](05-payload-opt-in.json).
Its geometry bytes intentionally differ; all other checkpoints have matching decoded SHA-256 hashes for every query.

## Reproduce

From `backend/` with requirements installed:

```powershell
python benchmarks/search.py --output ../outputs/search-performance/recheck-seeded.json
python benchmarks/search.py --root .. --repeats 5 --gzip --output ../outputs/search-performance/recheck-published.json
python benchmarks/report.py
```

From `frontend/`: `node --test tests/searchRequests.test.mjs` and
`node tests/benchmark-search.mjs ../outputs/search-performance/08-frontend.json`.

The benchmark accepts --limit 5000, --simplify, and --window sync_2016 for additional workloads.
Raw JSON files contain stage medians, plans, counts, hashes, and response sizes.

## Optional proposals — not implemented

- Keyset pagination with `(end_time, fire_id)` could reduce deep-page work; keep OFFSET compatibility and introduce a versioned cursor.
- Antimeridian support could split a wrapping bbox into two candidate ranges and deduplicate IDs before counting and pagination.
Both require separate approval and regression coverage before implementation.

Prepared-geometry behavior follows [Shapely documentation](https://shapely.readthedocs.io/en/stable/manual.html#prepared-geometry-operations).
Read-only/immutable safety follows [SQLite URI documentation](https://www.sqlite.org/uri.html);
float32 edge rechecks follow the [SQLite R-Tree rounding guidance](https://www.sqlite.org/rtree.html#roundoff_error).
