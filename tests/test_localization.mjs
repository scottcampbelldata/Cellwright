// SPDX-License-Identifier: EUPL-1.2
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const source=readFileSync(new URL('../dashboard/locales.js',import.meta.url),'utf8');
const html=readFileSync(new URL('../dashboard/index.html',import.meta.url),'utf8');

class Node {
  constructor(tag='div',attributes={}) { this.tagName=tag.toUpperCase();this.attributes={...attributes};this.children=[];this.listeners={};this.dataset={i18n:attributes['data-i18n']};this.style={};this.value='';this.elements=new Proxy({},{get:(fields,name)=>fields[name]??=new Node('input')});this.classList={toggle(){}}; }
  getAttribute(name) { return this.attributes[name]??null; }
  setAttribute(name,value) { this.attributes[name]=String(value); }
  get textContent() { return this.text??this.children.map(node=>node.textContent).join(''); }
  set textContent(value) { this.text=String(value);this.children=[]; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.text=undefined;this.children=[...nodes]; }
  addEventListener(name,listener) { this.listeners[name]=listener; }
  querySelectorAll(selector) { return this.children.flatMap(node=>[...(node.getAttribute(selector.slice(1,-1))!==null?[node]:[]),...node.querySelectorAll(selector)]); }
  querySelector() { return this.button??=new Node('button'); }
  closest() { return {close(){}}; }
  showModal() { this.open=true; }
}

function workspace({languages=['en-US'],stored=null,storageThrows=false,app=false}={}) {
  const writes=[],requests=[],nodes=new Map();
  const document=new Node('document');
  document.documentElement={lang:'en-US'};
  document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
  document.querySelector=()=>({content:'test-token'});
  document.createElement=tag=>new Node(tag);
  const storage={getItem(key){assert.equal(key,'cellwright.language');if(storageThrows)throw new Error('Storage denied');return stored;},setItem(key,value){if(storageThrows)throw new Error('Storage denied');writes.push([key,value]);}};
  const context=vm.createContext({document,navigator:{languages,language:languages[0]},localStorage:storage,Intl,console,setInterval(){},setTimeout(){},URL,Blob,FormData:class {constructor(form){this.values=Object.entries(form.data);}*[Symbol.iterator](){yield* this.values;}},fetch:async(path,options)=>{requests.push({path,options});return {ok:true,json:async()=>({jobs:[],assignments:[],schedules:[]})};}});
  vm.runInContext(source,context);
  vm.runInContext('i18n.apply()',context);
  if(app)vm.runInContext(readFileSync(new URL('../dashboard/app.js',import.meta.url),'utf8'),context);
  return {context,document,writes,requests,node:document.getElementById,run:code=>vm.runInContext(code,context)};
}

test('browser regional language, saved preference and unsupported languages negotiate safely',()=>{
  for(const [languages,stored,language,locale]of [
    [['de-CH'],null,'de','de-CH'],
    [['en-GB'],null,'en','en-GB'],
    [['fr-CA'],null,'fr','fr-CA'],
    [['es-ES','de-CH'],null,'de','de-CH'],
    [['es-ES'],null,'en','en-US'],
    [['fr-CA'],'de','de','de-DE'],
    [['fr-CA'],'fr','fr','fr-CA'],
    [['en-GB'],'en','en','en-GB'],
    [['de-CH'],'unsupported','de','de-CH'],
  ]) {
    const session=workspace({languages,stored});
    assert.equal(session.run('i18n.language'),language);
    assert.equal(session.run('i18n.locale'),locale);
    assert.equal(session.document.documentElement.lang,language);
    session.run('i18n.setLanguage(i18n.language)');
    assert.equal(session.run('i18n.locale'),locale);
  }
});

test('language selection persists, rejects unsupported values and survives denied storage',()=>{
  const session=workspace({languages:['de-CH']});
  session.run("i18n.setLanguage('fr')");
  assert.equal(session.run('i18n.language'),'fr');
  assert.equal(session.run('i18n.locale'),'fr-FR');
  assert.equal(session.document.documentElement.lang,'fr');
  assert.deepEqual(session.writes,[['cellwright.language','fr']]);
  try{session.run("i18n.setLanguage('es')");}catch{}
  assert.equal(session.run('i18n.language'),'fr');
  assert.equal(session.writes.length,1);
  const denied=workspace({languages:['fr-CA'],storageThrows:true});
  assert.equal(denied.run('i18n.language'),'fr');
  assert.doesNotThrow(()=>denied.run("i18n.setLanguage('de')"));
  assert.equal(denied.run('i18n.language'),'de');
});

test('translation uses English fallback and interpolates text without dropping zero values',()=>{
  const session=workspace({languages:['fr-FR']});
  assert.equal(session.run("i18n.t('Cancel')"),'Annuler');
  for(const key of ['constructor','__proto__','toString'])assert.equal(session.run('i18n.t('+JSON.stringify(key)+')'),key);
  assert.equal(session.run("i18n.t('Untranslated {count}: {value}',{count:0,value:'<script>alert(1)</script>'})"),'Untranslated 0: <script>alert(1)</script>');
  session.run("i18n.setLanguage('de')");
  assert.equal(session.run("i18n.t('Cancel')"),'Abbrechen');
  session.run("i18n.setLanguage('en')");
  assert.equal(session.run("i18n.t('Cancel')"),'Cancel');
});

