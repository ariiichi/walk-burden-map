// 画面の移動と遅い通信が重なっても古い区画に戻らないこと、失敗を空白と区別する。
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 let box=[0,0,1,1],events={},calls=[],updates=[],messages=[],resolveA;
 const entries={areas:[{id:'a',bounds:[[0,0],[1,1]],url:'a'},{id:'b',bounds:[[2,2],[3,3]],url:'b'},{id:'bad',bounds:[[4,4],[5,5]],url:'bad'}]};
 const value=id=>({roads:[{id}],slopes:[],stations:[],context:[],boundaries:[],contours:[]});
 const fetch=async url=>{calls.push(url);if(url==='index')return {ok:true,json:async()=>entries};if(url==='bad')return {ok:false,status:503};if(url==='a')await new Promise(r=>resolveA=r);return {ok:true,json:async()=>value(url)};};
 const window={};const context=vm.createContext({window,fetch,Map,Set,Promise,setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('area-loader.js','utf8'),context);
 const map={on:(n,f)=>events[n]=f,getBounds:()=>({getSouth:()=>box[0],getWest:()=>box[1],getNorth:()=>box[2],getEast:()=>box[3]})};
 const loader=window.createAreaLoader({map,indexUrl:'index',onData:v=>updates.push(v),onStatus:s=>messages.push(s)});
 await new Promise(r=>setImmediate(r));box=[2.1,2.1,2.9,2.9];await loader.refresh();
 resolveA();await loader.ready;
 assert.equal(updates.at(-1).roads[0].id,'b');assert.equal(updates.length,1);
 await loader.refresh();assert.equal(calls.filter(x=>x==='b').length,1);
 box=[6,6,7,7];await loader.refresh();assert.equal(updates.at(-1).roads.length,0);assert.match(messages.at(-1),/未収録/);
 box=[4.1,4.1,4.9,4.9];await loader.refresh();assert.match(messages.at(-1),/取得できません/);assert.doesNotMatch(messages.at(-1),/未収録/);
 await loader.refresh();assert.equal(calls.filter(x=>x==='bad').length,2);
 for(let i=0;i<24;i++){const x=10+i*2;entries.areas.push({id:'c'+i,bounds:[[x,0],[x+1,1]],url:'c'+i});box=[x+.1,.1,x+.9,.9];await loader.refresh();}
 assert.ok(loader.stats().cached<=16);
 console.log('PASS: 範囲遅延取得、通信の競合、画面外解除、キャッシュ再利用、範囲外の未収録表示');
})().catch(e=>{console.error(e);process.exitCode=1;});
