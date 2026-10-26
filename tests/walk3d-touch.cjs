// 任意の実ブラウザ検証：Playwrightが利用可能な環境で node tests/walk3d-touch.cjs
// localhost:8103 を起動しておく。Chromiumによるタッチエミュレーション（実機Safariではない）。
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
for(const viewport of [{width:1024,height:768},{width:820,height:1180}]){
 const context=await browser.newContext({viewport,hasTouch:true,isMobile:true,deviceScaleFactor:1});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8103');await page.waitForFunction(()=>window.walkBurdenMap?.ready);
 await page.evaluate(()=>{const Original=maplibregl.Map;maplibregl.Map=class extends Original{constructor(o){super(o);if(o.container==='map3d')window.test3d=this;}};window.walkBurdenMap.map.setView([35.6812,139.7671],16,{animate:false});});
 await page.locator('#btn3d').tap();await page.waitForFunction(()=>window.test3d?.getSource('v3d-ground'));
 assert.ok(await page.evaluate(()=>Math.abs(test3d.getCenter().lat-35.6812)<1e-6&&Math.abs(test3d.getZoom()-16)<1e-6));
 const selected=await page.locator('#interior-station').inputValue();assert.match(await page.locator('#v3d-location').innerText(),new RegExp(selected+'駅付近'));
 assert.ok(await page.evaluate(()=>['dragPan','touchZoomRotate','touchPitch','dragRotate','scrollZoom'].every(k=>test3d[k].isEnabled())));
 assert.equal(await page.evaluate(()=>document.elementFromPoint(450,350).tagName),'CANVAS');
 const cdp=await context.newCDPSession(page);
 async function gesture(start,end){await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:start.map((p,id)=>({x:p[0],y:p[1],id}))});for(let i=1;i<=15;i++){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:start.map((p,id)=>({x:p[0]+(end[id][0]-p[0])*i/15,y:p[1]+(end[id][1]-p[1])*i/15,id}))});await page.waitForTimeout(20);}await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await page.waitForTimeout(800);}
 let before=await page.evaluate(()=>test3d.getCenter().toArray());await gesture([[450,350]],[[600,400]]);let after=await page.evaluate(()=>test3d.getCenter().toArray());assert.ok(Math.hypot(after[0]-before[0],after[1]-before[1])>0.0001);
 let bearing=await page.evaluate(()=>test3d.getBearing());await gesture([[400,350],[600,350]],[[430,280],[570,420]]);assert.ok(Math.abs(await page.evaluate(()=>test3d.getBearing())-bearing)>5);
 let pitch=await page.evaluate(()=>test3d.getPitch());await gesture([[420,340],[580,340]],[[420,420],[580,420]]);assert.ok(Math.abs(await page.evaluate(()=>test3d.getPitch())-pitch)>2);
 let z=await page.evaluate(()=>test3d.getZoom());await gesture([[450,350],[550,350]],[[400,350],[600,350]]);assert.ok(Math.abs(await page.evaluate(()=>test3d.getZoom())-z)>.2);
 await page.evaluate(()=>test3d.jumpTo({center:[139.7436174,35.7015617]}));await page.waitForFunction(()=>document.getElementById('interior-station').value==='飯田橋');await page.waitForFunction(()=>!walkBurdenMap.interiorControl.isLoading());
 assert.match(await page.locator('#v3d-location').innerText(),/飯田橋駅/);
 const loc=await page.evaluate(()=>test3d.getCenter().toArray());await page.locator('#v3d-back').tap();const flat=await page.evaluate(()=>walkBurdenMap.map.getCenter());assert.ok(Math.abs(loc[0]-flat.lng)<1e-6&&Math.abs(loc[1]-flat.lat)<1e-6);
 assert.deepEqual(errors,[]);console.log('PASS touch',viewport,selected,'pan/rotate/pitch/pinch, station switch, return');await context.close();
}await browser.close();})().catch(e=>{console.error(e);process.exit(1)});
