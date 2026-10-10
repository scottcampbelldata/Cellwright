// SPDX-License-Identifier: EUPL-1.2
const paths = new Set(['/', '/guides/excel-vba-to-libreoffice/', '/guides/userforms-and-activex/', '/privacy/']);

export async function onRequestPost({request, env}) {
  const headers = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
  if (new URL(request.url).hostname !== 'cellwright.scottcampbell.io' || request.headers.get('Origin') !== 'https://cellwright.scottcampbell.io') return new Response(null,{status:403,headers});
  if (request.headers.get('DNT') === '1' || request.headers.get('Sec-GPC') === '1') return new Response(null,{status:204,headers});
  const reader=request.body?.getReader();
  if (!reader) return new Response(null,{status:400,headers});
  let size=0, text=''; const decoder=new TextDecoder();
  try {
    while (true) {
      const {done,value}=await reader.read(); if(done)break;
      size+=value.byteLength;
      if(size>1024){await reader.cancel();return new Response(null,{status:413,headers});}
      text+=decoder.decode(value,{stream:true});
    }
    text+=decoder.decode();
    const data=JSON.parse(text);
    if (!data || Object.keys(data).sort().join(',')!=='downloads,path,scrolled,seconds,views' || !paths.has(data.path)) throw new Error('Invalid fields');
    for(const name of ['views','downloads','scrolled','seconds']) if (!Number.isInteger(data[name]) || data[name]<0 || data[name]>(name==='seconds'?60:1)) throw new Error('Invalid counter');
    if(!env.TRAFFIC) return new Response(null,{status:503,headers});
    const day=new Date().toISOString().slice(0,10);
    await env.TRAFFIC.prepare('INSERT INTO daily_engagement (day,path,views,active_seconds,downloads,scrolled_views) VALUES (?,?,?,?,?,?) ON CONFLICT(day,path) DO UPDATE SET views=views+excluded.views,active_seconds=active_seconds+excluded.active_seconds,downloads=downloads+excluded.downloads,scrolled_views=scrolled_views+excluded.scrolled_views').bind(day,data.path,data.views,data.seconds,data.downloads,data.scrolled).run();
    return new Response(null,{status:204,headers});
  } catch(error) {
    return new Response(null,{status:error instanceof SyntaxError || error.message.startsWith('Invalid')?400:503,headers});
  } finally {reader.releaseLock();}
}

export function onRequest() {return new Response(null,{status:405,headers:{Allow:'POST','Cache-Control':'no-store'}});}
