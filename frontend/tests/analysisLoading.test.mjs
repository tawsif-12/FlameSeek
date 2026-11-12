import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';

await mkdir('.test-tmp-analysis-loading', { recursive: true });
await build({ entryPoints: ['src/api/client.ts'], outfile: '.test-tmp-analysis-loading/client.mjs', bundle: true, platform: 'node', format: 'esm', define: { 'import.meta.env.VITE_API_BASE_URL': '""' }, plugins: [{ name: 'http-fixture', setup(b) {
  b.onResolve({ filter: /^axios$/ }, () => ({ path: 'axios', namespace: 'fixture' }));
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: `export default {isAxiosError:()=>false,create:()=>({post:async(url,body)=>{globalThis.analysisPosts.push({url,body});if(url.endsWith('/saved'))return {data:{result:null}};return {data:{id:'job-'+globalThis.analysisPosts.length,status:'queued',result:null}};},get:async(url)=>{globalThis.analysisGets.push(url);await new Promise(r=>setTimeout(r,10));return {data:{id:url.split('/').pop(),status:globalThis.analysisFail?'failed':'completed',result:globalThis.analysisFail?null:{actual:42},error:'failed fixture'}};}})};` }));
}}] });
const api = await import('../.test-tmp-analysis-loading/client.mjs');
globalThis.analysisPosts = []; globalThis.analysisGets = [];
const area = { bbox: [90, 23, 91, 24] };

test('identical requests and concurrent polls are shared; completed results reopen without polling', async () => {
  const [first, second] = await Promise.all([api.startFireMemory(area, 5, ['modis'], 30), api.startFireMemory(area, 5, ['modis'], 30)]);
  assert.equal(first.id, second.id); assert.equal(analysisPosts.length, 1);
  const before = analysisGets.length;
  const [a, b] = await Promise.all([api.runJob(Promise.resolve(first), () => {}), api.runJob(Promise.resolve(second), () => {})]);
  assert.deepEqual(a, { actual: 42 }); assert.deepEqual(a, b); assert.equal(analysisGets.length - before, 1);
  const cached = await api.startFireMemory(area, 5, ['modis'], 30); assert.equal(cached.status, 'completed');
  const gets = analysisGets.length; await api.runJob(Promise.resolve(cached), () => {}); assert.equal(analysisGets.length, gets);
});

test('period, area, sensors and comparison settings never reuse another query', async () => {
  const before = analysisPosts.length;
  await api.startFireMemory(area, 6, ['modis'], 30);
  await api.startFireMemory(area, 6, ['viirs_snpp'], 30);
  await api.startFireMemory(area, 6, ['modis'], 60);
  await api.startFireMemory({ bbox: [91, 23, 92, 24] }, 6, ['modis'], 30);
  assert.equal(analysisPosts.length - before, 4);
  await api.savedFireMemory(area, 6, ['modis'], 60); assert.equal(analysisPosts.at(-1).body.comparison_window_days, 60);
});

test('failed analyses can be retried immediately', async () => {
  const job = await api.startPlacePipeline(area, 3); globalThis.analysisFail = true;
  await assert.rejects(api.runJob(Promise.resolve(job), () => {}), /failed fixture/);
  globalThis.analysisFail = false;
  assert.notEqual((await api.startPlacePipeline(area, 3)).id, job.id);
});
