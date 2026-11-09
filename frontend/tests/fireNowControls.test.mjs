import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/fire-map' });
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'localStorage']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
window.matchMedia = () => ({ matches: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// Leave the WebGL surface unmounted: this test exercises API-driven controls.
globalThis.requestAnimationFrame = () => 0;
await mkdir('.test-tmp-fire-now', { recursive: true });
await build({
  stdin: { contents: `export {default as Globe} from './src/components/CesiumFireGlobe'; export {AppProvider} from './src/context/AppContext';`, resolveDir: process.cwd() },
  outfile: '.test-tmp-fire-now/components.mjs', bundle: true, format: 'esm', platform: 'node', packages: 'external', jsx: 'automatic',
  define: { 'import.meta.env': '{}' },
  plugins: [{ name: 'test-boundaries', setup(b) {
    b.onResolve({ filter: /\.css$/ }, () => ({ path: 'css', namespace: 'empty' }));
    b.onLoad({ filter: /.*/, namespace: 'empty' }, () => ({ contents: '' }));
    b.onResolve({ filter: /^\.\/EventPanel$/ }, () => ({ path: 'panel', namespace: 'panel' }));
    b.onLoad({ filter: /.*/, namespace: 'panel' }, () => ({ contents: 'export default function Panel(){return null;}' }));
    b.onResolve({ filter: /api\/client$/ }, () => ({ path: 'client', namespace: 'fixture' }));
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: `
      export const getHarmonizedHotspots=(days)=>globalThis.fetchFireFixture(days);
      export const getCurrentHotspots=(sensors,days,limit,date)=>globalThis.fetchFireFixture(days,date);
      export const normalizeApiError=e=>e.message;
      export const getEvent=async()=>null, getEvents=async()=>({events:[],metadata:{}}), lookupEvent=async()=>null,
        runJob=async()=>null, searchPlaces=async()=>[], startEvidence=async()=>null, startOutlook=async()=>null;
    ` }));
  } }],
});
const React = await import('react');
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
const { MemoryRouter } = await import('react-router-dom');
const { Globe, AppProvider } = await import('../.test-tmp-fire-now/components.mjs');

test('date filters fetch real windows; toggles preserve counts; refresh failure exposes an honest empty state', async () => {
  const requests = [];
  let fail = false;
  globalThis.fetchFireFixture = async (days, date) => {
    requests.push({ days, date });
    if (fail) throw new Error('FIRMS offline');
    const point = { lat: 24, lon: 90, acq_datetime: '2026-11-09T12:00:00Z', confidence_pct: 90, frp: 12, sensor: 'modis', satellite: 'Terra', daynight: 'D' };
    return { hotspots: [], raw_hotspots: [point], metadata: { data_source: 'live', events_total: 7, raw_hotspot_count: 1, returned_hotspot_count: 0 } };
  };
  render(React.createElement(MemoryRouter, null, React.createElement(AppProvider, null, React.createElement(Globe))));
  try {
    await screen.findByText(/NRT available/);
    assert.equal(requests[0].days, 1);
    assert.ok(screen.getByText('7'));
    const terra = screen.getByRole('button', { name: /MODIS.*Terra/ });
    assert.equal(terra.getAttribute('aria-pressed'), 'false');
    fireEvent.click(terra);
    assert.equal(terra.getAttribute('aria-pressed'), 'true');
    assert.match(terra.textContent, /1$/);
    fireEvent.click(terra);
    assert.match(terra.textContent, /1$/);
    fireEvent.click(screen.getByRole('button', { name: 'Last 2 days' }));
    await waitFor(() => assert.equal(requests.at(-1).days, 2));
    await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Refresh FIRMS' }).disabled, false));
    fireEvent.click(screen.getByRole('button', { name: 'Last 5 days' }));
    await waitFor(() => assert.equal(requests.at(-1).days, 5));
    await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Refresh FIRMS' }).disabled, false));
    assert.ok(document.querySelector('time[datetime]'));
    fireEvent.click(screen.getByRole('button', { name: 'Pick a past date' }));
    await waitFor(() => assert.ok(requests.at(-1).date));
    fireEvent.change(screen.getByLabelText('Date (UTC)'), { target: { value: '2025-03-12' } });
    await waitFor(() => assert.equal(requests.at(-1).date, '2025-03-12'));
    await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Refresh FIRMS' }).disabled, false));
    assert.ok(screen.getByText('Historical observations loaded'));
    fail = true;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh FIRMS' }));
    await screen.findByText('Processing failed');
    assert.ok(screen.getByText('Observations unavailable'));
    assert.equal(screen.queryByText(/NRT available/), null);
    assert.equal(document.querySelector('.merged-count'), null);
    assert.ok(screen.getByRole('button', { name: 'Reset globe view' }));
  } finally { cleanup(); }
});
