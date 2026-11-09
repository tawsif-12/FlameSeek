import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/location/intelligence' });
for (const name of ['window','document','HTMLElement','Element','Node','MutationObserver']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
await mkdir('.test-tmp-merged-events', { recursive: true });
await build({ entryPoints: ['src/pages/HarmonizedMapPage.tsx'], outfile: '.test-tmp-merged-events/events.mjs', bundle: true, format: 'esm', platform: 'node', packages: 'external', jsx: 'automatic', plugins: [{ name: 'source-boundaries', setup(b) {
  b.onResolve({ filter: /\.css$/ }, () => ({ path: 'css', namespace: 'empty' }));
  b.onLoad({ filter: /.*/, namespace: 'empty' }, () => ({ contents: '' }));
  b.onResolve({ filter: /^(react-leaflet|leaflet)$|api\/harmonized$|context\/(AppContext|LanguageContext)$|components\/HarmonizedProvenance$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
    path === 'react-leaflet' ? 'export const MapContainer=()=>null, CircleMarker=()=>null,GeoJSON=()=>null,TileLayer=()=>null,Tooltip=()=>null,useMap=()=>({}),useMapEvents=()=>({});' :
    path === 'leaflet' ? 'export default {};' :
    path.includes('AppContext') ? 'export const useAppContext=()=>({aoi:{name:"Test district",bbox:[90,23,91,24]}}),aoiBBox=a=>a.bbox,describeAoi=a=>a.name;' :
    path.includes('LanguageContext') ? 'export const useLanguage=()=>({lang:"en",t:k=>k==="back_to_list"?"Back to list":k,fmt:n=>String(n)});' :
    path.includes('HarmonizedProvenance') ? 'export default function Provenance(){return null};export const StatusPill=()=>null;' :
    'const data={meta:{default_window:"current",windows:{current:{}}},translation:{words:{en:{intensity:[]}}}};export const useSiteData=()=>({data});export const snapshotGet=(...args)=>globalThis.eventSource(...args);'
  }));
} }] });
const React = await import('react');
const { render, screen, fireEvent, cleanup } = await import('@testing-library/react');
const { MemoryRouter } = await import('react-router-dom');
const { default: Events } = await import('../.test-tmp-merged-events/events.mjs');

test('embedded event list opens details without translations and returns to the list inside one overview', async () => {
  const event = { fire_id: 'source-event', start_time: '2026-11-09T05:24:00Z', end_time: '2026-11-09T17:40:00Z', platforms_seen: 'Terra;Aqua', FRP_MODIS_max: 149.6, centroid_lat: 23.5, centroid_lon: 90.5 };
  globalThis.eventSource = async path => path === '/fires/search' ? { count: 1, data: [event] } : { data: event };
  render(React.createElement(MemoryRouter, null, React.createElement('main', null, React.createElement(Events, { embedded: true }))));
  try {
    fireEvent.click(await screen.findByRole('button', { name: /149.6 MW/ }));
    await screen.findByText('source-event');
    assert.ok(screen.getByText(event.start_time));
    assert.ok(screen.getByText(event.end_time));
    assert.equal(document.querySelectorAll('main').length, 1);
    assert.ok(screen.getByRole('region', { name: 'Fire events' }));
    fireEvent.click(screen.getByRole('button', { name: 'Back to list' }));
    assert.ok(await screen.findByRole('button', { name: /149.6 MW/ }));
    assert.equal(screen.queryByText('source-event'), null);
  } finally { cleanup(); delete globalThis.eventSource; }
});
