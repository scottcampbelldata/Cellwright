// SPDX-License-Identifier: EUPL-1.2
const token = document.querySelector('meta[name="mf-session"]').content;
const labels = {no_known_blockers:'No known blockers',needs_edits:'Needs edits',needs_rewrite:'Needs rewrite',unknown:'Unknown',pending:'Pending',in_review:'In review',converted:'Converted',verified:'Verified by cases',blocked:'Blocked',completed:'Completed',partial:'Partial',failed:'Failed',queued:'Queued',running:'Running'};
const colors = {no_known_blockers:'#7286bb',needs_edits:'#dab16a',needs_rewrite:'#c77b70',unknown:'#b4b4b4'};
let state = {jobs:[],assignments:[],schedules:[]}, scan = null, scanId = null, selected = null, loading = false;
const $ = id => document.getElementById(id);
function element(tag, className, text) { const node=document.createElement(tag); if(className)node.className=className; if(text!==undefined)node.textContent=text; return node; }
function badge(value) { return element('span','badge '+value,labels[value]||value); }
function filename(path) { return path.split(/[\\/]/).pop(); }
function notify(message,error=false) { $('notice').className=error?'error-notice':'success-notice'; $('notice').textContent=message; }
async function api(path,value) {
 const response=await fetch(path,{method:value?'POST':'GET',headers:{'X-Cellwright-Token':token,...(value?{'Content-Type':'application/json'}:{})},body:value?JSON.stringify(value):undefined});
 const data=await response.json(); if(!response.ok)throw new Error(data.error||'Request failed'); return data;
}
function download(id,path,label) { const link=element('a',null,label); link.href='/files/'+encodeURIComponent(id)+'/'+path.split('/').map(encodeURIComponent).join('/'); return link; }
function view(name) {
 for(const section of document.querySelectorAll('.view'))section.hidden=section.id!==name;
 for(const button of document.querySelectorAll('.nav'))button.classList.toggle('active',button.dataset.view===name);
 const headings={overview:['Overview','Make your next move clear.','Understand the estate. Prioritise the work. Prove the migration.'],workbooks:['Workbook inventory','Know what needs to move.','Assign owners, inspect dependencies and track each workbook.'],conversions:['Conversions','Carry the code forward.','Review a candidate. Resolve the TODOs. Compare the outcomes.'],schedules:['Scheduled scans','Keep the estate in view.','Repeat your assessments as workbooks and dependencies change.']};
 const values=headings[name]; $('breadcrumb').textContent=values[0]; $('page-title').textContent=values[1]; $('page-description').textContent=values[2];
}
for(const button of document.querySelectorAll('.nav'))button.addEventListener('click',()=>view(button.dataset.view));
for(const button of document.querySelectorAll('[data-close]'))button.addEventListener('click',()=>button.closest('dialog').close());
$('new-scan').onclick=()=>$('scan-dialog').showModal();
$('new-conversion').onclick=()=>$('conversion-dialog').showModal();
$('new-schedule').onclick=()=>$('schedule-dialog').showModal();
$('convert-selected').onclick=()=>{ $('conversion-form').elements.path.value=selected.path; $('detail-dialog').close(); $('conversion-dialog').showModal(); };
function submitForm(id,endpoint,convertValues) {
 $(id).addEventListener('submit',async event=>{
  event.preventDefault(); const form=event.currentTarget,button=form.querySelector('button.primary'); button.disabled=true;
  try { const values=Object.fromEntries(new FormData(form)); await api(endpoint,convertValues(values,form)); form.closest('dialog')?.close(); notify('Saved. The workspace will update as the job progresses.'); await refresh(); }
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
  if(type==='boolean'){if(!/^(true|false)$/i.test(value.trim()))throw new Error('Use true or false for '+input.dataset.name);return value.trim().toLowerCase()==='true';}
  if(type==='null')return null;
  if(!value.trim()||!Number.isFinite(Number(value)))throw new Error('Provide a number for '+input.dataset.name);
  return Number(value);
 });
 const ranges={};for(const row of $('verify-ranges').children){const sheet=row.querySelector('.range-sheet').value.trim(),range=row.querySelector('.range-address').value.trim();if(!sheet||!range)throw new Error('Provide a sheet name and range for every comparison row.');(ranges[sheet]??=[]).push(range);}
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
 $('metric-workbooks').textContent=books.length.toLocaleString(); $('ring-count').textContent=books.length;
 $('metric-modules').textContent=scan.unique_modules.toLocaleString(); $('metric-rewrite').textContent=counts.needs_rewrite;
 $('metric-effort').textContent=Math.round(scan.estimated_hours_low)+'–'+Math.round(scan.estimated_hours_high)+' h';
 $('metric-files-note').textContent=books.filter(book=>book.status!=='inspected').length+' workbook(s) could not be fully inspected';
 $('metric-dedupe').textContent=scan.duplicates.length+' duplicate code cluster(s)';
 $('scan-meta').textContent=new Date(scan.generated_unix_seconds*1000).toLocaleDateString();
 const link=$('report-download');link.hidden=false;link.href='/files/'+scanId+'/report.html';link.textContent='Download offline report ↗';
 const legend=$('verdict-legend');legend.replaceChildren();let angle=0;const slices=[];
 for(const [key,count]of Object.entries(counts)){
  const row=element('div','legend-row');const dot=element('i');dot.style.background=colors[key];row.append(dot,element('span',null,labels[key]),element('strong',null,count));legend.append(row);
  const next=angle+(books.length?count/books.length*100:0);slices.push(colors[key]+' '+angle+'% '+next+'%');angle=next;
 }
 $('verdict-ring').style.background=books.length?'conic-gradient('+slices.join(',')+')':'#e4e7ef';
}
function assignment(path) { return state.assignments.find(value=>value.path===path)||{owner:'',state:'pending',notes:''}; }
function renderWorkbooks() {
 const body=$('workbook-rows');body.replaceChildren();if(!scan)return;
 const query=$('search').value.toLowerCase(),verdict=$('verdict-filter').value;
 const books=scan.workbooks.filter(book=>(!verdict||book.verdict===verdict)&&[book.path,...book.features,...book.modules.map(m=>m.name)].join(' ').toLowerCase().includes(query));
 $('inventory-empty').hidden=books.length>0;$('inventory-empty').textContent='No workbooks match this view.';$('workbook-count').textContent=books.length+' workbook(s)';
 for(const book of books){
  const owner=assignment(book.path),row=element('tr');const file=element('td');const link=element('button','row-link',filename(book.path));link.onclick=()=>details(book);file.append(link,element('small',null,book.path));
  const assessment=element('td');assessment.append(badge(book.verdict));const status=element('td');status.append(badge(owner.state));const action=element('td');const review=element('button','secondary','Review');review.onclick=()=>details(book);action.append(review);
  row.append(file,element('td',null,book.modules.length),assessment,element('td',null,owner.owner||'Unassigned'),status,action);body.append(row);
 }
}
$('search').oninput=renderWorkbooks;$('verdict-filter').onchange=renderWorkbooks;
function finding(value) { const node=element('div','finding');node.append(element('strong',null,value.rule_id+(value.line?' · line '+value.line:'')),element('span',null,value.messages[0]),element('p','help',value.verdict==='unknown'?'Not inspected: review this part separately; conversion does not clear unknown coverage.':'Next: review this location and use the matching manual migration recipe.'));return node; }
function details(book) {
 $('assignment-form').hidden=false;selected=book;const saved=assignment(book.path);$('detail-title').textContent=filename(book.path);$('detail-path').textContent=book.path;
 const assessment=$('detail-assessment');assessment.replaceChildren(badge(book.verdict));const chips=element('div','chips');for(const feature of book.features)chips.append(element('span',null,feature.replaceAll('_',' ')));assessment.append(chips);
 for(const key of ['owner','state','notes'])$('assignment-form').elements[key].value=saved[key];
 const content=$('detail-findings');content.replaceChildren();if(book.error)content.append(element('p','error-notice',book.error));for(const value of book.findings)content.append(finding(value));
 for(const module of book.modules){const item=element('details');item.append(element('summary',null,module.name+' · '+module.kind+' · '+module.code_lines+' code lines'));for(const value of module.findings)item.append(finding(value));if(module.source){const pre=element('pre');pre.append(element('code',null,module.source));item.append(pre);}else item.append(element('p','help','Source code is excluded from this assessment.'));content.append(item);}
 if(book.references.length)content.append(element('p','help','References: '+book.references.join(' · ')));
 if(book.entry_points?.length)content.append(element('p','help','Entry points: '+book.entry_points.join(' · ')));
 for(const query of book.queries){const item=element('details');item.append(element('summary',null,'Power Query · '+query.name));if(query.source)item.append(element('pre',null,query.source));content.append(item);}
 $('detail-dialog').showModal();
}
function renderJobs() {
 const activity=$('recent-jobs');activity.replaceChildren();
 if(!state.jobs.length)activity.append(element('p','empty','Your first scan starts the migration story.'));
 for(const job of state.jobs.slice(0,6)){const row=element('div','activity-row'),text=element('div');text.append(element('strong',null,job.label),element('p',null,(job.kind==='scan'?'Assessment':job.kind==='verify'?'Execution comparison':'Conversion')+' · '+new Date(job.created*1000).toLocaleString()));row.append(text,badge(job.state));activity.append(row);}
 const conversions=$('conversion-jobs');conversions.replaceChildren();const jobs=state.jobs.filter(job=>job.kind==='convert');
 if(!jobs.length)conversions.append(element('p','empty','Create a candidate from a workbook in your inventory.'));
 for(const job of jobs){
  const card=element('article','panel job-card'),head=element('div','head');head.append(element('h2',null,job.label),badge(job.state));card.append(head);
  const result=job.result?JSON.parse(job.result):null;
  const failure=job.error?.trim().split('\n').at(-1);
  card.append(element('p',null,failure||(result?result.target+' · '+result.modules+' modules · '+(result.queries||0)+' M sections · '+(result.buttons||0)+' buttons rebound · '+result.todos+' unresolved · Candidate generated · Not tested':'Preparing a candidate…')));
  if(result){const links=element('div','downloads');links.append(download(job.id,'conversion.json','Conversion report'),download(job.id,'inventory/report.html','Assessment'));if(result.queries!==undefined)links.append(download(job.id,'candidate.zip','Complete candidate ZIP'));if(result.target!=='python')links.append(download(job.id,'converted.ods','ODS candidate'));const inspect=element('button','secondary','Review source and diff');inspect.onclick=async()=>{
   try{const report=await api('/api/jobs/'+job.id);for(const module of report.modules){links.append(download(job.id,module.candidate,module.name+' source'),download(job.id,module.diff,module.name+' diff'));}for(const query of report.power_queries||[]){links.append(download(job.id,query.original,query.name+' original M'));if(query.candidate)links.append(download(job.id,query.candidate,query.name+' pandas script'));}if(report.buttons?.candidate)links.append(download(job.id,report.buttons.candidate,'Button wrappers'));for(const ui of report.user_interfaces||[]){if(ui.original)links.append(download(job.id,ui.original,ui.name+' original layout'));if(ui.candidate)links.append(download(job.id,ui.candidate,ui.name+' dialog layout'));}for(const button of report.buttons?.records||[]){const row=element('p',null,(button.sheet?button.sheet+' · ':'')+(button.control||button.before)+' · '+(button.status==='rewritten'?'Rebound to '+button.handler:button.reason));card.append(row);}inspect.remove();}catch(error){notify(error.message,true);}
  };links.append(inspect);if(result.target!=='python'){const verify=element('button','secondary',state.allow_execution?'Compare execution':'Macro execution disabled');verify.disabled=!state.allow_execution;verify.title=state.allow_execution?'Run a trusted test case':'Restart the dashboard with --allow-execution to enable verification';verify.onclick=()=>guidedVerification(job).catch(error=>notify(error.message,true));links.append(verify);}const checklist=element('button','secondary','Migration checklist');checklist.onclick=()=>showChecklist(job).catch(error=>notify(error.message,true));links.append(checklist);
   const handoff=element('button','secondary','Preview review summary');handoff.onclick=()=>previewHandoff(job).catch(error=>notify(error.message,true));links.append(handoff);card.append(links);
   for(const evidence of state.jobs.filter(value=>value.kind==='verify'&&JSON.parse(value.options).conversion_id===job.id)){const proof=evidence.result?JSON.parse(evidence.result):null;const row=element('div','activity-row');row.append(element('span',null,proof?(proof.passed?'Case passed':'Case differs')+' · '+proof.cells_checked+' cells · '+proof.differences+' differences':evidence.error||'Comparison '+evidence.state),badge(evidence.state));if(proof)row.append(download(evidence.id,'verification.json','Comparison evidence'));card.append(row);}
  }
  conversions.append(card);
 }
}
function renderSchedules() {
 const list=$('schedule-list');list.replaceChildren();if(!state.schedules.length)list.append(element('p','empty','No schedules yet. Add one for your recurring inventory.'));
 for(const schedule of state.schedules){const card=element('article','panel schedule-card'),text=element('div');text.append(element('h2',null,schedule.label),element('p',null,'Every '+schedule.interval_hours+' hours · '+(schedule.enabled?'Next scan '+new Date(schedule.next_run*1000).toLocaleString():'Paused')),element('p',null,JSON.parse(schedule.paths).join(' · ')));const actions=element('div','downloads');const toggle=element('button','secondary',schedule.enabled?'Pause':'Resume');toggle.onclick=async()=>{try{await api('/api/schedules',{...schedule,paths:JSON.parse(schedule.paths),enabled:!schedule.enabled});await refresh();}catch(error){notify(error.message,true);}};const remove=element('button','secondary','Remove');remove.onclick=async()=>{try{await api('/api/schedules/delete',{id:schedule.id});await refresh();}catch(error){notify(error.message,true);}};actions.append(toggle,remove);card.append(text,actions);list.append(card);}
}
async function refresh() {
 if(loading)return;loading=true;
 try{
  state=await api('/api/state');renderJobs();renderSchedules();renderSetup();
  const scans=state.jobs.filter(job=>job.kind==='scan'&&['completed','partial'].includes(job.state));const select=$('scan-select');select.replaceChildren();
  if(!scans.length){select.append(element('option',null,'No scans yet'));}else{for(const job of scans){const option=element('option',null,job.label);option.value=job.id;select.append(option);}if(!scanId){await loadScan(scans[0].id);}select.value=scanId;}
  renderWorkbooks();
 }catch(error){notify(error.message,true);}finally{loading=false;}
}
function renderSetup(){
 const container=$('setup-checks');container.replaceChildren();
 for(const check of state.setup?.checks||[]){const row=element('details');row.append(element('summary',null,(check.available?'Ready: ':'Setup needed: ')+check.label+' · '+check.needed_for));if(!check.available)row.append(element('p','help',check.action));container.append(row);}
 $('scan-demo').disabled=!state.setup?.demo||!state.setup?.first_scan_ready;
}
$('refresh-setup').onclick=async()=>{try{state.setup=await api('/api/setup');renderSetup();notify('Setup checks refreshed.');}catch(error){notify(error.message,true);}};
$('scan-demo').onclick=async()=>{try{await api('/api/scans',{label:'Demonstration · formatting and button',paths:[state.setup.demo],source:true});notify('Demonstration scan started. Review its workbook, then create a candidate.');await refresh();}catch(error){notify(error.message,true);}};
async function showChecklist(job){
 const report=await api('/api/jobs/'+job.id);
 $('detail-title').textContent='Migration checklist · '+job.label;$('detail-path').textContent='';$('assignment-form').hidden=true;
 const assessment=$('detail-assessment');assessment.replaceChildren(element('p',null,'Conversion: '+(report.checklist?.conversion_status||'candidate_generated').replaceAll('_',' ')));
 const evidence=state.jobs.filter(caseJob=>caseJob.kind==='verify'&&JSON.parse(caseJob.options).conversion_id===job.id&&caseJob.result).map(caseJob=>JSON.parse(caseJob.result));
 assessment.append(element('p',null,'Tests: '+(evidence.length?(evidence.every(caseJob=>caseJob.passed)?'Selected tests passed':'Selected tests differ'):'Not tested')+' · Passing cases cover only selected routines, inputs and cells.'));
 if(report.checklist?.coverage_status==='unknown')assessment.append(element('p','error-notice','Unknown coverage: some workbook parts were not inspected.'));
 const content=$('detail-findings');content.replaceChildren();
 for(const item of report.checklist?.items||[]){const row=element('div','finding');row.append(element('strong',null,item.status.replaceAll('_',' ')+' · '+item.location+(item.line?' · line '+item.line:'')),element('span',null,item.reason),element('p','help','Next: '+item.next_action));content.append(row);}
 const link=element('a',null,'Open manual migration recipes ↗');link.href='/recipes';link.target='_blank';link.rel='noreferrer';content.append(link);$('detail-dialog').showModal();
}
let routineReport=null;
function inputRows(){
 const name=$('verify-routine').value;
 const module=routineReport.modules.find(module=>name.startsWith(module.name+'.'));
 const procedure=module?.procedures.find(procedure=>name===module.name+'.'+procedure.name);
 $('routine-warning').textContent=module?.todos.length?'This module has unresolved work. Review its checklist before opting in.':'This case will compare only the chosen routine and cells.';
 const container=$('verify-inputs');container.replaceChildren();
 for(const [index,param]of (procedure?.parameters||'').split(',').filter(param=>param.trim()).entries()){
  const label=element('label',null,'Input '+(index+1)+' · '+param.trim());const type=element('select');for(const value of ['number','string','boolean','null']){const option=element('option',null,value);option.value=value;type.append(option);}
  type.value=/as string/i.test(param)?'string':/as boolean/i.test(param)?'boolean':'number';
  const input=element('input','input-value');input.required=true;input.dataset.name=param;input.dataset.type=type.value;input.value=type.value==='boolean'?'false':type.value==='number'?'0':'';
  type.onchange=()=>{input.dataset.type=type.value;input.required=type.value!=='null';if(type.value==='boolean')input.value='false';};label.append(type,input);container.append(label);
 }
}
function addRange(sheet='',range=''){
 const row=element('div','two-fields');const sheetLabel=element('label',null,'Sheet name'),addressLabel=element('label',null,'Cell or range');
 const sheetInput=element('input','range-sheet'),address=element('input','range-address');sheetInput.required=address.required=true;sheetInput.value=sheet;address.value=range;address.placeholder='A1:D5';sheetLabel.append(sheetInput);addressLabel.append(address);
 const remove=element('button','secondary','Remove range');remove.type='button';remove.onclick=()=>row.remove();row.append(sheetLabel,addressLabel,remove);$('verify-ranges').append(row);
}
$('verify-routine').onchange=inputRows;$('add-range').onclick=()=>addRange();
async function guidedVerification(job){
 routineReport=await api('/api/jobs/'+job.id);const select=$('verify-routine');select.replaceChildren();
 for(const module of routineReport.modules){if(module.kind!=='standard')continue;for(const procedure of module.procedures||[]){if(typeof procedure!=='object'||/^(auto_open|auto_close|workbook_|worksheet_)/i.test(procedure.name))continue;const option=element('option',null,module.name+'.'+procedure.name);option.value=module.name+'.'+procedure.name;select.append(option);}}
 if(!select.options.length)throw new Error('No ordinary standard-module routines were discovered; use the manual recipes to prepare a testable entry point.');
 $('verify-form').reset();$('verify-form').elements.conversion_id.value=job.id;$('verify-form').elements.golden.required=state.requires_golden;
 $('verify-ranges').replaceChildren();addRange('Data','A1');inputRows();$('verify-dialog').showModal();
}
let handoffJob=null,handoffValue=null,handoffRevision=0;
async function updateHandoff(){const revision=++handoffRevision;$('save-handoff').disabled=true;try{const value=await api('/api/handoff',{conversion_id:handoffJob.id,include_identifiers:$('handoff-identifiers').checked});if(revision===handoffRevision){handoffValue=value;$('handoff-preview').textContent=JSON.stringify(value,null,2);$('save-handoff').disabled=false;}}catch(error){if(revision===handoffRevision){handoffValue=null;$('handoff-preview').textContent='Preview unavailable. Please try again.';}throw error;}}
async function previewHandoff(job){handoffJob=job;$('handoff-identifiers').checked=false;await updateHandoff();const link=$('consulting-link'),url=state.setup?.consulting_url;link.hidden=true;if(url){try{const parsed=new URL(url);if(parsed.protocol==='https:'){link.href=parsed.href;link.hidden=false;}}catch{}}$('handoff-dialog').showModal();}
$('handoff-identifiers').onchange=()=>updateHandoff().catch(error=>notify(error.message,true));
$('save-handoff').onclick=()=>{if(!handoffValue)return;const link=element('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(handoffValue,null,2)+'\n'],{type:'application/json'}));link.download='cellwright-review-summary.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);};
refresh();setInterval(()=>{if(!document.hidden)refresh();},4000);
