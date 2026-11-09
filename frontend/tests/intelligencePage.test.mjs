import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/location/intelligence'});
for(const n of ['window','document','HTMLElement','Element','Node','MutationObserver'])globalThis[n]=dom.window[n];
Object.defineProperty(globalThis,'navigator',{value:dom.window.navigator,configurable:true});
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const area={name:'Test region',bbox:[90,23,91,24]};
globalThis.intelligenceArea=area;
await mkdir('.test-tmp-intelligence',{recursive:true});
await build({entryPoints:['src/pages/AreaIntelligencePage.tsx'],outfile:'.test-tmp-intelligence/page.mjs',bundle:true,format:'esm',platform:'node',packages:'external',jsx:'automatic',plugins:[{name:'boundaries',setup(b){
 b.onResolve({filter:/\.css$/},()=>({path:'css',namespace:'empty'}));b.onLoad({filter:/.*/,namespace:'empty'},()=>({contents:''}));
 b.onResolve({filter:/^react-plotly.js$|^react-leaflet$|api\/client$|context\/AppContext$|components\/(HarmonizedProvenance|PipelineFreshness)$|\.\/HarmonizedMapPage$/},({path})=>({path,namespace:'test'}));
 b.onLoad({filter:/.*/,namespace:'test'},({path})=>({resolveDir:process.cwd(),contents:
 path==='react-plotly.js'?'export default function Plot(){return null;}':
 path==='react-leaflet'?'export const GeoJSON=()=>null,MapContainer=()=>null,Rectangle=()=>null,TileLayer=()=>null,Tooltip=()=>null,useMap=()=>({fitBounds(){}});':
 path.includes('AppContext')?'export const useAppContext=()=>({aoi:globalThis.intelligenceArea,lockedArea:globalThis.intelligenceArea,setMemory(){}}),aoiBBox=a=>a.bbox,aoiContains=(a,lat,lon)=>lon>=a.bbox[0]&&lon<=a.bbox[2]&&lat>=a.bbox[1]&&lat<=a.bbox[3],describeAoi=a=>a.name;':
 path.includes('HarmonizedProvenance')?'export const StatusPill=()=>null;':
 path.includes('PipelineFreshness')?'export default function Freshness(){return null;}':
 path.includes('HarmonizedMapPage')?'import React from "react";export default function Events(p){return React.createElement("section",{"aria-label":"Embedded events"},p.summary);}':
 'export const normalizeApiError=e=>e.message;export const savedFireMemory=async()=>globalThis.intelligenceSaved,savedPlacePipeline=async()=>null;export const startFireMemory=(a,y)=>{globalThis.intelligenceRequests.push(y);return new Promise(()=>{});},startPlacePipeline=()=>new Promise(()=>{}),runJob=async p=>await p,getHotspotsInBox=async()=>{if(globalThis.intelligenceLiveError)throw new Error("NASA unavailable");return {hotspots:globalThis.intelligenceLive};};'
 }));
}}]});
const React=await import('react');const{render,screen,fireEvent,cleanup}=await import('@testing-library/react');const{MemoryRouter}=await import('react-router-dom');const{default:Page}=await import('../.test-tmp-intelligence/page.mjs');
const saved={period:{start:'2026-11-01',end:'2026-11-05',years:5},daily:[{date:'2026-11-01',hotspot_count:2}],monthly:[],summary:{total_harmonized_activity:1.5,total_hotspots:2},events:{count:1},seasonal_profile:{peak_months:[],quiet_months:[],months:[],years:[]},critical_periods:[],change_points:{change_points:[],status:'unavailable'},provenance:{generated_at:'2026-11-06T00:00:00Z'}};
test('dashboard retains the last valid result when history changes and does not imply continuous coverage',async()=>{
 globalThis.intelligenceSaved=saved;globalThis.intelligenceRequests=[];globalThis.intelligenceLive=[{lat:23.5,lon:90.5,acq_datetime:'2026-11-09T00:00:00Z'}];
 render(React.createElement(MemoryRouter,null,React.createElement(Page)));
 try{
  await screen.findByText('1.5');
  assert.ok(screen.getByRole('heading',{name:'Fire Intelligence',exact:true}));
  assert.equal(document.querySelectorAll('.space-hero-orbit').length,0);
  assert.equal(document.querySelectorAll('.intelligence-metric').length,4);
  assert.ok(screen.getByText('Unverified'));
  assert.ok(screen.getByRole('region',{name:'Embedded events'}));
  fireEvent.click(screen.getByRole('button',{name:'20 years',exact:true}));
  assert.equal(screen.getByRole('button',{name:'20 years',exact:true}).getAttribute('aria-pressed'),'true');
  assert.ok(screen.getByText('1.5'));
  assert.ok(screen.getByText(/Showing the last result while 20-year output loads/));
  assert.equal(document.querySelector('.intelligence-coverage').open,false);
  assert.equal(document.querySelector('.intelligence-analysis').open,false);
  assert.ok(screen.getByRole('listitem',{name:'2026-11: 2 detections'}));
 }finally{cleanup();}
});
test('live API failures stay unavailable instead of showing a zero observation count',async()=>{
 globalThis.intelligenceSaved=null;globalThis.intelligenceRequests=[];globalThis.intelligenceLiveError=true;
 render(React.createElement(MemoryRouter,null,React.createElement(Page)));
 try{
  await screen.findByText('Current observations unavailable: NASA unavailable');
  const recent=[...document.querySelectorAll('.intelligence-metric')].find(e=>e.textContent.includes('Recent detections'));
  assert.equal(recent.querySelector('strong').textContent,'Unavailable');
 }finally{cleanup();delete globalThis.intelligenceLiveError;}
});