test('plural forms follow the chosen locale including French zero and regional number formatting',()=>{
  const session=workspace();
  session.run("translations.en['fixture.one']='{count} item';translations.en['fixture.other']='{count} items';translations.fr['fixture.one']='{count} élément';translations.fr['fixture.other']='{count} éléments';translations.de['fixture.one']='{count} Element';translations.de['fixture.other']='{count} Elemente';");
  assert.equal(session.run("i18n.plural('fixture',1)"),'1 item');
  assert.equal(session.run("i18n.plural('fixture',2)"),'2 items');
  session.run("i18n.setLanguage('fr')");
  assert.equal(session.run("i18n.plural('fixture',0)"),'0 élément');
  assert.equal(session.run("i18n.plural('fixture',1000)"),new Intl.NumberFormat('fr-FR').format(1000)+' éléments');
  assert.equal(session.run("i18n.plural('fixture',1000000)"),new Intl.NumberFormat('fr-FR').format(1000000)+' éléments');
  session.run("i18n.setLanguage('de')");
  assert.equal(session.run("i18n.plural('fixture',0)"),'0 Elemente');
  assert.equal(session.run("i18n.plural('fixture',1000)"),'1.000 Elemente');
});

test('static translations preserve controls and apply accessible labels as text',()=>{
  const session=workspace({languages:['fr-FR']});
  const label=new Node('label'),caption=new Node('span',{'data-i18n':'Cancel'}),input=new Node('input',{'data-i18n-placeholder':'Cancel','data-i18n-title':'Cancel','data-i18n-aria-label':'Cancel'});
  input.value='User-entered path';label.append(caption,input);session.document.append(label);
  session.run('i18n.apply()');
  assert.equal(caption.textContent,'Annuler');
  for(const name of ['placeholder','title','aria-label'])assert.equal(input.getAttribute(name),'Annuler');
  assert.deepEqual(label.children,[caption,input]);
  assert.equal(input.value,'User-entered path');
  assert.doesNotMatch(source,/\.innerHTML\s*=/);
  for(const [labelHtml]of html.matchAll(/<label\b[\s\S]*?<\/label>/g)) {
    if(/<(?:input|select|textarea)\b/.test(labelHtml))assert.doesNotMatch(labelHtml,/^<label\b[^>]*\sdata-i18n=/);
  }
});

