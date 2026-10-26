// 通信なしの表示ロジック検証。Leaflet/DOMの代替なので、ブラウザ描画の検証ではない。
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.options=[];this.children=[];this.listeners={};this.checked=false;this.value='';this.attrs={};this.classList={toggle(){}};}
 add(o){this.options.push(o);if(this.options.length===1)this.value=o.value;}
 replaceChildren(...o){this.options=[];o.forEach(x=>this.add(x));}
 get selectedOptions(){return this.options.filter(o=>o.value===this.value);}
 addEventListener(n,f){(this.listeners[n]??=[]).push(f);}
 trigger(n){this['on'+n]?.();for(const f of this.listeners[n]||[])f();}
 append(x){this.children.push(x);}
 querySelector(){return new Element();}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
}
class Layer{
 constructor(kind,points,options){this.kind=kind;this.points=points;this.options=options;this.layers=new Set();this.events={};}
 addTo(g){g.addLayer(this);return this;}
 addLayer(x){this.layers.add(x);return this;}
 removeLayer(x){this.layers.delete(x);return this;}
 hasLayer(x){return this.layers.has(x);}
 clearLayers(){this.layers.clear();return this;}
 getLayers(){return [...this.layers];}
 bindTooltip(text,options){this.tooltip={text,options};return this;}
 bindPopup(text){this.popup=text;return this;}
 openPopup(){this.popupHTML=typeof this.popup==='function'?this.popup():this.popup;return this;}
 getBounds(){return this;}
 on(n,f){(this.events[n]??=[]).push(f);return this;}
 fire(n,arg){for(const f of this.events[n]||[])f(arg);}
}
class MapStub extends Layer{
 constructor(){super('map');this.zoom=undefined;this.panes={markerPane:{style:{}}};this.attributionControl={addAttribution(){}};}
 createPane(n){this.panes[n]={style:{}};}
 getPane(n){return this.panes[n];}
 getZoom(){return this.zoom;}
 getSize(){return {x:1280,y:900};}
 latLngToContainerPoint(p){assert.ok(Number.isFinite(this.zoom),'駅名の座標計算前に地図の表示位置を設定する');return {x:(p[1]-139.7)*10000,y:(35.72-p[0])*10000};}
 setZoom(z){this.zoom=z;this.fire('zoomend');}
 fitBounds(b,o){this.setZoom(o.maxZoom);}
 getBounds(){return {getSouth:()=>35.68,getNorth:()=>35.69,getWest:()=>139.735,getEast:()=>139.745};}
 setView(p,z){this.setZoom(z);}
 closePopup(){}
 invalidateSize(){}
}
const html=fs.readFileSync('index.html','utf8'),elements={};
for(const m of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)){
 elements[m[1]]=new Element();elements[m[1]].checked=/\bchecked\b/.test(m[0]);
}
elements['subway-level'].value='all';
const document={getElementById:id=>{assert.ok(elements[id],`HTMLに${id}が存在する`);return elements[id];},createElement:()=>new Element()};
const make=kind=>(points,options)=>new Layer(kind,points,options);
const L={map:()=>new MapStub(),layerGroup:make('group'),polyline:make('polyline'),polygon:make('polygon'),circleMarker:make('circle'),marker:make('marker'),imageOverlay:make('image'),tileLayer:make('tiles'),divIcon:x=>x,latLngBounds:x=>({contains:()=>true}),
 geoJSON:(f,o)=>Object.assign(new Layer('geoJSON',null,o),{feature:f}),control:{scale:()=>new Layer(),layers:()=>new Layer()}};
