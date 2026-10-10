// SPDX-License-Identifier: EUPL-1.2
// Aggregate public-page counters only; no cookies, IDs, referrers, URLs with queries, or workbook data.
if (location.hostname==='cellwright.scottcampbell.io' && navigator.doNotTrack!=='1' && !navigator.globalPrivacyControl) {
  let last=performance.now(), activity=last, active=document.visibilityState==='visible'&&document.hasFocus(), seconds=0, views=1, downloads=0, scrolled=0, countedScroll=false;
  function accrue() {
    const now=performance.now();
    if(active)seconds+=Math.max(0,Math.min(now,activity+60000)-last)/1000;
    last=now;active=document.visibilityState==='visible'&&document.hasFocus();
  }
  function send() {
    accrue();const whole=Math.min(60,Math.floor(seconds));
    if(!whole&&!views&&!downloads&&!scrolled)return;
    const body=JSON.stringify({path:location.pathname,seconds:whole,views,downloads,scrolled});
    if(navigator.sendBeacon('/api/engagement',new Blob([body],{type:'application/json'}))) {seconds-=whole;views=downloads=scrolled=0;}
  }
  function interact(){accrue();activity=last;}
  for(const event of ['pointerdown','keydown','touchstart'])addEventListener(event,interact,{passive:true});
  addEventListener('scroll',()=>{interact();if(!countedScroll&&scrollY+innerHeight>=document.documentElement.scrollHeight*.75){countedScroll=true;scrolled=1;}},{passive:true});
  addEventListener('click',event=>{const link=event.target.closest?.('a');if(link&&/\/releases\/download\/[^?#]+\.zip$/.test(link.href)){downloads=1;send();}});
  addEventListener('focus',interact);addEventListener('blur',send);
  document.addEventListener('visibilitychange',send);addEventListener('pagehide',send);
  setInterval(send,15000);send();
}
