import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { queryKey, SearchCache, scheduleSearch, clusterCentroids } from '../src/api/searchRequests.ts';

test('normalized keys include shape, window, and version', () => {
  assert.equal(queryKey({ window: 'a', shape: { a: 1, b: 2 } }), queryKey({ shape: { b: 2, a: 1 }, window: 'a' }));
  assert.notEqual(queryKey({ version: 1 }), queryKey({ version: 2 }));
});

test('cache bounds memory and entries, expires results, and uses LRU order', () => {
  let now = 0;
  const cache = new SearchCache(2, 200, 10, () => now);
  cache.put('a', 1); cache.put('b', 2); cache.get('a'); cache.put('c', 3);
  assert.equal(cache.get('b'), undefined);
  now = 11; assert.equal(cache.get('a'), undefined);
  cache.put('huge', 'x'.repeat(200)); assert.equal(cache.get('huge'), undefined);
  assert.ok(cache.bytes <= 200);
});

test('a burst of map changes issues one request, then repeated query is cached', async () => {
  const cache = new SearchCache(); let calls = 0; let settled = 0; let result;
  const options = { key: 'view', cache, delay: 5, load: async () => { calls++; return [1, 2]; }, onResult: (r) => { result = r; }, onError: assert.fail, onSettled: () => { settled++; } };
  let cancel;
  for (let i = 0; i < 20; i++) { cancel?.(); options.key = `view-${i}`; cancel = scheduleSearch(options); }
  await sleep(30);
  assert.equal(calls, 1); assert.deepEqual(result, [1, 2]); assert.equal(settled, 1);
  scheduleSearch(options); await sleep(10); assert.equal(calls, 1); assert.equal(settled, 2);
  cancel();
});

test('cancel aborts in-flight fetch and rejects stale results even if server ignores abort', async () => {
  let signal; let resolve; let result = false; let error = false;
  const cancel = scheduleSearch({ key: 'old', cache: new SearchCache(), delay: 0,
    load: (s) => { signal = s; return new Promise((r) => { resolve = r; }); },
    onResult: () => { result = true; }, onError: () => { error = true; }, onSettled: () => {} });
  await sleep(10); cancel(); assert.equal(signal.aborted, true); resolve('stale'); await sleep(10);
  assert.equal(result, false); assert.equal(error, false);
});

test('clustering preserves every event exactly once', () => {
  const events = Array.from({ length: 5000 }, (_, i) => ({ fire_id: String(i), centroid_lon: (i * 13.47) % 360 - 180, centroid_lat: (i * 3.71) % 130 - 60 }));
  const groups = clusterCentroids(events, 3);
  assert.ok(groups.length < events.length);
  assert.deepEqual(groups.flatMap((g) => g.events.map((e) => e.fire_id)).sort(), events.map((e) => e.fire_id).sort());
});
