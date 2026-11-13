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
  stdin: { contents: `export {default as Globe} from './src/components/CesiumFireGlobe'; export {AppProvider,useAppContext} from './src/context/AppContext';`, resolveDir: process.cwd() },
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
      export const getEvent=async()=>null, getEvents=async()=>({events:[],metadata:{}}), lookupEvent=async(...args)=>{globalThis.insightLookups?.push(args);return "fixture-event";},
        runJob=async()=>null, searchPlaces=async()=>globalThis.searchPlaceFixture?.() ?? [], startEvidence=async()=>null, startOutlook=async()=>null;
    ` }));
  } }],
});
const React = await import('react');
const { render, screen, fireEvent, waitFor, cleanup, act, within } = await import('@testing-library/react');
const { MemoryRouter } = await import('react-router-dom');
const { Globe, AppProvider, useAppContext } = await import('../.test-tmp-fire-now/components.mjs');

test('map stays on the last 24 hours; toggles preserve counts; refresh failure exposes an honest empty state', async () => {
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
    assert.ok(screen.getByText('Showing fire data from the last 24 hours.'));
    for (const name of ['Last 2 days', 'Last 5 days', 'Pick a past date']) {
      assert.equal(screen.queryByRole('button', { name }), null);
    }
    assert.equal(screen.queryByLabelText('Date (UTC)'), null);
    const previousRequests = requests.length;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh FIRMS' }));
    await waitFor(() => assert.ok(requests.length > previousRequests));
    assert.ok(requests.every(({ days, date }) => days === 1 && date === undefined));
    await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Refresh FIRMS' }).disabled, false));
    assert.ok(document.querySelector('time[datetime]'));
    fail = true;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh FIRMS' }));
    await screen.findByText('Processing failed');
    assert.ok(screen.getByText('Observations unavailable'));
    assert.equal(screen.queryByText(/NRT available/), null);
    assert.equal(document.querySelector('.merged-count'), null);
    assert.ok(screen.getByRole('button', { name: 'Reset globe view' }));
  } finally { cleanup(); }
});

test('real observations stay visible while event matching completes in the background', async () => {
  localStorage.clear();
  const originalTimer = window.setTimeout;
  let poll;
  window.setTimeout = (callback, delay, ...args) => {
    if (delay === 10000) { poll = callback; return 999999; }
    return originalTimer.call(window, callback, delay, ...args);
  };
  let completed = false;
  const point = { lat: 24, lon: 90, acq_datetime: '2026-11-09T12:00:00Z', confidence_pct: 90, frp: 12, sensor: 'modis', satellite: 'Terra', daynight: 'D' };
  globalThis.fetchFireFixture = async () => ({
    hotspots: [completed ? { ...point, harmonized: { event_id: 'real-fixture', observations: 1, platforms: 'Terra', confidence: .9, footprint_area_km2: 1 } } : point],
    raw_hotspots: [point], metadata: { data_source: 'live', raw_hotspot_count: 1, returned_hotspot_count: 1,
      processing_pending: !completed, refresh_in_progress: !completed, ...(completed ? {events_total: 1} : {}) },
  });
  render(React.createElement(MemoryRouter, null, React.createElement(AppProvider, null, React.createElement(Globe))));
  try {
    await screen.findByText('Observations loaded. Matching events...');
    assert.ok(screen.getByText('Showing individual satellite detections while merged fire events are unavailable.'));
    fireEvent.click(screen.getByRole('button', { name: 'At a glance', exact: true }));
    assert.match(screen.getByRole('complementary', { name: 'Insight panel' }).textContent, /Satellite heat detections1/);
    assert.ok(screen.getByText('12 MW'));
    fireEvent.click(screen.getByRole('button', { name: 'How strong', exact: true }));
    assert.match(screen.getByRole('complementary', { name: 'Insight panel' }).textContent, /Heat output/);
    fireEvent.click(screen.getByRole('button', { name: 'Close panel' }));
    assert.equal(screen.queryByText('No observations to display'), null);
    assert.equal(document.querySelector('.merged-count'), null);
    await waitFor(() => assert.equal(typeof poll, 'function'));
    completed = true;
    await act(async () => { poll(); });
    await screen.findByText('Ready');
    assert.match(document.querySelector('.merged-count').textContent, /1/);
    assert.equal(screen.queryByText('No observations to display'), null);
  } finally { cleanup(); window.setTimeout = originalTimer; }
});

test('floating search rejects point-only results and selects and clears the actual polygon', async () => {
  localStorage.clear();
  globalThis.fetchFireFixture=async()=>({hotspots:[],raw_hotspots:[],metadata:{data_source:'live',events_total:0,raw_hotspot_count:0,returned_hotspot_count:0}});
  const geometry={type:'Polygon',coordinates:[[[90,23],[91,23],[91,24],[90,24],[90,23]]]};
  const area={name:'Test district, Bangladesh',place_name:'Test district',type:'administrative',addresstype:'district',bbox:[90,23,91,24],center:[90.5,23.5],geometry};
  globalThis.searchPlaceFixture=()=>[{...area,name:'Point only',place_name:'Point only',geometry:null},area];
  function SelectedArea(){return React.createElement('pre',{'data-testid':'selected-area'},JSON.stringify(useAppContext().aoi));}
  render(React.createElement(MemoryRouter,null,React.createElement(AppProvider,null,React.createElement(React.Fragment,null,React.createElement(Globe),React.createElement(SelectedArea)))));
  try {
    fireEvent.click(screen.getByRole('button',{name:'Search location'}));
    fireEvent.change(screen.getByRole('textbox',{name:'Search place'}),{target:{value:'Test district'}});
    fireEvent.click(screen.getByRole('button',{name:'Go'}));
    await screen.findByText('Point only');
    fireEvent.click(screen.getByRole('button',{name:/Point only/}));
    assert.ok(screen.getByText(/No administrative boundary available/));
    assert.equal(screen.getByTestId('selected-area').textContent,'null');
    fireEvent.click(screen.getByRole('button',{name:/Test district/}));
    await waitFor(()=>assert.notEqual(screen.getByTestId('selected-area').textContent,'null'));
    assert.deepEqual(JSON.parse(screen.getByTestId('selected-area').textContent).geometry,geometry);
    fireEvent.click(screen.getByRole('button',{name:'Search location'}));
    assert.equal(screen.getByRole('checkbox',{name:'Show only this area'}).checked,true);
    fireEvent.click(screen.getByRole('button',{name:'Clear'}));
    assert.equal(document.querySelector('.boundary-focus'),null);
    assert.equal(screen.getByTestId('selected-area').textContent,'null');
  } finally {cleanup();delete globalThis.searchPlaceFixture;}
});


test('summary separates raw detections, merged events and today in UTC', async () => {
  localStorage.clear();
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const point = { lat: 24, lon: 90, acq_datetime: today + 'T00:00:00Z', confidence_pct: 90, frp: 12, sensor: 'modis', satellite: 'Terra', daynight: 'D' };
  const merged = (id, time) => ({ ...point, acq_datetime: time, harmonized: { event_id: id, observations: 2, platforms: 'Terra', confidence: .9, footprint_area_km2: 1 } });
  globalThis.fetchFireFixture = async () => ({ raw_hotspots: [point, { ...point, lon: 90.01 }, { ...point, acq_datetime: yesterday + 'T12:00:00Z' }], hotspots: [merged('today', point.acq_datetime), merged('yesterday', yesterday + 'T12:00:00Z')], metadata: { data_source: 'live', events_total: 2, raw_hotspot_count: 3, returned_hotspot_count: 2 } });
  render(React.createElement(MemoryRouter, null, React.createElement(AppProvider, null, React.createElement(Globe))));
  try {
    await screen.findByText('Ready');
    assert.match(document.querySelector('.detection-count').textContent, /3.*satellite heat detections/);
    assert.match(document.querySelector('.merged-count').textContent, /2.*merged fire events/);
    assert.equal(document.querySelector('.today-fire-count').textContent, 'Today (UTC): 2 heat detections; 1 merged event last seen today.');
    fireEvent.click(screen.getByRole('button', { name: /MODIS.*Terra/ }));
    assert.match(document.querySelector('.detection-count').textContent, /^3/);
  } finally { cleanup(); }
});


test('all four insight panels use real observations and merged groups, with working interval and event buttons', async () => {
  localStorage.clear();
  const now = Date.now();
  const point = { lat: 24, lon: 90, acq_datetime: new Date(now - 3600000).toISOString(), confidence_pct: 90, frp: 140, sensor: 'modis', satellite: 'Terra', daynight: 'D' };
  const large = { ...point, harmonized: { event_id: 'large-footprint', observations: 3, platforms: 'Terra;Aqua', confidence: .9, footprint_area_km2: 9 } };
  const small = { ...point, lat: 25, frp: null, harmonized: { ...large.harmonized, event_id: 'small-footprint', footprint_area_km2: 2 } };
  globalThis.insightLookups = [];
  globalThis.fetchFireFixture = async () => ({ raw_hotspots: [point, { ...point, lon: 90.01 }, { ...point, acq_datetime: new Date(now - 23 * 3600000).toISOString() }], hotspots: [small, large], metadata: { data_source: 'live', events_total: 2, raw_hotspot_count: 3, returned_hotspot_count: 2 } });
  render(React.createElement(MemoryRouter, null, React.createElement(AppProvider, null, React.createElement(Globe))));
  try {
    await screen.findByText('Ready');
    fireEvent.click(screen.getByRole('button', { name: 'At a glance', exact: true }));
    assert.match(screen.getByRole('complementary', { name: 'Insight panel' }).textContent, /Satellite heat detections3/);
    assert.match(screen.getByRole('complementary', { name: 'Insight panel' }).textContent, /Merged fire groups2/);
    fireEvent.click(screen.getByRole('button', { name: 'How strong', exact: true }));
    assert.match(screen.getByRole('complementary', { name: 'Insight panel' }).textContent, /Heat output unavailable for 1 points/);
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Data insights' })).getByRole('button', { name: 'Last 24 hours', exact: true }));
    const bars = document.querySelectorAll('.insight-timeline button');
    assert.equal(bars.length, 12);
    assert.match(bars[0].getAttribute('aria-label'), /1 detections/);
    assert.match(bars[11].getAttribute('aria-label'), /2 detections/);
    fireEvent.click(bars[11]); assert.equal(bars[11].getAttribute('aria-pressed'), 'true');
    assert.equal(bars[5].querySelector('span').style.height, '0%');
    fireEvent.click(screen.getByRole('button', { name: 'Biggest fires', exact: true }));
    const groups = [...document.querySelectorAll('.insight-event-list button')];
    assert.equal(groups[0].getAttribute('aria-label'), 'Open fire group large-footprint');
    fireEvent.click(groups[0]);
    await waitFor(() => assert.equal(globalThis.insightLookups.length, 1));
    fireEvent.click(screen.getByRole('button', { name: 'Close panel' }));
    assert.equal(screen.queryByRole('complementary', { name: 'Insight panel' }), null);
  } finally { cleanup(); delete globalThis.insightLookups; }
});
