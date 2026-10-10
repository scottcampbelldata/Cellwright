// SPDX-License-Identifier: EUPL-1.2
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
test('site, dashboard and report palettes exclude green and teal hues',()=>{
  for(const path of ['site/style.css','site/icon.svg','dashboard/style.css','dashboard/app.js','src/report.rs']) {
    const text=readFileSync(new URL('../'+path,import.meta.url),'utf8');
    assert.doesNotMatch(text,/\b(?:darkgreen|lightgreen|limegreen|seagreen|springgreen|forestgreen|olive|olivedrab|chartreuse|aquamarine|yellowgreen|teal)\b/i);
    for(const [color] of text.matchAll(/#(?:[\da-f]{8}|[\da-f]{6}|[\da-f]{4}|[\da-f]{3})\b/gi)) {
      const hex=color.length<=5?'#'+[...color.slice(1,4)].map(x=>x+x).join(''):color;
      const [r,g,b]=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
      const max=Math.max(r,g,b),min=Math.min(r,g,b),delta=max-min;
      if(!delta||delta/max<=.01)continue;
      const hue=((max===r?(g-b)/delta:max===g?2+(b-r)/delta:4+(r-g)/delta)*60+360)%360;
      assert.ok(hue<65||hue>200,`${path} contains green/teal ${color}`);
    }
  }
});
const source=readFileSync(new URL('../functions/api/engagement.js',import.meta.url),'utf8');
const {onRequestPost}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const payload={path:'/',views:1,seconds:15,downloads:0,scrolled:0};
function request(data=payload,origin='https://cellwright.scottcampbell.io') {return new Request('https://cellwright.scottcampbell.io/api/engagement',{method:'POST',headers:{Origin:origin},body:typeof data==='string'?data:JSON.stringify(data)});}
test('only bounded aggregate metrics reach the database',async()=>{
  let params;const TRAFFIC={prepare(sql){assert.match(sql,/ON CONFLICT/);return {bind(...values){params=values;return {run:async()=>({success:true})};}};}};
  assert.equal((await onRequestPost({request:request(),env:{TRAFFIC}})).status,204);
  assert.deepEqual(params.slice(1),['/',1,15,0,0]);
  for(const data of [{...payload,seconds:NaN},{...payload,seconds:61},{...payload,path:'/private'},{...payload,identity:'client'},{...payload,views:2},'x'.repeat(1025)])assert.ok([400,413].includes((await onRequestPost({request:request(data),env:{TRAFFIC}})).status));
  assert.deepEqual(params.slice(1),['/',1,15,0,0]);
  assert.equal((await onRequestPost({request:request(payload,'https://hostile.example'),env:{TRAFFIC}})).status,403);
  assert.equal((await onRequestPost({request:request(),env:{}})).status,503);
  const optedOut=request();optedOut.headers.set('Sec-GPC','1');assert.equal((await onRequestPost({request:optedOut,env:{}})).status,204);
});
test('engagement counts foreground active time and respects opt-outs',()=>{
  const code=readFileSync(new URL('../site/engagement.js',import.meta.url),'utf8');
  let now=0,visible='visible',focused=true,interval;const events={},packets=[];
  const context={location:{hostname:'cellwright.scottcampbell.io',pathname:'/'},navigator:{sendBeacon(url,blob){assert.equal(url,'/api/engagement');packets.push(blob.text);return true;}},Blob:class {constructor(parts){this.text=JSON.parse(parts[0]);}},performance:{now:()=>now},document:{get visibilityState(){return visible;},hasFocus:()=>focused,documentElement:{scrollHeight:2000},addEventListener:(name,fn)=>events[name]=fn},addEventListener:(name,fn)=>events[name]=fn,setInterval:fn=>interval=fn,scrollY:0,innerHeight:800};
  vm.runInNewContext(code,context);assert.equal(packets[0].views,1);
  now=15000;interval();assert.equal(packets[1].seconds,15);
  now=20000;visible='hidden';focused=false;events.visibilitychange();assert.equal(packets[2].seconds,5);
  now=120000;interval();assert.equal(packets.length,3);
  now=125000;visible='visible';focused=true;events.focus();now=140000;interval();assert.equal(packets[3].seconds,15);
  context.scrollY=1000;events.scroll();interval();assert.equal(packets.at(-1).scrolled,1);
  events.click({target:{closest:()=>({href:'https://github.com/scottcampbelldata/Cellwright/releases/download/v0.1.0/file.zip'})}});assert.equal(packets.at(-1).downloads,1);
  context.navigator.globalPrivacyControl=true;const count=packets.length;vm.runInNewContext(code,context);assert.equal(packets.length,count);
});