test('French and German catalogs cover marked HTML and app text and preserve every placeholder',()=>{
  const session=workspace();
  const catalogs=JSON.parse(session.run('JSON.stringify(translations)'));
  assert.match(html,/\bdata-i18n=/);
  assert.deepEqual(Object.keys(catalogs.fr).sort(),Object.keys(catalogs.de).sort());
  const placeholders=value=>[...value.matchAll(/\{(\w+)\}/g)].map(match=>match[1]).sort();
  for(const language of ['fr','de']) {
    for(const [key,value]of Object.entries(catalogs[language]))assert.deepEqual(placeholders(value),placeholders(catalogs.en?.[key]??key),`${language}: ${key}`);
    for(const [,key]of html.matchAll(/\bdata-i18n(?:-placeholder|-title|-aria-label)?="([^"]+)"/g)) {
      const decoded=key.replaceAll('&amp;','&').replaceAll('&quot;','"').replaceAll('&#39;',"'");
      assert.ok(Object.hasOwn(catalogs[language],decoded),`${language} is missing ${decoded}`);
    }
    const app=readFileSync(new URL('../dashboard/app.js',import.meta.url),'utf8');
    for(const [,,key]of app.matchAll(/\bt\((['"])([^'"\r\n]*)\1/g))assert.ok(Object.hasOwn(catalogs[language],key),`${language} is missing app text ${key}`);
  }
  assert.ok(html.indexOf('src="/locales.js"')<html.indexOf('src="/app.js"'),'load translations before app');
  assert.doesNotMatch(html+source,/consulting|scottcampbellconsulting/i,'no consulting link in the dashboard');
});

test('existing finding arrays display the chosen report message with English fallback',()=>{
  const session=workspace({app:true,languages:['de-CH']});
  session.context.findingValue={rule_id:'test',line:1,messages:['English finding','Constat français','Deutscher Befund'],verdict:'needs_edits'};
  assert.equal(session.run('finding(findingValue)').children[1].textContent,'Deutscher Befund');
  session.run("i18n.setLanguage('fr')");
  assert.equal(session.run('finding(findingValue)').children[1].textContent,'Constat français');
  session.context.findingValue.messages=['English only'];
  assert.equal(session.run('finding(findingValue)').children[1].textContent,'English only');
});

test('feature labels translate and remain searchable by local words and technical codes',()=>{
  const session=workspace({app:true,languages:['fr-FR']});
  session.context.book={path:'Budget.xlsm',verdict:'needs_edits',features:['external_connections'],modules:[],findings:[],references:[],queries:[]};
  session.run("scan={workbooks:[book,{...book,path:'Other.xlsm',features:[]}]}");
  const search=session.node('search'),rows=session.node('workbook-rows');
  search.value='connexions';session.run('renderWorkbooks()');
  assert.equal(rows.children.length,1);
  assert.equal(rows.children[0].children[0].children[0].textContent,'Budget.xlsm');
  session.run("i18n.setLanguage('de');details(book)");
  assert.equal(session.node('detail-assessment').children[1].children[0].textContent,'Externe Verbindungen');
  for(const query of ['verbindungen','external_connections']) {
    search.value=query;session.run('renderWorkbooks()');
    assert.equal(rows.children.length,1,query);
    assert.equal(rows.children[0].children[0].children[0].textContent,'Budget.xlsm');
  }
});

test('scheduled scans submit the selected report language and preserve path normalization',async()=>{
  const session=workspace({app:true,languages:['fr-CA']});
  session.node('new-schedule').onclick();
  const form=session.node('schedule-form');
  assert.equal(form.elements.lang.value,'fr');
  form.data={label:'Finance',paths:' C:\\Finance\n\n \\\\server\\reports ',interval_hours:'24',lang:'de'};
  await form.listeners.submit({preventDefault(){},currentTarget:form});
  const saved=session.requests.find(request=>request.path==='/api/schedules'&&request.options.method==='POST');
  assert.ok(saved,'schedule was submitted');
  assert.equal(saved.options.headers['X-Cellwright-Language'],'fr');
  assert.deepEqual(JSON.parse(saved.options.body),{label:'Finance',paths:['C:\\Finance','\\\\server\\reports'],interval_hours:24,lang:'de',enabled:true});
});

test('switching language refreshes findings while retaining unsaved assignments and scan consent',async()=>{
  const session=workspace({app:true});
  session.context.book={path:'Budget.xlsm',verdict:'needs_edits',features:[],findings:[{rule_id:'test',messages:['English finding','Constat français','Deutscher Befund'],verdict:'needs_edits'}],modules:[],references:[],queries:[]};
  session.run('details(book)');
  const assignment=session.node('assignment-form');
  const entered={owner:'Finance',state:'in_review',notes:'Keep these unsaved notes'};
  for(const [key,value]of Object.entries(entered))assignment.elements[key].value=value;
  const scan=session.node('scan-form');scan.elements.paths.value='C:\\Finance\\Budget.xlsm';scan.elements.source.checked=true;
  const verification=session.node('verify-form');verification.elements.golden.value='C:\\Captures\\budget.json';verification.elements.allow_execution.checked=true;
  const language=session.node('language');language.value='fr';
  await language.onchange({target:language});
  assert.equal(session.run('i18n.language'),'fr');
  assert.equal(session.document.documentElement.lang,'fr');
  for(const [key,value]of Object.entries(entered))assert.equal(assignment.elements[key].value,value);
  assert.equal(session.node('detail-findings').children[0].children[1].textContent,'Constat français');
  assert.equal(scan.elements.paths.value,'C:\\Finance\\Budget.xlsm');
  assert.equal(scan.elements.source.checked,true);
  assert.equal(verification.elements.golden.value,'C:\\Captures\\budget.json');
  assert.equal(verification.elements.allow_execution.checked,true);
});

test('demonstration scans use the interface language for the report and API response',async()=>{
  const session=workspace({app:true,languages:['de-CH']});
  session.run("state.setup={demo:'demo.xlsm'}");
  await session.node('scan-demo').onclick();
  const saved=session.requests.find(request=>request.path==='/api/scans'&&request.options.method==='POST');
  assert.equal(saved.options.headers['X-Cellwright-Language'],'de');
  assert.equal(JSON.parse(saved.options.body).lang,'de');
});

test('language changes retry a pending GET body and never replay a POST mutation',async()=>{
  const session=workspace({app:true});
  await new Promise(resolve=>setImmediate(resolve));
  for(const method of ['GET','POST']) {
    session.run("i18n.setLanguage('en')");
    const requests=[];let release,started;
    const bodyStarted=new Promise(resolve=>started=resolve);
    session.context.fetch=async(path,options)=>{
      requests.push({path,options});
      return {ok:true,json:()=>requests.length===1?new Promise(resolve=>{release=resolve;started();}):Promise.resolve({message:'Français'})};
    };
    session.context.requestValue=method==='POST'?{path:'Budget.xlsm'}:undefined;
    const pending=session.run("api(requestValue?'/api/assignments':'/api/setup',requestValue)");
    await bodyStarted;
    session.run("i18n.setLanguage('fr')");
    release({message:'English'});
    assert.equal((await pending).message,method==='GET'?'Français':'English');
    assert.deepEqual(requests.map(request=>request.options.method),method==='GET'?['GET','GET']:['POST']);
    assert.deepEqual(requests.map(request=>request.options.headers['X-Cellwright-Language']),method==='GET'?['en','fr']:['en']);
    if(method==='POST')assert.deepEqual(JSON.parse(requests[0].options.body),{path:'Budget.xlsm'});
  }
});
