'use strict';
// 立体表示：地上の道路・坂と、地下・地上・高架の駅構内を重ねる。
// 深さの実データは無いため level×5m×誇張倍率の模式表示。外部APIは使わない。
window.initWalk3D=function({data,map,interiors}){
 const $=id=>document.getElementById(id);
 const NEAR_STATION=900,PER_LEVEL=5;            // 対応駅を探す距離(m)・1階あたりの深さ(m)
 let gl=null,markers=[],open=false,glReady=false,station=null,view;
 const LC=(lat0)=>({kx:111320*Math.cos(lat0*Math.PI/180),ky:110574});
 // 線を幅w(m)の四角形に変換（lng/lat）。折れ線は線分ごとの四角形の集合。
 function quads(pts,w,c){
  const out=[];
  for(let i=0;i<pts.length-1;i++){
   const [x1,y1]=[(pts[i][0]-c.lng)*c.kx,(pts[i][1]-c.lat)*c.ky],[x2,y2]=[(pts[i+1][0]-c.lng)*c.kx,(pts[i+1][1]-c.lat)*c.ky];
   const dx=x2-x1,dy=y2-y1,l=Math.hypot(dx,dy);if(l<.01)continue;
   const nx=-dy/l*w/2,ny=dx/l*w/2;
   const P=(x,y)=>[c.lng+x/c.kx,c.lat+y/c.ky];
   out.push([[P(x1+nx,y1+ny),P(x2+nx,y2+ny),P(x2-nx,y2-ny),P(x1-nx,y1-ny),P(x1+nx,y1+ny)]]);
  }
  return out;
 }
 const sq=(p,w,c)=>quads([[p[0]-w/2/c.kx,p[1]],[p[0]+w/2/c.kx,p[1]]],w,c)[0];
 function dist2seg(p,a,b,c){ // メートルで点と線分の距離
  const X=q=>[(q[0]-c.lng)*c.kx,(q[1]-c.lat)*c.ky],[px,py]=X(p),[ax,ay]=X(a),[bx,by]=X(b);
  const dx=bx-ax,dy=by-ay,t=Math.max(0,Math.min(1,dx||dy?((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy):0));
  return Math.hypot(px-ax-t*dx,py-ay-t*dy);
 }
 const lvOf=p=>p.levels;
 const floorName=lv=>lv<0?`地下${-lv}階`:lv===0?'地上基準（level 0）':`上層（level ${lv}）`;
 function build(){
  const ex=Number($('v3d-ex').value),center=gl.getCenter();
  const c={lng:center.lng,lat:center.lat,...LC(center.lat)};
  const el=$('map3d'),R=Math.max(450,156543*Math.cos(c.lat*Math.PI/180)/2**gl.getZoom()*Math.hypot(el.clientWidth,el.clientHeight));
  const near=pts=>pts.some(q=>Math.hypot((q[1]-c.lng)*c.kx,(q[0]-c.lat)*c.ky)<R);
  const feats=data.features.filter(f=>f.properties.station===station?.name);
  const levels=[...new Set(feats.filter(f=>f.properties.kind!=='exit').flatMap(f=>lvOf(f.properties)))].sort((a,b)=>b-a);
  const minLv=Math.min(0,...levels),depth=lv=>-lv*PER_LEVEL*ex;
  const G=-minLv*PER_LEVEL*ex+6;       // 地面の高さ（負の高さを避けるための底上げ）
  // level 0も道路・坂に埋もれないよう4m浮かせる。実測の床高ではない。
  const z=lv=>G-depth(lv)+(lv>=0?4:0);
  const out={road:[],slope:[],ground:[],under:[],above:[],exit:[]};
  const F=(geom,props)=>({type:'Feature',geometry:{type:'Polygon',coordinates:geom},properties:props});
  const bx=R/c.kx,by=R/c.ky;
  out.ground.push(F([[[c.lng-bx,c.lat-by],[c.lng+bx,c.lat-by],[c.lng+bx,c.lat+by],[c.lng-bx,c.lat+by],[c.lng-bx,c.lat-by]]],{base:G-.6,top:G,color:'#f4f6ef'}));
  for(const r of data_roads)if(near(r.points)){
   const major=['trunk','primary','secondary','tertiary'].includes(r.kind);
   for(const q of quads(r.points.map(p=>[p[1],p[0]]),major?7:3.5,c))out.road.push(F(q,{base:G,top:G+.4,color:major?'#c8c5b3':'#dcdace'}));
  }
  const sc=g=>g<6?'#f08fb0':g<9?'#d6336c':'#8c0f45';
  for(const sl of data_slopes)if(near(sl.points))for(const q of quads(sl.points.map(p=>[p[1],p[0]]),6,c))out.slope.push(F(q,{base:G+.4,top:G+1.2,color:sc(sl.g)}));
  const under=feats.filter(f=>f.properties.kind!=='exit'&&f.geometry.type==='LineString'&&lvOf(f.properties).length);
  for(const f of under){
   const p=f.properties,lv=Math.max(...lvOf(p)),k=p.kind;       // 複数階にまたがる階段は浅い側を基準に斜めは表現しない
   const w=k==='platform'?9:k==='stairs'?3:5;
   const col=k==='platform'?(p.color||'#6a5acd'):k==='stairs'?'#b8692a':'#3a6a9c';
   const zz=z(lv);
   const target=lv>=0?out.above:out.under;
   for(const q of quads(f.geometry.coordinates,w,c))target.push(F(q,{base:zz-(k==='platform'?2.4:1.6),top:zz,color:col}));
   // 複数階をつなぐ階段は上下の階の間に縦の柱で示す
   const ls=lvOf(p);if(ls.length>1){const m=f.geometry.coordinates[Math.floor(f.geometry.coordinates.length/2)];target.push(F([sq(m,2.5,c)],{base:z(Math.min(...ls)),top:z(Math.max(...ls)),color:'#b8692a'}));}
  }
  for(const f of feats.filter(f=>['Polygon','MultiPolygon'].includes(f.geometry.type)&&lvOf(f.properties).length)){
   const p=f.properties,lv=Math.max(...lvOf(p)),zz=z(lv);
   for(const polygon of f.geometry.type==='MultiPolygon'?f.geometry.coordinates:[f.geometry.coordinates])
    (lv>=0?out.above:out.under).push(F(polygon,{base:zz-2.4,top:zz,color:p.color||'#6a5acd'}));
  }
  for(const f of feats.filter(f=>f.geometry.type==='Point'&&f.properties.kind!=='exit'&&lvOf(f.properties).length)){
   const p=f.properties,ls=lvOf(p),lv=Math.max(...ls),zz=z(lv);
   (lv>=0?out.above:out.under).push(F([sq(f.geometry.coordinates,3,c)],{base:ls.length>1?z(Math.min(...ls)):zz-1.6,top:zz,color:p.kind==='elevator'?'#2b997b':'#b8692a'}));
  }
  // 出口：最寄りの収録済み通路・階段・ホームの階への接続（推定）。
  const connectors=feats.filter(f=>f.properties.kind!=='exit'&&lvOf(f.properties).length&&['LineString','Polygon','MultiPolygon'].includes(f.geometry.type));
  const exits=feats.filter(f=>f.properties.kind==='exit');
  const info=[];
  for(const e of exits){
   const p=e.properties,pt=e.geometry.coordinates;let lv=null,est=true,d0=null;
   const own=lvOf(p).filter(n=>n!==0); // 出口自身のlevel 0だけでは構内の接続階は分からない
   if(own.length){lv=Math.min(...own);est=false;}
   else{for(const f of connectors){const rings=f.geometry.type==='MultiPolygon'?f.geometry.coordinates.map(p=>p[0]):[f.geometry.type==='Polygon'?f.geometry.coordinates[0]:f.geometry.coordinates];for(const cs of rings)for(let i=0;i<cs.length-1;i++){
     const dd=dist2seg(pt,cs[i],cs[i+1],c);
     if(d0===null||dd<d0){d0=dd;lv=Math.max(...lvOf(f.properties));}}}}
   if(lv===null)continue;
   // 出口の幅も模式的。通路に埋もれないよう太いオレンジの柱で示す。
   out.exit.push(F([sq(pt,5.5,c)],{base:Math.min(G,z(lv)),top:Math.max(G+8,z(lv)),color:'#ff7800'}));
   info.push({pos:pt,ref:p.ref,lv,est});
  }
  return {c,out,levels,z,G,info,ex,exitCount:exits.length};
 }
 let data_roads=[],data_slopes=[];
 const FC=a=>({type:'FeatureCollection',features:a});
 function addLayer(id,src,op,extra={}){
  gl.addLayer({id,type:'fill-extrusion',source:src,paint:{'fill-extrusion-color':['to-color',['coalesce',['get','color'],'#cccccc']],'fill-extrusion-base':['to-number',['coalesce',['get','base'],0],0],'fill-extrusion-height':['to-number',['coalesce',['get','top'],1],1],'fill-extrusion-opacity':op,'fill-extrusion-vertical-gradient':false,...extra}});
 }
 function refresh(){
  const b=build();
  for(const [k,id] of [['road','v3d-road'],['slope','v3d-slope'],['under','v3d-under'],['above','v3d-above'],['exit','v3d-exit'],['ground','v3d-ground']])gl.getSource(id).setData(FC(b.out[k]));
  for(const m of markers)m.remove();markers=[];
  const mk=(lng,lat,html,cls)=>{const el=document.createElement('div');el.className='v3d-label '+cls;el.innerHTML=html;markers.push(new maplibregl.Marker({element:el,anchor:'left',pitchAlignment:'viewport',rotationAlignment:'viewport',}).setLngLat([lng,lat]).addTo(gl));};
  if(station&&$('stationNames').checked){
   const name=station.name.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
   mk(station.pos[1],station.pos[0],name+'駅','station-name-label');
  }
  // 階ラベル（地面の外れ・各階の高さ）。MapLibre 4はMarkerに高さを持てないため、画面上の位置合わせはせず一覧で示す。
  $('v3d-legend-levels').innerHTML=(b.levels.length?'':'<span>構内の階情報は未収録です。</span>')+b.levels.map(lv=>`<span><i style="background:#3a6a9c"></i>${floorName(lv)}${lv<0?`：地表から約${-lv*PER_LEVEL}m`:lv>0?`：基準面から約${lv*PER_LEVEL}m（模式）`:''}</span>`).join('')+`<span>※高さは${b.ex}倍に誇張。JRの模式階を含みます。</span>`;
  for(const x of b.info){const t=`${x.ref||'出口'}→${floorName(x.lv)}${x.est?'（推定）':''}`;mk(x.pos[0],x.pos[1],t,'exit-label');}
  $('v3d-exits').textContent='出口と構内の階：'+(b.info.length?b.info.map(x=>`${x.ref||'番号なし'}→${floorName(x.lv)}${x.est?'(推定)':''}`).join('、'):b.exitCount?`接続階が未収録のため出口柱は表示できません（地表出口${b.exitCount}点）。`:'出口は未収録です。');
  return b;
 }
 // 中心から900m以内の対応駅だけを表示する。駅の選択・読込でカメラは動かさない。
 function selectNearby(){
  const c=gl?gl.getCenter():view.center,scale=LC(c.lat);
  let nearest=null,distance=NEAR_STATION;
  for(const s of data.stations){const d=Math.hypot((s.pos[1]-c.lng)*scale.kx,(s.pos[0]-c.lat)*scale.ky);if(d<distance){nearest=s;distance=d;}}
  station=nearest;
  $('v3d-location').textContent=station?`${station.name}駅付近を表示中`:'周辺の地面・道路・坂を表示中（900m以内に対応駅なし）';
  if(station)interiors.selectStation(station.name);
 }
 function syncView(){
  if(!open||!gl)return;
  selectNearby();
  const c=gl.getCenter();
  // 平面側の既存の範囲別遅延読込も追随させる。
  map.setView([c.lat,c.lng],gl.getZoom(),{animate:false});
  if(glReady)refresh();
 }
 function init(){
  if(!window.maplibregl)return false;
  try{gl=new maplibregl.Map({container:'map3d',style:{version:8,sources:{},layers:[{id:'bg',type:'background',paint:{'background-color':'#e9ece4'}}]},
   center:[view.center.lng,view.center.lat],zoom:view.zoom,pitch:55,bearing:-35,maxPitch:80,minZoom:0,maxZoom:24,
   interactive:true,cooperativeGestures:false,dragPan:true,touchZoomRotate:true,touchPitch:true,dragRotate:true,scrollZoom:true,attributionControl:{customAttribution:'道路・坂・構内：© OpenStreetMap contributors / 標高：国土地理院'}});
  gl.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'top-left');}catch(e){gl=null;return false;}
  for(const handler of ['dragPan','touchZoomRotate','touchPitch','dragRotate','scrollZoom'])gl[handler].enable();
  gl.touchZoomRotate.enableRotation();
  gl.on('moveend',syncView);
  gl.on('load',()=>{
   for(const id of ['v3d-ground','v3d-road','v3d-slope','v3d-under','v3d-above','v3d-exit'])gl.addSource(id,{type:'geojson',data:FC([])});
   // 描画順：不透明な地下を先に描き、その上に半透明の地面・道路・坂を重ねる（先に地面を描くと深度で地下が隠れる）
   addLayer('l-under','v3d-under',1);addLayer('l-exit','v3d-exit',1);
   addLayer('l-ground','v3d-ground',.14);addLayer('l-road','v3d-road',.3);addLayer('l-slope','v3d-slope',.55);
   addLayer('l-above','v3d-above',1);
   glReady=true;
   refresh();
  });
  return true;
 }
 function show(){
  view={center:map.getCenter(),zoom:map.getZoom()};
  data_roads=window.MAP_DATA.roads;data_slopes=window.MAP_DATA.slopes?.slopes||[];
  $('map3d-wrap').hidden=false;open=true;document.body.classList.add('is3d');$('btn3d').textContent='平面に戻る';
  if(!gl){if(!init()){$('v3d-err').hidden=false;}}
  else{gl.resize();gl.jumpTo({center:[view.center.lng,view.center.lat],zoom:view.zoom,pitch:55,bearing:-35});}
  if(gl)syncView();
 }
 function hide(){if(gl)syncView();$('map3d-wrap').hidden=true;open=false;document.body.classList.remove('is3d');$('btn3d').textContent='立体表示';}
 const toggle=()=>open?hide():show();
 $('btn3d').onclick=toggle;$('btn3d-panel').onclick=toggle;$('v3d-back').onclick=hide;
 $('v3d-ex').oninput=()=>{$('v3d-exv').textContent='×'+$('v3d-ex').value;if(glReady)refresh();};
 $('stationNames').addEventListener('change',()=>{if(open&&glReady)refresh();});
 window.addEventListener('walk-interiors-loaded',()=>{if(open&&glReady){refresh();}});
 window.addEventListener('walk-area-loaded',()=>{data_roads=window.MAP_DATA.roads;data_slopes=window.MAP_DATA.slopes?.slopes||[];if(open&&glReady)refresh();});
 return {toggle};
};
