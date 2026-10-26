'use strict';
// 静的JSONのみを読む。画面外の区画を描画から外し、未使用キャッシュを制限する。
window.createAreaLoader=function({map,indexUrl,onData,onStatus}){
 const cache=new Map(),pending=new Map();let entries=[],version=0,timer,activeIds=new Set(),inFlight=0;const queue=[];
 const acquire=()=>inFlight<4?(inFlight++,Promise.resolve()):new Promise(resolve=>queue.push(resolve));
 const release=()=>{const next=queue.shift();if(next)next();else inFlight--;};
 const trim=()=>{for(const key of cache.keys())if(cache.size>Math.max(16,activeIds.size)&&!activeIds.has(key))cache.delete(key);};
 const overlaps=(a,b)=>a[0][0]<=b[1][0]&&a[1][0]>=b[0][0]&&a[0][1]<=b[1][1]&&a[1][1]>=b[0][1];
 async function read(entry){
  if(cache.has(entry.id)){const v=cache.get(entry.id);cache.delete(entry.id);cache.set(entry.id,v);return v;}
  if(!pending.has(entry.id))pending.set(entry.id,(async()=>{await acquire();try{if(!activeIds.has(entry.id))throw new Error('画面外');const r=await fetch(entry.url);if(!r.ok)throw new Error(`${entry.id}: HTTP ${r.status}`);const j=await r.json();cache.set(entry.id,j);trim();return j;}finally{release();}})().finally(()=>pending.delete(entry.id)));
  return pending.get(entry.id);
 }
 async function update(){
  const token=++version,b=map.getBounds(),box=[[b.getSouth(),b.getWest()],[b.getNorth(),b.getEast()]];
  const wanted=entries.filter(e=>overlaps(e.bounds,box)),values=new Map(),failures=[];
  activeIds=new Set(wanted.map(e=>e.id));trim();
  onStatus(`表示範囲のデータを読み込み中（${wanted.length}区画）`);
  // APIではなく同梱JSONだが、同時通信数を制限する。
  let cursor=0;
  await Promise.all(Array.from({length:Math.min(4,wanted.length)},async()=>{while(cursor<wanted.length&&token===version){const e=wanted[cursor++];try{values.set(e.id,await read(e));}catch(err){failures.push(e.id);}}}));
  if(token!==version)return;
  const result={roads:[],context:[],boundaries:[],slopes:[],stations:[],subplatforms:[],subcorridors:[],subentrances:[]};
  for(const key of Object.keys(result)){
   const unique=new Map();for(const e of wanted)for(const item of values.get(e.id)?.[key]||[])unique.set(item._key||item.source||JSON.stringify(item),item);
   result[key]=[...unique.values()];
  }
  onData(result);
  trim();
  onStatus(failures.length?`${failures.length}区画を取得できません。移動・再読込で再試行します。`:wanted.length?`表示範囲：${wanted.length}区画 · 坂${result.slopes.length}区間 · 出口等${result.stations.length}点`:'この範囲の坂・出口標高は未収録です。');
 }
 const ready=(async()=>{try{const r=await fetch(indexUrl);if(!r.ok)throw new Error(r.status);entries=(await r.json()).areas;await update();}catch(e){onStatus('範囲データを読み込めません。HTTPサーバーから開いてください。');}})();
 map.on('moveend',()=>{clearTimeout(timer);timer=setTimeout(update,120);});
 return {ready,refresh:update,stats:()=>({cached:cache.size,pending:pending.size})};
};
