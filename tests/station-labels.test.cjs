// 実索引96駅で、広域の間引き・拡大時の候補・衝突回避を検証する。
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const window={};vm.runInNewContext(fs.readFileSync('station-labels.js','utf8'),{window});
const stations=JSON.parse(fs.readFileSync('data/station-index.json')).stations;
assert.equal(stations.length,96);
const points=new Map(stations.map((s,i)=>[s.pos,{x:180+(i%12)*360,y:80+Math.floor(i/12)*130}]));
const options={stations,project:p=>points.get(p),size:{x:4400,y:1100}};
const wide=window.layoutStationLabels({...options,zoom:13});
const close=window.layoutStationLabels({...options,zoom:17});
assert.ok(wide.length>0&&wide.length<96);
assert.equal(close.length,96);
assert.equal(window.layoutStationLabels({...options,zoom:17,backgroundHasNames:true}).length,0);
const crowded=window.layoutStationLabels({...options,zoom:15,size:{x:500,y:300},project:()=>({x:250,y:150})});
assert.ok(crowded.length>0&&crowded.length<96);
for(let i=0;i<crowded.length;i++){
 const a=crowded[i].box;
 assert.ok(a.x>=4&&a.y>=4&&a.x+a.width<=496&&a.y+a.height<=296);
 for(const b of crowded.slice(i+1).map(p=>p.box))assert.ok(!(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y));
}
assert.equal(window.layoutStationLabels({...options,zoom:17,project:()=>({x:-100,y:50})}).length,0);
console.log('PASS: 実索引96駅、ズーム13の間引き・17の全駅候補、重なり回避、画面外除外、背景駅名との重複抑制');
