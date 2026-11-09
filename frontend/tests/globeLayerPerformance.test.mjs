import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({ entryPoints: ['src/utils/globePoints.ts'], bundle: true, write: false, format: 'esm', platform: 'node' });
const { uploadPointBatches, toggleObservationLayer } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

test('all satellite buttons and merged view switch without stacking both datasets', () => {
  const satellites = ['Terra', 'Aqua', 'S-NPP', 'NOAA-20', 'NOAA-21'];
  for (const satellite of satellites) {
    const initial = { Harmonized: true, Boundaries: true, ...Object.fromEntries(satellites.map(name => [name, false])) };
    const raw = toggleObservationLayer(initial, satellite, satellites);
    assert.equal(raw[satellite], true);
    assert.equal(raw.Harmonized, false);
    assert.equal(raw.Boundaries, true);
    assert.equal(initial.Harmonized, true);
    assert.equal(toggleObservationLayer(raw, satellite, satellites)[satellite], false);
    const merged = toggleObservationLayer(raw, 'Harmonized', satellites);
    assert.equal(merged.Harmonized, true);
    for (const name of satellites) assert.equal(merged[name], false);
  }
});

test('61,479 observations upload across frames without truncation; rapid toggles cancel stale work', () => {
  const frames = new Map();
  let nextId = 0;
  globalThis.requestAnimationFrame = callback => { frames.set(++nextId, callback); return nextId; };
  globalThis.cancelAnimationFrame = id => frames.delete(id);
  const step = () => { const [id, callback] = frames.entries().next().value; frames.delete(id); callback(); };
  try {
    let uploaded = 0;
    const points = Array.from({ length: 61479 }, (_, i) => i);
    const cancel = uploadPointBatches(points, () => uploaded++, () => {});
    assert.equal(uploaded, 0);
    step();
    assert.equal(uploaded, 1000);
    cancel();
    assert.equal(frames.size, 0);
    const result = [];
    uploadPointBatches(points, point => result.push(point), () => {});
    let ticks = 0;
    while (frames.size) { step(); ticks++; }
    assert.equal(ticks, 62);
    assert.deepEqual(result, points);
  } finally {
    delete globalThis.requestAnimationFrame;
    delete globalThis.cancelAnimationFrame;
  }
});
