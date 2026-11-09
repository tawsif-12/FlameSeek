import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
await mkdir('.test-tmp-intelligence', { recursive: true });
await build({entryPoints:['src/components/IntelligenceSummary.tsx'],outfile:'.test-tmp-intelligence/summary.mjs',bundle:true,format:'esm',platform:'node',packages:'external',jsx:'automatic'});
const {observedTimeline} = await import('../.test-tmp-intelligence/summary.mjs');
test('timeline excludes padded zeros and groups only recorded detections by their actual month',()=>{
 const memory={daily:[{date:'2026-01-01',hotspot_count:0},{date:'2026-11-09',hotspot_count:3},{date:'2026-11-10',hotspot_count:2},{date:'2026-02-02',hotspot_count:1}]};
 assert.deepEqual(observedTimeline(memory,null),[{date:'2026-02',count:1},{date:'2026-11',count:5}]);
 assert.deepEqual(observedTimeline(null,null),[]);
});
test('pipeline timeline uses recorded event counts without filling requested but missing months',()=>{
 const pipeline={monthly:[{year:2026,month:3,n_events:0},{year:2026,month:11,n_events:4},{year:2025,month:12,n_events:2}]};
 assert.deepEqual(observedTimeline(null,pipeline),[{date:'2025-12',count:2},{date:'2026-11',count:4}]);
});
