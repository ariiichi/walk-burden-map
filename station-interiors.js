'use strict';
// 同梱データだけで描画。外部API・図版の座標化は使わない。
window.initStationInteriors=function({map,group,data,esc,popH,onChange}){
 const $=id=>document.getElementById(id);
 if(!data||!data.stations.length){
  $('interior-status').textContent='駅構内データは未収録です。';
  for(const id of ['interiors','interior-station','interior-level','interior-focus','interior-exits'])$(id).disabled=true;
  return {owns:()=>false};
 }
 for(const [name,z] of [['interiorArea',410],['interiorLine',420],['interiorPoint',430]]){
  map.createPane(name);map.getPane(name).style.zIndex=z;
 }
 const kindNames={platform:'ホーム',corridor:'通路',stairs:'階段',exit:'出入口',gate:'改札',concourse:'コンコース',elevator:'EV（駅所属推定）',escalator:'ES'};
 const floorLabel=n=>n<0?`地下${-n}階（level ${n}）`:n===0?'地上基準（level 0）':`上層（level ${n}）`;
 const floorText=p=>(p.levels.length?p.levels.map(floorLabel).join(' ↔ '):'階は未収録')+(p.level_method==='osm_surface_track_schematic'?'（地上・高架の模式階／推定）':'');
 const lines=[...new Set(data.stations.flatMap(s=>s.lines))].sort();
 for(const line of lines)$('interior-line').add(new Option(line,line));
 $('interior-line').value=lines[0];
 function stationOptions(){const select=$('interior-station');const line=$('interior-line').value;const stations=data.stations.filter(s=>s.lines.includes(line)).sort((a,b)=>(a.orders?.[line]??1e6)-(b.orders?.[line]??1e6)||a.name.localeCompare(b.name,'ja'));select.replaceChildren(...stations.map(s=>new Option(`${s.name}駅 · ホーム${s.counts.platform?'有':'未'} / 通路${s.counts.corridor?'有':'未'} / 出口${s.counts.exit?'有':'未'} / 階${s.levels.length?'有':'未'}`,s.name)));}
 stationOptions();
 let loading=false,selectionVersion=0;const stationCache=new Map();
 const current=()=>data.stations.find(s=>s.name===$('interior-station').value);
 const stationFeatures=()=>data.features.filter(f=>f.properties.station===current().name);
 const levelMatch=p=>$('interior-level').value==='all'||($('interior-level').value==='unknown'?!p.levels.length:p.levels.includes(Number($('interior-level').value)));
 const elevationText=p=>p.elevation?.h!=null?`${p.elevation.h.toFixed(1)} m`:'未収録';
 const label=p=>`${kindNames[p.kind]||p.kind}${p.ref?' '+p.ref:''}${p.kind==='exit'&&p.elevator?' EV':''}`;
 function popup(p){
  const elevation=p.kind==='exit'?`<p><b>出口の地表標高：${elevationText(p)}</b>${p.elevation?.h!=null?`<br><small>国土地理院・${esc(p.elevation.src)}。構内床の高さではありません。</small>`:''}</p>`:'';
  const exitNote=p.kind==='exit'?'<p class="small">地表出口の参照点として重ねています。接続する階・設備の停止階・内部経路は未収録です。</p>':'';
  const floorNote=p.level_method==='osm_surface_track_schematic'?`<p class="small">${esc(p.level_note)} 原level：${esc(p.level_raw??'未収録')}。</p>`:'';
  return `<div class="popup-category">駅構内レイヤー・OSM収録分</div><h4>${esc(p.station)}駅 ${esc(label(p))}</h4>${p.line?`<p>${esc(p.line)}（${p.line_method==='osm_route_membership'?'OSM路線メンバー':'元データの記載'}）</p>`:p.kind==='platform'?'<p>路線の割当ては未収録です。</p>':''}<p>${esc(floorText(p))}</p>${floorNote}${elevation}${exitNote}<p class="small">${p.assignment?.includes('nearest')?'駅所属は近接による推定です。':''}改札内外・通行可否は未確認。構内経路の案内には使えません。</p><div class="source-note">© OpenStreetMap contributors / ODbL<br><a href="https://www.openstreetmap.org/${p.osm_type}/${p.osm_id}" target="_blank" rel="noopener noreferrer">OSM ${p.osm_type} ${p.osm_id}</a></div>`;
 }
 function marker(latlng,text,style){
  return L.marker(latlng,{pane:'interiorPoint',icon:L.divIcon({className:'interior-symbol',html:`<span class="${style}">${esc(text)}</span>`,iconSize:[30,22],iconAnchor:[15,11]})});
 }
 function render(){
  if(loading)return;
  group.clearLayers();const s=current(),zoom=map.getZoom(),enabled=$('interiors').checked;
  const fs=stationFeatures();let visible=0;
  if(enabled){
   if(zoom<16){
    marker(s.pos,'構内','station').bindTooltip(`${esc(s.name)}駅の構内：拡大して表示`).on('click',focus).addTo(group);
   }else for(const f of fs){
    const p=f.properties,isExit=p.kind==='exit';
    if(isExit?!$('interior-exits').checked:!levelMatch(p))continue;
    if(!isExit&&p.kind!=='platform'&&zoom<17)continue;
    let layer;
    if(f.geometry.type==='Point'){
     const pos=[f.geometry.coordinates[1],f.geometry.coordinates[0]];
     if(isExit){
      layer=L.circleMarker(pos,{pane:'interiorPoint',radius:p.elevator?6:4.5,color:'#263c38',weight:2,fillColor:p.elevator?'#deeee7':'#fff',fillOpacity:1});
      const text=`${p.ref||'番号未収録'}${p.elevator?' EV':''}${zoom>=18?' · 地表 '+elevationText(p):''}`;
      layer.bindTooltip(esc(text),{permanent:zoom>=18,direction:'top',className:'interior-exit-label'});
     }else layer=marker(pos,label(p),'facility');
    }else{
     const underground=p.levels.some(n=>n<0),platform=p.kind==='platform';
     layer=L.geoJSON(f,{pane:platform?'interiorArea':'interiorLine',style:{
      color:platform?p.color:p.kind==='stairs'?'#995d29':'#365b7c',
      weight:platform?(f.geometry.type==='Polygon'?2:6):p.kind==='stairs'?4:3,
      fillOpacity:platform?.3:.12,opacity:.95,
      dashArray:platform?null:p.kind==='stairs'?'2 3':underground?'7 5':null
     }}).bindTooltip(esc(`${p.line?p.line+' ':''}${label(p)} · ${floorText(p)}`),{sticky:true});
     if(zoom>=18&&p.kind==='stairs'){
      const pts=f.geometry.type==='Polygon'?f.geometry.coordinates[0]:f.geometry.coordinates,pos=pts[Math.floor(pts.length/2)];
      marker([pos[1],pos[0]],'▥','stairs').bindPopup(popup(p),{maxWidth:320,maxHeight:popH()}).addTo(group);
     }
    }
    layer.bindPopup(popup(p),{maxWidth:320,maxHeight:popH()}).addTo(group);visible++;
   }
  }
  const applicable=fs.filter(f=>f.properties.kind!=='exit'&&levelMatch(f.properties));
  const selection=$('interior-level').selectedOptions[0].textContent;
  $('interior-status').textContent=!enabled?'駅構内レイヤーは非表示です。':zoom<16?'駅を拡大すると構内を表示します。':`${s.name}駅・${selection}：${visible}件表示。${!applicable.length?'この階の構内要素は未収録。':''}${zoom<17?'通路・階段はズーム17以上で表示。':''}`;
  $('interior-warning').textContent=loading?'駅データを読み込み中…':s.warnings.join(' ');
  onChange();
 }
 async function chooseStation(){
  const token=++selectionVersion,s=current();
  $('interior-availability').textContent=['platform','corridor','exit'].map(k=>`${kindNames[k]}：${s.counts[k]?'収録':'未収録'}`).join(' / ')+` / 階：${s.levels.length?'収録':'未収録'}`+(s.terrain?.missing_roads?`。周辺道路：標高欠測${s.terrain.missing_roads}本（坂の計算対象外）。`:'');
  loading=true;data.features=[];group.clearLayers();
  $('interior-status').textContent=`${s.name}駅を読み込み中…`;
  $('interior-level').replaceChildren(new Option('すべての階','all'));
  $('interior-coverage').textContent='読み込み中…';
  onChange();
  try{
   let loaded=stationCache.get(s.id);
   if(!loaded){const r=await fetch(s.url);if(!r.ok)throw new Error(r.status);loaded=await r.json();stationCache.set(s.id,loaded);if(stationCache.size>6)stationCache.delete(stationCache.keys().next().value);}
   if(token!==selectionVersion)return;
   data.features=loaded.features;data.input_source_note=loaded.input_source_note;
   Object.assign(s,loaded.stations[0]);
   const select=$('interior-level');select.replaceChildren(new Option('すべての階','all'));
   for(const lv of s.levels)select.add(new Option(floorLabel(lv),String(lv)));
   select.add(new Option('階未収録','unknown'));
   const c=s.counts;
   $('interior-coverage').innerHTML=`<p>収録：ホーム${c.platform}件・通路${c.corridor}本・階段${c.stairs}本・出口${c.exit}点（標高あり${c.exit_elevation}点）・階情報${s.levels.length?'あり':'未収録'}。EV（駅所属推定）${c.elevator}・ES${c.escalator}・改札${c.gate}件。</p>${s.terrain?`<p>周辺道路の勾配：${s.terrain.sampled_roads}本を計算（4%以上のみ表示）。標高欠測${s.terrain.missing_roads}本・短い道路${s.terrain.short_roads||0}本は未計算です。</p>`:''}<p>${s.warnings.map(esc).join('<br>')}</p><p>入力：${esc(loaded.input_source_note)}。</p>`;
   loading=false;render();window.dispatchEvent(new Event('walk-interiors-loaded'));
  }catch(e){if(token!==selectionVersion)return;loading=false;$('interior-status').textContent=`${s.name}駅のデータを読み込めません。駅を選び直すと再試行します。`;$('interior-coverage').textContent='読み込み失敗（未収録との判定ではありません）';}
 }
 function focus(){
  $('interiors').checked=true;
  if(!map.hasLayer(group))group.addTo(map);
  const fs=stationFeatures();if(!fs.length){map.setView(current().pos,17);render();return;}
  const bounds=L.geoJSON({type:'FeatureCollection',features:fs}).getBounds();
  map.fitBounds(bounds,{paddingTopLeft:window.innerWidth<=760?[45,140]:[75,230],paddingBottomRight:window.innerWidth<=760?[45,170]:[390,100],maxZoom:18});
  render();
 }
 $('interior-station').onchange=async()=>{focus();await chooseStation();focus();};
 $('interior-line').onchange=async()=>{stationOptions();focus();await chooseStation();focus();};
 $('interior-level').onchange=render;$('interior-exits').onchange=render;
 $('interior-focus').onclick=focus;$('interiors').addEventListener('change',render);
 map.on('zoomend',()=>{if(!loading)render();});const ready=chooseStation();
 // 自動選択では平面地図を駅へ移動しない。既存のキャッシュ・競合防止を共有する。
 function selectStation(name){
  const s=data.stations.find(s=>s.name===name);if(!s)return;
  if(current()?.name===name)return;
  if(!s.lines.includes($('interior-line').value)){$('interior-line').value=s.lines[0];stationOptions();}
  $('interior-station').value=name;
  return chooseStation();
 }
 return {ready,selectStation,isLoading:()=>loading,owns:osm=>$('interiors').checked&&data.features.some(f=>f.id===osm&&f.properties.station===current().name),render};
};
