import assert from 'node:assert/strict';
import { test, afterEach } from 'node:test';
import { mkdir, readFile } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/search' });
for (const name of ['window','document','HTMLElement','Element','Node','MutationObserver','localStorage','Event','KeyboardEvent']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
let mobile = false;
window.matchMedia = () => ({ matches: mobile, addEventListener() {}, removeEventListener() {} });
await mkdir('.test-tmp-location', { recursive: true });
await build({ stdin: { contents: `export { default as SearchPage } from './src/pages/SearchPage'; export { default as Dashboard } from './src/pages/LocationDashboard'; export { AppProvider, useAppContext } from './src/context/AppContext'; export * from './src/api/locationRoutes';`, resolveDir: process.cwd() }, outfile: '.test-tmp-location/components.mjs', bundle: true, format: 'esm', platform: 'node', packages: 'external', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'feature-boundaries', setup(builder) {
  builder.onResolve({ filter: /api\/client$/ }, () => ({ path: 'client', namespace: 'test' }));
  builder.onResolve({ filter: /components\/AOISelector$/ }, () => ({ path: 'map', namespace: 'test' }));
  builder.onResolve({ filter: /\/(AreaIntelligencePage|FireGlobePage|FireMemoryPage|FireDnaPage|HarmonizedMapPage)$/ }, ({ path }) => ({ path: path.split('/').at(-1), namespace: 'test' }));
  builder.onLoad({ filter: /.*/, namespace: 'test' }, ({ path }) => ({ resolveDir: process.cwd(), loader: 'jsx', contents: path === 'client' ? `export const searchPlaces=(q,signal)=>globalThis.locationSearch(q,signal); export const resolvePlace=(id,signal)=>globalThis.locationResolve(id,signal); export const normalizeApiError=e=>e.message;` : path === 'map' ? `import {useAppContext} from './src/context/AppContext'; export default function Map(){const {setAoi}=useAppContext();return <button onClick={()=>setAoi(globalThis.drawnArea)}>Draw test boundary</button>;}` : `import {useEffect} from 'react';import {useLocation} from 'react-router-dom';import {useAppContext} from './src/context/AppContext';export default function Feature(){const state=useAppContext();const route=useLocation();useEffect(()=>{globalThis.featureWrites.push({area:state.aoi,save:state.setMemory});},[]);return <main><h1>${path}</h1><pre data-testid="feature-area">{JSON.stringify({area:state.aoi,memory:state.memory,locked:state.lockedArea,section:route.pathname})}</pre></main>;}` }));
} }] });
const React = await import('react');
const { render, screen, cleanup, waitFor, act } = await import('@testing-library/react');
const { default: userEvent } = await import('@testing-library/user-event');
const { BrowserRouter, Routes, Route } = await import('react-router-dom');
const { SearchPage, Dashboard, AppProvider, dashboardUrl, areaFromUrl, placeArea, featureHref, locationId } = await import('../.test-tmp-location/components.mjs');
const boundary = { type:'Polygon',coordinates:[[[90,23],[91,23],[91,24],[90,24],[90,23]]] };
const result = name => ({ name:`${name}, Bangladesh`,place_name:name,parent_region:'Chattogram, Bangladesh',type:'administrative',addresstype:'district',place_id:`osm:relation:${name}`,bbox:[90,23,91,24],center:[90.5,23.5],geometry:boundary });
const noakhali = placeArea(result('Noakhali'));
const bangladesh = { ...placeArea(result('Bangladesh')), bbox:[88,20,93,27], geometry:{type:'Polygon',coordinates:[[[88,20],[93,20],[93,27],[88,27],[88,20]]]}};
function mount(path='/search', {small=false,saved=null}={}) {
  mobile=small; globalThis.featureWrites=[];
  window.history.replaceState({},'',path); localStorage.clear();
  if(saved) localStorage.setItem('flameseek.analysis-state.v1',JSON.stringify({aoi:saved,memory:{old:true}}));
  render(React.createElement(AppProvider,null,React.createElement(BrowserRouter,null,React.createElement(Routes,null,
    React.createElement(Route,{path:'/search',element:React.createElement(SearchPage)}),
    React.createElement(Route,{path:'/location/:section',element:React.createElement(Dashboard)}),
    React.createElement(Route,{path:'/location',element:React.createElement(Dashboard)})))));
}
const current = () => JSON.parse(screen.getByTestId('feature-area').textContent);
async function select(query) { await userEvent.type(screen.getByRole('combobox'),`${query}{Enter}`); await screen.findAllByRole('option'); await userEvent.keyboard('{ArrowDown}{Enter}'); await screen.findByTestId('feature-area'); }
afterEach(()=>{cleanup();globalThis.locationSearch=undefined;});

test('Explore starts empty and debounces typing requests',async()=>{
  let calls=0;globalThis.locationSearch=async()=>{calls++;return[];};mount('/search',{saved:bangladesh});
  assert.equal(screen.getByRole('combobox').value,'');assert.equal(screen.queryByText('Selected area'),null);
  assert.equal(screen.queryByRole('link',{name:'Fire Events'}),null);
  assert.ok(screen.getByRole('button',{name:'Select an area on the map'}));
  await userEvent.type(screen.getByRole('combobox'),'Noakhali');assert.equal(calls,0);
});

