import assert from 'node:assert/strict';
import { test, afterEach } from 'node:test';
import { mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {url:'http://localhost/search'});
for(const name of ['window','document','HTMLElement','Element','Node','MutationObserver','localStorage','Event','SVGElement']) globalThis[name]=dom.window[name];
Object.defineProperty(globalThis,'navigator',{value:dom.window.navigator,configurable:true});
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const create = document.createElementNS.bind(document);
document.createElementNS=(ns,name,...args)=>{const element=create(ns,name,...args);if(name==='svg')element.createSVGRect=()=>({});return element;};
const L=(await import('leaflet')).default;globalThis.L=L;window.L=L;
let actualMap;
const initialize=L.Map.prototype.initialize;
L.Map.prototype.initialize=function(...args){initialize.apply(this,args);actualMap=this;};
L.Map.prototype.getSize=()=>L.point(1024,768);
await mkdir('.test-tmp-location-map',{recursive:true});
await build({stdin:{contents:`export {default as Selector} from './src/components/AOISelector'; export {AppProvider,useAppContext} from './src/context/AppContext'; export * from './src/api/locationRoutes';`,resolveDir:process.cwd()},outfile:'.test-tmp-location-map/components.mjs',bundle:true,format:'esm',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'offline-geocoder',setup(builder){builder.onResolve({filter:/\.css$/},()=>({path:'css',namespace:'empty'}));builder.onLoad({filter:/.*/,namespace:'empty'},()=>({contents:''}));builder.onResolve({filter:/api\/client$/},()=>({path:'client',namespace:'test'}));builder.onLoad({filter:/.*/,namespace:'test'},()=>({contents:`export const searchPlaces=async()=>[];export const normalizeApiError=e=>e.message;` }));}}]});
const React=await import('react');
const {render,screen,cleanup,act}=await import('@testing-library/react');
const {BrowserRouter}=await import('react-router-dom');
const {Selector,AppProvider,useAppContext,areaFromUrl,dashboardUrl}=await import('../.test-tmp-location-map/components.mjs');
function ReadArea(){return React.createElement('pre',{'data-testid':'area'},JSON.stringify(useAppContext().aoi));}
afterEach(cleanup);

test('real Leaflet drawing events preserve rectangle, polygon and radius through dashboard URLs',async()=>{
  localStorage.clear();
  render(React.createElement(AppProvider,null,React.createElement(BrowserRouter,null,React.createElement(React.Fragment,null,React.createElement(Selector,{mapOnly:true}),React.createElement(ReadArea)))));
  for(const layer of [L.rectangle([[23,90],[24,91]]),L.polygon([[23,90],[23,91],[24,91],[24,90]]),L.circle([24,90],{radius:12500})]){
    await act(async()=>actualMap.fire(L.Draw.Event.CREATED,{layer}));
    const area=JSON.parse(screen.getByTestId('area').textContent);
    assert.ok(area);assert.deepEqual(areaFromUrl(new URL(dashboardUrl(area),'http://localhost').search),area);
    if(layer instanceof L.Circle){assert.equal(area.radius_km,12.5);assert.deepEqual(area.center,[90,24]);}
    else if(layer instanceof L.Rectangle)assert.deepEqual(area.bbox,[90,23,91,24]);
    else assert.equal(area.geometry.type,'Polygon');
  }
});
