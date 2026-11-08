"""Validate response hashes and summarize every sequential benchmark checkpoint."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]/'outputs/search-performance'
stages=['01-baseline','02-query-plan','03-count-cache','04-prepared-geometry','05-payload','06-sqlite','07-fallback','08-final']
lines=['# Search performance checkpoints','',
       'Recorded on the local Windows host. Each cell is HTTP p50 / p95 in milliseconds.',
       'These are sequential checkpoints: compare each column with the column immediately before it.',
       'Warm filesystem; one warm-up per case, 7 measured requests for the seeded R-Tree fixture',
       '(30,000 events) and 5 for the published fallback snapshot (138,576 events).',
       'At this small sample size p95 is the slowest observed request, not a load-test percentile.',
       'Limit is 200, geometry=true. This is a bounded reproducible HTTP workload, not a 5000-event browser load test.',
       'Count caches are warm after task 3. Shapely preparation caches are warm after task 4.',
       'Task 5 onward enables negotiated gzip for published-data measurements; decoded response hashes are compared.',
       'Host load and filesystem noise affect small differences. No published snapshot was modified.', '']
for suffix,title in [('-published','Published snapshot (coordinate fallback)'),('','Seeded R-Tree fixture')]:
    reports=[json.loads((root/(stage+suffix+'.json')).read_text()) for stage in stages]
    baseline=reports[0]['cases']
    lines+=['## '+title,'','| Query | T1 baseline | T2 plan | T3 count | T4 geometry | T5 payload | T6 SQLite | T7 fallback | T8 final |',
            '|---|'+'---:|'*8]
    for name,reference in baseline.items():
        values=[]
        for report in reports:
            case=report['cases'][name]
            assert case['sha256']==reference['sha256'],(report['dataset'],name,'response changed')
            assert case['stable'],(report['dataset'],name,'unstable output')
            values.append(f"{case['p50_ms']:.1f} / {case['p95_ms']:.1f}")
        lines.append('| '+name+' | '+' | '.join(values)+' |')
    lines.append('')
lines+=['## Trade-offs by task','',
        '1. Baseline: timing and EXPLAIN capture only; no optimization. Instrumentation itself has overhead.',
        '   `candidate_filter_ms` measures candidate SQL construction/schema lookup, not an isolated table scan.',
        '   Actual candidate traversal is pipelined within `count_ms` and `sort_limit_ms`.',
        '   `exact_containment_ms` is measured inside SQLite predicate callbacks and overlaps those two SQL timings.',
        '   `serialization_ms` includes event enrichment, footprints, JSON parsing and final JSONResponse encoding.',
        '   These stages must not be added together as exclusive timings.',
        '2. Plans: selective searches use R-Tree rowids followed by a narrow-ID sort and late payload fetch.',
        '   Broad boxes can walk event_order (or the legacy event_end index). Legacy selective boxes avoid a full ordered-index walk.',
        '   The broad-box threshold is a conservative heuristic, not a universal planner cost model; synthetic medium-box timings regress slightly.',
        '3. Counts: bounded 120-second process-local LRU. First use at any offset still computes the full exact count.',
        '   Warm hits avoid repeated full scans; cold requests and other worker processes pay the count cost.',
        '4. Geometry: Shapely is an added backend dependency. Preparation costs CPU/memory on cold queries.',
        '   Invalid polygons and near-boundary points retain ray casting. Circle boxes are conservative near poles/date line.',
        '   The approved combined-shape fix intentionally excludes centroids that pass the circle but fail the polygon.',
        '5. Payload: batching and one translation-config read reduce enrichment cost. Gzip spends server CPU to reduce wire bytes.',
        '   Simplification is opt-in; it changes footprint vertices, never event membership or order. Defaults are byte-identical.',
        '6. SQLite: readonly, mmap and cache tuning help repeated reads. At most 8 active leases, 8 MiB page cache each.',
        '   Persistent reuse defaults off on Windows to preserve atomic replacement; POSIX reuses idle connections.',
        '   Immutable mode is explicit opt-in for guaranteed immutable files, never inferred for writable snapshots.',
        '7. Fallback: rate-limited warnings and documentation only; timing differences are measurement noise.',
        '8. Frontend: 250 ms debounce adds intentional interaction latency before uncached requests.',
        '   A 30-second bounded cache can show recently fetched data until expiry; version changes produce new keys.',
        '   Low-zoom clustering retains every event; full-place search remains the default. Viewport filtering is opt-in.',
        '   Backend code is unchanged between T7 and T8; server timing differences are measurement noise.', '',
        '## Frontend lifecycle simulation','']
ui=json.loads((root/'08-frontend.json').read_text())
lines += [f"Twenty rapidly superseded query changes: {ui['before']['burst_requests']} immediate requests in the old request-lifecycle model versus {ui['after']['burst_requests']} with debounce.",
          f"Repeating the final query: {ui['before']['repeated_query_requests']} request versus {ui['after']['repeated_query_requests']} from cache.",
          f"At zoom 3, 5000 event shapes become {ui['after']['map_clusters']} clusters representing all {ui['after']['represented_events']} events.",
          f"Grouping CPU p50/p95: {ui['clustering_p50_ms']:.3f}/{ui['clustering_p95_ms']:.3f} ms.",
          'This is a Node simulation, not browser rendering or network latency. The original page did not issue map-move searches;',
          'the new map-view mode is opt-in. The simulation compares immediate versus debounced request lifecycles for changing query keys.', '',
          '## Compression and optional detail','',
          '| Published query | Decoded bytes | Gzip wire bytes | Reduction |','|---|---:|---:|---:|']
for name,case in json.loads((root/'08-final-published.json').read_text())['cases'].items():
    lines.append(f"| {name} | {case['response_bytes']} | {case['wire_bytes']} | {100*(1-case['wire_bytes']/case['response_bytes']):.1f}% |")
lines+=['','The optional-detail workload is separately recorded in [05-payload-opt-in.json](05-payload-opt-in.json).',
        'Its geometry bytes intentionally differ; all other checkpoints have matching decoded SHA-256 hashes for every query.', '',
        '## Reproduce','', 'From `backend/` with requirements installed:', '', '```powershell',
        'python benchmarks/search.py --output ../outputs/search-performance/recheck-seeded.json',
        'python benchmarks/search.py --root .. --repeats 5 --gzip --output ../outputs/search-performance/recheck-published.json',
        'python benchmarks/report.py', '```', '',
        'From `frontend/`: `node --test tests/searchRequests.test.mjs` and',
        '`node tests/benchmark-search.mjs ../outputs/search-performance/08-frontend.json`.', '',
        'The benchmark accepts --limit 5000, --simplify, and --window sync_2016 for additional workloads.',
        'Raw JSON files contain stage medians, plans, counts, hashes, and response sizes.', '',
        '## Optional proposals — not implemented','',
        '- Keyset pagination with `(end_time, fire_id)` could reduce deep-page work; keep OFFSET compatibility and introduce a versioned cursor.',
        '- Antimeridian support could split a wrapping bbox into two candidate ranges and deduplicate IDs before counting and pagination.',
        'Both require separate approval and regression coverage before implementation.', '',
        'Prepared-geometry behavior follows [Shapely documentation](https://shapely.readthedocs.io/en/stable/manual.html#prepared-geometry-operations).',
        'Read-only/immutable safety follows [SQLite URI documentation](https://www.sqlite.org/uri.html);',
        'float32 edge rechecks follow the [SQLite R-Tree rounding guidance](https://www.sqlite.org/rtree.html#roundoff_error).', '']
if (root/'09-limit-5000.json').exists():
    cold_reference=json.loads((root/'09-cold-reference.json').read_text())['cases']
    cold_final=json.loads((root/'09-cold-final.json').read_text())['cases']
    large={limit:json.loads((root/f'09-limit-{limit}.json').read_text())['cases'] for limit in [2000,5000]}
    profile=json.loads((root/'09-stage-profile.json').read_text())['cases']
    lines+=['## Cold-cache and larger pages','',
            'These additional measurements ran after all eight tasks. The cold reference loads the actual',
            'instrumented baseline source from commit `3f95ca7` into memory without changing the working tree.',
            'Forced-cold runs clear process-local count and prepared-geometry caches before every request;',
            'they do not flush the operating-system filesystem cache. Both reference and final omit gzip',
            'for this comparison, with limit 200 and 5 samples. Larger-page runs use warm repeat caches,',
            'negotiated gzip and 3 samples, so their p95 is only the maximum observed sample.', '',
            '| Query | Cold reference p50 / p95 | Cold final p50 / p95 | 2000-event page p50 / p95 | 5000-event page p50 / p95 |',
            '|---|---:|---:|---:|---:|']
    for name,old in cold_reference.items():
        new=cold_final[name]
        assert old['sha256']==new['sha256']
        assert new['sha256']==profile[name]['sha256']
        cells=[f"{case['p50_ms']:.1f} / {case['p95_ms']:.1f}" for case in [old,new,large[2000][name],large[5000][name]]]
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines+=['','Larger pages still pay to enrich/serialize/transmit every returned event; clustering reduces',
            'client drawing work, not response size. The full count remains independent of page size.', '',
            '## Isolated candidate diagnostics','',
            '`profile_stages=true` explicitly adds a coordinate-only candidate scan and exact-predicate pass.',
            'It leaves normal response bytes unchanged. This isolates candidate traversal rather than',
            'mislabeling SQL construction time as filter execution. Production requests do not pay this extra scan.',
            'The original T1–T8 JSON field `candidate_filter_ms` was query-construction time; the current',
            'logger correctly calls it `candidate_setup_ms`. Normal count/page timings still include',
            'candidate traversal and exact callback time; timings are overlapping, not additive.', '',
            '| Query | Candidate scan median ms | Diagnostic exact median ms |', '|---|---:|---:|']
    for name,case in profile.items():
        timing=case['stages_p50']
        lines.append(f"| {name} | {timing['candidate_filter_ms']:.3f} | {timing['diagnostic_exact_ms']:.3f} |")
    lines+=['','Reproduce with `--cold`, `--reference-commit 3f95ca7`, `--profile-stages`, or `--limit 5000`',
            'on `benchmarks/search.py`. Isolated diagnostic totals must not be compared as normal endpoint latencies.', '']
(root/'report.md').write_text('\n'.join(lines),encoding='utf-8')
print('All sequential checkpoint response hashes match; report.md written.')
