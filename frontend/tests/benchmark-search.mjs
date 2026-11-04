import { performance } from 'node:perf_hooks';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { SearchCache, scheduleSearch, clusterCentroids } from '../src/api/searchRequests.ts';

const cache = new SearchCache(); let calls = 0; let cancel;
const options = { key: 'view', cache, delay: 20, load: async () => { calls++; return { count: 5000 }; }, onResult: () => {}, onError: (e) => { throw e; }, onSettled: () => {} };
for (let i = 0; i < 20; i++) { cancel?.(); options.key = `view-${i}`; cancel = scheduleSearch(options); }
await sleep(80); const burstCalls = calls;
scheduleSearch(options); await sleep(10);
const events = Array.from({ length: 5000 }, (_, i) => ({ fire_id: String(i), centroid_lon: (i * 13.47) % 360 - 180, centroid_lat: (i * 3.71) % 130 - 60 }));
const samples = []; let groups;
for (let i = 0; i < 50; i++) { const tick = performance.now(); groups = clusterCentroids(events, 3); samples.push(performance.now() - tick); }
samples.sort((a, b) => a - b);
const report = { scenario: '20 rapidly superseded distinct view changes, seeded 5000-event page, zoom 3', before: { burst_requests: 20, repeated_query_requests: 1, map_shapes: 5000 }, after: { burst_requests: burstCalls, repeated_query_requests: calls - burstCalls, map_clusters: groups.length, represented_events: groups.reduce((n, g) => n + g.events.length, 0) }, clustering_p50_ms: samples[25], clustering_p95_ms: samples[47], note: 'Node lifecycle simulation and grouping CPU only, not browser paint or network latency. Production debounce is 250 ms (20 ms here to bound test duration). Whole-place searches stay whole-place by default; viewport searches are opt-in.' };
const target = process.argv[2]; mkdirSync(dirname(target), { recursive: true }); writeFileSync(target, JSON.stringify(report, null, 2) + '\n'); console.log(report);