const window={L,innerWidth:1280,innerHeight:900,addEventListener(){},dispatchEvent(){}};
const index=JSON.parse(fs.readFileSync('data/station-index.json'));
const fetch=async url=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(url,'utf8'))});
const context=vm.createContext({window,L,document,location:{protocol:'http:'},localStorage:{getItem:()=>null},setTimeout(){},clearTimeout(){},fetch,Event:class{},console,Option:function(text,value){this.textContent=text;this.value=value;}});
(async()=>{
for(const path of ['data.js','area-loader.js','station-interiors.js','station-labels.js','app.js'])vm.runInContext(fs.readFileSync(path,'utf8'),context,{filename:path});
for(let i=0;i<100&&!window.walkBurdenMap?.ready;i++)await new Promise(r=>setImmediate(r));
assert.ok(window.walkBurdenMap?.ready);
const {map,groups,stationLabels}=window.walkBurdenMap;
const geoFeatures=()=>groups.interiors.getLayers().filter(x=>x.feature).map(x=>x.feature);
const selectedLevel=value=>{elements['interior-level'].value=value;elements['interior-level'].trigger('change');};
assert.ok(!('samples' in window.MAP_DATA));assert.ok(!('samples' in groups));assert.ok(map.hasLayer(groups.slopes));
assert.ok(stationLabels);assert.ok(map.hasLayer(groups.stationNames));
assert.ok(groups.stationNames.getLayers().length>0);
elements.stationNames.checked=false;elements.stationNames.trigger('change');assert.ok(!map.hasLayer(groups.stationNames));
elements.stationNames.checked=true;elements.stationNames.trigger('change');assert.ok(map.hasLayer(groups.stationNames));
const {interiorControl}=window.walkBurdenMap;
assert.equal(index.stations.length,96);
const allData=index.stations.map(s=>({...s,data:JSON.parse(fs.readFileSync(s.url))}));
// 全駅の選択を確認し、各駅の実際の地物数から描画件数を検証する。
for(const station of allData){
 await interiorControl.selectStation(station.name);
 elements['interior-focus'].onclick();
 selectedLevel('all');
 assert.equal(elements['interior-station'].value,station.name);
 assert.ok(station.lines.includes(elements['interior-line'].value));
 assert.equal(map.getZoom(),18);
 const fs=station.data.features;
 assert.equal(geoFeatures().filter(f=>f.properties.kind==='platform').length,fs.filter(f=>f.properties.kind==='platform').length);
 assert.ok(geoFeatures().every(f=>f.properties.station===station.name));
 const exits=()=>groups.interiors.getLayers().filter(x=>x.kind==='circle');
 assert.equal(exits().length,fs.filter(f=>f.properties.kind==='exit').length);
 assert.ok(exits().every(x=>x.tooltip.options.permanent));
 for(const level of [...station.levels,'unknown']){
  selectedLevel(String(level));
  assert.ok(geoFeatures().every(f=>level==='unknown'?!f.properties.levels.length:f.properties.levels.includes(level)));
 }
 selectedLevel('all');
 elements['interior-exits'].checked=false;elements['interior-exits'].trigger('change');assert.equal(exits().length,0);
 elements['interior-exits'].checked=true;elements['interior-exits'].trigger('change');
}
const multi=allData.find(s=>s.data.features.some(f=>f.geometry.type!=='Point'&&f.properties.levels.length>1));
assert.ok(multi);
await interiorControl.selectStation(multi.name);
const feature=multi.data.features.find(f=>f.geometry.type!=='Point'&&f.properties.levels.length>1);
for(const level of feature.properties.levels){selectedLevel(String(level));assert.ok(geoFeatures().some(f=>f.id===feature.id));}
selectedLevel('all');
const suppressedCount=groups.subway.getLayers().length;
elements.interiors.checked=false;elements.interiors.trigger('change');
assert.equal(groups.interiors.getLayers().length,0);assert.ok(!map.hasLayer(groups.interiors));
assert.equal(groups.subway.getLayers().length,suppressedCount);
elements.interiors.checked=true;elements.interiors.trigger('change');
map.setZoom(15);assert.equal(groups.interiors.getLayers().length,1);
map.setZoom(16);assert.ok(geoFeatures().every(f=>f.properties.kind==='platform'));
map.setZoom(17);assert.ok(geoFeatures().some(f=>f.properties.kind!=='platform'));
elements.slopes.checked=false;elements.slopes.trigger('change');assert.ok(!map.hasLayer(groups.slopes));
elements.slopes.checked=true;elements.slopes.trigger('change');assert.ok(map.hasLayer(groups.slopes));
const savedZoom=map.getZoom();
await interiorControl.selectStation(index.stations[0].name);
assert.equal(map.getZoom(),savedZoom);
assert.equal(interiorControl.isLoading(),false);
assert.ok(/fetch/.test(fs.readFileSync('station-interiors.js','utf8')));
console.log('PASS: アプリ初期化、96駅の選択・階・出口件数、複数階の保持、駅名・坂切替、ズーム別表示、静的JSON遅延取得');
})().catch(e=>{console.error(e);process.exitCode=1;});
