'use strict';
// 国土地理院の地表標高・道路勾配とOSMの駅構内を表示。
if (!window.L) {
  document.getElementById('map-status').textContent='地図ライブラリが読み込めません。vendorフォルダを同じ場所に置いてください。';
} else {
(async()=>{
const d=window.MAP_DATA;
// 同梱範囲外にも移動できる。坂・構内は収録範囲のみ表示。
const map=L.map('map',{zoomControl:true,minZoom:12,maxZoom:19});
const mobile=()=>window.innerWidth<=760;
function fit(bounds){map.fitBounds(bounds,{paddingTopLeft:mobile()?[18,130]:[70,230],paddingBottomRight:mobile()?[25,90]:[390,70],maxZoom:17});}
// 駅名の画面座標計算や背景の範囲判定より先に、表示位置を確定する。
const bounds=L.latLngBounds(d.bounds);
fit(bounds);
L.control.scale({position:'bottomleft',imperial:false}).addTo(map);
const panes=[['context',210],['roads',220],['slopes',345],['subway',336],['subwaytop',395],['stationNames',650]];
for(const [name,z] of panes){map.createPane(name);map.getPane(name).style.zIndex=z;}
map.getPane('stationNames').style.pointerEvents='none';
let labelStations=[];
function prepareBaseStyle(style){
 // 対応駅の名前は独自ラベルに一本化。駅アイコンや未対応駅の名前は残す。
 const names=[...new Set(labelStations.flatMap(s=>[s.name,...(s.members||[]).map(m=>m.name)]).flatMap(n=>[n,n+'駅']))];
 for(const layer of style.layers||[])if(layer['source-layer']==='poi'&&layer.layout?.['text-field']){
  const name=['coalesce',['get','name:ja'],['get','name'],''];
  layer.layout['text-field']=['case',['all',['==',['get','class'],'rail'],['in',name,['literal',names]]],'',layer.layout['text-field']];
 }
 return style;
}
// 情報量の多いポップアップは画面の6割までの高さにして中をスクロール
const popH=()=>Math.max(260,Math.round(window.innerHeight*.62));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sourceNote=(source,method)=>source?`<div class="source-note">${esc(method)}<br><a href="${esc(source)}" target="_blank" rel="noopener noreferrer">位置の出典を開く ↗</a></div>`:'';
// ---------- 背景・道路（同梱データ） ----------
const vector=L.layerGroup();
function drawVector(){
vector.clearLayers();
for(const c of d.context){
 if(c.kind==='rail'){L.polyline(c.points,{pane:'context',color:'#b4b4a7',weight:2,interactive:false}).addTo(vector);continue;}
 if(c.points.length<3)continue;
 const edu=c.kind==='school'||c.kind==='university',water=c.kind==='water';
 L.polygon(c.points,{pane:'context',color:water?'#b9cdd3':edu?'#dad5c3':'#c6d7bd',weight:1,fillColor:water?'#c9dadf':edu?'#dfdccf':'#cddcc1',fillOpacity:.65,interactive:false}).addTo(vector);
}
for(const r of d.roads){
 const major=['trunk','primary','secondary','tertiary'].includes(r.kind);
 L.polyline(r.points,{pane:'roads',color:major?'#d0cebd':'#dfddd1',weight:major?6:3,interactive:false}).addTo(vector);
 L.polyline(r.points,{pane:'roads',color:'#fffdf5',weight:major?4:1.6,interactive:false}).addTo(vector);
}
}
// 背景地図。標準は、Googleマップに近い配色のOpenFreeMap（OpenStreetMapベースのベクター地図。登録・APIキー不要）。
// 地図名は日本語表記を優先するようスタイルを書き換える。WebGLが使えない・読み込めない場合は国土地理院の標準地図へ切り替える。
// OSM標準タイル・CARTOは、それぞれ警告画像・APIキー必須の透かしが出るため使わない。
const blank='data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
const vectorBase=L.layerGroup();
const baseDefs=[
 {name:'カラー地図（OpenFreeMap）',status:'カラー地図（OpenFreeMap / OpenStreetMap）+ 標高・道路勾配',vector:false,layer:vectorBase,gl:true},
 {name:'国土地理院・標準地図',status:'国土地理院の標準地図 + 標高・道路勾配',vector:false,layer:L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png',{maxNativeZoom:18,maxZoom:19,className:'base-std',errorTileUrl:blank,attribution:'背景：<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院（標準地図）</a>'})},
 {name:'国土地理院・淡色地図',status:'国土地理院の淡色地図 + 標高・道路勾配',vector:true,layer:L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png',{maxNativeZoom:18,maxZoom:19,className:'base-pale',errorTileUrl:blank,attribution:'背景：<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院（淡色地図）</a>'})},
];
map.attributionControl.addAttribution('道路・地物・経路 © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> / ODbL・標高：国土地理院の標高タイル等を加工');
const offline=L.layerGroup();
let loaded=0,fallbackPending=false,activeBase=baseDefs[0];
const status=t=>{document.getElementById('map-status').textContent=t;};
// 同梱の道路・公園（vector）は、淡色地図とオフライン時だけ重ねる（カラー地図では道路が二重になるため）
const syncVector=()=>{const on=!!activeBase.vector||map.hasLayer(offline);if(on&&!map.hasLayer(vector))vector.addTo(map);else if(!on&&map.hasLayer(vector))map.removeLayer(vector);};
let autoSwitching=false;
function switchBase(to,msg){
 autoSwitching=true;  // 自動の切り替えは「選んだ背景」として保存しない
 if(map.hasLayer(activeBase.layer))map.removeLayer(activeBase.layer);
 if(to){activeBase=to;to.layer.addTo(map);}else{activeBase={layer:offline};offline.addTo(map);}
 autoSwitching=false;syncVector();status(msg);
}
function useOffline(){
 if(!map.hasLayer(activeBase.layer))return;
 // カラー地図が使えないときは、まず国土地理院の標準地図へ。それも失敗したら同梱データ。
 if(activeBase.gl)switchBase(baseDefs[1],'カラー地図を読み込めなかったため、国土地理院の標準地図を表示');
 else switchBase(null,'背景の取得に失敗：同梱の道路・公園地図を表示');
}
for(const b of baseDefs){
 if(b.gl)continue;
 b.layer.on('tileload',()=>{loaded++;if(map.hasLayer(b.layer))status(b.status);});
 b.layer.on('tileerror',()=>{
  if(fallbackPending)return;
  fallbackPending=true;
  // Leafletの読み込み処理終了後、失敗した画像を含めて背景を取り外す。
  setTimeout(()=>{fallbackPending=false;useOffline();},0);
 });
}
let glLayer=null,glLoading=false,baseMode='local',baseRequest=0;
const bundledBounds=L.latLngBounds([[35.665,139.700],[35.728,139.778]]);
const desiredBase=()=>bundledBounds.contains(map.getBounds())?'local':'online';
async function loadVectorBase(){
 const mode=desiredBase();if((glLayer&&mode===baseMode)||glLoading)return;glLoading=true;const token=++baseRequest;status('カラー地図を読み込み中');
 try{
  if(!window.maplibregl||!L.maplibreGL)throw new Error('maplibre');
  // 地図データは vendor/basemap/ に同梱。相対パスを絶対URLに直して渡す
  // タイル・フォントはBase64テキスト（公開ページで配信できる形式）で同梱。b64:// で読み込み、元のバイナリに戻して渡す
  const bundledGlyphRanges=new Set(['0-255','256-511','8192-8447','8448-8703','8704-8959','9472-9727','12288-12543','65024-65279','65280-65535']);
  if(!loadVectorBase.protocol){maplibregl.addProtocol('b64',async(params,abort)=>{
   // 同梱されていない補助文字は空字形。日本語はlocalIdeographFontFamilyで描く。
   if(params.url.includes('/basemap/fonts/')&&!bundledGlyphRanges.has(params.url.split('/').pop().replace('.pbf.txt','')))return {data:new ArrayBuffer(0)};
   const r=await fetch(new URL(params.url.slice(6),location.href),{signal:abort.signal});if(!r.ok)throw new Error(r.status);
   const bin=atob((await r.text()).trim());const buf=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)buf[i]=bin.charCodeAt(i);
   return {data:buf.buffer};});loadVectorBase.protocol=true;}
  const response=await fetch(mode==='local'?'vendor/basemap/style.json':'https://tiles.openfreemap.org/styles/liberty');if(!response.ok)throw new Error(response.status);
  const style=await response.json();
  if(mode==='online')for(const layer of style.layers||[])if(layer.layout?.['text-field'])layer.layout['text-field']=['coalesce',['get','name:ja'],['get','name']];
  prepareBaseStyle(style);
  if(token!==baseRequest)return;
  if(typeof style.sprite==='string')style.sprite=new URL(style.sprite,location.href).href;
  if(glLayer)vectorBase.removeLayer(glLayer);
  baseMode=mode;
  glLayer=L.maplibreGL({style,attribution:'背景：<a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/">OpenMapTiles</a>',localIdeographFontFamily:'"Hiragino Sans","Noto Sans JP",sans-serif'});
  vectorBase.addLayer(glLayer);
  const gl=glLayer.getMaplibreMap();
  if(!gl)throw new Error('webgl');
  gl.on('load',()=>{loaded++;if(map.hasLayer(vectorBase))status(baseDefs[0].status+(baseMode==='online'?'（オンライン）':'（同梱範囲）'));});
  gl.on('error',async()=>{if(baseMode==='online'){baseMode='offline';status('オンライン背景の取得に失敗：背景は同梱範囲のみ表示');try{const local=prepareBaseStyle(await (await fetch('vendor/basemap/style.json')).json());local.sprite=new URL(local.sprite,location.href).href;gl.setStyle(local);}catch(e){useOffline();}}});
 }catch(e){if(mode==='online'){baseMode='offline';status('オンライン背景を取得できません。同梱範囲のみ表示');if(glLayer)vectorBase.removeLayer(glLayer);glLayer=null;
  // 通信できない場合も、同梱タイルは使える。再読込時にオンラインへ戻る。
  try{const local=prepareBaseStyle(await (await fetch('vendor/basemap/style.json')).json());local.sprite=new URL(local.sprite,location.href).href;glLayer=L.maplibreGL({style:local});vectorBase.addLayer(glLayer);}catch(err){useOffline();}
 }else{glLayer=null;if(map.hasLayer(vectorBase))useOffline();}}
 finally{glLoading=false;if(baseMode!=='offline'&&desiredBase()!==baseMode)loadVectorBase();}
}
// 画面が隠れている間は描画が止まるため、表示されてから数え始める。
function glWatchdog(){if(document.hidden){document.addEventListener('visibilitychange',glWatchdog,{once:true});return;}
 // 地図データは同梱なので、時間切れではなく「地図を作れなかった」ときだけ予備の地図へ（描画が遅い端末で誤って切り替えない）
 setTimeout(()=>{if(!glLayer&&!glLoading&&map.hasLayer(vectorBase))useOffline();},15000);}
map.on('moveend',()=>{if(map.hasLayer(vectorBase)&&baseMode!=='offline')loadVectorBase();});
vectorBase.on('add',()=>{loaded=0;loadVectorBase();glWatchdog();});
const bases=Object.fromEntries([...baseDefs.map(b=>[b.name,b.layer]),['同梱の道路・公園地図（オフライン）',offline]]);
L.control.layers(bases,null,{position:'topleft',collapsed:true}).addTo(map);
let savedBase=null;try{savedBase=localStorage.getItem('walk-burden-map-base');}catch(e){}
activeBase=(location.protocol==='file:'||savedBase==='同梱の道路・公園地図（オフライン）')?{layer:offline}:baseDefs.find(b=>b.name===savedBase)||baseDefs[0];
activeBase.layer.addTo(map);syncVector();
if(activeBase.layer===offline)status('同梱の公開道路・公園地図を表示');
map.on('baselayerchange',e=>{
 if(!autoSwitching){try{localStorage.setItem('walk-burden-map-base',e.name);}catch(err){}}
 const b=baseDefs.find(x=>x.layer===e.layer);
 if(!b){activeBase={layer:offline};status('同梱の公開道路・公園地図');syncVector();return;}
 activeBase=b;syncVector();if(b.gl||autoSwitching)return;loaded=0;status('背景地図を読み込み中');setTimeout(()=>{if(!loaded)useOffline();},6000);
});
map.getPane('markerPane').style.zIndex=680;

const $=id=>document.getElementById(id);
const groups={stationNames:L.layerGroup(),stations:L.layerGroup(),slopes:L.layerGroup(),subway:L.layerGroup(),interiors:L.layerGroup()};
const elevBlock=p=>{
 if(!p.elev||p.elev.h==null)return '';
 return `<div class="elev"><b>標高 ${p.elev.h.toFixed(1)} m</b> <small>国土地理院・${esc(p.elev.src)}・代表点</small></div>`;
};
// ---------- 地下鉄：線路・ホーム・地下通路・出入口（OpenStreetMap） ----------
// level（階）の数字はOSMのタグのまま。負の数＝地下（-1＝地下1階）。正の数は地上より上の階（日本のOSMでは数え方が揃っていないため番号のまま表示）
const lvText=l=>{if(l==null||l==='')return '階の情報なし';const n=parseFloat(String(l).split(';')[0]);return isNaN(n)?`level ${l}`:n<0?`地下${-n}階`:n===0?'地上（1階）':`地上より上（level ${l}）`;};
const sub=d.subway||{tracks:[],platforms:[],corridors:[],entrances:[],structure:{}};
let interiorControl=null;
const subLayers=[];  // {layer, bucket, osm}  bucket = above | b1 | b2 | b3 （階で絞り込む用）
const bucketOf=l=>{const n=parseFloat(String(l??'').split(';')[0]);if(isNaN(n))return 'unknown';return n>=0?'above':n>=-1?'b1':n>=-2?'b2':'b3';};
function structureHtml(st){
 const s=sub.structure[st];if(!s)return '';
 const fl=s.floors.length?s.floors.map(f=>`<div class="floor"><span class="flv">${esc(lvText(f.level))}</span>${f.lines.map(l=>`<i style="background:${sub.colors[l]||'#777'}"></i>${esc(l)}`).join(' ')}</div>`).join(''):'<p class="small">ホームの階のデータなし（OSM）</p>';
 const ex=sub.entrances.filter(e=>e.station===st&&Object.keys(e.to_platform).length).sort((a,b)=>String(a.ref).localeCompare(String(b.ref),'ja',{numeric:true}));
 const lines=[...new Set(ex.flatMap(e=>Object.keys(e.to_platform)))];
 const tbl=ex.length?`<table><thead><tr><th>出入口</th>${lines.map(l=>`<th><i class="ln" style="background:${sub.colors[l]}"></i>${esc(l)}</th>`).join('')}</tr></thead><tbody>${ex.map(e=>`<tr><td>${esc(e.ref||'（番号なし）')}${e.elevator?' EV':''}</td>${lines.map(l=>`<td class="num">${e.to_platform[l]?'約'+e.to_platform[l].m+'m':'—'}</td>`).join('')}</tr>`).join('')}</tbody></table><p class="small">出入口からホームの端までの<b>直線距離</b>（OSMの位置から計算した目安）。階段・エスカレーター・改札を通る実際の歩行距離や時間ではありません。</p>`:'';
 return `<div class="walks access"><b>${esc(st)}駅：ホームの階（OSM）</b><div class="floors">${fl}</div>${tbl}<p class="small">ホーム${s.platforms}・出入口${s.entrances}・地下通路${s.corridors}本のデータ（OpenStreetMap）。駅によって細かさが違います。</p></div>`;
}
const stationOf=name=>Object.keys(sub.structure).sort((a,b)=>b.length-a.length).find(k=>name.includes(k)||name.includes(k.replace('ケ','ヶ')));
function drawSubway(){groups.subway.clearLayers();subLayers.length=0;
for(const t of sub.tracks){
 const c=t.color;
 if(!t.under)subLayers.push({bucket:'above',layer:L.polyline(t.points,{pane:'subway',color:'#fff',weight:7,opacity:.9,interactive:false})});
 subLayers.push({bucket:t.under?(t.layer<=-3?'b3':t.layer<=-2?'b2':'b1'):'above',layer:L.polyline(t.points,{pane:'subway',color:c,weight:t.under?3:4.5,opacity:t.under?.75:.95,dashArray:t.under?'7 6':null}).bindTooltip(`${esc(t.line||'地下鉄')}の線路（${t.under?'地下':'地上・高架'}${t.layer?`・layer ${t.layer}`:''}）`,{sticky:true})});
}
for(const c of sub.corridors)subLayers.push({osm:'way/'+c.id,bucket:bucketOf(c.lvl),cls:'corr',layer:L.polyline(c.points,{pane:'subway',color:'#4d5f86',weight:c.kind==='steps'?2.5:1.6,opacity:.55,dashArray:c.kind==='steps'?'2 3':null,className:'corridor'}).bindTooltip(`${c.kind==='steps'?'階段':c.kind==='elevator'?'エレベーター':'通路'}（${esc(lvText(c.level))}）`,{sticky:true})});
for(const p of sub.platforms){
 const opt={pane:'subway',color:p.color,weight:p.closed?1.5:7,opacity:.95,fillColor:p.color,fillOpacity:.45};
 const ly=(p.closed?L.polygon(p.points,opt):L.polyline(p.points,opt)).bindTooltip(`${esc(p.station)}駅 ${esc(p.line||'路線不明')}のホーム（${esc(lvText(p.level))}）`,{sticky:true}).bindPopup(()=>structureHtml(p.station),{maxWidth:340,maxHeight:popH()});
 subLayers.push({osm:'way/'+p.id,bucket:bucketOf(p.level),layer:ly});
}
for(const e of sub.entrances){
 const m=L.circleMarker(e.pos,{pane:'subwaytop',radius:4.5,color:'#263c38',weight:1.5,fillColor:'#fff',fillOpacity:1}).bindTooltip(`${esc(e.station)} ${esc(e.ref||'')}${e.ref?'出入口':''}`,{direction:'top',offset:[0,-4],className:'exit-label'})
  .bindPopup(()=>`<div class="popup-category">地下鉄の出入口（OSM）</div><h4>${esc(e.station)}駅 ${esc(e.ref||'')}${e.ref?'番出入口':'（番号なし）'}</h4>${Object.entries(e.to_platform).map(([l,v])=>`<p class="small"><i class="ln" style="background:${sub.colors[l]}"></i>${esc(l)}ホームまで直線約${v.m}m（${esc(lvText(v.level))}）</p>`).join('')}${structureHtml(e.station)}<div class="source-note">OpenStreetMap node ${e.id}</div>`,{maxWidth:340,maxHeight:popH()});
 subLayers.push({osm:'node/'+e.id,bucket:'exit',layer:m});
}
}
drawSubway();
function syncSubway(){const f=$('subway-level').value;for(const x of subLayers){const on=(f==='all'||x.bucket===f||x.bucket==='exit'||(x.bucket==='above'&&f==='above'))&&!interiorControl?.owns(x.osm);setIn(groups.subway,x.layer,on);}}
function drawSlopes(){
 groups.slopes.clearLayers();
 if(d.slopes){
 const sc=g=>g<6?'#f08fb0':g<9?'#d6336c':'#8c0f45';
 for(const s of d.slopes.slopes){
  L.polyline(s.points,{pane:'slopes',color:'#ffffff',weight:7,opacity:.7,interactive:false}).addTo(groups.slopes);
  L.polyline(s.points,{pane:'slopes',color:sc(s.g),weight:4.5,opacity:.95}).bindTooltip(`${s.name?esc(s.name)+'：':''}勾配 約${s.g}%（元の測定区間：${s.len}mで約${s.rise}m）`,{sticky:true}).addTo(groups.slopes);
 }
}

}

function setIn(group,layer,on){if(on&&!group.hasLayer(layer))group.addLayer(layer);else if(!on&&group.hasLayer(layer))group.removeLayer(layer);}
let stationMarkers=[];
function drawStationMarkers(){groups.stations.clearLayers();
stationMarkers=d.stations.map(s=>({osm:(s.source||'').replace('https://www.openstreetmap.org/',''),layer:L.circleMarker(s.pos,{radius:5,color:'#263c38',fillColor:'#fff',fillOpacity:1}).bindTooltip(esc(s.name)).bindPopup(`<h4>${esc(s.name)}</h4>${elevBlock(s)}${sourceNote(s.source,'OSMの駅出入口・駅代表点')}`).addTo(groups.stations)}));
}

function syncStationMarkers(){for(const s of stationMarkers)setIn(groups.stations,s.layer,!interiorControl?.owns(s.osm));}
function sync(){for(const [id,g] of Object.entries(groups))setIn(map,g,$(id).checked);$('slope-key').hidden=!$('slopes').checked;$('subway-key').hidden=!$('subway').checked;}
for(const id of Object.keys(groups))$(id).onchange=sync;
$('subway-level').onchange=syncSubway;syncSubway();sync();
const stationResponse=await fetch(d.stationIndex);if(!stationResponse.ok)throw new Error('駅一覧を読み込めません');
const stationIndex=await stationResponse.json();
labelStations=stationIndex.stations;
const stationLabels=window.initStationLabels({map,group:groups.stationNames,stations:labelStations,esc,
 backgroundHasNames:()=>!activeBase.gl&&activeBase.layer!==offline&&map.getZoom()>=15});
map.on('baselayerchange',()=>stationLabels.refresh());
d.stationInteriors={stations:stationIndex.stations,features:[]};
interiorControl=window.initStationInteriors({map,group:groups.interiors,data:d.stationInteriors,esc,popH,onChange:()=>{syncSubway();syncStationMarkers();}});
syncSubway();syncStationMarkers();
// 対応駅全体から表示範囲を設定。駅選択で周辺を拡大できる。
const toggle=$('panel-toggle');
function setPanel(open){$('panel').classList.toggle('closed',!open);$('panel').inert=!open;toggle.classList.toggle('collapsed',!open);toggle.setAttribute('aria-expanded',open);toggle.textContent=open?'パネルを閉じる ›':'表示設定 ‹';}
toggle.onclick=()=>setPanel(toggle.getAttribute('aria-expanded')!=='true');if(mobile())setPanel(false);
window.addEventListener('resize',()=>map.invalidateSize());
function labelVisibility(){$('map').classList.toggle('hide-subway',map.getZoom()<15);$('map').classList.toggle('hide-corridors',map.getZoom()<17);$('map').classList.toggle('hide-slopes',map.getZoom()<15);}
map.on('zoomend',labelVisibility);labelVisibility();
setTimeout(()=>{if(!loaded&&!activeBase.gl)useOffline();},6000);
if(window.initWalk3D&&d.stationInteriors&&d.stationInteriors.stations.length)window.initWalk3D({data:d.stationInteriors,map,interiors:interiorControl});
const areaLoader=window.createAreaLoader({map,indexUrl:d.areaIndex,onStatus:t=>$('area-status').textContent=t,onData:area=>{
 d.roads=area.roads;d.context=area.context;d.stations=area.stations;d.slopes.slopes=area.slopes;
 sub.platforms=area.subplatforms;sub.corridors=area.subcorridors;sub.entrances=area.subentrances;drawSubway();syncSubway();
 drawVector();drawSlopes();drawStationMarkers();
 syncStationMarkers();window.dispatchEvent(new Event('walk-area-loaded'));
}});
window.walkBurdenMap={map,groups,stationLabels,vector,areaLoader,interiorControl};
await Promise.all([areaLoader.ready,interiorControl.ready]);
window.walkBurdenMap.ready=true;
})().catch(e=>{document.getElementById('map-status').textContent=`地図を初期化できません：${e.message}`;console.error(e);});
}
