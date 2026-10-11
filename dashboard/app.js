// SPDX-License-Identifier: EUPL-1.2
const token = document.querySelector('meta[name="mf-session"]').content;
const {t, plural} = i18n;
const labels = {no_known_blockers:'No known blockers',needs_edits:'Needs edits',needs_rewrite:'Needs rewrite',unknown:'Unknown',pending:'Pending',in_review:'In review',converted:'Converted',verified:'Verified by cases',blocked:'Blocked',completed:'Completed',partial:'Partial',failed:'Failed',queued:'Queued',running:'Running',candidate_generated:'Candidate generated',manual_work_required:'Manual work required',unknown_coverage:'Unknown coverage'};
const colors = {no_known_blockers:'#7286bb',needs_edits:'#dab16a',needs_rewrite:'#c77b70',unknown:'#b4b4b4'};
let state = {jobs:[],assignments:[],schedules:[]}, scan = null, scanId = null, selected = null, loading = false, currentView = 'overview';
const $ = id => document.getElementById(id);
function element(tag, className, text) { const node=document.createElement(tag); if(className)node.className=className; if(text!==undefined)node.textContent=text; return node; }
function badge(value) { return element('span','badge '+value,t(labels[value]||value)); }
function filename(path) { return path.split(/[\\/]/).pop(); }
function notify(message,error=false) { $('notice').className=error?'error-notice':'success-notice'; $('notice').textContent=message; }
async function api(path,value) {
 const language=i18n.language;
 const response=await fetch(path,{method:value?'POST':'GET',headers:{'X-Cellwright-Token':token,'X-Cellwright-Language':i18n.language,...(value?{'Content-Type':'application/json'}:{})},body:value?JSON.stringify(value):undefined});
 const data=await response.json();
 if(!value&&language!==i18n.language)return api(path);
 if(!response.ok)throw new Error(data.error||t('Request failed')); return data;
}
function download(id,path,label) { const link=element('a',null,label); link.href='/files/'+encodeURIComponent(id)+'/'+path.split('/').map(encodeURIComponent).join('/'); return link; }
function view(name) {
 currentView=name;
 for(const section of document.querySelectorAll('.view'))section.hidden=section.id!==name;
 for(const button of document.querySelectorAll('.nav'))button.classList.toggle('active',button.dataset.view===name);
 const headings={overview:['Overview','Make your next move clear.','Understand the estate. Prioritize the work. Prove the migration.'],workbooks:['Workbook inventory','Know what needs to move.','Assign owners, inspect dependencies and track each workbook.'],conversions:['Conversions','Carry the code forward.','Review a candidate. Resolve the TODOs. Compare the outcomes.'],schedules:['Scheduled scans','Keep the estate in view.','Repeat your assessments as workbooks and dependencies change.']};
 const values=headings[name]; $('breadcrumb').textContent=t(values[0]); $('page-title').textContent=t(values[1]); $('page-description').textContent=t(values[2]);
}
for(const button of document.querySelectorAll('.nav'))button.addEventListener('click',()=>view(button.dataset.view));
for(const button of document.querySelectorAll('[data-close]'))button.addEventListener('click',()=>button.closest('dialog').close());
$('new-scan').onclick=()=>{ $('scan-form').elements.lang.value=i18n.language; $('scan-dialog').showModal(); };
$('new-conversion').onclick=()=>$('conversion-dialog').showModal();
$('new-schedule').onclick=()=>{ $('schedule-form').elements.lang.value=i18n.language; $('schedule-dialog').showModal(); };
$('convert-selected').onclick=()=>{ $('conversion-form').elements.path.value=selected.path; $('detail-dialog').close(); $('conversion-dialog').showModal(); };
function submitForm(id,endpoint,convertValues) {
 $(id).addEventListener('submit',async event=>{
  event.preventDefault(); const form=event.currentTarget,button=form.querySelector('button.primary'); button.disabled=true;
  try { const values=Object.fromEntries(new FormData(form)); await api(endpoint,convertValues(values,form)); form.closest('dialog')?.close(); notify(t('Saved. The workspace will update as the job progresses.')); await refresh(); }
  catch(error){notify(error.message,true);} finally{button.disabled=false;}
 });
}
submitForm('scan-form','/api/scans',(values,form)=>({...values,paths:values.paths.split('\n').map(v=>v.trim()).filter(Boolean),source:form.elements.source.checked}));
submitForm('conversion-form','/api/conversions',values=>values);
submitForm('schedule-form','/api/schedules',values=>({...values,paths:values.paths.split('\n').map(v=>v.trim()).filter(Boolean),interval_hours:Number(values.interval_hours),enabled:true}));
submitForm('assignment-form','/api/assignments',values=>({...values,path:selected.path}));
submitForm('verify-form','/api/verifications',(values,form)=>{
 const inputs=[...$('verify-inputs').querySelectorAll('.input-value')].map(input=>{
  const type=input.dataset.type,value=input.value;
  if(type==='string')return value;
  if(type==='boolean'){if(!/^(true|false)$/i.test(value.trim()))throw new Error(t('Use true or false for {name}',{name:input.dataset.name}));return value.trim().toLowerCase()==='true';}
  if(type==='null')return null;
  if(!value.trim()||!Number.isFinite(Number(value)))throw new Error(t('Provide a number for {name}',{name:input.dataset.name}));
  return Number(value);
 });
 const ranges={};for(const row of $('verify-ranges').children){const sheet=row.querySelector('.range-sheet').value.trim(),range=row.querySelector('.range-address').value.trim();if(!sheet||!range)throw new Error(t('Provide a sheet name and range for every comparison row.'));(ranges[sheet]??=[]).push(range);}
 return {...values,golden:values.golden.trim(),inputs,ranges,allow_execution:form.elements.allow_execution.checked};
});
async function loadScan(id) {
 try { scan=await api('/api/jobs/'+id); scanId=id; renderScan(); renderWorkbooks(); }
 catch(error){notify(error.message,true);}
}
$('scan-select').onchange=event=>loadScan(event.target.value);
function renderScan() {
 if(!scan)return;
 const books=scan.workbooks,counts=Object.fromEntries(Object.keys(colors).map(key=>[key,books.filter(book=>book.verdict===key).length]));
 $('metric-workbooks').textContent=books.length.toLocaleString(i18n.locale); $('ring-count').textContent=books.length.toLocaleString(i18n.locale);
 $('metric-modules').textContent=scan.unique_modules.toLocaleString(i18n.locale); $('metric-rewrite').textContent=counts.needs_rewrite.toLocaleString(i18n.locale);
 $('metric-effort').textContent=Math.round(scan.estimated_hours_low).toLocaleString(i18n.locale)+'–'+Math.round(scan.estimated_hours_high).toLocaleString(i18n.locale)+' h';
 $('metric-files-note').textContent=plural('incomplete',books.filter(book=>book.status!=='inspected').length);
 $('metric-dedupe').textContent=plural('duplicates',scan.duplicates.length);
 $('scan-meta').textContent=new Date(scan.generated_unix_seconds*1000).toLocaleDateString(i18n.locale);
 const link=$('report-download');link.hidden=false;link.href='/files/'+scanId+'/report.html';link.textContent=t('Download offline report ↗');
 const legend=$('verdict-legend');legend.replaceChildren();let angle=0;const slices=[];
 for(const [key,count]of Object.entries(counts)){
  const row=element('div','legend-row');const dot=element('i');dot.style.background=colors[key];row.append(dot,element('span',null,t(labels[key])),element('strong',null,count.toLocaleString(i18n.locale)));legend.append(row);
  const next=angle+(books.length?count/books.length*100:0);slices.push(colors[key]+' '+angle+'% '+next+'%');angle=next;
 }
 $('verdict-ring').style.background=books.length?'conic-gradient('+slices.join(',')+')':'#e4e7ef';
}
function assignment(path) { return state.assignments.find(value=>value.path===path)||{owner:'',state:'pending',notes:''}; }
function renderWorkbooks() {
 const body=$('workbook-rows');body.replaceChildren();if(!scan)return;
 const query=$('search').value.toLowerCase(),verdict=$('verdict-filter').value;
 const books=scan.workbooks.filter(book=>(!verdict||book.verdict===verdict)&&[book.path,...book.features.flatMap(feature=>[feature,t(feature.replaceAll('_',' '))]),...book.modules.map(m=>m.name)].join(' ').toLowerCase().includes(query));
 $('inventory-empty').hidden=books.length>0;$('inventory-empty').textContent=t('No workbooks match this view.');$('workbook-count').textContent=plural('workbooks',books.length);
 for(const book of books){
  const owner=assignment(book.path),row=element('tr');const file=element('td');const link=element('button','row-link',filename(book.path));link.onclick=()=>details(book);file.append(link,element('small',null,book.path));
  const assessment=element('td');assessment.append(badge(book.verdict));const status=element('td');status.append(badge(owner.state));const action=element('td');const review=element('button','secondary',t('Review'));review.onclick=()=>details(book);action.append(review);
  row.append(file,element('td',null,book.modules.length.toLocaleString(i18n.locale)),assessment,element('td',null,owner.owner||t('Unassigned')),status,action);body.append(row);
 }
}
$('search').oninput=renderWorkbooks;$('verdict-filter').onchange=renderWorkbooks;
function finding(value) { const node=element('div','finding');node.append(element('strong',null,value.rule_id+(value.line?' · '+t('line {line}',{line:value.line}):'')),element('span',null,value.messages[['en','fr','de'].indexOf(i18n.language)]||value.messages[0]),element('p','help',t(value.verdict==='unknown'?'Not inspected: review this part separately; conversion does not clear unknown coverage.':'Next: review this location and use the matching manual migration recipe.')));return node; }
let checklistJob=null;
function details(book) {
 checklistJob=null;
 $('assignment-form').hidden=false;selected=book;const saved=assignment(book.path);$('detail-title').textContent=filename(book.path);$('detail-path').textContent=book.path;
 const assessment=$('detail-assessment');assessment.replaceChildren(badge(book.verdict));const chips=element('div','chips');for(const feature of book.features)chips.append(element('span',null,t(feature.replaceAll('_',' '))));assessment.append(chips);
 for(const key of ['owner','state','notes'])$('assignment-form').elements[key].value=saved[key];
 const content=$('detail-findings');content.replaceChildren();if(book.error)content.append(element('p','error-notice',book.error));for(const value of book.findings)content.append(finding(value));
 for(const module of book.modules){const item=element('details');item.append(element('summary',null,module.name+' · '+t(module.kind)+' · '+plural('codeLines',module.code_lines)));for(const value of module.findings)item.append(finding(value));if(module.source){const pre=element('pre');pre.append(element('code',null,module.source));item.append(pre);}else item.append(element('p','help',t('Source code is excluded from this assessment.')));content.append(item);}
 if(book.references.length)content.append(element('p','help',t('References: {references}',{references:book.references.join(' · ')})));
 if(book.entry_points?.length)content.append(element('p','help',t('Entry points: {entries}',{entries:book.entry_points.join(' · ')})));
 for(const query of book.queries){const item=element('details');item.append(element('summary',null,'Power Query · '+query.name));if(query.source)item.append(element('pre',null,query.source));content.append(item);}
 $('detail-dialog').showModal();
}
function renderJobs() {
 const activity=$('recent-jobs');activity.replaceChildren();
 if(!state.jobs.length)activity.append(element('p','empty',t('Your first scan starts the migration story.')));
 for(const job of state.jobs.slice(0,6)){const row=element('div','activity-row'),text=element('div');text.append(element('strong',null,job.label),element('p',null,t(job.kind==='scan'?'Assessment':job.kind==='verify'?'Execution comparison':'Conversion')+' · '+new Date(job.created*1000).toLocaleString(i18n.locale)));row.append(text,badge(job.state));activity.append(row);}
 const conversions=$('conversion-jobs');conversions.replaceChildren();const jobs=state.jobs.filter(job=>job.kind==='convert');
 if(!jobs.length)conversions.append(element('p','empty',t('Create a candidate from a workbook in your inventory.')));
 for(const job of jobs){
  const card=element('article','panel job-card'),head=element('div','head');head.append(element('h2',null,job.label),badge(job.state));card.append(head);
  const result=job.result?JSON.parse(job.result):null;
  const failure=job.error?.trim().split('\n').at(-1);
  card.append(element('p',null,failure||(result?t('{target} · {modules} modules · {queries} M sections · {buttons} buttons rebound · {todos} unresolved · Candidate generated · Not tested',{target:result.target,modules:result.modules.toLocaleString(i18n.locale),queries:(result.queries||0).toLocaleString(i18n.locale),buttons:(result.buttons||0).toLocaleString(i18n.locale),todos:result.todos.toLocaleString(i18n.locale)}):t('Preparing a candidate…'))));
  if(result){const links=element('div','downloads');links.append(download(job.id,'conversion.json',t('Conversion report')),download(job.id,'inventory/report.html',t('Assessment')));if(result.queries!==undefined)links.append(download(job.id,'candidate.zip',t('Complete candidate ZIP')));if(result.target!=='python')links.append(download(job.id,'converted.ods',t('ODS candidate')));const inspect=element('button','secondary',t('Review source and diff'));inspect.onclick=async()=>{
   try{const report=await api('/api/jobs/'+job.id);for(const module of report.modules){links.append(download(job.id,module.candidate,t('{name} source',{name:module.name})),download(job.id,module.diff,t('{name} diff',{name:module.name})));}for(const query of report.power_queries||[]){links.append(download(job.id,query.original,t('{name} original M',{name:query.name})));if(query.candidate)links.append(download(job.id,query.candidate,t('{name} pandas script',{name:query.name})));}if(report.buttons?.candidate)links.append(download(job.id,report.buttons.candidate,t('Button wrappers')));for(const ui of report.user_interfaces||[]){if(ui.original)links.append(download(job.id,ui.original,t('{name} original layout',{name:ui.name})));if(ui.candidate)links.append(download(job.id,ui.candidate,t('{name} dialog layout',{name:ui.name})));}for(const button of report.buttons?.records||[]){const row=element('p',null,(button.sheet?button.sheet+' · ':'')+(button.control||button.before)+' · '+(button.status==='rewritten'?t('Rebound to {handler}',{handler:button.handler}):button.reason));card.append(row);}inspect.remove();}catch(error){notify(error.message,true);}
  };links.append(inspect);if(result.target!=='python'){const verify=element('button','secondary',t(state.allow_execution?'Compare execution':'Macro execution disabled'));verify.disabled=!state.allow_execution;verify.title=t(state.allow_execution?'Run a trusted test case':'Restart the dashboard with --allow-execution to enable verification');verify.onclick=()=>guidedVerification(job).catch(error=>notify(error.message,true));links.append(verify);}const checklist=element('button','secondary',t('Migration checklist'));checklist.onclick=()=>showChecklist(job).catch(error=>notify(error.message,true));links.append(checklist);
   const handoff=element('button','secondary',t('Preview review summary'));handoff.onclick=()=>previewHandoff(job).catch(error=>notify(error.message,true));links.append(handoff);card.append(links);
   for(const evidence of state.jobs.filter(value=>value.kind==='verify'&&JSON.parse(value.options).conversion_id===job.id)){const proof=evidence.result?JSON.parse(evidence.result):null;const row=element('div','activity-row');row.append(element('span',null,proof?t('{result} · {cells} cells · {differences} differences',{result:t(proof.passed?'Case passed':'Case differs'),cells:proof.cells_checked.toLocaleString(i18n.locale),differences:proof.differences.toLocaleString(i18n.locale)}):evidence.error||t('Comparison {state}',{state:t(labels[evidence.state]||evidence.state)})),badge(evidence.state));if(proof)row.append(download(evidence.id,'verification.json',t('Comparison evidence')));card.append(row);}
  }
  conversions.append(card);
 }
}
function renderSchedules() {
 const list=$('schedule-list');list.replaceChildren();if(!state.schedules.length)list.append(element('p','empty',t('No schedules yet. Add one for your recurring inventory.')));
 for(const schedule of state.schedules){const card=element('article','panel schedule-card'),text=element('div');text.append(element('h2',null,schedule.label),element('p',null,t('Every {hours} hours · {next}',{hours:schedule.interval_hours.toLocaleString(i18n.locale),next:schedule.enabled?t('Next scan {date}',{date:new Date(schedule.next_run*1000).toLocaleString(i18n.locale)}):t('Paused')})+' · '+t('Report language')+': '+({en:'English',fr:'Français',de:'Deutsch'}[schedule.lang||'en'])),element('p',null,JSON.parse(schedule.paths).join(' · ')));const actions=element('div','downloads');const toggle=element('button','secondary',t(schedule.enabled?'Pause':'Resume'));toggle.onclick=async()=>{try{await api('/api/schedules',{...schedule,paths:JSON.parse(schedule.paths),enabled:!schedule.enabled});await refresh();}catch(error){notify(error.message,true);}};const remove=element('button','secondary',t('Remove'));remove.onclick=async()=>{try{await api('/api/schedules/delete',{id:schedule.id});await refresh();}catch(error){notify(error.message,true);}};actions.append(toggle,remove);card.append(text,actions);list.append(card);}
}
async function refresh() {
 if(loading)return;loading=true;
 try{
  state=await api('/api/state');renderJobs();renderSchedules();renderSetup();
  const scans=state.jobs.filter(job=>job.kind==='scan'&&['completed','partial'].includes(job.state));const select=$('scan-select');select.replaceChildren();
  if(!scans.length){select.append(element('option',null,t('No scans yet')));}else{for(const job of scans){const option=element('option',null,job.label);option.value=job.id;select.append(option);}if(!scanId){await loadScan(scans[0].id);}select.value=scanId;}
  renderWorkbooks();
 }catch(error){notify(error.message,true);}finally{loading=false;}
}
function renderSetup(){
 const container=$('setup-checks');container.replaceChildren();
 for(const check of state.setup?.checks||[]){const row=element('details');row.append(element('summary',null,t(check.available?'Ready: {label} · {needed}':'Setup needed: {label} · {needed}',{label:check.label,needed:check.needed_for})));if(!check.available)row.append(element('p','help',check.action));container.append(row);}
 $('scan-demo').disabled=!state.setup?.demo||!state.setup?.first_scan_ready;
}
$('refresh-setup').onclick=async()=>{try{state.setup=await api('/api/setup');renderSetup();notify(t('Setup checks refreshed.'));}catch(error){notify(error.message,true);}};
$('scan-demo').onclick=async()=>{try{await api('/api/scans',{label:t('Demonstration · formatting and button'),paths:[state.setup.demo],source:true,lang:i18n.language});notify(t('Demonstration scan started. Review its workbook, then create a candidate.'));await refresh();}catch(error){notify(error.message,true);}};
async function showChecklist(job){
 checklistJob=job;
 const report=await api('/api/jobs/'+job.id);
 $('detail-title').textContent=t('Migration checklist')+' · '+job.label;$('detail-path').textContent='';$('assignment-form').hidden=true;
 const assessment=$('detail-assessment');assessment.replaceChildren(element('p',null,t('Conversion: {status}',{status:t(report.checklist?.conversion_status==='candidate_generated'||!report.checklist?.conversion_status?'Candidate generated':labels[report.checklist.conversion_status]||report.checklist.conversion_status.replaceAll('_',' '))})));
 const evidence=state.jobs.filter(caseJob=>caseJob.kind==='verify'&&JSON.parse(caseJob.options).conversion_id===job.id&&caseJob.result).map(caseJob=>JSON.parse(caseJob.result));
 assessment.append(element('p',null,t('Tests: {status} · Passing cases cover only selected routines, inputs and cells.',{status:t(evidence.length?(evidence.every(caseJob=>caseJob.passed)?'Selected tests passed':'Selected tests differ'):'Not tested')})));
 if(report.checklist?.coverage_status==='unknown')assessment.append(element('p','error-notice',t('Unknown coverage: some workbook parts were not inspected.')));
 const content=$('detail-findings');content.replaceChildren();
 for(const item of report.checklist?.items||[]){const row=element('div','finding');row.append(element('strong',null,t(labels[item.status]||item.status.replaceAll('_',' '))+' · '+item.location+(item.line?' · '+t('line {line}',{line:item.line}):'')),element('span',null,item.reason),element('p','help',t('Next: {action}',{action:item.next_action})));content.append(row);}
 const link=element('a',null,t('Open manual migration recipes ↗'));link.href='/recipes';link.target='_blank';link.rel='noreferrer';content.append(link);$('detail-dialog').showModal();
}
let routineReport=null;
function inputRows(){
 const name=$('verify-routine').value;
 const module=routineReport.modules.find(module=>name.startsWith(module.name+'.'));
 const procedure=module?.procedures.find(procedure=>name===module.name+'.'+procedure.name);
 $('routine-warning').dataset.i18n=module?.todos.length?'This module has unresolved work. Review its checklist before opting in.':'This case will compare only the chosen routine and cells.';
 $('routine-warning').textContent=t($('routine-warning').dataset.i18n);
 const container=$('verify-inputs');container.replaceChildren();
 for(const [index,param]of (procedure?.parameters||'').split(',').filter(param=>param.trim()).entries()){
  const label=element('label'),caption=element('span','input-caption',t('Input {number} · {parameter}',{number:index+1,parameter:param.trim()}));caption.dataset.number=index+1;caption.dataset.parameter=param.trim();label.append(caption);
  const type=element('select');for(const value of ['number','string','boolean','null']){const option=element('option',null,t(value));option.value=value;option.dataset.i18n=value;type.append(option);}
  type.value=/as string/i.test(param)?'string':/as boolean/i.test(param)?'boolean':'number';
  const input=element('input','input-value');input.required=true;input.dataset.name=param;input.dataset.type=type.value;input.value=type.value==='boolean'?'false':type.value==='number'?'0':'';
  type.onchange=()=>{input.dataset.type=type.value;input.required=type.value!=='null';if(type.value==='boolean')input.value='false';};label.append(type,input);container.append(label);
 }
}
function addRange(sheet='',range=''){
 const row=element('div','two-fields');const sheetLabel=element('label'),addressLabel=element('label');
 const sheetCaption=element('span',null,t('Sheet name')),addressCaption=element('span',null,t('Cell or range'));sheetCaption.dataset.i18n='Sheet name';addressCaption.dataset.i18n='Cell or range';sheetLabel.append(sheetCaption);addressLabel.append(addressCaption);
 const sheetInput=element('input','range-sheet'),address=element('input','range-address');sheetInput.required=address.required=true;sheetInput.value=sheet;address.value=range;address.placeholder='A1:D5';sheetLabel.append(sheetInput);addressLabel.append(address);
 const remove=element('button','secondary',t('Remove range'));remove.dataset.i18n='Remove range';remove.type='button';remove.onclick=()=>row.remove();row.append(sheetLabel,addressLabel,remove);$('verify-ranges').append(row);
}
$('verify-routine').onchange=inputRows;$('add-range').onclick=()=>addRange();
async function guidedVerification(job){
 routineReport=await api('/api/jobs/'+job.id);const select=$('verify-routine');select.replaceChildren();
 for(const module of routineReport.modules){if(module.kind!=='standard')continue;for(const procedure of module.procedures||[]){if(typeof procedure!=='object'||/^(auto_open|auto_close|workbook_|worksheet_)/i.test(procedure.name))continue;const option=element('option',null,module.name+'.'+procedure.name);option.value=module.name+'.'+procedure.name;select.append(option);}}
 if(!select.options.length)throw new Error(t('No ordinary standard-module routines were discovered; use the manual recipes to prepare a testable entry point.'));
 $('verify-form').reset();$('verify-form').elements.conversion_id.value=job.id;$('verify-form').elements.golden.required=state.requires_golden;
 $('verify-ranges').replaceChildren();addRange('Data','A1');inputRows();$('verify-dialog').showModal();
}
let handoffJob=null,handoffValue=null,handoffRevision=0;
async function updateHandoff(){const revision=++handoffRevision;$('save-handoff').disabled=true;try{const value=await api('/api/handoff',{conversion_id:handoffJob.id,include_identifiers:$('handoff-identifiers').checked});if(revision===handoffRevision){handoffValue=value;$('handoff-preview').textContent=JSON.stringify(value,null,2);$('save-handoff').disabled=false;}}catch(error){if(revision===handoffRevision){handoffValue=null;$('handoff-preview').textContent=t('Preview unavailable. Please try again.');}throw error;}}
async function previewHandoff(job){handoffJob=job;$('handoff-identifiers').checked=false;await updateHandoff();$('handoff-dialog').showModal();}
$('handoff-identifiers').onchange=()=>updateHandoff().catch(error=>notify(error.message,true));
$('save-handoff').onclick=()=>{if(!handoffValue)return;const link=element('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(handoffValue,null,2)+'\n'],{type:'application/json'}));link.download='cellwright-review-summary.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);};
i18n.apply();$('language').value=i18n.language;
document.title='Cellwright · '+t('Migration workspace');
$('language').onchange=async event=>{
 if(!i18n.setLanguage(event.target.value))return;
 document.title='Cellwright · '+t('Migration workspace');
 view(currentView);renderScan();renderWorkbooks();renderJobs();renderSchedules();
 const form=$('assignment-form');
 if($('detail-dialog').open&&!form.hidden&&selected){
  const entered=Object.fromEntries(['owner','state','notes'].map(key=>[key,form.elements[key].value]));
  details(selected);for(const [key,value]of Object.entries(entered))form.elements[key].value=value;
 }
 for(const caption of document.querySelectorAll('.input-caption'))caption.textContent=t('Input {number} · {parameter}',caption.dataset);
 $('notice').textContent='';$('notice').className='';
 await refresh();
 try{
  if($('detail-dialog').open&&form.hidden&&checklistJob)await showChecklist(checklistJob);
  if($('handoff-dialog').open&&handoffJob)await updateHandoff();
 }catch(error){notify(error.message,true);}
};
refresh();setInterval(()=>{if(!document.hidden)refresh();},4000);
