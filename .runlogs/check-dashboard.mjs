import { writeFile, mkdir, readFile } from 'node:fs/promises';
const targets = await fetch('http://127.0.0.1:9333/json/list').then(r=>r.json());
const target = targets.find(t=>t.type==='page' && (t.url==='about:blank' || t.url.startsWith('http://127.0.0.1:5173/')));
if (!target) throw new Error('Isolated test page missing');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let id=0; const waiting=new Map(); const errors=[];
ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=waiting.get(m.id);waiting.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const call=++id;waiting.set(call,{resolve,reject});ws.send(JSON.stringify({id:call,method,params}));});
const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;};
await send('Page.enable'); await send('Runtime.enable');
let area;
try {const data=JSON.parse(await readFile('frontend/.test-tmp-location/places.json','utf8'));const p=data.Bangladesh.find(p=>p.geometry);area={id:p.place_id,name:p.place_name||'Bangladesh',bbox:p.bbox,geometry:p.geometry,kind:'place'};}catch{}
if(!area){
 const data=await fetch('http://127.0.0.1:8000/api/places/search?q=Bangladesh',{signal:AbortSignal.timeout(20000)}).then(r=>r.json());
 const p=data.results.find(p=>p.geometry);if(!p)throw new Error('Actual Bangladesh boundary unavailable');
 area={id:p.place_id,name:p.place_name||'Bangladesh',bbox:p.bbox,geometry:p.geometry,kind:'place'};
}
const params=new URLSearchParams({area:JSON.stringify(area)});
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url:`http://127.0.0.1:5173/location/intelligence${params.toString().length > 4096 ? '#' : '?'}${params}`});
for(let n=0;n<100;n++){if(await evaluate('!!document.querySelector(".intelligence-map-summary")'))break;await new Promise(r=>setTimeout(r,300));}
await mkdir('screenshots/dashboard',{recursive:true});
const results=[];
for(const [name,width,height] of [['desktop',1440,1000],['tablet',1024,900],['mobile',390,844],['light',1440,1000]]){
 await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
 await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(name==='light'?'day':'night')};window.scrollTo(0,0);window.dispatchEvent(new Event('resize'));`);
 await new Promise(r=>setTimeout(r,500));
 const state=await evaluate(`(()=>{const rect=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,header:rect('.app-header'),title:rect('.intelligence-header'),sidebar:rect('.location-sidebar'),map:rect('.hz-map-frame'),titleFont:getComputedStyle(document.querySelector('.intelligence-header h2')).fontSize,nav:[...document.querySelectorAll('[aria-label="Location sections"] a')].map(a=>a.textContent),decorations:document.querySelectorAll('.fire-intelligence-dashboard .space-hero-orbit').length,metrics:document.querySelector('.intelligence-metrics').innerText,bodyError:document.querySelector('vite-error-overlay')!==null}})()`);
 const png=await send('Page.captureScreenshot',{format:'png'});await writeFile(`screenshots/dashboard/${name}.png`,Buffer.from(png.data,'base64'));
 results.push({name,...state});
}
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
const inspectSidebar=`(()=>{const s=document.querySelector('.location-sidebar'),n=s.querySelector('nav'),a=n.querySelector('a'),active=n.querySelector('a.active');return {width:s.getBoundingClientRect().width,background:getComputedStyle(s).backgroundColor,rowHeight:a.getBoundingClientRect().height,gap:getComputedStyle(n).gap,padding:getComputedStyle(s).paddingLeft,activeBackground:getComputedStyle(active).backgroundColor,activeColor:getComputedStyle(active).color,iconSizes:[...n.querySelectorAll('svg')].map(i=>i.getAttribute('width')),tooltips:[...n.querySelectorAll('a')].map(a=>a.title),mainX:document.querySelector('.location-content').getBoundingClientRect().x,visibleLabels:[...n.querySelectorAll('.location-sidebar-label')].filter(e=>getComputedStyle(e).display!=='none').length,identityVisible:getComputedStyle(s.querySelector('.location-identity')).display!=='none',footerVisible:getComputedStyle(s.querySelector('footer')).display!=='none'}})()`;
results.push({expandedSidebar:await evaluate(inspectSidebar)});
await evaluate(`document.querySelector('[aria-label="Collapse sidebar"]').click()`);
await new Promise(r=>setTimeout(r,250));
results.push({collapsedSidebar:await evaluate(inspectSidebar)});
const collapsedPng=await send('Page.captureScreenshot',{format:'png'});await writeFile('screenshots/dashboard/sidebar-collapsed.png',Buffer.from(collapsedPng.data,'base64'));
await evaluate(`document.querySelector('[aria-label="Expand sidebar"]').click()`);
await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
await evaluate(`document.querySelector('[aria-label="Open location navigation"]').click()`);
await new Promise(r=>setTimeout(r,250));
results.push({mobileDrawer:await evaluate(`!!document.querySelector('[role="dialog"][aria-label="Location navigation"]')`)});
const mobilePng=await send('Page.captureScreenshot',{format:'png'});await writeFile('screenshots/dashboard/sidebar-mobile.png',Buffer.from(mobilePng.data,'base64'));
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
results.push({drawerClosed:await evaluate(`!document.querySelector('[role="dialog"][aria-label="Location navigation"]')`)});
console.log(JSON.stringify({results,errors},null,2));
await writeFile('screenshots/dashboard/layout-check.json',JSON.stringify({results,errors},null,2));
ws.close();