test('typing shows suggestions without submitting and Enter selects the highlighted location',async()=>{
  const calls=[];globalThis.locationSearch=async q=>{calls.push(q);return[result('Noakhali')];};mount();
  await userEvent.type(screen.getByRole('combobox'),'fires in Noakhali');
  assert.equal(calls.length,0);
  await screen.findAllByRole('option');
  assert.deepEqual(calls,['fires in Noakhali']);
  assert.equal(screen.getByRole('combobox').getAttribute('aria-expanded'),'true');
  await userEvent.keyboard('{ArrowDown}{Enter}');
  await screen.findByTestId('feature-area');
});

test('select Noakhali then all four sections retain the exact boundary; refresh, Back and Forward restore section',async()=>{
  globalThis.locationSearch=async()=>[result('Noakhali')];mount();await select('Noakhali');
  assert.equal(current().section,'/location/intelligence');
  assert.deepEqual([...screen.getByRole('navigation',{name:'Location sections'}).querySelectorAll('a')].map(a=>a.getAttribute('aria-label')), ['Fire Intelligence','Fire Now','Burning Calendar','Fire DNA']);
  for(const [label,section] of [['Fire Intelligence','intelligence'],['Fire Now','now'],['Burning Calendar','calendar'],['Fire DNA','dna']]) {
    await userEvent.click(screen.getByRole('link',{name:label,exact:true}));
    await waitFor(()=>assert.equal(current().section,`/location/${section}`));
    assert.deepEqual(current().area,noakhali);assert.equal(current().locked,true);
    assert.equal(screen.getByRole('link',{name:label,exact:true}).getAttribute('aria-current'),'page');
    assert.equal(new URLSearchParams(window.location.search).get('location_id'),locationId(noakhali));
  }
  await act(async()=>window.history.back());await waitFor(()=>assert.equal(current().section,'/location/calendar'));
  await act(async()=>window.history.forward());await waitFor(()=>assert.equal(current().section,'/location/dna'));
  const refreshUrl=window.location.pathname+window.location.search;cleanup();mount(refreshUrl,{saved:bangladesh});
  await screen.findByTestId('feature-area');assert.deepEqual(current().area,noakhali);assert.equal(current().memory,null);
});

test('switch to Bangladesh clears old data and rejects a late write from the previous location',async()=>{
  globalThis.locationSearch=async q=>q==='Bangladesh'?[{...result('Bangladesh'),...bangladesh}]:[result('Noakhali')];
  mount();await select('Noakhali');const old=globalThis.featureWrites[0];
  await userEvent.click(screen.getByRole('button',{name:'Change location'}));
  assert.equal(screen.getByRole('combobox').value,'');await select('Bangladesh');
  await act(async()=>old.save({old:true,aoi:noakhali}));
  assert.deepEqual(current().area,bangladesh);assert.equal(current().memory,null);
  for(const label of ['Fire Now','Burning Calendar','Fire DNA']){
    await userEvent.click(screen.getByRole('link',{name:label,exact:true}));await waitFor(()=>assert.deepEqual(current().area,bangladesh));
  }
});

test('point results require map confirmation; custom polygon and radius URLs round-trip',async()=>{
  globalThis.locationSearch=async()=>[{...result('Noakhali'),geometry:null}];globalThis.drawnArea={name:'Custom area',geometry:boundary,kind:'polygon'};
  mount();await userEvent.type(screen.getByRole('combobox'),'Noakhali{Enter}');await screen.findByRole('option');await userEvent.keyboard('{ArrowDown}{Enter}');
  assert.ok(screen.getByText(/Only a point/));assert.equal(screen.queryByTestId('feature-area'),null);
  await userEvent.click(screen.getByRole('button',{name:'Select an area on the map'}));
  await userEvent.click(screen.getByRole('button',{name:'Draw test boundary'}));await userEvent.click(screen.getByRole('button',{name:'Open location dashboard'}));
  await screen.findByTestId('feature-area');assert.deepEqual(current().area,globalThis.drawnArea);
  const radius={center:[90,24],radius_km:12.5,kind:'radius'};assert.deepEqual(areaFromUrl(new URL(dashboardUrl(radius),'http://localhost').search),radius);
  assert.equal(areaFromUrl('?area=invalid'),null);
  assert.equal(featureHref('/fire-map?date=2026-11-09',radius,true).startsWith('/location/now?'),true);
});

