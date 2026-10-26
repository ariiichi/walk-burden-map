'use strict';
// 代表点の画面座標で配置を決める。区画データや構内JSONの取得は増やさない。
window.layoutStationLabels=function({stations,zoom,project,size,backgroundHasNames=false}){
 if(backgroundHasNames)return [];
 const major=new Set(['東京','新宿','池袋','渋谷','品川','上野','秋葉原','飯田橋','四ツ谷','御茶ノ水']);
 const priority=s=>(major.has(s.name)?100:0)+(s.lines?.length||0);
 const candidates=stations.filter(s=>zoom>=14||priority(s)>=3).slice().sort((a,b)=>priority(b)-priority(a)||a.id.localeCompare(b.id));
 const placed=[],gap=zoom<14?22:zoom<16?9:4;
 for(const station of candidates){
  const p=project(station.pos),text=station.name+'駅',width=Array.from(text).length*11+6,height=18;
  if(p.x<0||p.y<0||p.x>size.x||p.y>size.y)continue;
  // 上・下・左右を試し、代表点から離しすぎない。
  const offsets=[[-width/2,-25],[-width/2,9],[10,-height/2],[-width-10,-height/2]];
  for(const [dx,dy] of offsets){
   const box={x:p.x+dx,y:p.y+dy,width,height};
   if(box.x<4||box.y<4||box.x+width>size.x-4||box.y+height>size.y-4)continue;
   if(placed.some(q=>box.x<q.box.x+q.box.width+gap&&box.x+width+gap>q.box.x&&box.y<q.box.y+q.box.height+gap&&box.y+height+gap>q.box.y))continue;
   placed.push({station,text,box,anchor:[-dx,-dy]});break;
  }
 }
 return placed;
};
window.initStationLabels=function({map,group,stations,esc,backgroundHasNames}){
 function refresh(){
  group.clearLayers();
  for(const p of window.layoutStationLabels({stations,zoom:map.getZoom(),project:pos=>map.latLngToContainerPoint(pos),size:map.getSize(),backgroundHasNames:backgroundHasNames()})){
   L.marker(p.station.pos,{pane:'stationNames',interactive:false,keyboard:false,
    icon:L.divIcon({className:'station-name-label',html:esc(p.text),iconSize:[p.box.width,p.box.height],iconAnchor:p.anchor})}).addTo(group);
  }
 }
 map.on('zoomend',refresh);map.on('moveend',refresh);map.on('resize',refresh);
 refresh();
 return {refresh};
};
