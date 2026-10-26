// MapLibreへ渡す高さを検証。実際のWebGL表示は別途ブラウザで確認する。
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const els={},ids=[...fs.readFileSync('index.html','utf8').matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
for(const id of ids)els[id]={value:id==='v3d-ex'?'3':'',checked:id==='stationNames',listeners:{},addEventListener(n,f){this.listeners[n]=f;},clientWidth:1024,clientHeight:768,classList:{add(){},remove(){}}};
const sources={};let instance;
class MapStub{
 constructor(options){instance=this;this.options=options;this.center={lng:options.center[0],lat:options.center[1]};this.zoom=options.zoom;this.events={};
 for(const k of ['dragPan','touchZoomRotate','touchPitch','dragRotate','scrollZoom'])this[k]={enable(){this.enabled=true;},enableRotation(){this.rotation=true;}};
 }
 addControl(){}
 on(name,fn){this.events[name]=fn;}
 getCenter(){return this.center;}
 getZoom(){return this.zoom;}
 addSource(id,source){sources[id]={...source,setData(data){this.data=data;}};}
 addLayer(){}
 getSource(id){return sources[id];}
 loaded(){return false;} // GeoJSON処理中でも、作成済みソースへの更新を止めない
 resize(){}
 jumpTo(o){this.center={lng:o.center[0],lat:o.center[1]};this.zoom=o.zoom??this.zoom;this.events.moveend();}
}
const markers=new Set();
class Marker{constructor(options){this.element=options.element;}setLngLat(){return this;}addTo(){markers.add(this);return this;}remove(){markers.delete(this);}}
const platform=(id,lv,type='LineString',kind='platform')=>({id,type:'Feature',geometry:{type,coordinates:type==='Point'?[139.7,35.68]:type==='Polygon'?[[[139.7,35.68],[139.7001,35.68],[139.7,35.6801],[139.7,35.68]]]:[[139.7,35.68],[139.7001,35.68]]},properties:{station:'検証',kind,levels:lv,color:'#123456'}});
const data={features:[platform('b',[-2]),platform('g',[0]),platform('e',[2],'Polygon'),platform('unknown',[]),platform('stairs',[-2,2],'LineString','stairs'),platform('ev',[-2,2],'Point','elevator'),platform('exit',[2],'Point','exit')]};
const events={};
const window={MAP_DATA:{roads:[],slopes:{slopes:[]}},addEventListener(n,f){events[n]=f;}};
const document={getElementById:id=>els[id],body:{classList:{add(){},remove(){}}},createElement:()=>({})};
const context=vm.createContext({window,document,maplibregl:{Map:MapStub,Marker,NavigationControl:class{}}});
window.maplibregl=context.maplibregl;
vm.runInContext(fs.readFileSync('walk3d.js','utf8'),context);
data.stations=[{name:'検証',pos:[35.68,139.7]},{name:'隣',pos:[35.69,139.7]}];
let selected,center={lat:35.6801,lng:139.7002},zoom=15.5;
const map={getCenter:()=>center,getZoom:()=>zoom,setView(p,z){center={lat:p[0],lng:p[1]};zoom=z;}};
const control=window.initWalk3D({data,map,interiors:{selectStation(name){selected=name;}}});
control.toggle();assert.ok(instance);instance.events.load();
const stationLabels=()=>[...markers].filter(m=>m.element.className.includes('station-name-label'));
assert.equal(stationLabels().length,1);assert.equal(stationLabels()[0].element.innerHTML,'検証駅');
els.stationNames.checked=false;els.stationNames.listeners.change();assert.equal(stationLabels().length,0);
els.stationNames.checked=true;els.stationNames.listeners.change();assert.equal(stationLabels().length,1);
assert.equal(selected,'検証');assert.equal(instance.getZoom(),15.5);
assert.equal(instance.getCenter().lng,139.7002);
for(const k of ['dragPan','touchZoomRotate','touchPitch','dragRotate','scrollZoom'])assert.ok(instance[k].enabled);
assert.ok(instance.touchZoomRotate.rotation);
const ground=sources['v3d-ground'].data.features[0].properties.top;
const below=sources['v3d-under'].data.features,above=sources['v3d-above'].data.features;
assert.ok(below.some(f=>f.properties.top<ground));
assert.ok(above.some(f=>f.properties.base>ground&&f.properties.top===ground+4)); // level 0
assert.ok(above.some(f=>f.properties.base>ground&&f.properties.top===ground+34)); // level 2 × 5m × 3倍 + 表示余白
assert.ok(above.some(f=>f.properties.base<ground&&f.properties.top>ground)); // 地下↔高架の階段/EV
assert.equal(below.length,1); // 階未収録のホームは地上にも地下にも創作しない
assert.ok(sources['v3d-exit'].data.features.every(f=>f.properties.base<=f.properties.top));
assert.match(els['v3d-legend-levels'].innerHTML,/地下2階/);
assert.match(els['v3d-legend-levels'].innerHTML,/level 0/);
assert.match(els['v3d-legend-levels'].innerHTML,/上層/);
assert.match(els['v3d-exits'].textContent,/上層/);
els['v3d-ex'].value='1';els['v3d-ex'].oninput();
assert.ok(sources['v3d-above'].data.features.some(f=>f.properties.top===sources['v3d-ground'].data.features[0].properties.top+14));
console.log('PASS: 地下・level 0・高架の高さ、階段/EVの跨階、上層への出口、欠測非補完、誇張倍率');

instance.jumpTo({center:[139.7,35.69],zoom:16.25});
assert.equal(selected,'隣');assert.match(els['v3d-location'].textContent,/隣駅付近/);
assert.equal(sources['v3d-under'].data.features.length,0);
events['walk-interiors-loaded']();assert.equal(instance.getCenter().lat,35.69);
instance.jumpTo({center:[139.5,35.5],zoom:13});
assert.match(els['v3d-location'].textContent,/対応駅なし/);
assert.equal(sources['v3d-under'].data.features.length,0);
assert.equal(sources['v3d-ground'].data.features.length,1);
control.toggle();assert.equal(center.lat,35.5);assert.equal(zoom,13);
center={lat:35.68,lng:139.7};zoom=18;control.toggle();
assert.equal(instance.getCenter().lat,35.68);assert.equal(instance.getZoom(),18);
console.log('PASS: 中心・ズーム引継ぎ、近接駅切替、駅なし、読込時カメラ維持、タッチ設定、平面復帰・再表示');