test('desktop collapse keeps accessible labels; mobile drawer supports section navigation, focus and Escape',async()=>{
  mount(dashboardUrl(noakhali));await screen.findByTestId('feature-area');
  await userEvent.click(screen.getByRole('button',{name:'Collapse sidebar'}));
  assert.ok(document.querySelector('.sidebar-collapsed'));assert.equal(screen.getByRole('link',{name:'Fire Intelligence'}).title,'Fire Intelligence');
  cleanup();mount(dashboardUrl(noakhali),{small:true});await screen.findByTestId('feature-area');
  assert.equal(screen.queryByRole('navigation',{name:'Location sections'}),null);
  const toggle=screen.getByRole('button',{name:'Open location navigation'});await userEvent.click(toggle);
  assert.ok(screen.getByRole('dialog',{name:'Location navigation'}));
  await userEvent.click(screen.getByRole('link',{name:'Fire Now'}));await waitFor(()=>assert.equal(current().section,'/location/now'));
  assert.equal(screen.queryByRole('dialog'),null);await userEvent.click(toggle);await userEvent.keyboard('{Escape}');
  assert.equal(screen.queryByRole('dialog'),null);assert.equal(document.activeElement,toggle);
});

test('query changes cancel stale results; error, retry and no-results states remain usable',async()=>{
  let finish;globalThis.locationSearch=()=>new Promise(resolve=>{finish=resolve;});mount();
  const field=screen.getByRole('combobox');await userEvent.type(field,'Noakhali{Enter}');await userEvent.type(field,'x');
  await act(async()=>finish([result('Noakhali')]));assert.equal(screen.queryByRole('option'),null);
  globalThis.locationSearch=async()=>{throw new Error('Geocoder unavailable');};await userEvent.click(screen.getByRole('button',{name:'Search',exact:true}));await screen.findByRole('alert');
  globalThis.locationSearch=async()=>[];await userEvent.click(screen.getByRole('button',{name:'Retry search'}));await screen.findByText(/No results for/);
  await userEvent.click(screen.getByRole('button',{name:'Clear location search'}));assert.equal(field.value,'');assert.equal(document.activeElement,field);
});

test('live geocoder fixture, when present, preserves the actual Noakhali and Bangladesh boundaries',async()=>{
  let data;try{data=JSON.parse(await readFile('.test-tmp-location/places.json','utf8'));}catch{return;}
  for(const query of ['Noakhali','Bangladesh']){
    const resolved=data[query].find(place=>place.geometry);assert.ok(resolved);const selected=placeArea(resolved);
    for(const section of ['intelligence','now','memory','dna','calendar','events']){const url=new URL(dashboardUrl(selected,section),'http://localhost');assert.deepEqual(areaFromUrl(url.search,url.hash).geometry,resolved.geometry);assert.ok(url.search.length<5000);}
  }
});

test('large boundaries use a refreshable fragment and do not exceed request-line limits',async()=>{
  const ring=Array.from({length:600},(_,i)=>[90+Math.cos(i/600*Math.PI*2),24+Math.sin(i/600*Math.PI*2)]);ring.push(ring[0]);
  const large={name:'Large custom boundary',geometry:{type:'Polygon',coordinates:[ring]},kind:'polygon'};
  const url=dashboardUrl(large,'events');const parsed=new URL(url,'http://localhost');
  assert.ok(parsed.hash.startsWith('#area='));assert.ok(parsed.search.length<500);
  assert.deepEqual(areaFromUrl(parsed.search,parsed.hash),large);
  mount(url,{saved:bangladesh});await screen.findByTestId('feature-area');assert.deepEqual(current().area,large);
});

test('merged links preserve the location and event query while legacy sections redirect',async()=>{
  for (const [oldSection, destination] of [['memory','calendar'],['events','intelligence']]) {
    const canonical = new URL(dashboardUrl(noakhali, oldSection, { event: 'existing-event' }), 'http://localhost');
    assert.equal(canonical.pathname, `/location/${destination}`);
    assert.equal(canonical.searchParams.get('event'), 'existing-event');
    assert.deepEqual(areaFromUrl(canonical.search), noakhali);
    if (oldSection === 'events') assert.equal(canonical.searchParams.get('view'), 'events');
    mount(`/location/${oldSection}?${new URLSearchParams({ area: JSON.stringify(noakhali), event: 'existing-event' })}`);
    await screen.findByTestId('feature-area');
    assert.equal(current().section, `/location/${destination}`);
    assert.deepEqual(current().area, noakhali);
    assert.equal(new URLSearchParams(window.location.search).get('event'), 'existing-event');
    cleanup();
  }
});


test('fresh suggestions resolve their boundary on selection instead of treating a point as an area', async () => {
  let resolutions = 0;
  globalThis.locationSearch = async () => [{ ...result('Chattogram District'), geometry: null, requires_resolution: true, place_id: 'osm:relation:3824577' }];
  globalThis.locationResolve = async id => { resolutions++; assert.equal(id, 'osm:relation:3824577'); return { ...result('Chattogram District'), place_id: id }; };
  mount();
  try {
    await userEvent.type(screen.getByRole('combobox'), 'chittagong');
    await screen.findAllByRole('option');
    assert.equal(resolutions, 0);
    await userEvent.keyboard('{ArrowDown}{Enter}');
    await screen.findByTestId('feature-area');
    assert.equal(resolutions, 1);
    assert.equal(current().area.id, 'osm:relation:3824577');
    assert.deepEqual(current().area.geometry, boundary);
  } finally { delete globalThis.locationResolve; }
});
